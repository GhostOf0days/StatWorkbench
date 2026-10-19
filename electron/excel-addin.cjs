// The Excel COM add-in hands off only a request ID. Paths and executable code are never accepted.
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const IDS=new Set([...require('./procedures.json'),...require('./extension-procedures.json')].map(p=>p.id));
const MAX_BYTES=16*1024, MAX_AGE=10*60*1000;
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function requestDirectory(){return path.join(process.env.LOCALAPPDATA||path.join(os.homedir(),'AppData','Local'),'StatWorkbench','ExcelAddin','Requests');}
function rangeBounds(range){
 const columns=/^([A-Z]{1,3}):([A-Z]{1,3})$/.exec(range);
 if(columns)return rangeBounds(columns[1]+'1:'+columns[2]+'1048576');
 const match=/^([A-Z]{1,3})([1-9]\d{0,6})(?::([A-Z]{1,3})([1-9]\d{0,6}))?$/.exec(range);
 if(!match)throw new Error('Select one rectangular cell range in Excel.');
 const col=s=>[...s].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0);
 const startColumn=col(match[1])-1,endColumn=col(match[3]||match[1])-1,startRow=Number(match[2])-1,endRow=Number(match[4]||match[2])-1;
 if(endRow<startRow||endColumn<startColumn||endColumn>=16384||endRow>=1048576)throw new Error('Excel selection is outside worksheet bounds.');
 return {startRow,endRow,startColumn,endColumn};
}
function validateLaunchRequest(value,{now=Date.now(),requestId}={}){
 if(!value||value.version!==1||!UUID.test(value.requestId)||requestId&&value.requestId!==requestId)throw new Error('Invalid Excel add-in request.');
 if(!Number.isSafeInteger(value.createdAt)||value.createdAt>now+30000||now-value.createdAt>MAX_AGE)throw new Error('Excel command expired. Click its ribbon button again.');
 if(!['open','preferences'].includes(value.command)&&!(typeof value.command==='string'&&value.command.startsWith('analysis:')&&IDS.has(value.command.slice(9))))throw new Error('Unknown Excel ribbon command.');
 if(!Number.isSafeInteger(value.excelProcessId)||value.excelProcessId<=0||value.excelProcessId>0xffffffff)throw new Error('Invalid Excel process reference.');
 for(const key of ['workbook','sheet'])if(typeof value[key]!=='string'||!value[key].length||value[key].length>1000||/[\x00-\x1f]/.test(value[key]))throw new Error('Invalid Excel workbook or sheet.');
 if(typeof value.rangeA1!=='string')throw new Error('Invalid Excel selection.');
 const bounds=rangeBounds(value.rangeA1);
 return {version:1,requestId:value.requestId,createdAt:value.createdAt,command:value.command,excelProcessId:value.excelProcessId,workbook:value.workbook,sheet:value.sheet,rangeA1:value.rangeA1,...bounds};
}
async function readLaunchRequest(argv,{directory=requestDirectory(),now=Date.now()}={}){
 const args=argv.filter(arg=>typeof arg==='string'&&arg.startsWith('--excel-addin='));
 if(!args.length)return null;
 if(args.length!==1)throw new Error('Only one Excel command can be opened at a time.');
 const id=args[0].slice('--excel-addin='.length);
 if(!UUID.test(id))throw new Error('Invalid Excel request ID.');
 const filename=path.join(directory,id+'.json');
 const info=await fs.lstat(filename);
 if(!info.isFile()||info.isSymbolicLink()||info.size>MAX_BYTES)throw new Error('Invalid Excel request file.');
 if(path.dirname(await fs.realpath(filename))!==await fs.realpath(directory))throw new Error('Excel request resolves outside its inbox.');
 const handle=await fs.open(filename,'r');
 let value;
 try{const opened=await handle.stat();if(!opened.isFile()||opened.size>MAX_BYTES||opened.ino!==info.ino||opened.dev!==info.dev)throw new Error('Excel request file changed while opening.');const bytes=Buffer.alloc(MAX_BYTES+1);const {bytesRead}=await handle.read(bytes,0,bytes.length,0);if(bytesRead>MAX_BYTES)throw new Error('Excel request is too large.');value=validateLaunchRequest(JSON.parse(bytes.subarray(0,bytesRead).toString('utf8')),{now,requestId:id});}finally{await handle.close();}
 await fs.unlink(filename);
 return value;
}
module.exports={readLaunchRequest,validateLaunchRequest,rangeBounds,requestDirectory};
