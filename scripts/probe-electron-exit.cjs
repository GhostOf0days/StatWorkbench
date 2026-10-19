// Isolate Electron/OS teardown from StatWorkbench's renderer and Python worker.
const fs = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');
const os = require('node:os');
const output = path.resolve(process.argv[2] || 'test-artifacts/electron-exit');
fs.mkdirSync(output, {recursive:true});
const electron = require('electron');
async function probe(window) {
  const name = window ? 'hidden-window' : 'no-window';
  const profile = fs.mkdtempSync(path.join(output, name+'-'));
  const main = path.join(profile, 'main.cjs');
  fs.writeFileSync(main, `const {app,BrowserWindow}=require('electron');
app.setPath('userData', ${JSON.stringify(profile)});
app.on('quit',()=>console.log('QUIT_EVENT'));
app.whenReady().then(async()=>{
${window ? "const win=new BrowserWindow({show:false});await win.loadURL('about:blank');" : ''}
setTimeout(()=>app.quit(),500);
});`);
  return await new Promise(resolve=>{
    const start=Date.now();let log='',quit=false,finished=false;
    const child=spawn(electron,[main],{stdio:['ignore','pipe','pipe']});
    const finish=value=>{if(finished)return;finished=true;clearTimeout(timer);resolve({name,pid:child.pid,elapsedMs:Date.now()-start,quitEvent:quit,...value,log});};
    const timer=setTimeout(()=>{child.kill('SIGKILL');finish({exited:false,error:'Process did not exit within 15 seconds'});child.unref();child.stdout.destroy();child.stderr.destroy();},15000);
    const record=data=>{log+=data.toString();quit=log.includes('QUIT_EVENT');};
    child.stdout.on('data',record);child.stderr.on('data',record);
    child.on('error',error=>finish({exited:false,error:error.message}));
    child.on('exit',(code,signal)=>finish({exited:true,code,signal}));
  });
}
(async()=>{
  const results=[];
  for(const window of [false,true]) {const result=await probe(window);results.push(result);console.log(JSON.stringify(result));}
  const report={checkedAt:new Date().toISOString(),platform:process.platform,arch:process.arch,osRelease:os.release(),electron:require('electron/package.json').version,results,verified:results.every(r=>r.exited&&r.code===0&&r.quitEvent)};
  fs.writeFileSync(path.join(output,'verification.json'),JSON.stringify(report,null,2));
  process.exitCode=report.verified?0:1;
})();
