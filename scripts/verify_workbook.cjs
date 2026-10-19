// Run the real spreadsheet renderer, including images, formulas and disposal.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const output = path.resolve(process.env.STATWORKBENCH_WORKBOOK_OUTPUT || path.join(root, 'test-artifacts', 'workbook-adapter'));
fs.mkdirSync(output, {recursive:true});
if (!process.versions.electron) {
  const {spawn} = require('node:child_process');
  const child = spawn(require('electron'), [__filename], {cwd:root, env:process.env, stdio:'inherit'});
  const timer = setTimeout(() => {child.kill('SIGKILL');}, 180000);
  child.on('error', error => {clearTimeout(timer);console.error(error);process.exitCode=1;});
  child.on('close', (code) => {clearTimeout(timer);process.exitCode=code ?? 1;});
} else {
  const {app, BrowserWindow} = require('electron');
  app.setPath('userData', path.join(output, 'profile'));
  let server, window;
  const started = Date.now();
  const result = {verified:false, platform:process.platform, checks:[], rendererErrors:[]};
  app.whenReady().then(async () => {
    try {
      const {createServer} = await import('vite');
      server = await createServer({root:path.join(root,'renderer'),configFile:path.join(root,'vite.config.mjs'),server:{host:'127.0.0.1',port:0,strictPort:false}});
      await server.listen();
      window = new BrowserWindow({show:false,width:1280,height:900,webPreferences:{nodeIntegration:false,contextIsolation:true,sandbox:true,backgroundThrottling:false}});
      window.webContents.on('render-process-gone', (_event, details) => result.rendererErrors.push(details.reason));
      await window.loadURL(`http://127.0.0.1:${server.httpServer.address().port}/adapter-test.html`);
      let contents = '';
      while (Date.now()-started < 150000) {
        contents = await window.webContents.executeJavaScript('document.getElementById("results").textContent');
        if (/^(ALL \d+ CHECKS PASSED|FAILED:)/.test(contents)) break;
        await new Promise(resolve=>setTimeout(resolve,250));
      }
      result.checks=contents.split('\n').filter(line=>line.startsWith('PASS ')).map(line=>line.slice(5));
      if (!/^ALL \d+ CHECKS PASSED/.test(contents)) throw Error(contents);
      if (result.rendererErrors.length) throw Error(result.rendererErrors.join('\n'));
      result.verified=true;
    } catch(error) {result.error=error.stack||String(error);process.exitCode=1;}
    finally {
      result.durationSeconds=(Date.now()-started)/1000;
      fs.writeFileSync(path.join(output,'verification.json'),JSON.stringify(result,null,2)+'\n');
      console.log(JSON.stringify({verified:result.verified,checks:result.checks.length,error:result.error,output},null,2));
      if(window&&!window.isDestroyed())window.destroy();
      if(server)await server.close();
      app.exit(result.verified?0:1);
    }
  });
}
