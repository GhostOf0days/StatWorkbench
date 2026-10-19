const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const { test } = require("node:test");

function loadConfig(signing) {
  const env = { ...process.env };
  if (signing) env.STATWORKBENCH_RELEASE_SIGNING = "1";
  else delete env.STATWORKBENCH_RELEASE_SIGNING;
  const output = execFileSync(
    process.execPath,
    ["-e", "process.stdout.write(JSON.stringify(require('./electron-builder.config.cjs')))"],
    { cwd: process.cwd(), env, encoding: "utf8" },
  );
  return JSON.parse(output);
}

test("development packaging keeps working without signing credentials", () => {
  const config = loadConfig(false);
  assert.equal(config.forceCodeSigning, false);
  assert.equal(config.mac.identity, "-");
  assert.equal(config.mac.hardenedRuntime, false);
  assert.equal(config.mac.notarize, undefined);
});

test("release packaging requires signatures and notarizes the Mac app", () => {
  const config = loadConfig(true);
  assert.equal(config.forceCodeSigning, true);
  assert.equal(config.mac.identity, undefined);
  assert.equal(config.mac.hardenedRuntime, true);
  assert.equal(config.mac.notarize, true);
});
