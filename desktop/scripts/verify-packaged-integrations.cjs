const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { join, resolve } = require("node:path");
const desktopRoot = resolve(__dirname, "..");
const resourcesArg = process.argv.indexOf("--resources");
const resources = resourcesArg >= 0 ? resolve(process.argv[resourcesArg + 1]) : join(desktopRoot, "release", "win-unpacked", "resources");
const env = Object.fromEntries(["SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"]
  .filter((name) => process.env[name]).map((name) => [name, process.env[name]]));
env.PATH = join(process.env.SystemRoot || "C:\\Windows", "System32");
const result = spawnSync(join(resources, "python-runtime", "python.exe"),
  ["-I", join(__dirname, "verify-packaged-integrations.py"), "--resources", resources],
  { cwd: process.env.TEMP, env, encoding: "utf8", timeout: 60000, windowsHide: true });
assert.equal(result.error, undefined);
assert.equal(result.status, 0, result.stderr);
console.log(result.stdout.trim());
