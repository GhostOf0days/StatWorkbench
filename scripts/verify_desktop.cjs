// Executes the real Electron application and validates artifacts written by its
// IPC smoke path. No browser-server substitute is used here.
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {createRuntimeErrorTracker} = require('./desktop-runtime-errors.cjs');
const runtimeErrors = createRuntimeErrorTracker();
const root = path.resolve(__dirname, '..');
const executableArgument = process.argv.indexOf('--executable');
const packaged = executableArgument !== -1 || process.argv.includes('--packaged');
const packageExecutable = process.platform === 'darwin'
  ? path.join('release', process.arch === 'x64' ? 'mac' : `mac-${process.arch}`, 'StatWorkbench.app', 'Contents', 'MacOS', 'StatWorkbench')
  : process.platform === 'win32' ? path.join('release', process.arch === 'x64' ? 'win-unpacked' : `win-${process.arch}-unpacked`, 'StatWorkbench.exe')
  : path.join('release', process.arch === 'x64' ? 'linux-unpacked' : `linux-${process.arch}-unpacked`, 'statworkbench-desktop');
const executable = packaged ? path.resolve(executableArgument !== -1 ? process.argv[executableArgument + 1] : path.join(root, packageExecutable)) : require('electron');
const output = path.resolve(process.env.STATWORKBENCH_SMOKE_OUTPUT || path.join(root, 'test-artifacts', packaged ? 'native-packaged' : 'native-development'));
fs.mkdirSync(output, {recursive: true});
const started = Date.now();
const logPath = path.join(output, 'desktop-runtime.log');
const log = fs.createWriteStream(logPath);
const child = spawn(executable, [...(packaged ? [] : [root]), '--smoke-test'], {
  cwd: root, env: {...process.env, STATWORKBENCH_SMOKE_OUTPUT: output}, stdio: ['ignore', 'pipe', 'pipe'],
});
let timedOut = false, finished = false, timeoutPhase = null, workflowCompletedAt = null, shutdownTimeout, stdoutTail = '';
// Opening the complete analysis catalog deliberately exercises worksheet settling
// and native layout. Allow the full catalog traversal on slower desktops.
const timeoutMilliseconds = 420000;
const shutdownTimeoutMilliseconds = 30000;
function expire(phase) {timedOut = true; timeoutPhase = phase; child.kill('SIGKILL'); finish(null, 'SIGKILL');}
function watchShutdown() {if (!shutdownTimeout) shutdownTimeout = setTimeout(() => expire('shutdown'), shutdownTimeoutMilliseconds);}
const timeout = setTimeout(() => expire('overall'), timeoutMilliseconds);
// Once both artifacts exist, bound teardown separately. Successful worksheet
// work is reported independently; a stuck process still fails verification.
const artifactPoll = setInterval(() => {
  try {
    if (['desktop-smoke.json','desktop.png'].every(name => fs.statSync(path.join(output,name)).mtimeMs >= started)) {
      workflowCompletedAt = new Date().toISOString();
      clearInterval(artifactPoll);
      watchShutdown();
    }
  } catch { /* The workflow has not written both artifacts yet. */ }
}, 1000);
child.stdout.on('data', chunk => {
  runtimeErrors.append('stdout', chunk);
  log.write(chunk); process.stdout.write(chunk);
  stdoutTail = (stdoutTail + chunk.toString()).slice(-2048);
  if (stdoutTail.includes('[desktop-smoke] quit event:')) watchShutdown();
});
child.stderr.on('data', chunk => {runtimeErrors.append('stderr', chunk); log.write(chunk); process.stderr.write(chunk);});
child.on('error', error => {log.write(String(error)); finish(null, 'SPAWN_ERROR');});
// Wait for output pipes to drain before judging renderer errors. The timeout
// still bounds a process that cannot emit close during a failed OS teardown.
child.on('close', finish);
function finish(code, signal) {
  if (finished) return;
  finished = true;
  clearTimeout(timeout);
  clearInterval(artifactPoll);
  clearTimeout(shutdownTimeout);
  const result = {startedAt: new Date(started).toISOString(), finishedAt: new Date().toISOString(), elapsedSeconds: (Date.now() - started) / 1000, platform: process.platform, architecture: process.arch, packaged, executable, minimumWindow:process.env.STATWORKBENCH_SMOKE_MINIMUM==='1', exitCode: code, signal, timedOut, timeoutPhase, workflowCompletedAt, workflowVerified: false, processExitVerified: code === 0 && !timedOut, verified: false};
  try {
    const smokePath = path.join(output, 'desktop-smoke.json');
    if (fs.statSync(smokePath).mtimeMs < started) throw new Error('Desktop did not write a fresh smoke result.');
    result.smoke = JSON.parse(fs.readFileSync(smokePath, 'utf8'));
    const independentExtensions = ['copula.bivariate','dependence.association','dependence.partial','dependence.distance','dependence.mutual_information','dependence.tail_coexceedance','dependence.lead_lag','stochastic.markov_chain'];
    if (!result.smoke.ok || result.smoke.catalog !== 125 || result.smoke.coreCatalog !== 117 || !independentExtensions.every(id => result.smoke.extensions?.includes(id)) || !Number.isInteger(result.smoke.renderedControls) || result.smoke.renderedControls < 720 || !result.smoke.favorites || !result.smoke.nativeMenus || !result.smoke.worksheetReports || !result.smoke.savedProject || !result.smoke.imports || !result.smoke.export || !result.smoke.generatedData || result.smoke.formulaCell !== 431) throw new Error('Desktop smoke results are incomplete.');
    for (const feature of ['preferences','quickAccess','chartEditing','migrationGuide','recent','legacyProject','originalFormulaRecalculation','originalFormulaProvenance','legacyProjectExport','originalNamedArrayFormulas','copulas']) {
      if (result.smoke[feature] !== true) throw new Error(`Desktop did not verify ${feature}.`);
    }
    const screenshot = path.join(output, 'desktop.png');
    if (fs.statSync(screenshot).mtimeMs < started) throw new Error('Desktop did not write a fresh screenshot.');
    result.screenshot = screenshot;
    result.screenshotSha256 = crypto.createHash('sha256').update(fs.readFileSync(screenshot)).digest('hex');
    result.workflowVerified = true;
  } catch (error) {result.error = error.message; console.error(error.message);}
  if (!result.processExitVerified) {
    result.exitError = `Desktop exited ${code ?? signal}${timedOut ? ` after the ${(timeoutPhase === 'shutdown' ? shutdownTimeoutMilliseconds : timeoutMilliseconds) / 1000}-second ${timeoutPhase} limit` : ''}`;
    result.error = [result.error, result.exitError].filter(Boolean).join(' ');
    console.error(result.exitError);
  }
  result.rendererErrors = runtimeErrors.finish();
  result.rendererVerified = result.rendererErrors.length === 0;
  if (!result.rendererVerified) {
    const rendererError = `Desktop reported ${result.rendererErrors.length} renderer error(s).`;
    result.error = [result.error, rendererError].filter(Boolean).join(' ');
    console.error(rendererError);
  }
  result.verified = result.workflowVerified && result.processExitVerified && result.rendererVerified;
  fs.writeFileSync(path.join(output, 'desktop-verification.json'), JSON.stringify(result, null, 2) + '\n');
  // A macOS process suspended before exec may never emit close, even after
  // SIGKILL. Always finish the report and bound the verification command.
  log.end(() => process.exit(result.verified ? 0 : 1));
}
