import test from 'node:test';
import assert from 'node:assert/strict';
import {WorkbookChartRegistry,WorkbookImageRegistry} from '../renderer/workbook-charts.mjs';
const chart={type:'line',title:'Original',series:[{x:[1,2],y:[2,3]}]};
function fixture(){
 const images=new Map([['d','source1']]);
 const drawings=[{drawingId:'d',placement:{from:{row:2,column:3},width:680,height:330},bounds:{left:300,top:44,width:680,height:330}}];
 const sheet={getSheetId:()=> 's',getImages:()=>[...images].map(([id,source])=>({getId:()=>id,toBuilder:()=>({getSource:()=>source})})),getDrawingLayout:()=>({drawings}),getMaxRows:()=>100,getMaxColumns:()=>26,getRowHeight:()=>22,getColumnWidth:()=>100};
 const registry=new WorkbookChartRegistry();
 registry.register('s','d',chart,{row:2,column:3,width:680,height:330},'source1',4);
 return {registry,sheet,images,drawings};
}
test('chart registry persists immutable model, native identity and current moved/resized placement',()=>{
 const {registry,sheet,drawings}=fixture();
 drawings[0].placement.from={row:7,column:5};drawings[0].bounds.width=500;drawings[0].bounds.height=250;
 const [entry]=registry.snapshot([sheet]);
 assert.deepEqual(entry.position,{row:7,column:5,width:500,height:250});assert.equal(entry.originalIndex,4);
 entry.chart.title='mutated';assert.equal(registry.snapshot([sheet])[0].chart.title,'Original');
});
test('chart edits and undo/redo export the model matching the actual image source',()=>{
 const {registry,sheet,images}=fixture();
 registry.register('s','d',{...chart,title:'Edited'},{},'source2');
 images.set('d','source2');assert.equal(registry.snapshot([sheet])[0].chart.title,'Edited');
 images.set('d','source1');assert.equal(registry.snapshot([sheet])[0].chart.title,'Original');
 images.set('d','source2');assert.equal(registry.snapshot([sheet])[0].originalIndex,4);
});
test('removed drawings and sheets disappear, while undo restores their chart definitions',()=>{
 const {registry,sheet,images}=fixture();
 images.delete('d');assert.deepEqual(registry.snapshot([sheet]),[]);
 images.set('d','source1');assert.equal(registry.snapshot([sheet]).length,1);
 assert.deepEqual(registry.snapshot([]),[]);
});
test('copied charts get independent export identity and unrelated images are excluded',()=>{
 const {registry,sheet,images,drawings}=fixture();
 images.set('copy','source1');images.set('photo','jpeg');
 drawings.push({...drawings[0],drawingId:'copy'},{...drawings[0],drawingId:'photo'});
 const entries=registry.snapshot([sheet]);assert.equal(entries.length,2);
 assert.equal(entries[1].drawingId,'copy');assert.equal(entries[1].originalIndex,undefined);
});
test('snapshot reload restores live chart models and ignores missing or malformed entries',()=>{
 const {registry,sheet}=fixture(),entries=registry.snapshot([sheet]);
 const restored=new WorkbookChartRegistry();restored.restore([...entries,null,{sheetId:'gone',drawingId:'x',chart}], [sheet]);
 assert.deepEqual(restored.snapshot([sheet]),entries);
 restored.restore(undefined,[sheet]);assert.deepEqual(restored.snapshot([sheet]),[]);
});
test('absolute and two-cell drawings use current layout dimensions and drawing order',()=>{
 const {registry,sheet,drawings}=fixture();
 drawings[0].placement={kind:'absolute'};drawings[0].bounds={left:550,top:155,width:460,height:210};
 assert.deepEqual(registry.snapshot([sheet])[0].position,{row:7,column:5,width:460,height:210});
 drawings[0].placement={from:{row:4,column:2},to:{row:10,column:5}};
 assert.deepEqual(registry.snapshot([sheet])[0].position,{row:4,column:2,width:460,height:210});
});

test('picture registry preserves original source and metadata while reading live bounds',()=>{
 const {sheet,drawings}=fixture(),registry=new WorkbookImageRegistry();
 registry.register('s','d','original-png',{left:10,top:20,width:300,height:200},{pictureStretch:2,name:'Picture'},7,'source1');
 drawings[0].bounds={left:13,top:47,width:300,height:200};
 const [entry]=registry.snapshot([sheet]);
 assert.equal(entry.source,'original-png');assert.equal(entry.originalIndex,7);
 assert.deepEqual(entry.position,{left:13,top:47,width:300,height:200});assert.equal(entry.native.pictureStretch,2);
 entry.native.name='mutated';assert.equal(registry.snapshot([sheet])[0].native.name,'Picture');
});

test('picture registry excludes chart drawings, reflects deletion and follows copied pictures',()=>{
 const {sheet,images,drawings}=fixture(),registry=new WorkbookImageRegistry();
 registry.register('s','d','original-png',{}, {},7,'source1');
 images.set('copy','source1');images.set('chart','chart-svg');
 drawings.push({...drawings[0],drawingId:'copy'},{...drawings[0],drawingId:'chart'});
 const entries=registry.snapshot([sheet],[{sheetId:'s',drawingId:'chart'}]);
 assert.equal(entries.length,2);assert.equal(entries[1].source,'original-png');assert.equal(entries[1].originalIndex,undefined);
 images.delete('d');assert.equal(registry.snapshot([sheet],[{sheetId:'s',drawingId:'chart'}]).length,1);
 images.set('d','source1');assert.equal(registry.snapshot([sheet])[0].originalIndex,7);
});

test('picture source edits and project reload preserve the current live picture',()=>{
 const {sheet,images}=fixture(),registry=new WorkbookImageRegistry();
 registry.register('s','d','original-png',{}, {name:'Picture'},7,'source1');
 images.set('d','replaced-png');
 const entries=registry.snapshot([sheet]);assert.equal(entries[0].source,'replaced-png');
 const restored=new WorkbookImageRegistry();restored.restore(entries,[sheet]);
 assert.deepEqual(restored.snapshot([sheet]),entries);
 restored.restore(undefined,[sheet]);assert.equal(restored.snapshot([sheet])[0].source,'replaced-png');
});

test('nonuniform styled-picture resizing exports displayed pixels and undo restores its native layout',()=>{
 const {sheet,drawings}=fixture(),registry=new WorkbookImageRegistry();
 registry.register('s','d','original-png',{left:300,top:44,width:680,height:330},{pictureStretch:2,borderStyle:'solid',borderWidth:3,backColor:'#fff'},7,'source1');
 drawings[0].bounds={left:300,top:44,width:800,height:150};drawings[0].placement.kind='0';
 const [resized]=registry.snapshot([sheet]);
 assert.equal(resized.source,'source1');assert.equal(resized.native.pictureStretch,0);assert.equal(resized.native.borderStyle,'none');assert.equal(resized.native.backColor,null);
 assert.equal(resized.flattenedStyle,true);assert.equal(resized.originalIndex,7);
 assert.equal(resized.native.dynamicMove,true);assert.equal(resized.native.dynamicSize,false);
 drawings[0].bounds.width=680;drawings[0].bounds.height=330;
 const [undone]=registry.snapshot([sheet]);assert.equal(undone.source,'original-png');assert.equal(undone.native.pictureStretch,2);assert.equal(undone.flattenedStyle,undefined);
});

test('identical copied picture pixels take anchor behavior from each live drawing',()=>{
 const {sheet,images,drawings}=fixture(),registry=new WorkbookImageRegistry();
 registry.register('s','d','source1',{}, {dynamicMove:false,dynamicSize:false},7);
 images.set('copy','source1');drawings[0].placement.kind='2';drawings.push({...drawings[0],drawingId:'copy',placement:{kind:'1'}});
 const [original,copied]=registry.snapshot([sheet]);
 assert.equal(original.native.dynamicMove,false);assert.equal(original.native.dynamicSize,false);
 assert.equal(copied.native.dynamicMove,true);assert.equal(copied.native.dynamicSize,true);assert.equal(copied.originalIndex,undefined);
});
