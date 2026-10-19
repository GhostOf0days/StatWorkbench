const {validateProject}=require('./project.cjs');
const {createFavoritesStore}=require('./favorites.cjs');
const {createPreferencesStore}=require('./preferences.cjs');
const {createExternalSpreadsheetBridge}=require('./external-spreadsheet.cjs');
const {readLaunchRequest}=require('./excel-addin.cjs');
const {app, BrowserWindow, ipcMain, dialog, Menu} = require('electron');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const readline = require('node:readline');
const {randomUUID} = require('node:crypto');
const root = path.resolve(__dirname, '..');
const applicationIcon = path.join(root,'assets','statworkbench.png');
app.setName('StatWorkbench');
const smoke = process.argv.includes('--smoke-test');
// A verification process must not share Chromium storage/locks with a user's
// running desktop. Each invocation keeps its profile beside its test artifacts.
const smokeOutput=smoke?path.resolve(process.env.STATWORKBENCH_SMOKE_OUTPUT||path.join(app.getPath('temp'),`statworkbench-smoke-${process.pid}`)):null;
if(smoke){const profile=path.join(smokeOutput,`profile-${process.pid}`);fs.mkdirSync(profile,{recursive:true});app.setPath('userData',profile);}
const excelAddinEnabled=process.platform==='win32'&&!smoke;
const ownsInstance=!excelAddinEnabled||app.requestSingleInstanceLock();
if(!ownsInstance)app.quit();
const excelRequests=[];
let excelRequestChain=Promise.resolve();
function enqueueExcelRequest(argv){
  excelRequestChain=excelRequestChain.then(async()=>{
    const request=await readLaunchRequest(argv);
    if(request){if(excelRequests.length>=20)throw new Error('Too many pending Excel commands. Try again after completing the current analysis.');excelRequests.push(request);menuAction('excel-addin');}
    if(win){if(win.isMinimized())win.restore();win.show();win.focus();}
  }).catch(error=>{console.error('Excel add-in:',error);dialog.showErrorBox('Excel add-in',error.message);});
  return excelRequestChain;
}
if(excelAddinEnabled&&ownsInstance)app.on('second-instance',(_event,argv)=>{void enqueueExcelRequest(argv);});
const minimumSmokeWindow = smoke && process.env.STATWORKBENCH_SMOKE_MINIMUM === '1';
const smokeTrace = message => {if (smoke) console.log(`[desktop-smoke] ${message}`);};
let win, worker, dirty = false, sequence = 0, quitting = false;
const pending = new Map();
const approvedImports = new Set();
let workerDiagnostics = '';
let preferencesStore, favorites, menuProcedures, recentAnalyses = [];
const externalSpreadsheets=createExternalSpreadsheetBridge({windowsExecutable:app.isPackaged?path.join(process.resourcesPath,'spreadsheet-bridge','StatWorkbench.SpreadsheetBridge.exe'):path.join(root,'dist-windows','StatWorkbench.SpreadsheetBridge.exe'),createReportWorkbook:(reportPath,report)=>engine('export_report_xlsx',{path:reportPath,report})});
let spreadsheetSource='standalone';

function rejectPending(message) {
  for (const item of pending.values()) {clearTimeout(item.timer); item.reject(new Error(message));}
  pending.clear();
}
function startWorker() {
  if (worker) return;
  let command, args;
  if (app.isPackaged) {
    command = path.join(process.resourcesPath, 'engine', `statworkbench-engine${process.platform === 'win32' ? '.exe' : ''}`);
    args = [];
  } else {
    const localPython = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    command = process.env.STATWORKBENCH_PYTHON || (fs.existsSync(localPython) ? localPython : (process.platform === 'win32' ? 'python' : 'python3'));
    args = ['-u', '-m', 'backend.worker'];
  }
  workerDiagnostics = '';
  worker = spawn(command, args, {cwd: app.isPackaged ? app.getPath('userData') : root, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'], env: {...process.env, PYTHONUNBUFFERED: '1', PYTHONDONTWRITEBYTECODE: '1'}});
  smokeTrace(`engine spawned: ${command}`);
  const processRef = worker;
  readline.createInterface({input: worker.stdout}).on('line', line => {
    let message;
    try {message = JSON.parse(line);} catch {workerDiagnostics = `Unexpected engine output: ${line.slice(0, 300)}`; return;}
    const item = pending.get(String(message.id));
    if (!item) return;
    clearTimeout(item.timer); pending.delete(String(message.id));
    if (message.ok) item.resolve(message.result); else item.reject(new Error(typeof message.error === 'string' ? message.error : JSON.stringify(message.error)));
  });
  worker.stderr.on('data', chunk => {workerDiagnostics = (workerDiagnostics + chunk.toString()).slice(-8000);});
  worker.on('error', error => {rejectPending(`Could not start the statistics engine: ${error.message}`); if (worker === processRef) worker = null;});
  worker.on('exit', code => {rejectPending(`Statistics engine stopped (${code}). ${workerDiagnostics.slice(-1500)}`); if (worker === processRef) worker = null;});
}
function engine(method, params = {}) {
  startWorker();
  const id = String(++sequence);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {pending.delete(id); reject(new Error('Analysis exceeded five minutes. Restart the app before trying a smaller dataset.')); if (worker) worker.kill();}, 300000);
    pending.set(id, {resolve, reject, timer});
    const request = JSON.stringify({id, method, params}) + '\n';
    if (Buffer.byteLength(request) > 32 * 1024 * 1024) {clearTimeout(timer); pending.delete(id); reject(new Error('Request is too large; use a dataset under 32 MB.')); return;}
    worker.stdin.write(request, error => {if (error) {clearTimeout(timer); pending.delete(id); reject(error);}});
  });
}
function assertSender(event) {
  if (!win || event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) throw new Error('Unrecognized application window');
}
function handle(channel, handler) {
  ipcMain.handle(channel, async (event, ...args) => {assertSender(event); return handler(...args);});
}
let currentProjectPath=null,recentPresets;const spreadsheetSnapshots=new Map();
function presetSource(input){const source=input?.source?.app||'standalone';if(source==='standalone')return {app:source,...(currentProjectPath?{path:currentProjectPath}:{})};const snapshot=spreadsheetSnapshots.get(source);if(!snapshot)throw new Error('Reconnect the source spreadsheet before saving its analysis.');return {app:source,workbook:snapshot.workbook,...(snapshot.path?{path:snapshot.path}:{}),sheet:input.source.sheet||snapshot.activeSheetId};}
async function openPresetSource(store,id){const preset=(await store.list()).find(item=>item.favoriteId===id);if(!preset)throw new Error('Saved analysis not found.');const source=preset.source||{app:'standalone'};if(source.app==='standalone'){if(!source.path)return {source};const stat=await fs.promises.stat(source.path);if(stat.size>64*1024*1024)throw new Error('Project exceeds64MB.');const project=validateProject(JSON.parse(await fs.promises.readFile(source.path,'utf8')));currentProjectPath=source.path;return {source,project};}if(source.path){const opened=await externalSpreadsheets.request({app:source.app,operation:'open',path:source.path});return {source:{...source,...(opened.workbook?{workbook:opened.workbook}:{}),...(opened.workbookId?{workbookId:opened.workbookId}:{})}};}return {source};}
const dataFilters = [{name: 'Data files', extensions: ['csv','tsv','tab','txt','xlsx','xls','ods','json','spjs','sqlite','sqlite3','db','db3','dta','sav','zsav','por','sas7bdat','xport','dbf','rdata','rda','rds']}, {name: 'All files', extensions: ['*']}];
handle('engine:catalog', () => engine('catalog'));
handle('engine:analyze', async params => {
  if (!params || typeof params.analysis !== 'string') throw new Error('Choose an analysis first.');
  const result = await engine('analyze', params);
  recentAnalyses = [params.analysis,...recentAnalyses.filter(id=>id!==params.analysis)].slice(0,20);
  await createMenu().catch(error=>console.error('Could not refresh analysis menus:',error));
  return result;
});
handle('preferences:load',()=>preferencesStore.load());
handle('preferences:save',value=>preferencesStore.save(value));
handle('spreadsheet:list',()=>externalSpreadsheets.list());
handle('excel-addin:take',()=>excelRequests.shift()||null);
handle('spreadsheet:request',async request=>{if(request?.operation==='open')throw new Error('Open sources through a saved analysis.');const result=await externalSpreadsheets.request(request);if(request.operation==='read')spreadsheetSnapshots.set(request.app,result);return result;});
handle('spreadsheet:source',async source=>{if(!['standalone','excel','numbers'].includes(source))throw new Error('Invalid spreadsheet source.');spreadsheetSource=source;await createMenu();return source;});
handle('favorites:source',id=>openPresetSource(favorites,id));
handle('recent:list',()=>recentPresets.list());
handle('recent:save',async value=>{const saved=await recentPresets.save({...value,source:presetSource(value)});await createMenu();return saved;});
handle('recent:source',id=>openPresetSource(recentPresets,id));
handle('favorites:list',()=>favorites.list());
handle('favorites:save',async favorite=>{const result=await favorites.save({...favorite,source:presetSource(favorite)});await createMenu();return result;});
handle('favorites:delete',async favoriteId=>{const result=await favorites.delete(favoriteId);await createMenu();return result;});
handle('file:import', async (options = {}) => {
  let selected;
  if (options.path && approvedImports.has(options.path)) selected = options.path;
  else {
    const result = await dialog.showOpenDialog(win, {title: 'Import data', properties: ['openFile'], filters: dataFilters});
    if (result.canceled) return null;
    selected = result.filePaths[0]; approvedImports.add(selected);
  }
  const data = await engine('import_file', {path: selected, ...(options.sheet ? {sheet: options.sheet} : {})});
  return {...data, importPath: selected};
});
handle('file:export', async data => {
  const selected = await dialog.showSaveDialog(win, {title: 'Export current sheet', defaultPath: `${safeName(data?.name || 'dataset')}.csv`, filters: [{name: 'CSV', extensions: ['csv']}, {name: 'Excel workbook', extensions: ['xlsx']}, {name: 'Tab-separated', extensions: ['tsv']}, {name: 'Dataset JSON', extensions: ['json']}]});
  if (selected.canceled) return null;
  await engine('export_file', {path: selected.filePath, data});
  return selected.filePath;
});
function safeName(name) {return String(name).replace(/[^a-z0-9._ -]/gi, '_').slice(0, 100);}
handle('project:export-original',async workbook=>{
  validateProject({format:'statworkbench',version:2,workbook,results:[]});
  const selected=await dialog.showSaveDialog(win,{title:'Export legacy project',defaultPath:'analysis.spjs',filters:[{name:'Legacy .spjs project',extensions:['spjs']}]});
  if(selected.canceled)return null;
  return engine('export_spjs',{path:selected.filePath,workbook});
});
handle('project:clear-source',()=>{currentProjectPath=null;return true;});
handle('project:save', async project => {
  validateProject(project);
  const selected = await dialog.showSaveDialog(win, {title: 'Save project', defaultPath: 'analysis.statworkbench.json', filters: [{name: 'StatWorkbench project', extensions: ['json']}]});
  if (selected.canceled) return null;
  const temporary = selected.filePath + '.' + randomUUID() + '.writing';
  try {
    await fs.promises.writeFile(temporary, JSON.stringify(project, null, 2), {flag:'wx'});
    await fs.promises.rename(temporary, selected.filePath);
  } catch(error) {await fs.promises.unlink(temporary).catch(()=>{});throw error;}
  currentProjectPath=selected.filePath;return selected.filePath;
});
handle('project:open', async () => {
  const selected = await dialog.showOpenDialog(win, {title: 'Open project', properties: ['openFile'], filters: [{name: 'StatWorkbench project', extensions: ['json']}]});
  if (selected.canceled) return null;
  const stat = await fs.promises.stat(selected.filePaths[0]);
  if (stat.size > 64 * 1024 * 1024) throw new Error('Project exceeds the 64 MB limit.');
  const project=validateProject(JSON.parse(await fs.promises.readFile(selected.filePaths[0], 'utf8')));currentProjectPath=selected.filePaths[0];return project;
});
handle('report:save', async html => {
  if (typeof html !== 'string' || html.length > 32 * 1024 * 1024) throw new Error('Invalid report.');
  const selected = await dialog.showSaveDialog(win, {title: 'Export analysis report', defaultPath: 'analysis-report.html', filters: [{name: 'HTML report', extensions: ['html']}]});
  if (selected.canceled) return null;
  await fs.promises.writeFile(selected.filePath, html); return selected.filePath;
});
ipcMain.on('project:dirty', (event, value) => {assertSender(event); dirty = Boolean(value);});

function menuAction(action) {if (win) win.webContents.send('menu:action', action);}
async function createMenu() {
  const names=[...require('./procedures.json'),...require('./extension-procedures.json')];
  const procedures=menuProcedures||(menuProcedures=(await engine('catalog')).map(p=>({...p,name:names.find(n=>n.id===p.id)?.name||p.name})).sort((a,b)=>names.findIndex(n=>n.id===a.id)-names.findIndex(n=>n.id===b.id)));
  let savedFavorites=[],savedRecent=[];
  try{savedRecent=(await recentPresets.list()).slice().reverse();}catch(error){console.error('Could not read recent analyses:',error.message);}
  try {savedFavorites=await favorites.list();}catch(error){console.error('Could not read analysis favorites:',error.message);}
  const command=(label,action,accelerator)=>({label,accelerator,click:()=>menuAction(action)});
  const procedureItems=category=>procedures.filter(p=>p.category===category).map(p=>command(p.name+'…','analysis:'+p.id));
  const categories=['Basic statistics','ANOVA and multivariate','Design of experiments','Regression','Nonparametric statistics','Time series','Survival analysis','Dependence models'];
  const template=[
    ...(process.platform==='darwin'?[{label:'StatWorkbench',submenu:[{role:'about'},{type:'separator'},command('Preferences…','preferences','CmdOrCtrl+,'),{type:'separator'},{role:'hide'},{role:'hideOthers'},{type:'separator'},{role:'quit'}]}]:[]),
    {label:'File',submenu:[command('New Workbook','new','CmdOrCtrl+N'),command('Open…','import','CmdOrCtrl+O'),command('Open Project…','open-project'),{type:'separator'},command('Save Project…','save','CmdOrCtrl+S'),command('Export Worksheet…','export'),command('Export Original Project…','export-original'),command('Export Analysis Report…','report'),{type:'separator'},command('Example Data…','example'),{type:'separator'},{role:process.platform==='darwin'?'close':'quit'}]},
    {label:'Edit',submenu:[command('Undo','undo','CmdOrCtrl+Z'),command('Redo','redo','CmdOrCtrl+Shift+Z'),{type:'separator'},{role:'cut'},{role:'copy'},{role:'paste'},{role:'selectAll'},{type:'separator'},command('Find…','find','CmdOrCtrl+F'),command('Format Cells…','format')]},
    {label:'Spreadsheet',submenu:[{label:'Built-in spreadsheet',type:'radio',checked:spreadsheetSource==='standalone',click:()=>menuAction('spreadsheet:standalone')},...externalSpreadsheets.list().filter(item=>item.supported).map(item=>({label:item.name,type:'radio',checked:spreadsheetSource===item.id,click:()=>menuAction('spreadsheet:'+item.id)})),{type:'separator'},command('Reconnect Spreadsheet…','spreadsheet-reconnect'),command('Workbook Preferences…','preferences')]},
    {label:'Statistics',submenu:categories.map(label=>({label,submenu:procedureItems(label)}))},
    {label:'Data',submenu:['Data','Random numbers','Sample size'].map(label=>({label,submenu:procedureItems(label)}))},
    {label:'Charts',submenu:[...procedureItems('Charts'),{type:'separator'},command('View Last Analysis Charts…','charts')]},
    {label:'Recent',submenu:[...savedRecent.map(item=>command(item.name+'…','recent:'+item.favoriteId)),...(recentAnalyses.length?[{type:'separator'}]:[]),command('Analysis History…','history')]},
    {label:'Favorites',submenu:[command('Save Analysis As…','favorite-save'),command('Organize Favorites…','favorites'),...(savedFavorites.length?[{type:'separator'}]:[]),...savedFavorites.map(favorite=>command(favorite.name,'favorite:'+favorite.favoriteId))]},
    {label:'Window',submenu:[command('Customize Quick Access Toolbar…','toolbar'),command('Analysis History…','history'),{role:'minimize'},{role:'zoom'},{role:'togglefullscreen'},...(!app.isPackaged?[{role:'toggleDevTools'}]:[])]},
    {label:'Help',submenu:[command('Analysis ToolPak Migration Guide…','migration'),command('About StatWorkbench…','about')]}
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}
async function createWindow() {
  smokeTrace('app ready; creating window');
  await fs.promises.mkdir(app.getPath('userData'),{recursive:true});
  let smokeFolder;
  if (smoke) {
    smokeFolder=smokeOutput;
    await fs.promises.mkdir(smokeFolder,{recursive:true});
    await fs.promises.writeFile(path.join(smokeFolder,'input.csv'),'Label,Value\nA,1\nB,2\nC,3\n');
    await fs.promises.writeFile(path.join(smokeFolder,'input.spjs'),JSON.stringify(require('./smoke-input.json')));
    let importIndex=0;
    dialog.showOpenDialog=async (_window,options)=>({canceled:false,filePaths:[path.join(smokeFolder,options.title==='Open project'?'smoke.statworkbench.json':importIndex++===0?'input.csv':'input.spjs')]});
    dialog.showSaveDialog=async (_window,options)=>{
      let saveName='export.csv';
      if(options.title==='Save project')saveName='smoke.statworkbench.json';
      else if(options.title==='Export analysis report')saveName='report.html';
      else if(path.extname(options.defaultPath||'').toLowerCase()==='.spjs')saveName='export.spjs';
      return {canceled:false,filePath:path.join(smokeFolder,saveName)};
    };
  }
  preferencesStore=createPreferencesStore(path.join(smoke?smokeFolder:app.getPath('userData'),'preferences.json'));
  favorites=createFavoritesStore(path.join(smoke?smokeFolder:app.getPath('userData'),'favorites.json'));
  recentPresets=createFavoritesStore(path.join(smoke?smokeFolder:app.getPath('userData'),'recent.json'),{limit:20,trim:true});
  if(process.platform==='darwin')app.dock?.setIcon(applicationIcon);
  if(process.platform==='win32')app.setAppUserModelId('org.statworkbench.desktop');
  win = new BrowserWindow({show:!smoke||process.env.STATWORKBENCH_SMOKE_VISIBLE==='1',icon:applicationIcon,width:minimumSmokeWindow?1040:1440,height:minimumSmokeWindow?700:940,minWidth:1040,minHeight:700,backgroundColor:'#e9e9e9',title:'StatWorkbench',webPreferences:{preload:path.join(__dirname,'preload.cjs'),nodeIntegration:false,contextIsolation:true,sandbox:true,backgroundThrottling:!smoke}});
  if (smoke) {
    win.webContents.on('console-message', details => console.log(`[renderer:${details.level}] ${details.message}`));
    win.webContents.on('render-process-gone', (_event, details) => console.error('[desktop-smoke] renderer stopped', details));
    win.webContents.on('did-fail-load', (_event, code, description) => console.error(`[desktop-smoke] renderer failed to load: ${code} ${description}`));
  }
  win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  win.webContents.on('will-navigate',(event,url)=>{if(url!==win.webContents.getURL())event.preventDefault();});
  win.on('close',event=>{
    if (dirty && !quitting && !smoke) {
      const choice=dialog.showMessageBoxSync(win,{type:'question',buttons:['Keep working','Discard changes'],defaultId:0,cancelId:0,title:'Unsaved work',message:'This project has unsaved changes.',detail:'Save the project before closing to retain its sheets and results.'});
      if(choice===0)event.preventDefault();
    }
  });
  smokeTrace('loading renderer');
  await win.loadFile(path.join(root,'renderer-dist','index.html'));
  smokeTrace('renderer loaded; creating menus');
  await createMenu();
  smokeTrace('menus ready');
  if (smoke) {
    try {
      smokeTrace('running renderer workflow');
      const outcome=await win.webContents.executeJavaScript('window.runDesktopSmokeTest()');
      smokeTrace('renderer workflow complete; validating files');
      const nativeMenu=Menu.getApplicationMenu();
      const expectedMenu=['File','Edit','Spreadsheet','Statistics','Data','Charts','Recent','Favorites','Window','Help'];
      const actualMenu=nativeMenu.items.map(item=>item.label).filter(label=>label!=='StatWorkbench');
      if(JSON.stringify(actualMenu)!==JSON.stringify(expectedMenu))throw new Error('Application menu order differs from the configured layout');
      const favoriteMenu=nativeMenu.items.find(item=>item.label==='Favorites')?.submenu?.items;
      if(favoriteMenu?.[0]?.label!=='Save Analysis As…'||favoriteMenu?.[1]?.label!=='Organize Favorites…')throw new Error('Native Favorites commands are missing');
      if(!recentAnalyses.includes('1001')||!recentAnalyses.includes('3100'))throw new Error('Native Recent menu did not retain successful analyses');
      outcome.nativeMenus=true;
      outcome.nativeMenuOrder=actualMenu;
      outcome.windowSize=win.getSize();
      outcome.minimumWindow=minimumSmokeWindow;
      const folder=smokeFolder;
      const saved=JSON.parse(await fs.promises.readFile(path.join(folder,'smoke.statworkbench.json'),'utf8'));
      if(saved.version!==2 || saved.results.length!==1 || saved.workbook.sheetOrder.length<3)throw new Error('Project round trip lost worksheets or analyses');
      if(!(await fs.promises.readFile(path.join(folder,'export.csv'),'utf8')).includes('Original cell,42'))throw new Error('CSV export did not preserve the imported .spjs values');
      if(!(await fs.promises.readFile(path.join(folder,'report.html'),'utf8')).includes('Descriptive'))throw new Error('Report did not retain analysis output');
      const originalExport=await engine('import_file',{path:path.join(folder,'export.spjs')});
      if(!originalExport.workbook||originalExport.workbook.sheetOrder.length!==saved.workbook.sheetOrder.length)throw new Error('Original-format export lost worksheets');
      await fs.promises.writeFile(path.join(folder,'desktop-smoke.json'),JSON.stringify(outcome,null,2));
      await fs.promises.writeFile(path.join(folder,'desktop.png'),(await win.webContents.capturePage()).toPNG());
      console.log(JSON.stringify(outcome));
      // Exercise the same window/worker shutdown lifecycle as a normal Quit.
      quitting=true;dirty=false;smokeTrace('requesting normal application quit');app.quit();
    } catch(error) {console.error(error);quitting=true;if(worker)worker.kill();app.exit(1);}
  }
}
if(ownsInstance)app.whenReady().then(async()=>{if(excelAddinEnabled)await enqueueExcelRequest(process.argv);await createWindow();}).catch(error=>{console.error('Application startup failed:',error);quitting=true;if(worker)worker.kill();app.exit(1);});
app.on('window-all-closed',()=>{quitting=true;app.quit();});
app.on('before-quit',()=>smokeTrace('before-quit'));
app.on('will-quit',()=>{smokeTrace('will-quit');if(worker){worker.kill();worker=null;}});
app.on('quit',(_event,code)=>smokeTrace(`quit event: ${code}`));
app.on('activate',()=>{if(BrowserWindow.getAllWindows().length===0)createWindow();});
