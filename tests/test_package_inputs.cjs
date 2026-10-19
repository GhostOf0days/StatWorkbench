const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {verifyPackageInputs,verifyWindowsBridge} = require('../scripts/verify-package-inputs.cjs');

test('packaging rejects unverified engines and later edits or additions', t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'statworkbench-package-'));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  fs.mkdirSync(path.join(root,'backend'));
  fs.mkdirSync(path.join(root,'renderer-dist'));
  fs.mkdirSync(path.join(root,'dist-backend','statworkbench-engine'), {recursive:true});
  fs.writeFileSync(path.join(root,'backend','worker.py'),'original source\n');
  fs.writeFileSync(path.join(root,'renderer-dist','index.html'),'<!doctype html>');
  const manifestPath = path.join(root,'dist-backend','statworkbench-engine','build-verification.json');
  const target={platform:'darwin',architecture:'arm64'};
  const manifest = {verified:false,...target,source_sha256:{'backend/worker.py':crypto.createHash('sha256').update('original source\n').digest('hex')}};
  fs.writeFileSync(manifestPath,JSON.stringify(manifest));
  assert.throws(()=>verifyPackageInputs(root,target), /not passed its native runtime checks/);
  manifest.verified=true;
  fs.writeFileSync(manifestPath,JSON.stringify(manifest));
  assert.deepEqual(verifyPackageInputs(root,target), {backendFiles:1,verified:true});
  assert.throws(()=>verifyPackageInputs(root, {platform:'win32',architecture:'arm64'}), /does not match the desktop target/);
  assert.throws(()=>verifyPackageInputs(root, {platform:'darwin',architecture:'x64'}), /does not match the desktop target/);
  fs.writeFileSync(path.join(root,'backend','worker.py'),'changed source\n');
  assert.throws(()=>verifyPackageInputs(root,target), /stale/);
  fs.writeFileSync(path.join(root,'backend','worker.py'),'original source\n');
  fs.writeFileSync(path.join(root,'backend','new_analysis.py'),'new source\n');
  assert.throws(()=>verifyPackageInputs(root,target), /files have changed/);
});

test('Windows packages require a verified native bridge and matching source and executable hashes', t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'statworkbench-windows-package-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 fs.mkdirSync(path.join(root,'dist-windows'));fs.mkdirSync(path.join(root,'electron','windows'),{recursive:true});
 assert.throws(()=>verifyWindowsBridge(root),/Build the compiled Windows/);
 const source=path.join(root,'electron','windows','SpreadsheetBridge.cs'),binary=path.join(root,'dist-windows','StatWorkbench.SpreadsheetBridge.exe'),manifestFile=path.join(root,'dist-windows','build-verification.json');
 fs.writeFileSync(source,'C# source');fs.writeFileSync(binary,'MZ-test-fixture');const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
 const manifest={verified:false,managedRuntime:true,platform:'win32',architecture:'anycpu',source_sha256:hash(source),executable_sha256:hash(binary)};const save=()=>fs.writeFileSync(manifestFile,JSON.stringify(manifest));save();
 assert.throws(()=>verifyWindowsBridge(root),/managed runtime/);manifest.verified=true;save();assert.doesNotThrow(()=>verifyWindowsBridge(root));
 fs.writeFileSync(source,'changed C#');assert.throws(()=>verifyWindowsBridge(root),/stale/);fs.writeFileSync(source,'C# source');
 fs.writeFileSync(binary,'changed binary');assert.throws(()=>verifyWindowsBridge(root),/stale/);manifest.executable_sha256=hash(binary);save();assert.throws(()=>verifyWindowsBridge(root),/not a Windows executable/);
});
