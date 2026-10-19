#!/usr/bin/env node
// Native product-adapter integration test. Creates new synthetic workbooks only.
// Existing documents are never written, closed, saved, or replaced.
const fs=require('node:fs/promises');
const path=require('node:path');
const assert=require('node:assert/strict');
const {createExternalSpreadsheetBridge}=require('../electron/external-spreadsheet.cjs');
const app=process.argv[2]||'excel';
const output=path.resolve(process.argv[3]||`test-artifacts/spreadsheet-${app}.json`);
const bridge=createExternalSpreadsheetBridge();
const fixtureName=`SW Verify ${Date.now()}`;
const report={app,platform:process.platform,startedAt:new Date().toISOString(),fixtureName,verified:false,created:[],checks:{}};
const matrix=[['Measure','Value','Literal'],['P',.012345,'=1+1'],['Percent',.125,'@test'],['Boolean',true,null],['Numeric text',0,'001'],['Leading quote',1,"'quoted"]];
const formats=[{range:'B2',numberFormat:'0.00000'},{range:'B3',numberFormat:'0.00%'}];
// Use the bundled valid PNG; corrupt synthetic PNGs can mask adapter failures.
const pngFile=path.join(__dirname,'..','assets','statworkbench.png');
let workbookId;
const normalize=m=>m.map(row=>row.map(v=>v===null?'':v));
async function read(workbook,sheet){return bridge.request({app,operation:'read',workbook,sheet,...(workbookId?{workbookId}:{})});}
(async()=>{
 if(process.platform!=='darwin'&&!(process.platform==='win32'&&app==='excel'))throw new Error('Native spreadsheet verification requires macOS or Windows with Excel installed.');
 if(!['excel','numbers'].includes(app))throw new Error('Use excel or numbers.');
 const first=await bridge.request({app,operation:'write',outputMode:'workbook',name:fixtureName,matrix,formats});
 report.created.push(first);workbookId=first.workbookId;await persist();
 const sheet=app==='numbers'?JSON.stringify([first.sheet,'Results']):first.sheet;
 const initial=await read(first.workbook,sheet);
 assert.deepEqual(normalize(initial.matrix),normalize(matrix));report.checks.valueAndLiteralRoundtrip=true;
 assert(initial.sheets.some(s=>s.id===sheet));report.checks.sheetEnumeration=true;
 report.formatReadback=first.reportFormats||null;report.fontReadback=first.reportFont;assert.equal(first.reportFont.size,11);assert.match(first.reportFont.name,/Arial/i);report.checks.fontReadback=true;
 if(app==='excel'){assert.deepEqual(first.reportFormats,formats);report.checks.exactNumberFormats=true;}
 if(app==='numbers'){assert.equal(first.reportFormats.find(item=>item.range==='B3')?.format,'percent');report.checks.percentFormatReadback=true;}
 await bridge.request({app,operation:'activate',workbook:first.workbook,...(workbookId?{workbookId}:{}),sheet,range:'A2:C3'});
 const selected=await bridge.request({app,operation:'selection',workbook:first.workbook,...(workbookId?{workbookId}:{}),sheet});
 assert.deepEqual({r:selected.selection?.startRow,c:selected.selection?.startColumn,rr:selected.selection?.endRow,cc:selected.selection?.endColumn},{r:1,c:0,rr:2,cc:2});
 assert.equal(selected.selection.sheetId,sheet);report.checks.rangeSelectionAndActivation=true;
 const second=await bridge.request({app,operation:'write',outputMode:'worksheet',workbook:first.workbook,...(workbookId?{workbookId}:{}),name:fixtureName,matrix:[['Second report'],[42]]});
 report.created.push(second);await persist();
 if(workbookId){assert.equal(second.workbookId,workbookId);report.checks.stableDocumentIdentity=true;report.documentRenamedDuringTest=second.workbook!==first.workbook;}else assert.equal(second.workbook,first.workbook);assert.notEqual(second.sheet,first.sheet);
 assert.deepEqual(normalize((await read(first.workbook,sheet)).matrix),normalize(matrix));report.checks.newWorksheetPreservesSource=true;
 const activated=await bridge.request({app,operation:'activate',workbook:first.workbook,...(workbookId?{workbookId}:{}),sheet});
 assert.equal(activated.activated,true);
 const reselected=await bridge.request({app,operation:'selection'});
 assert.equal(reselected.selection.sheetId,sheet);if(workbookId)assert.equal(reselected.workbookId,workbookId);else assert.equal(reselected.workbook,first.workbook);report.checks.activateConnectedSource=true;
 assert.equal((await bridge.request({app,operation:'activate'})).activated,true);report.checks.activateWithoutTarget=true;
 const png='data:image/png;base64,'+(await fs.readFile(pngFile)).toString('base64');
 const image=await bridge.request({app,operation:'write',outputMode:'worksheet',workbook:first.workbook,...(workbookId?{workbookId}:{}),name:'Chart verification',matrix:[['Chart import'],[1]],chartImages:[{png,title:'Verification image'}]});
 report.created.push(image);assert.equal(image.chartImagesWritten,1);report.checks.chartImageWriteback=true;
 if(app==='excel'){
  const other=await bridge.request({app,operation:'write',outputMode:'workbook',name:'Other workbook selection',matrix:[['Other source'],[99]]});report.created.push(other);
  await bridge.request({app,operation:'activate',workbook:other.workbook,sheet:other.sheet,range:'A2'});
  assert.equal((await read(first.workbook,sheet)).selection??null,null);report.checks.otherWorkbookSelectionRejected=true;
  assert.deepEqual(normalize((await read(first.workbook,sheet)).matrix),normalize(matrix));report.checks.otherWorkbookPreservesSource=true;
  await bridge.request({app,operation:'activate',workbook:first.workbook,sheet,range:'A2:C3'});
 }
 report.warnings=[...new Set(report.created.flatMap(item=>item.warnings||[]))];
 report.verified=true;
})().catch(error=>{report.error=error.message;process.exitCode=1;}).finally(async()=>{report.finishedAt=new Date().toISOString();await persist();console.log(JSON.stringify(report,null,2));});
async function persist(){await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(report,null,2)+'\n');}
