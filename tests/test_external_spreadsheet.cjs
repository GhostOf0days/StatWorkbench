const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const vm=require('node:vm');
const {createExternalSpreadsheetBridge,validateRequest,validateReadResult}=require('../electron/external-spreadsheet.cjs');
test('spreadsheet bridge accepts only bounded typed data and fixed applications',()=>{
 assert.throws(()=>validateRequest({app:'Finder',operation:'activate'}));
 assert.throws(()=>validateRequest({app:'excel',operation:'eval'}));
 assert.throws(()=>validateRequest({app:'excel',operation:'write',matrix:[[Infinity]]}));
 assert.throws(()=>validateRequest({app:'excel',operation:'write',matrix:[Array(1001).fill(1)]}));
 assert.deepEqual(validateRequest({app:'numbers',operation:'write',matrix:[[false,0,null,'=1+1']],name:'Result'}).matrix,[[false,0,null,'=1+1']]);
 assert.throws(()=>validateReadResult({workbook:'Book',sheets:[],matrix:[[{}]]}));
});
test('native bridge passes data via private JSON, copies packaged script and cleans transfer files',async()=>{
 let payloadPath;
 const execute=async(command,args,options,callback)=>{try{
  assert.equal(command,'/usr/bin/osascript');assert.deepEqual(args.slice(0,2),['-l','JavaScript']);assert.equal(options.timeout,120000);
  payloadPath=args[3];const request=JSON.parse(await fs.readFile(payloadPath,'utf8'));assert.equal(request.workbook,'quoted " workbook; $(example)');
  assert.match(await fs.readFile(args[2],'utf8'),/function run\(args\)/);
  callback(null,JSON.stringify({workbook:request.workbook,sheets:[{id:'Data',name:'Data'}],activeSheetId:'Data',matrix:[[1,2],[3,4]]}),'');
 }catch(e){callback(e,'','');}};
 const bridge=createExternalSpreadsheetBridge({platform:'darwin',execute});const result=await bridge.request({app:'excel',operation:'read',workbook:'quoted " workbook; $(example)'});assert.equal(result.matrix[1][1],4);
 await assert.rejects(fs.stat(path.dirname(payloadPath)),{code:'ENOENT'});
});
test('unsupported platforms offer file import and permission denials are actionable',async()=>{
 await assert.rejects(createExternalSpreadsheetBridge({platform:'linux'}).request({app:'excel',operation:'read'}),/XLSX or CSV/);
 const bridge=createExternalSpreadsheetBridge({platform:'darwin',execute:(_command,_args,_options,done)=>done(new Error('Denied'),'','Not authorized to send Apple events. -1743')});
 await assert.rejects(bridge.request({app:'numbers',operation:'read'}),/Privacy & Security.*Automation/);
});
test('Windows spreadsheet runtime invokes the compiled adapter directly without a script interpreter',async()=>{
 let requestFile;const executable=path.join(path.sep,'packaged resources','spreadsheet-bridge','StatWorkbench.SpreadsheetBridge.exe');
 const execute=async(command,args,options,callback)=>{try{assert.equal(command,executable);assert.equal(args.length,1);requestFile=args[0];const p=JSON.parse(await fs.readFile(requestFile,'utf8'));assert.equal(p.excelProcessId,321);assert.equal(p.operation,'read');assert.equal(options.windowsHide,true);callback(null,JSON.stringify({workbook:'Book',sheets:[{id:'Data',name:'Data'}],matrix:[[1]]}),'');}catch(e){callback(e,'','');}};
 const bridge=createExternalSpreadsheetBridge({platform:'win32',windowsExecutable:executable,execute});assert.equal((await bridge.request({app:'excel',operation:'read',excelProcessId:321})).matrix[0][0],1);await assert.rejects(fs.stat(requestFile),{code:'ENOENT'});
});
test('report format ranges cannot affect cells beyond the returned report',()=>{
 for(const range of ['A0','B2:A1','A1:ZZZ1','A1:A100001','A1:C1','A3'])assert.throws(()=>validateRequest({app:'excel',operation:'write',matrix:[[1,2],[3,4]],formats:[{range,numberFormat:'0.00%'}]}));
 assert.deepEqual(validateRequest({app:'excel',operation:'write',matrix:[[1,2],[3,4]],formats:[{range:'B2',numberFormat:'0.0000'}]}).formats,[{range:'B2',numberFormat:'0.0000'}]);
});
test('spreadsheet activation accepts a bounded rectangular selection only',()=>{
 const request=validateRequest({app:'excel',operation:'activate',workbook:'Fixture',sheet:'Data',range:'A2:C3'});assert.equal(request.range,'A2:C3');
 for(const range of ['=1+1','A1;delete','C3:A2','A1:ZZZ2'])assert.throws(()=>validateRequest({app:'numbers',operation:'activate',range}));
 assert.throws(()=>validateRequest({app:'excel',operation:'read',range:'A1'}));
});
test('Windows forwards bounded range activation to its compiled adapter',async()=>{
 let captured;
 const execute=async(_command,args,_options,done)=>{try{captured=JSON.parse(await fs.readFile(args[0],'utf8'));done(null,'{"activated":true,"workbook":"Fixture","sheet":"Data"}','');}catch(error){done(error,'','');}};
 const bridge=createExternalSpreadsheetBridge({platform:'win32',execute});
 assert.equal((await bridge.request({app:'excel',operation:'activate',workbook:'Fixture',sheet:'Data',range:'A2:C3'})).activated,true);
 assert.equal(captured.range,'A2:C3');assert.equal(captured.workbook,'Fixture');assert.equal(captured.sheet,'Data');
});
test('read boundary rejects invalid sheet identities and nonfinite cells',()=>{
 assert.throws(()=>validateReadResult({workbook:'Book',sheets:[{id:1,name:'Bad'}]}));
 assert.throws(()=>validateReadResult({workbook:'Book',sheets:[],matrix:[[Infinity]]}));
 assert.throws(()=>validateReadResult({workbook:'Book',sheets:[],matrix:[[NaN]]}));
});
test('Numbers stable document identity survives renames and is rejected for other adapters',()=>{
 assert.equal(validateRequest({app:'numbers',operation:'read',workbook:'old name',workbookId:'stable-id'}).workbookId,'stable-id');
 for(const workbookId of ['',42,'x'.repeat(1001)])assert.throws(()=>validateRequest({app:'numbers',operation:'read',workbookId}));
 assert.throws(()=>validateRequest({app:'excel',operation:'read',workbookId:'id'}));
 assert.equal(validateReadResult({workbook:'new name',workbookId:'stable-id',sheets:[]}).workbookId,'stable-id');
 assert.throws(()=>validateReadResult({workbook:'Book',workbookId:12,sheets:[]}));
});
test('Excel image adapter passes variable data as arguments and cleans files after success',async()=>{
 let transferFolder,calls=0;
 const png='data:image/png;base64,'+(await fs.readFile(path.join(__dirname,'..','assets','statworkbench.png'))).toString('base64');
 const workbook='quoted " workbook; $(no execution)',sheet="Results ' test";
 const execute=async(command,args,options,done)=>{try{
  calls++;assert.equal(command,'/usr/bin/osascript');assert.deepEqual(args.slice(0,2),['-l','JavaScript']);assert.equal(options.timeout,120000);
  transferFolder=path.dirname(args[2]);
  if(calls===1){const payload=JSON.parse(await fs.readFile(args[3],'utf8'));assert.equal(payload.images.length,1);assert.equal(payload.chartImages,undefined);done(null,JSON.stringify({workbook,sheet}),'');}
  else{assert.equal(path.basename(args[2]),'spreadsheet-macos-images.js');assert.deepEqual(args.slice(3,5),[workbook,sheet]);assert.equal(args[6],'54');assert.equal((await fs.readFile(args[5])).subarray(1,4).toString(),'PNG');assert.match(await fs.readFile(args[2],'utf8'),/pasteWorksheet/);done(null,'{"inserted":true}','');}
 }catch(error){done(error,'','');}};
 const response=await createExternalSpreadsheetBridge({platform:'darwin',execute}).request({app:'excel',operation:'write',matrix:[[1]],chartImages:[{png}]});
 assert.equal(calls,2);assert.equal(response.chartImagesWritten,1);await assert.rejects(fs.stat(transferFolder),{code:'ENOENT'});
});
test('Excel reports partial transfer when native chart insertion fails and still removes private files',async()=>{
 let transferFolder,calls=0;
 const png='data:image/png;base64,'+(await fs.readFile(path.join(__dirname,'..','assets','statworkbench.png'))).toString('base64');
 const execute=(_command,args,_options,done)=>{transferFolder=path.dirname(args[2]);calls++;if(calls===1)done(null,'{"workbook":"Fixture","sheet":"Report"}','');else done(new Error('Paste failed'),'','Native paste error');};
 await assert.rejects(createExternalSpreadsheetBridge({platform:'darwin',execute}).request({app:'excel',operation:'write',matrix:[[1]],chartImages:[{png}]}),/values were written to Fixture \/ Report, but chart insertion failed/);
 await assert.rejects(fs.stat(transferFolder),{code:'ENOENT'});
});
test('editable charts use a host-owned XLSX path, retain warnings and clean the transfer',async()=>{
 const png='data:image/png;base64,'+(await fs.readFile(path.join(__dirname,'..','assets','statworkbench.png'))).toString('base64');
 const chart={type:'scatter',series:[{x:[1,2],y:[2,4]}]};let temporary,compiled=0;
 const createReportWorkbook=async(file,report)=>{temporary=file;assert.deepEqual(report.chartImages[0].chart,chart);await fs.writeFile(file,'test workbook');compiled++;return {nativeCharts:1,imageCharts:0,warnings:['Explicit format limitation']};};
 const execute=async(_command,args,_options,done)=>{try{const p=JSON.parse(await fs.readFile(args[3],'utf8'));assert.equal(p.reportPath,temporary);assert.notEqual(p.reportPath,'/untrusted/file.xlsx');assert.equal(p.reportNativeCharts,1);assert.equal(p.images,undefined);assert.equal(p.chartImages,undefined);done(null,'{"workbook":"Fixture","sheet":"Report","nativeChartsWritten":1}','');}catch(error){done(error,'','');}};
 const result=await createExternalSpreadsheetBridge({platform:'darwin',execute,createReportWorkbook}).request({app:'excel',operation:'write',matrix:[[1]],reportPath:'/untrusted/file.xlsx',chartImages:[{png,chart}]});
 assert.equal(compiled,1);assert.equal(result.nativeChartsWritten,1);assert.deepEqual(result.warnings,['Explicit format limitation']);await assert.rejects(fs.stat(temporary),{code:'ENOENT'});
 for(const bad of [{...chart,series:[{y:[Infinity]}]},{...chart,series:[{x:[1],y:[1,2]}]},{type:'execute',series:[{y:[1]}]}])assert.throws(()=>validateRequest({app:'excel',operation:'write',matrix:[[1]],chartImages:[{png,chart:bad}]}));
});
test('failed editable chart generation never invokes Excel and removes its partial file',async()=>{
 const png='data:image/png;base64,'+(await fs.readFile(path.join(__dirname,'..','assets','statworkbench.png'))).toString('base64');let temporary,invoked=false;
 const bridge=createExternalSpreadsheetBridge({platform:'darwin',execute:()=>{invoked=true;},createReportWorkbook:async file=>{temporary=file;await fs.writeFile(file,'partial');throw Error('Invalid chart geometry');}});
 await assert.rejects(bridge.request({app:'excel',operation:'write',matrix:[[1]],chartImages:[{png,chart:{type:'line',series:[{y:[1,2]}]}}]}),/Invalid chart geometry/);
 assert.equal(invoked,false);await assert.rejects(fs.stat(temporary),{code:'ENOENT'});
});
test('Numbers uses editable report import only for explicitly requested new workbooks',async()=>{
 const png='data:image/png;base64,'+(await fs.readFile(path.join(__dirname,'..','assets','statworkbench.png'))).toString('base64');
 const chart={type:'scatter',series:[{x:[1,2],y:[2,4]}]};let compiled=0;const requests=[];
 const createReportWorkbook=async(file)=>{compiled++;await fs.writeFile(file,'test workbook');return {nativeCharts:1,imageCharts:0};};
 const execute=async(_command,args,_options,done)=>{try{const request=JSON.parse(await fs.readFile(args[3],'utf8'));requests.push(request);done(null,JSON.stringify({workbook:'Result',workbookId:'test-id',sheet:'Report',nativeChartsWritten:request.reportPath?1:0,chartImagesWritten:request.images?.length||0}),'');}catch(error){done(error,'','');}};
 const bridge=createExternalSpreadsheetBridge({platform:'darwin',execute,createReportWorkbook});
 await bridge.request({app:'numbers',operation:'write',outputMode:'workbook',matrix:[[1]],chartImages:[{png,chart}]});
 await bridge.request({app:'numbers',operation:'write',outputMode:'worksheet',workbookId:'existing-id',matrix:[[1]],chartImages:[{png,chart}]});
 assert.equal(compiled,1);assert.equal(requests[0].reportNativeCharts,1);assert.equal(requests[0].images,undefined);
 assert.equal(requests[1].reportPath,undefined);assert.equal(requests[1].workbookId,'existing-id');assert.equal(requests[1].images.length,1);
 for(const request of requests)await assert.rejects(fs.stat(request.reportPath||request.images[0].path),{code:'ENOENT'});
 assert.equal(validateRequest({app:'numbers',operation:'read',inspectCharts:true}).inspectCharts,true);
 assert.throws(()=>validateRequest({app:'numbers',operation:'write',matrix:[[1]],inspectCharts:true}),/spreadsheet read/);
});
test('opening a Numbers favorite returns the resolved runtime identity without persisting it',async()=>{
 const execute=async(_command,args,_options,done)=>{try{const payload=JSON.parse(await fs.readFile(args[3],'utf8'));assert.equal(payload.operation,'open');assert.equal(payload.path,'/tmp/synthetic folder/Fixture.numbers');assert.equal(payload.workbookId,undefined);done(null,'{"opened":true,"workbook":"Fixture","workbookId":"runtime-document-id"}','');}catch(error){done(error,'','');}};
 const result=await createExternalSpreadsheetBridge({platform:'darwin',execute}).request({app:'numbers',operation:'open',path:'/tmp/synthetic folder/Fixture.numbers'});
 assert.equal(result.workbookId,'runtime-document-id');assert.equal(result.workbook,'Fixture');
});
async function macScript(application){
 const $=text=>({stringByStandardizingPath:{stringByResolvingSymlinksInPath:path.posix.normalize(text)}});
 $.NSURL={URLWithString:value=>({path:new URL(value.stringByStandardizingPath.stringByResolvingSymlinksInPath).pathname})};
 const context=vm.createContext({Application:()=>application,Path:value=>value,ObjC:{import(){},unwrap:value=>value},$});
 vm.runInContext(await fs.readFile(path.join(__dirname,'..','electron','spreadsheet-macos.js'),'utf8'),context);return context;
}
test('Mac Excel rejects same-name replacement paths before any existing-workbook operation',async()=>{
 let creations=0;const wb={fullName:()=>'/other/Fixture.xlsx'};
 const workbooks=()=>[wb];workbooks.byName=()=>wb;
 const app={running:()=>true,workbooks,make(){creations++;throw Error('new-workbook-reached');}};
 const script=await macScript(app);
 for(const operation of ['read','activate','write'])assert.throws(()=>script.excel({operation,workbook:'Fixture.xlsx',expectedWorkbookPath:'/original/Fixture.xlsx',outputMode:'worksheet'}),/Reconnected?|Reconnect/);
 assert.equal(creations,0);
 assert.throws(()=>script.excel({operation:'write',workbook:'Fixture.xlsx',expectedWorkbookPath:'/original/Fixture.xlsx',outputMode:'workbook'}),/new-workbook-reached/);assert.equal(creations,1);
});
test('Numbers favorite opening distinguishes same-name documents by exact file path',async()=>{
 const doc=(file,id)=>({name:()=> 'Fixture',id:()=>id,file:()=>({toString:()=>file})});let opened;
 const app={open:value=>{opened=value;},documents:()=>[doc('/other/Fixture.numbers','wrong-id'),doc('/chosen/Fixture.numbers','right-id')]};
 const script=await macScript(app);
 const response=script.numbers({operation:'open',path:'/chosen/Fixture.numbers'});
 assert.equal(opened,'/chosen/Fixture.numbers');assert.equal(response.workbookId,'right-id');
 assert.throws(()=>script.numbers({operation:'open',path:'/missing/Fixture.numbers'}),/exact file identity/);
});
test('Mac chart paste preserves every clipboard item/type on success and failure and respects a newer copy',async()=>{
 const source=await fs.readFile(path.join(__dirname,'..','electron','spreadsheet-macos-images.js'),'utf8');
 for(const mode of ['success','failure','new-copy']){
  const collection=items=>({count:items.length,objectAtIndex:index=>items[index]});
  const item=data=>({data, get types(){return collection(Object.keys(this.data));},dataForType(type){return this.data[type];},setDataForType(bytes,type){this.data[type]=bytes;return true;}});
  const original=[{'public.utf8-plain-text':'private text','public.rtf':'private rich text'},{'public.png':'private image'}];
  const board={contents:original.map(data=>item({...data})),changeCount:1,get pasteboardItems(){return collection(this.contents);},get clearContents(){this.contents=[];this.changeCount++;return this.changeCount;},writeObjects(items){this.contents=items;this.changeCount++;return true;}};
  const $=value=>value;$.NSData={dataWithContentsOfFile:()=>Buffer.from('PNG')};$.NSImage={alloc:{initWithData:()=>({TIFFRepresentation:Buffer.from('TIFF')})}};$.NSPasteboard={generalPasteboard:board};$.NSPasteboardItem={alloc:{get init(){return item({});}}};
  const shapes=[];const sheet={exists:()=>true,shapes:()=>shapes};Object.defineProperty(sheet.shapes,'name',{value:()=>shapes.length?shapes.map(shape=>shape.name()):null});
  const app={workbooks:{byName:()=>({worksheets:{byName:()=>sheet}})},pasteWorksheet(){if(mode==='failure')throw Error('native paste failure');shapes.push({name:()=> 'Picture 1'});if(mode==='new-copy'){board.clearContents;board.writeObjects([item({'public.utf8-plain-text':'new user copy'})]);}}};
  const context=vm.createContext({Application:()=>app,ObjC:{import(){}},$});vm.runInContext(source,context);
  if(mode==='failure')assert.throws(()=>context.run(['Book','Results','/tmp/chart.png','72']),/native paste failure/);
  else assert.equal(JSON.parse(context.run(['Book','Results','/tmp/chart.png','72'])).inserted,true);
  assert.deepEqual(Array.from(board.contents,value=>value.data),mode==='new-copy'?[{'public.utf8-plain-text':'new user copy'}]:original);
 }
});
