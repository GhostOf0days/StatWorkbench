const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const {readLaunchRequest,validateLaunchRequest,rangeBounds}=require('../electron/excel-addin.cjs');
const {validateRequest}=require('../electron/external-spreadsheet.cjs');
const uuid='ac3fa1dd-e035-4bb2-8d11-cd9be1fdbb92',now=Date.now();
const request={version:1,requestId:uuid,createdAt:now,command:'analysis:1001',excelProcessId:1234,workbook:'Cohort.xlsx',sheet:"Patients' data",rangeA1:'B2:D15'};
test('Excel ribbon accepts only shared analysis IDs and three bounded source references',()=>{
 assert.equal(validateLaunchRequest(request,{now}).command,'analysis:1001');
 for(const bad of [{command:'analysis:9999'},{command:'file:open'},{excelProcessId:-1},{workbook:''},{sheet:'x\0y'},{rangeA1:'A1,B5'},{rangeA1:'XFE1'},{rangeA1:'A1048577'},{rangeA1:'B4:A1'},{requestId:'../data'}])assert.throws(()=>validateLaunchRequest({...request,...bad},{now}));
 assert.throws(()=>validateLaunchRequest({...request,createdAt:now-600001},{now}),/expired/);
 assert.throws(()=>validateLaunchRequest({...request,createdAt:now+30001},{now}),/expired/);
 assert.deepEqual(rangeBounds('A:C'),{startRow:0,endRow:1048575,startColumn:0,endColumn:2});
});
test('Excel request file is consumed once, bounded and never selected by arbitrary path',async()=>{
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'statworkbench-addin-test-'));
 try{
  const target=path.join(directory,uuid+'.json');await fs.writeFile(target,JSON.stringify(request));
  const result=await readLaunchRequest(['app','--excel-addin='+uuid],{directory,now});assert.equal(result.sheet,request.sheet);
  await assert.rejects(fs.stat(target),{code:'ENOENT'});
  await assert.rejects(readLaunchRequest(['--excel-addin=../../private'],{directory,now}),/request ID/);
  await assert.rejects(readLaunchRequest(['--excel-addin='+uuid,'--excel-addin='+uuid],{directory,now}),/Only one/);
  await fs.writeFile(target,' '.repeat(16385));await assert.rejects(readLaunchRequest(['--excel-addin='+uuid],{directory,now}),/request file/);
  await fs.unlink(target);await fs.mkdir(target);await assert.rejects(readLaunchRequest(['--excel-addin='+uuid],{directory,now}),/request file/);
 }finally{await fs.rm(directory,{recursive:true,force:true});}
});
test('Excel handoff rejects symlinks and mismatched request identity',async t=>{
 const directory=await fs.mkdtemp(path.join(os.tmpdir(),'statworkbench-addin-test-'));
 try{
  const target=path.join(directory,uuid+'.json');await fs.writeFile(target,JSON.stringify({...request,requestId:'bc3fa1dd-e035-4bb2-8d11-cd9be1fdbb92'}));
  await assert.rejects(readLaunchRequest(['--excel-addin='+uuid],{directory,now}),/Invalid/);
  await fs.unlink(target);await fs.writeFile(path.join(directory,'other.json'),JSON.stringify(request));
  try{await fs.symlink(path.join(directory,'other.json'),target);}catch(e){if(['EPERM','EACCES'].includes(e.code)){t.diagnostic('Symlink creation unavailable on this host; identity rejection verified.');return;}throw e;}
  await assert.rejects(readLaunchRequest(['--excel-addin='+uuid],{directory,now}),/request file/);
 }finally{await fs.rm(directory,{recursive:true,force:true});}
});
test('Ribbon selection fills only the first applicable field with correctly quoted sheet names',async()=>{
 const {excelLaunchRanges}=await import('../renderer/excel-addin.mjs');const quote=s=>"'"+s.replaceAll("'","''")+"'";
 const fields=[{key:'alpha',type:'number'},{key:'response',type:'column'},{key:'predictors',type:'columns'}];
 assert.deepEqual(excelLaunchRanges(request,fields,quote),{response:"'Patients'' data'!B2:B15"});
 assert.deepEqual(excelLaunchRanges({...request,rangeA1:'B:D'},fields,quote),{response:"'Patients'' data'!B:B"});
 assert.deepEqual(excelLaunchRanges(request,[{key:'samples',type:'columns'}],quote),{samples:"'Patients'' data'!B2:D15"});
 assert.deepEqual(excelLaunchRanges(request,[{key:'count',type:'integer'}],quote),{});
});
test('Excel instance identity survives reads, range picking and writeback',async()=>{
 const {ExternalWorkbook}=await import('../renderer/external-workbook.mjs');const calls=[];
 const api={externalSpreadsheet:async p=>{calls.push(p);return {workbook:'Cohort.xlsx',sheets:[{id:'Patients',name:'Patients'}],activeSheetId:'Patients',matrix:[[1]],selection:{sheetId:'Patients',rangeA1:'A1'}};}};
 const book=new ExternalWorkbook(api,'excel',{workbook:'Cohort.xlsx',sheet:'Patients',excelProcessId:1234});await book.connect();await book.readSheet('Patients');await book.selection();await book.activate();await book.write([[1]],'Results',{},'0.00');
 for(const p of calls){assert.equal(p.excelProcessId,1234);assert.equal(validateRequest(p).excelProcessId,1234);}
 assert.equal(calls[2].workbook,undefined,'selection must reflect the active Excel workbook to detect mismatches');
 assert.throws(()=>validateRequest({app:'numbers',operation:'read',excelProcessId:1234}),/Invalid Excel/);
});
test('Excel utility commands cannot rebind an existing analysis to a different workbook',async()=>{
 const {applyExcelCommand}=await import('../renderer/excel-addin.mjs');let source='A.xlsx',dialog='A.xlsx';const events=[];
 const actions={preferences(){events.push('preferences');},resetAnalysis(){dialog=null;events.push('reset');},async connect(hint){assert.equal(dialog,null,'an old dialog must be invalidated before rebinding');source=hint.workbook;events.push('connect');},async openAnalysis(id){dialog=source;events.push(id);}};
 await applyExcelCommand({...request,command:'preferences'},actions);assert.equal(source,'A.xlsx');assert.equal(dialog,'A.xlsx');assert.deepEqual(events,['preferences']);
 events.length=0;await applyExcelCommand({...request,command:'open'},actions);assert.equal(source,'Cohort.xlsx');assert.equal(dialog,null);assert.deepEqual(events,['reset','connect']);
 events.length=0;await applyExcelCommand(request,actions);assert.equal(dialog,'Cohort.xlsx');assert.deepEqual(events,['reset','connect','1001']);
 events.length=0;await assert.rejects(applyExcelCommand(request,{...actions,connect:async()=>{throw new Error('No Excel');}}),/No Excel/);assert.equal(dialog,null);assert.deepEqual(events,['reset']);
});
test('ordinary Excel connections pin the returned process ID for subsequent reads and writeback',async()=>{
 const {ExternalWorkbook}=await import('../renderer/external-workbook.mjs');const calls=[];
 const api={externalSpreadsheet:async p=>{calls.push(p);return {workbook:'Book.xlsx',sheets:[{id:'Data',name:'Data'}],activeSheetId:'Data',excelProcessId:9876,matrix:[[1]]};}};
 const book=new ExternalWorkbook(api,'excel');await book.connect();await book.readSheet('Data');await book.write([[3.5]],'Results',{},'0.00');
 assert.equal(calls[0].excelProcessId,undefined);assert.equal(calls[1].excelProcessId,9876);assert.equal(calls[2].excelProcessId,9876);
});
