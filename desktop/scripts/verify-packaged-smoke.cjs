const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { copyFileSync, existsSync, mkdtempSync, readFileSync, mkdirSync } = require("node:fs");
const { join, resolve } = require("node:path");

const desktopRoot = resolve(__dirname, "..");
const projectRoot = resolve(desktopRoot, "..");
const executableArg = process.argv.indexOf("--executable");
const executable = executableArg >= 0
  ? resolve(process.argv[executableArg + 1] || "")
  : join(desktopRoot, "release", "win-unpacked", "Data Analysis Agent.exe");
const labelArg = process.argv.indexOf("--label");
const label = labelArg >= 0 ? process.argv[labelArg + 1] : "m6.4-smoke";
assert.match(label || "", /^[a-z0-9][a-z0-9.-]*$/, "Smoke label must contain only lowercase letters, digits, dots and hyphens");
const fixture = join(projectRoot, "tests", "fixtures", "sales.csv");
assert.ok(existsSync(executable), `Build the Windows unpacked artifact first: ${executable}`);
assert.ok(existsSync(fixture), `CSV fixture is missing: ${fixture}`);
const outputDirectory = mkdtempSync(join(desktopRoot, "release", `${label}-`));
const selectedCsv = join(outputDirectory, "sales.csv");
copyFileSync(fixture, selectedCsv);
const userData = join(outputDirectory, "profile");
mkdirSync(userData);

function launch(phase, threadId) {
  const resultPath = join(outputDirectory, `${phase}.json`);
  // Deliberately omit development PATH, PYTHONPATH, Provider selection and keys.
  const env = Object.fromEntries(["SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"]
    .filter((name) => process.env[name]).map((name) => [name, process.env[name]]));
  Object.assign(env, {
    PATH: join(process.env.SystemRoot || "C:\\Windows", "System32"),
    DATA_AGENT_PACKAGING_SMOKE_USER_DATA: userData,
    DATA_AGENT_PACKAGING_SMOKE: `m6.4-${phase}`,
    DATA_AGENT_PACKAGING_SMOKE_RESULT: resultPath,
    DATA_AGENT_PACKAGING_SMOKE_FILE: selectedCsv,
    ...(threadId ? { DATA_AGENT_PACKAGING_SMOKE_THREAD: threadId } : {}),
  });
  delete env.ELECTRON_RUN_AS_NODE;
  const child = spawnSync(executable, [], {
    env, cwd: outputDirectory, encoding: "utf8", windowsHide: true, timeout: 90000,
  });
  assert.equal(child.error, undefined, `Packaged ${phase} launch error: ${child.error}`);
  assert.equal(child.status, 0,
    `Packaged ${phase} exited ${child.status}; stderr=${child.stderr}; stdout=${child.stdout}`);
  assert.ok(existsSync(resultPath), `Packaged ${phase} produced no result: ${resultPath}`);
  const result = JSON.parse(readFileSync(resultPath, "utf8"));
  assert.equal(result.packaged, true);
  assert.equal(resolve(result.executable).toLowerCase(), resolve(executable).toLowerCase());
  assert.match(result.rendererUrl, /app\.asar/);
  return result;
}

const first = launch("first");
assert.equal(first.status, "completed");
assert.equal(first.settings.defaultProvider, "deterministic");
assert.equal(first.settings.externalPage, true);
assert.equal(first.settings.missingCredentials, true);
assert.equal(first.settings.mcpEnabled, true);
assert.equal(first.hitlReject, true);
assert.match(first.dataset, /sales\.csv/);
assert.match(first.answer, /1580/);
for (const type of ["run_started", "route_selected", "tool_called", "run_completed"]) {
  assert.ok(first.eventTypes.includes(type), `Missing Runtime event ${type}`);
}
const resumed = launch("resume", first.threadId);
assert.notEqual(resumed.pid, first.pid, "Restart did not create a new process");
assert.equal(resumed.userData, first.userData, "Restart changed Electron userData directory");
assert.equal(resumed.threadId, first.threadId, "Restart recovered a different Session");
assert.equal(resumed.status, "completed");
assert.ok(resumed.traceCount > 0 && resumed.messageCount >= 2);
assert.ok(resumed.traceIds.includes(first.traceId), "Recovered Session lost the original trace");
assert.equal(resumed.newRuntimeEvents, 0, "Hydration unexpectedly emitted a new run");
assert.equal(resumed.settings.restored, true);
assert.equal(resumed.settings.mcpDisabled, true);
console.log(JSON.stringify({
  outcome: "passed", executable, launch: "spawnSync(actual packaged exe, twice)",
  resultDirectory: outputDirectory, userData: first.userData,
  first: { pid: first.pid, status: first.status, threadId: first.threadId,
    traceId: first.traceId, traceCount: first.traceCount, eventTypes: first.eventTypes },
  restart: { pid: resumed.pid, status: resumed.status, threadId: resumed.threadId,
    messageCount: resumed.messageCount, traceCount: resumed.traceCount },
  settings: { first: first.settings, restart: resumed.settings },
  hitlReject: first.hitlReject,
  developmentPathRemoved: true,
}, null, 2));
