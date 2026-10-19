import test from 'node:test';
import assert from 'node:assert/strict';
import {parseReference,splitReferences,prepareAnalysis} from '../renderer/analysis-input.js';
const sheets=[{id:'d',name:'Data'},{id:'q',name:"O'Brien, Trial"}];
const data={d:[['Group','Score','Score'],['A',10,30],['B',20,null],['A',40,50]],q:[['Measure'],[7],[9]]};
const adapter={getSheets:()=>sheets,getActiveSheetId:()=> 'd',readSheet:async id=>data[id]};
const proc={id:'demo',fields:[{key:'columns',label:'Variables',type:'columns',required:true},{key:'group',label:'Group',type:'column'}]};
test('references support quoted sheet names, absolute cells and column ranges',()=>{assert.deepEqual(splitReferences("'O''Brien, Trial'!$A$1:$A$3, Data!B:C"),["'O''Brien, Trial'!$A$1:$A$3",'Data!B:C']);assert.deepEqual(parseReference("'O''Brien, Trial'!$A$1:$A$3",sheets,'d'),{sheetId:'q',sheetName:"O'Brien, Trial",startColumn:0,endColumn:0,startRow:0,endRow:2});});
test('invalid, reversed and oversized ranges fail before reading data',()=>{for(const ref of ['A0:A2','B1:A2','A2:A1','A1:B','A100001','BAD!A:A','A:ZZZ'])assert.throws(()=>parseReference(ref,sheets,'d'));assert.throws(()=>splitReferences("'Data!A:A"));});
test('whole columns use first-row labels and preserve data alignment',async()=>{const r=await prepareAnalysis(adapter,proc,{columns:'B:C',group:'A:A'},{confidence:.95});assert.deepEqual(r.data.columns,['Score','Score (2)','Group']);assert.deepEqual(r.data.rows,[[10,30,'A'],[20,null,'B'],[40,50,'A']]);assert.deepEqual(r.options,{confidence:.95,columns:['Score','Score (2)'],group:'Group'});});
test('bounded ranges consume only selected rows and support no labels',async()=>{const r=await prepareAnalysis(adapter,proc,{columns:'B2:B3'},{},false);assert.deepEqual(r.data,{name:'Data',columns:['B'],rows:[[10],[20]]});});
test('labels are relative to each selected range and duplicate references reuse columns',async()=>{const r=await prepareAnalysis(adapter,proc,{columns:'B2:B4,B2:B4',group:'B2:B4'},{});assert.deepEqual(r.data.columns,['10']);assert.deepEqual(r.data.rows,[[20],[40]]);assert.deepEqual(r.options,{columns:['10'],group:'10'});});
test('separate worksheets and different length selections are padded, not truncated',async()=>{const r=await prepareAnalysis(adapter,proc,{columns:"Data!B:B,'O''Brien, Trial'!A:A"},{});assert.deepEqual(r.data.rows,[[10,7],[20,9],[40,null]]);});
test('required and single-column input constraints are enforced',async()=>{await assert.rejects(prepareAnalysis(adapter,proc,{},{}),/Select Variables/);await assert.rejects(prepareAnalysis(adapter,proc,{columns:'B:C',group:'A:B'},{}),/requires one column/);});
test('parameter-only procedures receive an empty valid dataset',async()=>{const r=await prepareAnalysis(adapter,{id:'power',fields:[]},{},{n:10});assert.deepEqual(r.data,{name:'Parameters',columns:['Value'],rows:[]});});

test('scalar Cell fields accept a computed numeric cell without consuming it as a label',async()=>{const p={id:'z',fields:[{key:'variance',type:'number',label:'Population variance',cellReference:true}]};const result=await prepareAnalysis(adapter,p,{}, {variance:'Data!B2'});assert.equal(result.options.variance,10);await assert.rejects(prepareAnalysis(adapter,p,{}, {variance:'Data!A2'}),/numeric cell/);await assert.rejects(prepareAnalysis(adapter,p,{}, {variance:'B2:B3'}),/single cell/);});

test('constant-substitution ranges align with measured rows and do not lose a label row',async()=>{
 const p={id:'pchart',fields:[{key:'size',type:'column',label:'Subgroup sizes',constantSubstitute:true,required:true},...proc.fields]};
 const result=await prepareAnalysis(adapter,p,{size:'100',columns:'B:B'},{});
 assert.deepEqual(result.data.rows,[[10,100],[20,100],[40,100]]);
 assert.equal(result.options.size,'Constant (Subgroup sizes)');
 const range=await prepareAnalysis(adapter,p,{size:'C:C',columns:'B:B'},{});
 assert.deepEqual(range.data.rows,[[30,10],[null,20],[50,40]]);
});
test('disabled dependent ranges are not required and cannot influence the request',async()=>{
 const p={...proc,fields:[...proc.fields,{key:'weights',type:'column',required:true,enabled:false}]};
 const r=await prepareAnalysis(adapter,p,{columns:'B:B',weights:'invalid'},{});
 assert.equal(r.options.weights,null);assert.equal(r.data.columns.length,1);
});
test('resolved scalar cells obey the same bounds and validators as literals',async()=>{
 const p={id:'bounded',fields:[{key:'count',type:'integer',label:'Count',cellReference:true,min:1,max:9}]};
 await assert.rejects(prepareAnalysis(adapter,p,{}, {count:'Data!B2'}),/Count/);
 p.fields[0].max=100;p.fields[0].validator='0,30-';
 await assert.rejects(prepareAnalysis(adapter,p,{}, {count:'Data!B2'}),/Count/);
 assert.equal((await prepareAnalysis(adapter,p,{}, {count:'Data!C2'})).options.count,30);
});
