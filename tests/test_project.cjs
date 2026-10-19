const test=require('node:test');
const assert=require('node:assert/strict');
const {validateProject}=require('../electron/project.cjs');
function project(){return {format:'statworkbench',version:2,workbook:{sheetOrder:['one'],sheets:{one:{name:'Data',rowCount:100,columnCount:26,cellData:{0:{0:{v:2,f:null},1:null}}}}},results:[],preferences:{alpha:.05,decimals:4,font:'Arial',fontSize:11,labels:true}};}
test('version2 projects accept cleared cells and nullable formula fields',()=>{const p=project();assert.equal(validateProject(p),p);});
test('version2 validates every analysis record just as version1 does',()=>{const p=project();p.results=[{id:'1001',result:{tables:[],charts:[],notes:[]}}];assert.equal(validateProject(p),p);p.results[0].result.tables=[{columns:[],rows:['bad']}];assert.throws(()=>validateProject(p),/table/);});
test('invalid preferences cannot reach report formatting or HTML attributes',()=>{for(const [key,value]of[['alpha','" malicious'],['alpha',1],['decimals',1000000000],['decimals',-1],['fontSize',1000],['labels','yes']]){const p=project();p.preferences[key]=value;assert.throws(()=>validateProject(p));}});
test('duplicate sheets and stored cells outside sheet bounds are rejected',()=>{const p=project();p.workbook.sheetOrder.push('one');assert.throws(()=>validateProject(p));const q=project();q.workbook.sheets.one.cellData[100]={0:{v:1}};assert.throws(()=>validateProject(q));});
