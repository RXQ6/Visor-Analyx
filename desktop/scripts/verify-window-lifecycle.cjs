const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { existsSync, mkdtempSync, mkdirSync, readFileSync, writeFileSync } = require('node:fs');
const { dirname, join, resolve } = require('node:path');

const desktop = resolve(__dirname, '..');
const root = resolve(desktop, '..');
const arg = (name) => { const index = process.argv.indexOf(name); return index < 0 ? undefined : process.argv[index + 1]; };
const mode = arg('--mode') || 'dev';
assert.ok(['dev', 'packaged', 'installed'].includes(mode));
const native = process.argv.includes('--native');
const executable = mode === 'dev' ? require('electron') : resolve(arg('--executable') || join(desktop, 'release', 'win-unpacked', 'Data Analysis Agent.exe'));
assert.ok(existsSync(executable));
const directory = mkdtempSync(join(desktop, 'release', `phase291-${mode}-${native ? 'native' : 'auto'}-`));
const profile = join(directory, 'profile'); mkdirSync(profile);
const resultPath = join(directory, 'result.json');
const env = Object.fromEntries(['SystemRoot', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA'].filter(n => process.env[n]).map(n => [n, process.env[n]]));
env.PATH = join(process.env.SystemRoot || 'C:\\Windows', 'System32');
if (mode === 'dev') {
  env.DATA_AGENT_PYTHON = process.env.DATA_AGENT_PYTHON || join(desktop, 'release', 'win-unpacked', 'resources', 'python-runtime', 'python.exe');
  env.DATA_AGENT_NODE = process.execPath;
  env.PATH = `${dirname(process.execPath)};${env.PATH}`;
}
// Visibility is part of this test. Do not launch its window with SW_HIDE.
const child = spawn(executable, ['--inspect=127.0.0.1:0', `--user-data-dir=${profile}`, ...(mode === 'dev' ? [desktop] : [])], { cwd: directory, env, windowsHide: false, stdio: ['ignore', 'pipe', 'pipe'] });
let stdout = '', stderr = '', socket, retainNativeFailure = false;
const exited = new Promise(resolve => child.once('exit', (code, signal) => resolve({ code, signal })));
child.stdout.on('data', chunk => { stdout += chunk; process.stdout.write(chunk); });
child.stderr.on('data', chunk => { stderr += chunk; });
async function run() {
  const url = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Main inspector did not start')), 15000);
    const consume = chunk => { const match = String(chunk).match(/ws:\/\/127\.0\.0\.1:\d+\/[^\s]+/); if (match) { clearTimeout(timeout); resolve(match[0]); } };
    child.stderr.on('data', consume);
    child.once('error', reject);
    child.once('exit', code => { clearTimeout(timeout); reject(new Error(`App exited before inspector: ${code}\n${stderr}`)); });
  });
  socket = new WebSocket(url);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let id = 0; const pending = new Map();
  let mainParsedResolve;
  const mainParsed = new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Production Main script not parsed')), 15000);
    mainParsedResolve = () => { clearTimeout(timeout); resolve(); };
  });
  socket.onmessage = ({ data }) => {
    const message = JSON.parse(data);
    if (message.id) { pending.get(message.id)?.(message); pending.delete(message.id); }
    if (message.method === 'Debugger.scriptParsed' && /[\\/]dist[\\/]src[\\/]main[\\/]index\.js$/.test(message.params.url)) mainParsedResolve();
  };
  const command = (method, params) => new Promise(resolve => { const next = ++id; pending.set(next, resolve); socket.send(JSON.stringify({ id: next, method, params })); });
  await command('Debugger.enable', {});
  await mainParsed;
  const options = { mode, native, resultPath, csv: join(root, 'tests', 'fixtures', 'sales.csv'), invalidCsv: join(root, 'tests', 'fixtures', 'empty.csv') };
  const testRequire = `process.getBuiltinModule('module').createRequire(${JSON.stringify(__filename)})`;
  const expression = `${testRequire}(${JSON.stringify(join(desktop, 'tests', 'window-lifecycle-probe.cjs'))}).run(${JSON.stringify(options)})`;
  const result = await Promise.race([
    command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }),
    exited.then(value => { throw new Error('App exited during probe: ' + JSON.stringify(value)); }),
  ]);
  if (result.result?.exceptionDetails || result.error) throw new Error(JSON.stringify(result));
  const report = JSON.parse(readFileSync(resultPath, 'utf8'));
  assert.equal(report.status, 'passed');
  assert.equal(report.packaged, mode !== 'dev');
  assert.equal(resolve(report.executable).toLowerCase(), resolve(executable).toLowerCase());
  if (mode !== 'dev') assert.match(report.rendererUrl, /app\.asar/);
  console.log(JSON.stringify({ status: report.status, mode, native, checks: report.checks, resultPath }, null, 2));
  await command('Runtime.evaluate', { expression: `${testRequire}('electron').app.quit()` });
  socket.close();
}
run().catch(error => {
  console.error(error); process.exitCode = 1; socket?.close();
  if (native) {
    retainNativeFailure = true;
    console.error('Native probe failed; application retained for inspection. PID=' + child.pid);
    child.stdout.destroy(); child.stderr.destroy(); child.unref();
  } else child.kill();
}).finally(async () => {
  if (!retainNativeFailure) await exited;
  writeFileSync(join(directory, 'stdout.log'), stdout); writeFileSync(join(directory, 'stderr.log'), stderr);
});
