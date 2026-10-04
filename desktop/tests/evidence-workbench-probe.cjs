// Test-only Main inspector probe. File registration, tools and events are real.
const assert = require('node:assert/strict');
const { writeFileSync } = require('node:fs');
const { join } = require('node:path');
const { app, BrowserWindow, dialog } = require('electron');

exports.run = async function run(options) {
  await app.whenReady();
  let window = BrowserWindow.getAllWindows()[0];
  if (!window) window = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Production window not created')), 15000);
    app.once('browser-window-created', (_event, value) => { clearTimeout(timeout); resolve(value); });
  });
  if (window.webContents.isLoadingMainFrame()) await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Renderer load timed out')), 15000);
    window.webContents.once('did-finish-load', () => { clearTimeout(timeout); resolve(); });
  });
  const evaluate = code => window.webContents.executeJavaScript(code);
  // Wait on actual DOM changes. Timeouts fail the test; they never delay actions.
  const until = condition => evaluate(`new Promise((resolve, reject) => {
    const check = () => { if (${condition}) { observer.disconnect(); clearTimeout(timeout); resolve(true); } };
    const observer = new MutationObserver(check);
    const timeout = setTimeout(() => { observer.disconnect(); reject(new Error('UI state did not settle')); }, 15000);
    observer.observe(document.body, { subtree: true, childList: true, attributes: true, characterData: true });
    check();
  })`);
  const paint = () => evaluate(`(async () => {
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    await Promise.all(document.querySelector('#left-sidebar').getAnimations().map(animation => animation.finished));
    await new Promise(resolve => requestAnimationFrame(resolve));
  })()`);
  const report = { mode: options.mode, executable: process.execPath, packaged: app.isPackaged,
    rendererUrl: window.webContents.getURL(), checks: [], status: 'running', screenshots: [] };
  const save = () => writeFileSync(join(options.directory, 'result.json'), JSON.stringify(report, null, 2));
  const pass = label => { report.checks.push(label); save(); };
  const screenshot = async name => {
    await paint();
    const path = join(options.directory, name + '.png');
    writeFileSync(path, (await window.webContents.capturePage()).toPNG());
    report.screenshots.push(path); save();
  };
  const layout = () => evaluate(`(() => {
    const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }; };
    return { width: innerWidth, overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      sidebar: rect('#left-sidebar'), center: rect('#center-panel'), trace: rect('#trace-panel'),
      composer: rect('#composer'), header: rect('#context-header'), traceOpen: document.querySelector('#trace-panel').open };
  })()`);
  const originalDialog = dialog.showOpenDialog;
  try {
    window.setContentSize(1440, 900);
    window.show();
    await until("document.querySelector('#run-status').dataset.state === 'empty'");
    const empty = await evaluate(`({ welcome: !document.querySelector('#welcome').hidden,
      fieldsHidden: document.querySelector('#dataset-fields-panel').hidden,
      metrics: document.querySelector('#metric-cards').childElementCount,
      evidenceHidden: document.querySelector('#evidence-source').hidden,
      resultHidden: document.querySelector('#result-surface').hidden })`);
    assert.deepEqual(empty, { welcome: true, fieldsHidden: true, metrics: 0, evidenceHidden: true, resultHidden: true });
    assert.equal((await layout()).overflow, false);
    pass('Empty state contains no invented data or results');
    await screenshot('empty');

    dialog.showOpenDialog = async (parent, settings) => {
      assert.equal(parent, window);
      assert.deepEqual(settings.properties, ['openFile']);
      assert.deepEqual(settings.filters[0].extensions, ['csv', 'xlsx']);
      return { canceled: false, filePaths: [options.csv] };
    };
    await evaluate("document.querySelector('#file-select').click()");
    await until("!document.querySelector('#file-select').disabled && document.querySelector('#dataset-filename').textContent === 'sales.csv'");
    const data = await evaluate(`({ fields: [...document.querySelectorAll('#dataset-fields .dataset-field-name')].map(e => e.textContent),
      types: [...document.querySelectorAll('#dataset-fields .dataset-field-type')].map(e => e.textContent),
      metrics: [...document.querySelectorAll('#metric-cards strong')].map(e => e.textContent),
      file: document.querySelector('#evidence-filename').textContent,
      rows: document.querySelector('#evidence-rows').textContent, columns: document.querySelector('#evidence-columns').textContent })`);
    assert.deepEqual(data, { fields: ['日期', '地区', '产品', '销售额'], types: ['日期', '文本', '文本', '数值'],
      metrics: ['5', '4'], file: 'sales.csv', rows: '5 行', columns: '4 个字段' });
    pass('CSV parent binding and real DatasetSummary field/evidence projection');

    const analyze = async question => {
      await evaluate(`document.querySelector('#run-input').value = ${JSON.stringify(question)}; document.querySelector('#run-submit').click()`);
      await until("document.querySelector('#run-status').dataset.state === 'completed'");
      assert.equal(window.isDestroyed(), false);
      assert.equal(window.webContents.isDestroyed(), false);
      assert.equal(window.isVisible(), true);
      assert.equal(window.isMinimized(), false);
    };
    await analyze('计算销售额总和');
    assert.match(await evaluate("document.querySelector('#analysis-summary-content').textContent"), /1580/);
    const wide = await layout();
    assert.equal(wide.traceOpen, true);
    assert.equal(wide.overflow, false);
    assert.ok(wide.sidebar.right <= wide.center.left && wide.center.right <= wide.trace.left);
    assert.ok(wide.composer.top >= wide.header.bottom);
    const events = await evaluate("[...document.querySelectorAll('#event-list > li')].map(e => Number(e.dataset.sequence))");
    assert.ok(events.length > 0);
    assert.equal(new Set(events).size, events.length);
    pass('Real result 1580, three non-overlapping panels and unique Runtime events');
    await screenshot('analysis');

    await analyze('按地区生成销售额柱状图');
    await until("Boolean(document.querySelector('#charts svg'))");
    const chart = await evaluate(`({ marks: [...document.querySelectorAll('#charts svg .data-mark')].map(e => e.getAttribute('aria-label')),
      rows: [...document.querySelectorAll('#charts .chart-data-details tr:has(td)')].map(row => [...row.querySelectorAll('td')].map(cell => cell.textContent)),
      visible: !document.querySelector('#result-surface').hidden })`);
    assert.equal(chart.visible, true);
    assert.ok(chart.marks.length >= 2);
    assert.deepEqual(chart.rows, [['华南', '1,200'], ['华东', '380']]);
    assert.equal((await layout()).overflow, false);
    pass('Real chart and source table retain regional totals 380 / 1200');
    await evaluate("document.querySelector('#analysis-scroll').scrollTop = 0");
    await screenshot('chart');

    await evaluate("document.querySelector('#settings-open').click()");
    await until("!document.querySelector('#settings-view').hidden");
    const settings = await evaluate(`({ traceHidden: getComputedStyle(document.querySelector('#trace-panel')).display === 'none',
      composerHidden: document.querySelector('#composer').hidden, provider: Boolean(document.querySelector('#settings-provider')) })`);
    assert.deepEqual(settings, { traceHidden: true, composerHidden: true, provider: true });
    assert.equal((await layout()).overflow, false);
    pass('Settings has no trace/composer overlap and retains existing controls');
    await screenshot('settings');
    await evaluate("document.querySelector('#workspace-open').click()");
    await until("document.querySelector('#settings-view').hidden");

    for (const width of [1000, 700, 520]) {
      window.setContentSize(width, 800);
      await paint();
      const view = await layout();
      assert.equal(view.width, width);
      assert.equal(view.overflow, false);
      assert.ok(view.composer.top >= view.header.bottom && view.composer.bottom <= 800);
      if (width === 1000) assert.ok(view.center.right <= view.trace.left);
      if (width <= 900) {
        assert.ok(view.sidebar.right <= 0, 'Collapsed navigation must be fully outside the viewport');
        assert.equal(view.traceOpen, false, 'Crossing into compact layout must fold the wide trace panel');
        assert.ok(view.composer.bottom <= view.trace.top, 'Compact trace must not cover the composer');
      }
      if (width === 520) await screenshot('compact');
    }
    pass('1000 / 700 / 520px responsive layout preserves composer and page bounds');
    const sessions = await evaluate('window.agent.listSessions()');
    assert.equal(sessions.ok, true);
    pass('Existing Session IPC remains available after all UI transitions');
    report.status = 'passed';
    report.note = 'Chooser answer supplied by test; registration, Python computation, ChartSpec and Runtime events real. Not native chooser acceptance.';
    save();
    return report;
  } catch (error) {
    report.status = 'failed'; report.error = String(error.stack || error); save(); throw error;
  } finally {
    dialog.showOpenDialog = originalDialog;
  }
};
