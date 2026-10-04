import assert from "node:assert/strict";
import test from "node:test";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { createServer } from "node:http";
import { RuntimeClient } from "../src/bridge/runtimeClient";
import { RuntimeProcessManager } from "../src/bridge/processManager";
import { SettingsStore } from "../src/main/settings-store";
import { SettingsController } from "../src/main/settings-controller";
import { defaultSettings, validateSettings, type DesktopSettings } from "../src/shared/settings";
import type { AgentEvent } from "../src/bridge/protocol";

const repoRoot = resolve(__dirname, "../../..");
const pythonExecutable = process.env.DATA_AGENT_PYTHON;
const variable = "PHASE28_TEST_API_KEY";
const key = "synthetic-phase28-no-real-key";
function external(endpoint = "https://phase28.invalid/v1"): DesktopSettings {
  return { provider: { provider_id: "openai-compatible", model_name: "phase28-model", endpoint, api_key_env: variable }, mcp: { enabled: false } };
}
function setup(credential = key) {
  const directory = mkdtempSync(join(tmpdir(), "data-agent-settings-"));
  const manager = new RuntimeProcessManager({ repoRoot, pythonExecutable,
    environment: { DATA_AGENT_RUNTIME_DIR: directory, [variable]: credential } });
  const runtime = new RuntimeClient(manager);
  const store = new SettingsStore(directory);
  return { directory, manager, runtime, store, controller: new SettingsController(runtime, store) };
}
function terminal(events: AgentEvent[], runId: string): Promise<AgentEvent> {
  return new Promise((resolveEvent, reject) => {
    const timer = setInterval(() => {
      const found = events.find((event) => event.run_id === runId && ["run_completed", "run_failed"].includes(event.type));
      if (found) { clearInterval(timer); clearTimeout(timeout); resolveEvent(found); }
    }, 15);
    const timeout = setTimeout(() => { clearInterval(timer); reject(new Error("Settings worker validation timed out")); }, 20000);
  });
}

test("Settings default and explicit selection validate without introducing providers", () => {
  assert.deepEqual(validateSettings(defaultSettings()), defaultSettings());
  assert.deepEqual(validateSettings(external()), external());
  assert.throws(() => validateSettings({ ...external(), provider: { ...external().provider, provider_id: "anthropic" } }));
  for (const field of ["model_name", "endpoint", "api_key_env"]) {
    assert.throws(() => validateSettings({ ...external(), provider: { ...external().provider, [field]: null } }));
  }
});

test("Settings rejects key values, endpoint credentials and MCP permission expansion", () => {
  for (const provider of [{ ...external().provider, api_key: key }, { ...external().provider, api_key_env: "sk-private" },
    { ...external().provider, endpoint: "https://user:secret@phase28.invalid/v1" }, { ...external().provider, endpoint: "https://phase28.invalid/v1?key=secret" }]) {
    assert.throws(() => validateSettings({ provider, mcp: { enabled: false } }), (error: unknown) => {
      assert.equal(String(error).includes(key), false); assert.equal(String(error).includes("user:secret"), false); return true;
    });
  }
  for (const field of ["root", "command", "allowed_tools", "read_only", "env"]) {
    assert.throws(() => validateSettings({ ...defaultSettings(), mcp: { enabled: true, [field]: "unauthorized" } }));
  }
});

test("Settings store persists only non-sensitive metadata and rejects corrupt configuration", () => {
  const directory = mkdtempSync(join(tmpdir(), "data-agent-settings-store-"));
  const store = new SettingsStore(directory);
  assert.deepEqual(store.load(), defaultSettings());
  store.save(external());
  assert.deepEqual(new SettingsStore(directory).load(), external());
  assert.equal(readFileSync(store.path, "utf8").includes(key), false);
  assert.deepEqual(Object.keys(JSON.parse(readFileSync(store.path, "utf8"))), ["provider", "mcp"]);
  writeFileSync(store.path, '{"provider":{"api_key":"not-allowed"}}');
  assert.throws(() => store.load(), /settings|配置/);
});

test("Settings Runtime default, explicit external and missing credentials have no fallback", { skip: !pythonExecutable }, async () => {
  const { manager, runtime, controller, store } = setup();
  const events: AgentEvent[] = [];
  runtime.onEvent((event) => events.push(event));
  try {
    assert.deepEqual((await controller.get()).config, defaultSettings());
    const applied = await controller.apply(external());
    assert.equal(applied.credentials, "available");
    assert.equal(applied.config.provider.provider_id, "openai-compatible");
    assert.equal(events.length, 0); // Configuration responses are not Runtime Events.
    assert.equal(readFileSync(store.path, "utf8").includes(key), false);
    await assert.rejects(controller.apply({ ...external(), provider: { ...external().provider, api_key_env: "PHASE28_ABSENT_CREDENTIAL" } }));
    assert.deepEqual((await controller.get()).config, external());
  } finally { manager.stop(); }
});

test("Settings MCP enabled/disabled uses the fixed real server and cannot expand its scope", { skip: !pythonExecutable }, async () => {
  const { manager, runtime, controller } = setup();
  try {
    await controller.get();
    const enabled = await controller.apply({ ...defaultSettings(), mcp: { enabled: true } });
    assert.deepEqual(enabled.mcp.registered_tools, ["mcp_filesystem__get_file_info"]);
    assert.equal(enabled.mcp.read_only, true);
    assert.equal(enabled.mcp.status, "ready");
    await assert.rejects(controller.apply({ ...enabled.config, mcp: { enabled: true, root: "D:/" } }));
    assert.equal((await runtime.getSettings()).mcp.enabled, true);
    const disabled = await controller.apply(defaultSettings());
    assert.deepEqual(disabled.mcp.registered_tools, []);
    assert.equal(disabled.mcp.status, "disabled");
  } finally { manager.stop(); }
});

test("Settings restores external metadata after supervisor restart and missing credentials block runs", { skip: !pythonExecutable }, async () => {
  const original = setup();
  try {
    await original.controller.apply(external());
    original.manager.stop();
    const manager = new RuntimeProcessManager({ repoRoot, pythonExecutable, environment: { DATA_AGENT_RUNTIME_DIR: original.directory, [variable]: "" } });
    const runtime = new RuntimeClient(manager);
    const controller = new SettingsController(runtime, new SettingsStore(original.directory));
    try {
      const restored = await controller.get();
      assert.deepEqual(restored.config, external());
      assert.equal(restored.credentials, "missing");
      assert.equal(restored.ready, false);
      await assert.rejects(controller.ensureReady());
      await assert.rejects(runtime.startRun("hello"));
      assert.deepEqual((await runtime.getSettings()).config, external());
      await controller.apply(defaultSettings());
      await controller.ensureReady();
    } finally { manager.stop(); }
  } finally { original.manager.stop(); }
});

test("Settings corrupt storage blocks analysis until an explicit valid save", { skip: !pythonExecutable }, async () => {
  const { manager, controller, store } = setup();
  try {
    writeFileSync(store.path, "invalid-json");
    await assert.rejects(controller.ensureReady());
    await controller.apply(defaultSettings());
    await controller.ensureReady();
  } finally { manager.stop(); }
});

test("Settings selected Provider and real MCP reach the existing worker without configuration in Session or Trace", { skip: !pythonExecutable }, async () => {
  let requests = 0;
  let receivedSchema = false;
  let receivedObservation = false;
  const server = createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => { body += chunk; });
    request.on("end", () => {
      try {
        assert.equal(request.headers.authorization, "Bearer " + key);
        assert.equal(body.includes(key), false);
        const payload = JSON.parse(body);
        requests++;
        const schema = payload.tools.find((item: { function: { name: string } }) => item.function.name === "mcp_filesystem__get_file_info");
        assert.equal(schema.function.parameters.properties.path.type, "string");
        receivedSchema = true;
        const observation = payload.messages.find((item: { role: string }) => item.role === "tool");
        let choice;
        if (!observation) {
          choice = { finish_reason: "tool_calls", message: { role: "assistant", content: null, tool_calls: [{
            id: "call-phase28", type: "function", function: { name: schema.function.name, arguments: '{"path":"metadata.txt"}' },
          }] } };
        } else {
          const result = JSON.parse(observation.content);
          assert.equal(result.ok, true);
          assert.equal(observation.tool_call_id, "call-phase28");
          const size = /^size: (\d+)$/m.exec(result.data.structuredContent.content)?.[1];
          assert.equal(size, "78"); receivedObservation = true;
          choice = { finish_reason: "stop", message: { role: "assistant", content: `File metadata verified: ${size} bytes.` } };
        }
        response.writeHead(200, { "Content-Type": "application/json" }); response.end(JSON.stringify({ choices: [choice] }));
      } catch { response.writeHead(500); response.end("{}"); }
    });
  });
  await new Promise<void>((ready) => server.listen(0, "127.0.0.1", ready));
  const address = server.address(); assert.ok(address && typeof address === "object");
  const configuration = external(`http://127.0.0.1:${address.port}/v1`);
  configuration.mcp.enabled = true;
  const { manager, runtime, controller } = setup();
  const events: AgentEvent[] = [];
  const errors: string[] = [];
  runtime.onEvent((event) => events.push(event)); runtime.onStderr((message) => errors.push(message));
  try {
    await controller.apply(configuration);
    const dataset = await runtime.registerDataset(join(repoRoot, "tests/fixtures/sales.csv"));
    const run = await runtime.startRun("计算销售额总和", dataset.threadId, String(dataset.dataset.datasetId));
    const completed = await terminal(events, run.runId);
    assert.equal(completed.type, "run_completed");
    assert.equal(requests, 2); assert.equal(receivedSchema, true); assert.equal(receivedObservation, true);
    assert.ok(events.some((event) => event.type === "tool_completed"));
    const session = await runtime.getSession(run.threadId);
    const serialized = JSON.stringify({ session, events, errors });
    for (const marker of [key, variable, configuration.provider.model_name!, configuration.provider.endpoint!, '"provider_config"', '"api_key_env"', "Authorization"]) {
      assert.equal(serialized.includes(marker), false, "Configuration leaked outside Settings");
    }
  } finally { manager.stop(); await new Promise<void>((done) => server.close(() => done())); }
});
