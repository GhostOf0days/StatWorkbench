const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

function pythonSources(directory, prefix = 'backend') {
  return fs.readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const name = `${prefix}/${entry.name}`;
    if (entry.isDirectory()) return pythonSources(path.join(directory, entry.name), name);
    return entry.isFile() && entry.name.endsWith('.py') ? [name] : [];
  }).sort();
}

function verifyPackageInputs(project, target = {platform: process.platform, architecture: process.arch}) {
  const engine = path.join(project, 'dist-backend', 'statworkbench-engine');
  const manifestPath = path.join(engine, 'build-verification.json');
  if (!fs.existsSync(manifestPath)) throw new Error('Build the statistics engine before packaging: python scripts/build_backend.py');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  if (manifest.verified !== true) throw new Error('The frozen statistics engine has not passed its native runtime checks. Rebuild it before packaging.');
  if (manifest.platform !== target.platform || manifest.architecture !== target.architecture) throw new Error(`Frozen engine platform/architecture (${manifest.platform || 'unknown'}/${manifest.architecture || 'unknown'}) does not match the desktop target (${target.platform}/${target.architecture}). Build and verify the engine on the target OS and architecture before packaging.`);
  const sources = pythonSources(path.join(project, 'backend'));
  const recorded = Object.keys(manifest.source_sha256 || {}).sort();
  if (JSON.stringify(sources) !== JSON.stringify(recorded)) throw new Error('Backend files have changed since the frozen engine was built. Rebuild the engine before packaging.');
  for (const file of sources) {
    const digest = crypto.createHash('sha256').update(fs.readFileSync(path.join(project, file))).digest('hex');
    if (digest !== manifest.source_sha256[file]) throw new Error(`Frozen engine is stale: ${file} changed. Rebuild the engine before packaging.`);
  }
  if (!fs.existsSync(path.join(project, 'renderer-dist', 'index.html'))) throw new Error('Build the renderer before packaging: npm run build:renderer');
  if(target.platform==='win32')verifyWindowsBridge(project);
  return {backendFiles: sources.length, verified: true};
}

function verifyWindowsBridge(project){
  const directory=path.join(project,'dist-windows'),manifestPath=path.join(directory,'build-verification.json');
  if(!fs.existsSync(manifestPath))throw new Error('Build the compiled Windows Excel adapter before packaging: python scripts/build_windows_bridge.py');
  const manifest=JSON.parse(fs.readFileSync(manifestPath,'utf8'));
  if(manifest.verified!==true||manifest.managedRuntime!==true||manifest.platform!=='win32'||manifest.architecture!=='anycpu')throw new Error('The Windows spreadsheet adapter has not passed its managed runtime check.');
  for(const[file,key]of [[path.join(project,'electron','windows','SpreadsheetBridge.cs'),'source_sha256'],[path.join(directory,'StatWorkbench.SpreadsheetBridge.exe'),'executable_sha256']]){
    if(!fs.existsSync(file)||crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')!==manifest[key])throw new Error('The compiled Windows spreadsheet adapter is stale. Rebuild it before packaging.');
  }
  if(fs.readFileSync(path.join(directory,'StatWorkbench.SpreadsheetBridge.exe')).subarray(0,2).toString()!=='MZ')throw new Error('The Windows spreadsheet adapter is not a Windows executable.');
}

module.exports = async context => {
  const {Arch} = require('builder-util');
  const result = verifyPackageInputs(context.packager.projectDir, {platform: context.electronPlatformName, architecture: Arch[context.arch]});
  console.log(`Verified ${result.backendFiles} backend source files match the tested frozen engine.`);
};
module.exports.verifyPackageInputs = verifyPackageInputs;
module.exports.verifyWindowsBridge = verifyWindowsBridge;
