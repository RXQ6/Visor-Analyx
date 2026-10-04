const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } = require('node:fs');
const { dirname, join, resolve } = require('node:path');

const desktop = resolve(__dirname, '..');
const arg = name => { const index = process.argv.indexOf(name); return index < 0 ? undefined : process.argv[index + 1]; };
const mode = arg('--mode') || 'dev';
assert.ok(['dev', 'packaged', 'installed'].includes(mode));
const executable = mode === 'dev' ? require('electron') : resolve(arg('--executable') || '');
assert.ok(existsSync(executable));
const directory = mkdtempSync(join(desktop, 'release', `evidence-ui-${mode}-`));
const profile = join(directory, 'profile');
mkdirSync(profile);
const env = Object.fromEntries(['SystemRoot', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA']
  .filter(name => process.env[name]).map(name => [name, process.env[name]]));
env.PATH = join(process.env.SystemRoot || 'C:\\Windows', 'System32');
if (mode === 'dev') {
  env.DATA_AGENT_PYTHON = process.env.DATA_AGENT_PYTHON || join(desktop, 'release/win-unpacked/resources/python-runtime/python.exe');
  env.DATA_AGENT_NODE = process.execPath;
  env.PATH = `${dirname(process.execPath)};${env.PATH}`;
}
const child = spawn(executable, ['--inspect=127.0.0.1:0', `--user-data-dir=${profile}`, ...(mode === 'dev' ? [desktop] : [])],
  { cwd: directory, env, windowsHide: false, stdio: ['ignore', 'pipe', 'pipe'] });
let stdout = '', stderr = '', socket;
const exited = new Promise(resolveExit => child.once('exit', (code, signal) => resolveExit({ code, signal })));
const inspector = new Promise((resolveUrl, reject) => {
  const timeout = setTimeout(() => reject(new Error('Main inspector did not start')), 15000);
  child.stderr.on('data', chunk => {
    stderr += chunk;
    const match = String(chunk).match(/ws:\/\/127\.0\.0\.1:\d+\/[^\s]+/);
    if (match) { clearTimeout(timeout); resolveUrl(match[0]); }
  });
  child.once('error', error => { clearTimeout(timeout); reject(error); });
  child.once('exit', code => { clearTimeout(timeout); reject(new Error(`App exited before inspector: ${code}\n${stderr}`)); });
});
child.stdout.on('data', chunk => { stdout += chunk; });
async function run() {
  socket = new WebSocket(await inspector);
  await new Promise((resolveOpen, reject) => { socket.onopen = resolveOpen; socket.onerror = reject; });
  let id = 0;
  const pending = new Map();
  let parsed;
  const mainParsed = new Promise((resolveParsed, reject) => {
    const timeout = setTimeout(() => reject(new Error('Production Main script not parsed')), 15000);
    parsed = () => { clearTimeout(timeout); resolveParsed(); };
  });
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.id) { pending.get(message.id)?.(message); pending.delete(message.id); }
    if (message.method === 'Debugger.scriptParsed' && /[\\/]dist[\\/]src[\\/]main[\\/]index\.js$/.test(message.params.url)) parsed();
  };
  const command = (method, params) => new Promise(resolveCommand => {
    const next = ++id;
    pending.set(next, resolveCommand);
    socket.send(JSON.stringify({ id: next, method, params }));
  });
  await command('Debugger.enable', {});
  await mainParsed;
  const options = { mode, directory, csv: join(desktop, '../tests/fixtures/sales.csv') };
  const testRequire = `process.getBuiltinModule('module').createRequire(${JSON.stringify(__filename)})`;
  const expression = `${testRequire}(${JSON.stringify(join(desktop, 'tests/evidence-workbench-probe.cjs'))}).run(${JSON.stringify(options)})`;
  const response = await Promise.race([
    command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }),
    exited.then(value => { throw new Error('App exited during probe: ' + JSON.stringify(value)); }),
  ]);
  if (response.result?.exceptionDetails || response.error) throw new Error(JSON.stringify(response));
  const resultPath = join(directory, 'result.json');
  const report = JSON.parse(readFileSync(resultPath, 'utf8'));
  assert.equal(report.status, 'passed');
  assert.equal(report.packaged, mode !== 'dev');
  assert.equal(resolve(report.executable).toLowerCase(), resolve(executable).toLowerCase());
  if (mode !== 'dev') assert.match(report.rendererUrl, /app\.asar/);
  console.log(JSON.stringify({ status: report.status, mode, checks: report.checks, resultPath }, null, 2));
  await command('Runtime.evaluate', { expression: `${testRequire}('electron').app.quit()` });
  socket.close();
}
run().catch(error => {
  console.error(error);
  process.exitCode = 1;
  socket?.close();
  child.kill();
}).finally(async () => {
  await exited;
  writeFileSync(join(directory, 'stdout.log'), stdout);
  writeFileSync(join(directory, 'stderr.log'), stderr);
});
