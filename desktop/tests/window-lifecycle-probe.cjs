// Loaded only by the diagnostic runner through the test process's Main inspector.
// Exercises the production Main, preload, renderer and Python bridge.
const assert = require('node:assert/strict');
const { writeFileSync } = require('node:fs');
const { basename } = require('node:path');
const { app, BrowserWindow, dialog } = require('electron');

exports.run = async function run(options) {
  await app.whenReady();
  let window = BrowserWindow.getAllWindows()[0];
  if (!window) {
    window = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Production window not created')), 15000);
      app.once('browser-window-created', (_event, value) => { clearTimeout(timeout); resolve(value); });
    });
  }
  if (window.webContents.isLoadingMainFrame()) {
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Renderer load timed out')), 15000);
      window.webContents.once('did-finish-load', () => { clearTimeout(timeout); resolve(); });
    });
  }
  const id = window.id;
  const webContentsId = window.webContents.id;
  const events = [];
  const checks = [];
  const report = {
    mode: options.mode, nativeChooser: options.native, pid: process.pid,
    executable: process.execPath, packaged: app.isPackaged,
    rendererUrl: window.webContents.getURL(), userData: app.getPath('userData'),
    windowId: id, webContentsId, events, checks, status: 'running',
  };
  const save = () => writeFileSync(options.resultPath, JSON.stringify(report, null, 2));
  const record = (event, detail) => { events.push({ event, detail, time: Date.now() }); save(); };
  const bindings = [];
  // Record OS system commands separately from JavaScript method calls.
  // A titlebar/system-menu minimize produces SC_MINIMIZE (0xf020).
  window.hookWindowMessage(0x0112, (wParam) => record('WM_SYSCOMMAND', { command: wParam.readUInt32LE(0) & 0xfff0 }));
  const originalMethods = new Map();
  for (const name of ['hide', 'close', 'minimize', 'destroy']) {
    const original = window[name]; originalMethods.set(name, original);
    window[name] = function (...args) { record('javascript-' + name, { stack: new Error().stack }); return original.apply(this, args); };
  }
  for (const event of ['close', 'closed', 'hide', 'show', 'minimize', 'restore', 'focus', 'blur']) {
    const handler = () => record(event);
    window.on(event, handler); bindings.push([window, event, handler]);
  }
  for (const event of ['destroyed', 'did-start-loading', 'did-finish-load', 'render-process-gone']) {
    const handler = (_event, detail) => record(event, detail);
    window.webContents.on(event, handler); bindings.push([window.webContents, event, handler]);
  }
  const originalDialog = dialog.showOpenDialog;
  let selection;
  let lastDialogAnswer;
  let nativeNext = options.native;
  dialog.showOpenDialog = async (...args) => {
    assert.equal(args[0], window, 'Chooser parent must be the requesting window');
    assert.deepEqual(args[1].properties, ['openFile']);
    assert.deepEqual(args[1].filters[0].extensions, ['csv', 'xlsx']);
    record('dialog-open', { parentId: args[0].id, native: nativeNext });
    let answer;
    if (nativeNext) {
      nativeNext = false;
      console.log('NATIVE_CHOOSER: select ' + options.csv);
      // Test fixture convenience only; the production parent, filters and
      // properties were asserted above and the real Windows chooser still runs.
      answer = await originalDialog.call(dialog, args[0], { ...args[1], defaultPath: options.csv });
    } else {
      assert.ok(selection, 'No queued diagnostic chooser response');
      answer = selection;
    }
    record('dialog-result', { canceled: answer.canceled, files: answer.filePaths.length });
    lastDialogAnswer = answer;
    return answer;
  };
  const evaluate = (code) => window.webContents.executeJavaScript(code);
  function alive(label, start, allowReload = false) {
    assert.equal(window.isDestroyed(), false, label + ': window destroyed');
    assert.equal(window.webContents.isDestroyed(), false, label + ': renderer destroyed');
    assert.equal(window.id, id); assert.equal(window.webContents.id, webContentsId);
    assert.equal(BrowserWindow.fromWebContents(window.webContents), window);
    assert.equal(window.isVisible(), true, label + ': window hidden');
    assert.equal(window.isMinimized(), false, label + ': window minimized');
    const forbidden = ['close', 'closed', 'hide', 'minimize', 'destroyed', 'render-process-gone'];
    if (!allowReload) forbidden.push('did-start-loading');
    assert.deepEqual(events.slice(start).filter((entry) => forbidden.includes(entry.event)), [], label);
    checks.push(label); save();
  }
  async function choose(label, answer, expectError = false) {
    selection = answer;
    const nativeSelection = nativeNext;
    const start = events.length;
    const view = await evaluate(`new Promise((resolve, reject) => {
      const button = document.querySelector('#file-select');
      const timeout = setTimeout(() => { observer.disconnect(); reject(new Error('File selection did not settle')); }, ${options.native ? 120000 : 15000});
      const observer = new MutationObserver(() => {
        if (!button.disabled) {
          observer.disconnect(); clearTimeout(timeout);
          resolve({ dataset: document.querySelector('#dataset-summary').textContent,
            error: document.querySelector('#error-card').hidden ? '' : document.querySelector('#error-code').textContent,
            buttonEnabled: !button.disabled });
        }
      });
      observer.observe(document.body, { subtree: true, childList: true, attributes: true });
      button.click();
    })`);
    assert.equal(view.buttonEnabled, true);
    if (expectError) assert.ok(view.error, 'Registration failure must display an error');
    else assert.equal(view.error, '');
    if (nativeSelection) {
      assert.equal(lastDialogAnswer.canceled, false, 'Native acceptance requires a CSV selection');
      assert.equal(lastDialogAnswer.filePaths.length, 1);
      assert.match(lastDialogAnswer.filePaths[0], /\.csv$/i);
      assert.ok(view.dataset.startsWith(basename(lastDialogAnswer.filePaths[0]) + ' · '), 'Dataset summary must match the actual native selection');
    } else if (!answer.canceled && !expectError) assert.match(view.dataset, /sales\.csv/);
    const sessions = await evaluate('window.agent.listSessions()');
    assert.equal(sessions.ok, true, 'IPC must survive selection');
    alive(label, start);
  }
  async function analyze(label) {
    const start = events.length;
    const result = await evaluate(`new Promise((resolve, reject) => {
      const received = [];
      const timeout = setTimeout(() => { unsubscribe(); observer.disconnect(); reject(new Error('Analysis did not finish')); }, 15000);
      const finish = () => {
        if (received.some(e => e.type === 'run_completed') && document.querySelector('#run-status').textContent.includes('已完成')) {
          clearTimeout(timeout); unsubscribe(); observer.disconnect();
          resolve({ types: received.map(e => e.type), answer: document.querySelector('#messages').textContent });
        }
      };
      const unsubscribe = window.agent.onAgentEvent(e => { received.push(e); finish(); });
      const observer = new MutationObserver(finish);
      observer.observe(document.body, { subtree: true, childList: true, attributes: true });
      document.querySelector('#run-input').value = '销售额总和是多少';
      document.querySelector('#run-submit').click();
    })`);
    assert.ok(result.types.includes('tool_called'));
    assert.match(result.answer, /1580/);
    alive(label, start);
  }
  save();
  try {
    // Initial activation is test setup. No restore/show/focus is used after a chooser.
    if (window.isMinimized()) window.restore();
    window.show(); window.focus();
    await choose('CSV success and parent binding', { canceled: false, filePaths: [options.csv] });
    if (options.native) await choose('Fixed sales fixture before numeric analysis', { canceled: false, filePaths: [options.csv] });
    await analyze('Real analysis and event listener after CSV');
    await choose('Chooser cancel', { canceled: true, filePaths: [] });
    await choose('CSV registration failure', { canceled: false, filePaths: [options.invalidCsv] }, true);
    await choose('Retry after registration failure', { canceled: false, filePaths: [options.csv] });
    const beforeReload = events.length;
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Renderer reload failed')), 15000);
      window.webContents.once('did-finish-load', () => { clearTimeout(timeout); resolve(); });
      window.webContents.reload();
    });
    alive('Explicit renderer reload preserves window', beforeReload, true);
    await choose('CSV after renderer reload', { canceled: false, filePaths: [options.csv] });
    await analyze('IPC and event listener after reload');
    report.status = 'passed';
    report.note = options.native ? 'First CSV chooser native; remaining chooser answers supplied by test; all registrations and analyses real.' : 'Chooser answers supplied by test; all registrations and analyses real. Not native chooser acceptance.';
    save();
    return report;
  } catch (error) {
    report.status = 'failed'; report.error = String(error.stack || error); save(); throw error;
  } finally {
    dialog.showOpenDialog = originalDialog;
    window.unhookWindowMessage(0x0112);
    for (const [name, original] of originalMethods) window[name] = original;
    for (const [emitter, event, handler] of bindings) emitter.removeListener(event, handler);
  }
};
