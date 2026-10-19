#!/usr/bin/env node
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.resolve("release");

function run(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8" });
  if (result.stdout) process.stdout.write(result.stdout);
  if (result.stderr) process.stderr.write(result.stderr);
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(`${command} ${args.join(" ")} exited with ${result.status}`);
  }
}

function findFiles(directory, predicate, found = []) {
  if (!fs.existsSync(directory)) return found;
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const item = path.join(directory, entry.name);
    if (entry.isDirectory()) findFiles(item, predicate, found);
    else if (predicate(item)) found.push(item);
  }
  return found;
}

if (!fs.existsSync(root)) throw new Error("release/ does not exist");

if (process.platform === "darwin") {
  const apps = findFiles(root, (file) => file.endsWith("/StatWorkbench.app/Contents/Info.plist"))
    .map((file) => file.slice(0, -"/Contents/Info.plist".length));
  if (apps.length === 0) throw new Error("No packaged StatWorkbench.app was found");
  for (const app of apps) {
    run("codesign", ["--verify", "--deep", "--strict", "--verbose=2", app]);
    run("spctl", ["--assess", "--type", "execute", "--verbose=4", app]);
    run("xcrun", ["stapler", "validate", app]);
  }
  console.log(`Verified signature, Gatekeeper acceptance, and notarization ticket for ${apps.length} app bundle(s).`);
} else if (process.platform === "win32") {
  const executables = fs.readdirSync(root)
    .filter((name) => /^StatWorkbench.*\.exe$/i.test(name))
    .map((name) => path.join(root, name));
  if (executables.length === 0) throw new Error("No packaged StatWorkbench Windows executable was found");
  for (const executable of executables) {
    const escaped = executable.replaceAll("'", "''");
    const script = `$sig = Get-AuthenticodeSignature -LiteralPath '${escaped}'; if ($sig.Status -ne 'Valid') { Write-Error \"Signature status $($sig.Status): $($sig.StatusMessage)\"; exit 1 }; if (-not $sig.SignerCertificate) { Write-Error 'Missing publisher certificate'; exit 1 }; Write-Output \"Valid Authenticode signature: $($sig.SignerCertificate.Subject)\"`;
    run("powershell", ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script]);
  }
  console.log(`Verified Authenticode signature for ${executables.length} Windows executable(s).`);
} else {
  console.log("No desktop code-signature verification is configured for this platform.");
}
