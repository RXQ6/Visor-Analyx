// Test-only wire fault injection around the same pinned external MCP server.
// No new product server, tools or roots. Never logs requests or responses.
const { spawn } = require('node:child_process');
const { createInterface } = require('node:readline');
const [entry, root, mode, marker] = process.argv.slice(2);
const child = spawn(process.execPath, [entry, root], {
  shell: false, stdio: ['pipe', 'pipe', 'ignore'], env: process.env,
});
const fs = require('node:fs');
const pending = new Map();
const cancelled = new Set();
const timers = new Set();
let delayed = false;
const mark = (text) => { if (marker) fs.appendFileSync(marker, `${text}\n`); };
const send = (message) => process.stdout.write(`${JSON.stringify(message)}\n`);
createInterface({ input: process.stdin }).on('line', (line) => {
  const message = JSON.parse(line);
  if (message.id !== undefined && message.method) pending.set(message.id, message.method);
  if (message.method === 'notifications/cancelled') {
    cancelled.add(message.params.requestId);
    mark('cancel_notification');
  }
  child.stdin.write(`${line}\n`);
}).on('close', () => child.stdin.end());
createInterface({ input: child.stdout }).on('line', (line) => {
  const message = JSON.parse(line);
  const method = pending.get(message.id);
  pending.delete(message.id);
  if (mode === 'stall-startup') return;
  if (method === 'tools/list' && mode === 'bad-schema' && message.result) {
    const selected = message.result.tools.find((item) => item.name === 'get_file_info');
    selected.inputSchema.properties.path = { oneOf: [{ type: 'string' }] };
  }
  if (method === 'tools/call') {
    mark('real_call_completed');
    if (mode === 'disconnect') { child.kill(); return; }
    if (mode === 'malformed' && message.result) message.result.content = 'invalid';
    if (mode === 'bad-output' && message.result) message.result.structuredContent = { content: 7 };
    if (mode === 'missing-output' && message.result) delete message.result.structuredContent;
    if (mode === 'delay' && !delayed) {
      delayed = true;
      const timer = setTimeout(() => {
        timers.delete(timer);
        if (!cancelled.has(message.id)) send(message);
      }, 2000);
      timers.add(timer);
      return;
    }
  }
  send(message);
});
child.on('exit', () => {
  for (const timer of timers) clearTimeout(timer);
  process.exit(0);
});
child.on('error', () => process.exit(1));
