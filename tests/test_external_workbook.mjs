import test from 'node:test';
import assert from 'node:assert/strict';
import {ExternalWorkbook} from '../renderer/external-workbook.mjs';

const snapshot=(workbook,workbookId)=>({workbook,workbookId,sheets:[{id:'Data::Table 1',name:'Data'}],activeSheetId:'Data::Table 1',matrix:[[1,2]],selection:{sheetId:'Data::Table 1',range:'A1:B1'}});

test('Numbers selection follows the same document through a rename but rejects another document',async()=>{
 const requests=[];let response=snapshot('Untitled','document-a');
 const book=new ExternalWorkbook({externalSpreadsheet:async request=>{requests.push(request);return response;}},'numbers');
 await book.connect();response=snapshot('Saved data','document-a');
 assert.deepEqual(await book.selection(),response.selection);
 assert.equal(book.getName(),'Saved data');
 assert.equal(requests.at(-1).workbookId,undefined,'selection must inspect the active document');
 await book.activate();assert.equal(requests.at(-1).workbookId,'document-a');
 assert.equal(requests.at(-1).workbook,'Saved data');
 response=snapshot('Saved data','document-b');
 await assert.rejects(book.selection(),/Select cells in Saved data/);
});

test('Generated data follows its new report workbook without reusing the source document ID',async()=>{
 const requests=[];const book=new ExternalWorkbook({externalSpreadsheet:async request=>{requests.push(request);return snapshot('Source','source-id');}},'numbers');
 await book.connect();
 await book.write([[1]],'Report',{outputMode:'worksheet'},'0.00');
 assert.equal(requests.at(-1).workbookId,'source-id');
 await book.write([[2]],'Generated',{outputMode:'worksheet'},'0.00',[],{workbook:'Results',workbookId:'result-id'});
 assert.equal(requests.at(-1).workbook,'Results');assert.equal(requests.at(-1).workbookId,'result-id');
 assert.equal(book.source.workbookId,'source-id','output must not change the input workbook');
 await book.write([[3]],'Generated',{outputMode:'worksheet'},'0.00',[],'Other');
 assert.equal(requests.at(-1).workbookId,undefined);
});

test('Excel read and range selection retain the chosen process and workbook',async()=>{
 const requests=[];const response={...snapshot('Book1',undefined),excelProcessId:123};
 const book=new ExternalWorkbook({externalSpreadsheet:async request=>{requests.push(request);return response;}},'excel');
 await book.connect();await book.readSheet('Data');await book.selection();await book.activate();
 assert.ok(requests.slice(1).every(request=>request.excelProcessId===123));
 assert.equal(requests.at(-1).workbook,'Book1');
});

test('Excel rejects a different file with the same name and process',async()=>{
 let response={...snapshot('Data.xlsx',undefined),path:'C:\\first\\Data.xlsx',excelProcessId:123};
 const requests=[];const book=new ExternalWorkbook({externalSpreadsheet:async request=>{requests.push(request);return response;}},'excel');
 await book.connect();await book.write([[1]],'Report',{outputMode:'worksheet'},'0.00');
 assert.equal(requests.at(-1).expectedWorkbookPath,'C:\\first\\Data.xlsx');
 response={...response,path:'c:\\FIRST\\Data.xlsx'};await book.selection();
 response={...response,path:'C:\\second\\Data.xlsx'};
 await assert.rejects(book.selection(),/replaced or moved/);
 await assert.rejects(book.readSheet('Data'),/replaced or moved/);
 assert.equal(book.snapshot.path,'c:\\FIRST\\Data.xlsx');
 await book.write([[1]],'Generated',{outputMode:'worksheet'},'0.00',[],'New results');
 assert.equal(requests.at(-1).expectedWorkbookPath,undefined);
});
