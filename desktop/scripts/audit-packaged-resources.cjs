const assert = require("node:assert/strict");
const { readdirSync, readFileSync, statSync } = require("node:fs");
const { join, resolve, relative, basename } = require("node:path");
const { createHash } = require("node:crypto");
const asar = require("@electron/asar");
const desktopRoot = resolve(__dirname, "..");
const projectRoot = resolve(desktopRoot, "..");
const resources = process.argv[2] ? resolve(process.argv[2]) : join(desktopRoot, "release/win-unpacked/resources");
let count = 0;
function walk(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    assert.ok(!entry.isSymbolicLink(), "Packaged resources must not include symbolic links");
    assert.ok(!/^\.env(?:\.|$)/i.test(entry.name) && ![".git", "runtime-settings.json"].includes(entry.name), `Forbidden packaged file: ${entry.name}`);
    const file = join(directory, entry.name);
    if (entry.isDirectory()) walk(file); else count++;
  }
}
walk(resources);
function same(source, target) {
  const digest = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");
  assert.equal(digest(source), digest(target), `Stale packaged source: ${relative(projectRoot, source)}`);
}
for (const directory of ["providers"]) {
  for (const entry of readdirSync(join(projectRoot, directory))) {
    if (entry.endsWith(".py")) same(join(projectRoot, directory, entry), join(resources, directory, entry));
  }
}
for (const file of ["runtime_bridge.py", "runtime_settings.py"]) same(join(desktopRoot, "python", file), join(resources, "desktop/python", file));
for (const file of ["main/index.js", "main/settings-controller.js", "main/settings-store.js", "preload/index.js", "shared/settings.js", "renderer/index.html", "renderer/bundle.js"]) {
  assert.deepEqual(asar.extractFile(join(resources, "app.asar"), join("dist", "src", file)), readFileSync(join(desktopRoot, "dist/src", file)), `Stale Desktop asset: ${file}`);
}
const root = join(resources, "tests/fixtures/mcp-readonly");
assert.deepEqual(readdirSync(root), ["metadata.txt"]);
same(join(projectRoot, "tests/fixtures/mcp-readonly/metadata.txt"), join(root, "metadata.txt"));
assert.equal(statSync(join(root, "metadata.txt")).size, 78);
const manifest = JSON.parse(readFileSync(join(resources, "packaged-dependencies.json")));
assert.equal(manifest.pythonPackages.mcp, "2.2.0");
assert.equal(manifest.filesystemServer, "2026.8.31");
assert.deepEqual(manifest.allowedTools, ["get_file_info"]);
assert.equal(manifest.allowedRoot, "tests/fixtures/mcp-readonly");
console.log(JSON.stringify({ status: "PASS", resources, filesAudited: count, noEnvironmentOrUserSettings: true,
  latestProviderSettingsAssets: true, fixedFixtureScope: true, pythonPackages: Object.keys(manifest.pythonPackages).length,
  npmPackages: manifest.npmPackages }));
