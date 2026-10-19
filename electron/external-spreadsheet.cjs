// OS spreadsheet adapters use fixed scripts and a JSON data file, never eval or shell interpolation.
const {execFile}=require('node:child_process');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const APPS={excel:{name:'Microsoft Excel',mac:'com.microsoft.Excel'},numbers:{name:'Apple Numbers',mac:'com.apple.iWork.Numbers'}};
const OPERATIONS=new Set(['read','selection','activate','write','open']);
function reportChart(input){
 if(!input||!['line','spline','step','scatter','bar','histogram','box'].includes(input.type)||!Array.isArray(input.series)||!input.series.length||input.series.length>100)throw new Error('Invalid editable report chart.');
 // This is data for the independent XLSX serializer, never executable code or a file path.
 for(const series of input.series){
  if(!series||!Array.isArray(series.y)||series.y.length>100000||series.y.some(v=>v!==null&&(typeof v!=='number'||!Number.isFinite(v))))throw new Error('Invalid chart values.');
  if(series.x!==undefined&&(!Array.isArray(series.x)||series.x.length!==series.y.length||series.x.some(v=>v!==null&&!(typeof v==='number'&&Number.isFinite(v))&&!(typeof v==='string'&&v.length<=10000))))throw new Error('Invalid chart coordinates.');
 }
 const copy=JSON.parse(JSON.stringify(input));
 if(Buffer.byteLength(JSON.stringify(copy))>4*1024*1024)throw new Error('Editable chart exceeds four MiB.');
 return copy;
}
function rectangle(address){
 if(typeof address!=='string')throw new Error('Invalid spreadsheet range.');
 const m=address.match(/^([A-Z]{1,3})([1-9][0-9]{0,5})(?::([A-Z]{1,3})([1-9][0-9]{0,5}))?$/);
 if(!m)throw new Error('Invalid spreadsheet range.');
 const col=s=>[...s].reduce((v,c)=>v*26+c.charCodeAt(0)-64,0);
 const left=col(m[1]),right=col(m[3]||m[1]),top=Number(m[2]),bottom=Number(m[4]||m[2]);
 if(left>right||top>bottom||right>1000||bottom>100000||(right-left+1)*(bottom-top+1)>2000000)throw new Error('Spreadsheet range exceeds the supported limits.');
 return {left,right,top,bottom};
}
function validateRequest(input){
 if(!input||!APPS[input.app]||!OPERATIONS.has(input.operation))throw new Error('Choose a supported spreadsheet and operation.');
 const value={app:input.app,operation:input.operation};
 if(input.inspectCharts!==undefined){if(input.operation!=='read'||typeof input.inspectCharts!=='boolean')throw new Error('Chart inspection requires a spreadsheet read.');value.inspectCharts=input.inspectCharts;}
 if(input.expectedWorkbookPath!==undefined){if(input.app!=='excel'||typeof input.expectedWorkbookPath!=='string'||input.expectedWorkbookPath.length>4096||input.expectedWorkbookPath.includes('\0')||!/^(?:\/|[A-Za-z]:[\\/]|\\\\)/.test(input.expectedWorkbookPath))throw new Error('Invalid expected workbook path.');value.expectedWorkbookPath=input.expectedWorkbookPath;}
 if(input.workbookId!==undefined){if(input.app!=='numbers'||typeof input.workbookId!=='string'||!input.workbookId||input.workbookId.length>1000)throw new Error('Invalid Numbers document identity.');value.workbookId=input.workbookId;}
 if(input.excelProcessId!==undefined){if(input.app!=='excel'||!Number.isSafeInteger(input.excelProcessId)||input.excelProcessId<=0||input.excelProcessId>0xffffffff)throw new Error('Invalid Excel process reference.');value.excelProcessId=input.excelProcessId;}
 for(const key of ['workbook','sheet','name'])if(input[key]!==undefined){if(typeof input[key]!=='string'||input[key].length>1000)throw new Error('Invalid spreadsheet reference.');value[key]=input[key];}
 if(input.range!==undefined){if(input.operation!=='activate')throw new Error('A selected range is only supported when activating a spreadsheet.');rectangle(input.range);value.range=input.range;}
 if(input.operation==='open'){if(typeof input.path!=='string'||!path.isAbsolute(input.path)||input.path.length>4096||input.path.includes('\0'))throw new Error('Invalid workbook path.');value.path=input.path;}
 if(input.operation==='write'){
  if(!Array.isArray(input.matrix)||!input.matrix.length||input.matrix.length>100000)throw new Error('Invalid result worksheet.');
  const width=Math.max(...input.matrix.map(row=>Array.isArray(row)?row.length:1001));
  if(width<1||width>1000||width*input.matrix.length>2000000)throw new Error('Result exceeds worksheet limits.');
  value.matrix=input.matrix.map(row=>Array.from({length:width},(_,c)=>{const v=row[c]??null;if(!['string','number','boolean'].includes(typeof v)&&v!==null)throw new Error('Invalid result cell.');if(typeof v==='number'&&!Number.isFinite(v)||typeof v==='string'&&v.length>100000)throw new Error('Invalid result cell.');return v;}));
  value.outputMode=input.outputMode==='workbook'?'workbook':'worksheet';
  value.numberFormat=typeof input.numberFormat==='string'&&/^0(?:\.[0#]{1,15})?(?:%|E\+00)?$/.test(input.numberFormat)?input.numberFormat:'0.00000';
  value.formats=[];
  if(input.formats!==undefined){if(!Array.isArray(input.formats)||input.formats.length>100000)throw new Error('Too many report formats.');value.formats=input.formats.map(item=>{if(!item||typeof item.numberFormat!=='string'||item.numberFormat.length>100||/[\x00-\x1f]/.test(item.numberFormat))throw new Error('Invalid report number format.');const area=rectangle(item.range);if(area.right>width||area.bottom>value.matrix.length)throw new Error('Report formats must stay inside the result worksheet data.');return {range:item.range,numberFormat:item.numberFormat};});}
  value.font=typeof input.font==='string'&&input.font.length<=100?input.font:'Arial';
  value.fontSize=Number.isFinite(input.fontSize)&&input.fontSize>=6&&input.fontSize<=72?input.fontSize:11;
  if(input.chartImages!==undefined){
   if(!Array.isArray(input.chartImages)||input.chartImages.length>30)throw new Error('Too many charts for one report.');
   value.chartImages=input.chartImages.map(item=>{if(!item||typeof item.png!=='string'||item.png.length>8*1024*1024||!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(item.png))throw new Error('Invalid report chart.');return {png:item.png,title:String(item.title||'Chart').slice(0,200),...(item.chart?{chart:reportChart(item.chart)}:{})};});
  }
 }
 if(Buffer.byteLength(JSON.stringify(value))>32*1024*1024)throw new Error('Spreadsheet transfer exceeds32MB.');
 return value;
}
function validateReadResult(value){
 if(!value||typeof value.workbook!=='string'||!Array.isArray(value.sheets)||value.sheets.length>1000)throw new Error('The spreadsheet returned an invalid workbook.');
 if(value.sheets.some(sheet=>!sheet||typeof sheet.id!=='string'||typeof sheet.name!=='string'||sheet.id.length>2000||sheet.name.length>2000))throw new Error('The spreadsheet returned an invalid sheet reference.');
 if(value.workbookId!==undefined&&(typeof value.workbookId!=='string'||!value.workbookId||value.workbookId.length>1000))throw new Error('The spreadsheet returned an invalid document identity.');
 if(value.excelProcessId!==undefined&&(!Number.isSafeInteger(value.excelProcessId)||value.excelProcessId<=0||value.excelProcessId>0xffffffff))throw new Error('The spreadsheet returned an invalid Excel process reference.');
 if(value.matrix){if(!Array.isArray(value.matrix)||value.matrix.length>100000)throw new Error('The spreadsheet exceeds100,000 rows.');let cells=0;for(const row of value.matrix){if(!Array.isArray(row)||row.length>1000)throw new Error('The spreadsheet exceeds1,000 columns.');cells+=row.length;if(cells>2000000)throw new Error('The spreadsheet exceeds two million cells.');for(const cell of row)if(cell!==null&&(!['string','number','boolean'].includes(typeof cell)||typeof cell==='number'&&!Number.isFinite(cell)))throw new Error('Unsupported spreadsheet cell.');}}
 return value;
}
function createExternalSpreadsheetBridge({platform=process.platform,execute=execFile,tempDirectory=os.tmpdir(),scriptDirectory=__dirname,windowsExecutable=path.join(__dirname,'..','dist-windows','StatWorkbench.SpreadsheetBridge.exe'),createReportWorkbook}={}){
 return {
  list(){return Object.entries(APPS).map(([id,app])=>({id,name:app.name,supported:platform==='darwin'||(platform==='win32'&&id==='excel')}));},
  async request(input){
   const value=validateRequest(input);
   if(platform!=='darwin'&&!(platform==='win32'&&value.app==='excel'))throw new Error(`${APPS[value.app].name} live integration is unavailable on this platform. Open an exported XLSX or CSV workbook instead.`);
   const folder=await fs.mkdtemp(path.join(tempDirectory,'statworkbench-spreadsheet-'));
   try{
    let reportInfo;
    if((value.app==='excel'||value.app==='numbers'&&value.outputMode==='workbook')&&value.operation==='write'&&value.chartImages?.some(item=>item.chart)&&createReportWorkbook){
     const reportPath=path.join(folder,path.basename(folder)+'.xlsx');reportInfo=await createReportWorkbook(reportPath,value);
     if(!reportInfo||!Number.isInteger(reportInfo.nativeCharts)||!Number.isInteger(reportInfo.imageCharts)||reportInfo.nativeCharts<0||reportInfo.imageCharts<0||reportInfo.nativeCharts+reportInfo.imageCharts!==value.chartImages.length)throw new Error('The generated chart report is incomplete.');
     const generated=await fs.stat(reportPath);if(!generated.isFile()||generated.size>64*1024*1024)throw new Error('Invalid generated spreadsheet report.');
     value.reportPath=reportPath;value.reportNativeCharts=reportInfo.nativeCharts;value.reportImageCharts=reportInfo.imageCharts;
     delete value.chartImages;
    }
    if(value.chartImages){value.images=[];for(const [index,image]of value.chartImages.entries()){const bytes=Buffer.from(image.png.split(',')[1],'base64');if(!bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])))throw new Error('Invalid PNG chart.');const filename=path.join(folder,`chart-${index}.png`);await fs.writeFile(filename,bytes,{mode:0o600});value.images.push({path:filename,title:image.title});}delete value.chartImages;}
    const payload=path.join(folder,'request.json');await fs.writeFile(payload,JSON.stringify(value),{mode:0o600});
    // macOS needs a real script path outside ASAR. Windows uses a compiled adapter, independent of PowerShell policy.
    let command=windowsExecutable,args=[payload];
    if(platform==='darwin'){const script=path.join(folder,'spreadsheet-macos.js');await fs.writeFile(script,await fs.readFile(path.join(scriptDirectory,'spreadsheet-macos.js')),{mode:0o600});command='/usr/bin/osascript';args=['-l','JavaScript',script,payload];}
    const invoke=(command,args)=>new Promise((resolve,reject)=>{let settled=false,child;const finish=(error,stdout,stderr)=>{if(settled)return;settled=true;clearTimeout(timer);if(error){const detail=String(stderr||error.message);reject(new Error(/1743|not authorized|not permitted/i.test(detail)?'Spreadsheet access was denied. Allow StatWorkbench to control the selected spreadsheet app in System Settings → Privacy & Security → Automation, then reconnect.':`Spreadsheet connection failed: ${detail.slice(-1500)}`));}else resolve(stdout);};const timer=setTimeout(()=>{child?.kill?.('SIGKILL');finish(new Error('The operating system did not complete the spreadsheet request within120 seconds. Check for a permission dialog, then reconnect.'));},120000);timer.unref?.();try{child=execute(command,args,{timeout:120000,killSignal:'SIGKILL',maxBuffer:32*1024*1024,windowsHide:true},finish);}catch(error){finish(error);}});
    const response=JSON.parse(String(await invoke(command,args)).trim());if(response.error)throw new Error(response.error);
    if(reportInfo?.warnings?.length)response.warnings=[...(response.warnings||[]),...reportInfo.warnings];
    if(platform==='darwin'&&value.app==='excel'&&value.operation==='write'&&value.images?.length){const imageScript=path.join(folder,'spreadsheet-macos-images.js');await fs.writeFile(imageScript,await fs.readFile(path.join(scriptDirectory,'spreadsheet-macos-images.js')),{mode:0o600});response.chartImagesWritten=0;for(const [index,image]of value.images.entries()){try{const inserted=JSON.parse(String(await invoke('/usr/bin/osascript',['-l','JavaScript',imageScript,response.workbook,response.sheet,image.path,String((value.matrix.length+2)*18+index*440)])).trim());if(inserted.inserted!==true)throw new Error('Excel did not confirm the inserted image.');response.chartImagesWritten++;}catch(error){throw new Error(`Report values were written to ${response.workbook} / ${response.sheet}, but chart insertion failed: ${error.message}`);}}}
    return ['read','selection'].includes(value.operation)?validateReadResult(response):response;
   }finally{await fs.rm(folder,{recursive:true,force:true});}
  }
 };
}
module.exports={createExternalSpreadsheetBridge,validateRequest,validateReadResult};
