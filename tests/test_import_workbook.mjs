import test from 'node:test';
import assert from 'node:assert/strict';
import {loadOriginalWorkbook} from '../renderer/import-workbook.mjs';
import {validateSnapshot} from '../renderer/workbook-data.mjs';

const input = () => ({
  workbook: {id:'original',sheetOrder:['raw','report'],sheets:{
    raw:{id:'raw',name:'Raw',rowCount:20,columnCount:5,cellData:{0:{0:{v:'X',t:1}},1:{0:{v:2,t:2}},2:{0:{f:'=SUM(A2,3)',v:null,custom:{statplusImport:{formula:'SUM(A2,3)',cachedValue:9,formulaStatus:'translated'}}}}}},
    report:{id:'report',name:'Report',rowCount:50,columnCount:8,cellData:{0:{0:{v:'Summary',t:1,s:{bl:1}}}},mergeData:[{startRow:0,endRow:0,startColumn:0,endColumn:4}]},
  },custom:{statworkbenchActiveSheetId:'report',statplusImport:{sourceFormat:'spjs'}}},
  importedCharts:[{sheetId:'report',originalIndex:0,chart:{type:'line',title:'Trend',series:[{x:[1,2],y:[2,3]}]},position:{row:5,column:0,width:500,height:300}}],
  notes:['Original formula caches are retained as provenance.'],
});

test('original import retains sheet coordinates, formulas, style and active sheet',async()=>{
  const data=input(),calls=[];
  const book={loadSnapshot:async snapshot=>{const validated=validateSnapshot(snapshot);calls.push(['load',validated]);},addChart:async(...args)=>calls.push(['chart',...args]),selectSheet:async id=>calls.push(['active',id])};
  const notes=await loadOriginalWorkbook(book,data);
  assert.deepEqual(calls.map(call=>call[0]),['load','chart','active']);
  assert.deepEqual(calls[0][1],data.workbook);
  assert.equal(calls[0][1].sheets.raw.cellData[0][0].v,'X');
  assert.equal(calls[0][1].sheets.raw.cellData[2][0].f,'=SUM(A2,3)');
  assert.deepEqual(calls[1].slice(1),['report',data.importedCharts[0].chart,{...data.importedCharts[0].position,originalIndex:0}]);
  assert.deepEqual(calls[2],['active','report']);
  assert.deepEqual(notes,data.notes);
});

test('chart rendering failure is explicit while original worksheet data survives',async()=>{
  const data=input(),calls=[];
  data.workbook.custom.statplusImport.managedChartIndices=[0,2];
  let current;
  const book={loadSnapshot:async snapshot=>{current=structuredClone(snapshot);calls.push('loaded');},getSnapshot:()=>structuredClone(current),addChart:async()=>{throw new Error('Image decoder failed');},selectSheet:async()=>calls.push('active')};
  const notes=await loadOriginalWorkbook(book,data);
  assert.deepEqual(calls,['loaded','loaded','active']);
  assert.deepEqual(current.custom.statplusImport.managedChartIndices,[2]);
  assert.deepEqual(data.workbook.custom.statplusImport.managedChartIndices,[0,2]);
  assert.match(notes.at(-1),/Chart 1.*Image decoder failed/);
  assert.equal(data.notes.length,1);
});

test('invalid workbook fails before chart insertion or active sheet change',async()=>{
  const data=input();data.workbook.sheets.raw.rowCount=100001;
  const book={loadSnapshot:async snapshot=>validateSnapshot(snapshot),addChart:async()=>assert.fail('must not create charts'),selectSheet:async()=>assert.fail('must not select')};
  await assert.rejects(loadOriginalWorkbook(book,data),/dimensions/);
});

test('embedded original pictures restore before charts with native identity and exact bounds',async()=>{
  const data=input(),calls=[];
  const picture={sheetId:'raw',originalIndex:3,source:'data:image/png;base64,AA==',position:{left:13,top:47,width:200,height:100},native:{name:'Plot picture',pictureStretch:2}};
  data.workbook.custom.statplusImport.importedImages=[picture];
  const book={loadSnapshot:async()=>calls.push(['load']),addImage:async(...args)=>calls.push(['image',...args]),addChart:async()=>calls.push(['chart']),selectSheet:async()=>calls.push(['active'])};
  await loadOriginalWorkbook(book,data);
  assert.deepEqual(calls.map(call=>call[0]),['load','image','chart','active']);
  assert.deepEqual(calls[1].slice(1),['raw',picture.source,{...picture.position,native:picture.native,originalIndex:3}]);
});

test('picture decode failure retains the original floating object for later native export',async()=>{
  const data=input();let current;
  data.workbook.sheets.raw.custom={statplusImport:{managedImageIndices:[1,3],floatingObjects:[{},{},{},{src:'corrupt'}]}};
  data.importedImages=[{sheetId:'raw',originalIndex:3,source:'corrupt',position:{left:0,top:0,width:20,height:10}}];
  const book={loadSnapshot:async snapshot=>{current=structuredClone(snapshot);},getSnapshot:()=>structuredClone(current),addImage:async()=>{throw new Error('Image decoder failed');},addChart:async()=>{},selectSheet:async()=>{}};
  const notes=await loadOriginalWorkbook(book,data);
  assert.match(notes.at(-1),/Picture 4.*Image decoder failed/);
  assert.deepEqual(current.sheets.raw.custom.statplusImport.managedImageIndices,[1]);
  assert.equal(current.sheets.raw.custom.statplusImport.floatingObjects[3].src,'corrupt');
  assert.deepEqual(data.workbook.sheets.raw.custom.statplusImport.managedImageIndices,[1,3]);
});
