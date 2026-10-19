#!/usr/bin/env node
// Native Numbers integration; only the workbook created by this run is changed.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {execFile}=require('node:child_process');
const {promisify}=require('node:util');
const execute=promisify(execFile);
const {createExternalSpreadsheetBridge}=require('../electron/external-spreadsheet.cjs');
const root=path.resolve(__dirname,'..'),python=process.env.STATWORKBENCH_PYTHON||path.join(root,'.venv/bin/python');
const output=path.resolve(process.argv[2]||'test-artifacts/spreadsheet-numbers-native-charts.json');
const evidence={startedAt:new Date().toISOString(),platform:process.platform,verified:false,checks:{},created:[]};
async function compileReport(file,report){
 const folder=await fs.mkdtemp(path.join(os.tmpdir(),'statworkbench-numbers-report-'));
 try{const request=path.join(folder,'request.json');await fs.writeFile(request,JSON.stringify({file,report}),{mode:0o600});
  const result=await execute(python,['-c','import json,sys; from backend.report_xlsx import export_report_xlsx; p=json.load(open(sys.argv[1])); print(json.dumps(export_report_xlsx(p["file"],p["report"])))',request],{cwd:root,timeout:120000,maxBuffer:1024*1024});return JSON.parse(result.stdout);
 }finally{await fs.rm(folder,{recursive:true,force:true});}
}
function reportCells(read,expected){assert.deepEqual(read.matrix.map(row=>row.slice(0,expected[0].length)),expected);assert(read.matrix.every(row=>row.slice(expected[0].length).every(value=>value===null)));}
(async()=>{
 if(process.platform!=='darwin')throw Error('This native verification requires Apple Numbers on macOS.');
 const png='data:image/png;base64,'+(await fs.readFile(path.join(root,'assets/statworkbench.png'))).toString('base64');
 const charts=[
  {title:'Numbers scatter',type:'scatter',series:[{name:'Measured',x:[1,2,3],y:[2,4,3]}]},
  {title:'Numbers columns',type:'bar',series:[{name:'Groups',x:['A','B','C'],y:[2,-1,0]}]},
  {title:'Numbers line',type:'line',series:[{name:'Line',x:[1,2,3],y:[2,5,3]}]},
  {title:'Numbers spline',type:'spline',series:[{name:'Spline',x:[0,1,2,3],y:[0,2,1,4]}]},
  {title:'Numbers step',type:'step',series:[{name:'Step',x:[0,2,5],y:[1,.75,.25]}]},
  {title:'Numbers stacked columns',type:'bar',stack:'normal',series:[{name:'First',x:['A','B'],y:[2,-1]},{name:'Second',x:['A','B'],y:[3,-2]}]},
  {title:'Numbers percent columns',type:'bar',stack:'percent',series:[{name:'First',x:['A','B'],y:[-1,1]},{name:'Second',x:['A','B'],y:[3,1]}]},
  {title:'Numbers category line',type:'line',series:[{name:'Category line',x:['A','B','C'],y:[4,2,5]}]},
  {title:'Numbers histogram',type:'histogram',series:[{name:'Frequency',x:[.5,1.5,2.5],y:[2,5,3],binEdges:[0,1,2,3]}]},
  {title:'Numbers custom ticks',type:'scatter',xMin:0,xMax:4,yMin:0,yMax:10,xTicks:[{value:1,label:'First'},{value:2.5,label:'Second'}],series:[{name:'Measurements',x:[1,2.5,3],y:[2,7,4]}]},
  {title:'Numbers box',type:'box',yMin:-2,yMax:20,series:[{name:'Group',y:[1,2,7,9],box:{q1:3,median:5,q3:8,low:1,high:10,mean:6,mildOutliers:[12],extremeOutliers:[18]}}]},
 ];
 const expected=charts.map(chart=>({title:chart.title,series:chart.series.map(series=>({name:series.name,x:[...(series.x||[])],y:[...series.y]}))}));
 expected[4].series[0].x=[0,2,2,5,5];expected[4].series[0].y=[1,1,.75,.75,.25];expected[6].series[0].y=[-25,50];expected[6].series[1].y=[75,50];
 // Histograms use an evenly spaced category axis; Numbers writes its displayed category labels as strings.
 expected[8].series[0].x=expected[8].series[0].x.map(String);
 expected[9].series.push({name:'Axis labels',x:[1,2.5],y:[0,0]});
 const matrix=[['Native Numbers charts','Value'],['=1+1','001'],[true,42.125]];
 const bridge=createExternalSpreadsheetBridge({createReportWorkbook:compileReport});
 const first=await bridge.request({app:'numbers',operation:'write',outputMode:'workbook',name:'Editable chart verification',matrix,chartImages:[...charts.map(chart=>({png,title:chart.title,chart})),{png,title:'Image fallback',chart:{type:'histogram',series:[{name:'Unequal bins',x:[.5,2],y:[2,3],binEdges:[0,1,3]}]}}]});
 evidence.created.push(first);assert.equal(first.nativeChartsWritten,9);assert.equal(first.chartImagesWritten,3);assert(first.workbookId);evidence.checks.nativeChartsAndFallbackImported=true;
 const read=await bridge.request({app:'numbers',operation:'read',workbookId:first.workbookId,inspectCharts:true});
 reportCells(read,matrix);assert.equal(read.nativeChartCount,9);assert.equal(read.chartImageCount,3);evidence.checks.nativeObjectAndLiteralCellReadback=true;
 const exportPath=path.join(root,'test-artifacts/numbers-native-chart-roundtrip.xlsx');
 const folder=await fs.mkdtemp(path.join(os.tmpdir(),'statworkbench-numbers-export-'));
 try{
  const script=path.join(folder,'export.js');
  await fs.writeFile(script,"function run(args){var app=Application('com.apple.iWork.Numbers'),doc=app.documents.byId(args[0]);if(!doc.exists())throw Error('Created test document is no longer open.');var chart=doc.sheets[0].charts[0],before=chart.width();chart.width=before+7;if(chart.width()!==before+7)throw Error('Native chart editing failed.');chart.width=before;app.export(doc,{to:Path(args[1]),as:'Microsoft Excel'});return JSON.stringify({chartWidthEditable:true});}",{mode:0o600});
  const exported=await execute('/usr/bin/osascript',['-l','JavaScript',script,first.workbookId,exportPath],{timeout:120000,maxBuffer:1024*1024});assert(JSON.parse(exported.stdout).chartWidthEditable);evidence.checks.nativeChartEditable=true;
 }finally{await fs.rm(folder,{recursive:true,force:true});}
 const inspected=await execute(python,[path.join(root,'scripts/inspect_chart_workbook.py'),exportPath],{timeout:30000,maxBuffer:8*1024*1024});
 const returned=JSON.parse(inspected.stdout);assert.equal(returned.length,9);
 for(let i=0;i<9;i++){const actual=returned.find(chart=>chart.title===expected[i].title);assert(actual,expected[i].title);assert.deepEqual(actual.series,expected[i].series);}
 assert(first.warnings.filter(note=>note.includes('Numbers does not preserve custom point labels')).length===2);evidence.checks.unsupportedLabelsRetainImage=true;
 evidence.checks.nineChartSeriesSurviveNumbersExport=true;evidence.nativeCharts=returned;
 const second=await bridge.request({app:'numbers',operation:'write',workbookId:first.workbookId,outputMode:'worksheet',name:'Existing workbook image',matrix:[['Existing output'],[7]],chartImages:[{png,title:charts[0].title,chart:charts[0]}]});
 evidence.created.push(second);assert.equal(second.workbookId,first.workbookId);assert.equal(second.chartImagesWritten,1);assert(second.warnings.some(w=>/new output workbook/.test(w)));evidence.checks.existingWorkbookRetainsImageOutput=true;
 const preserved=await bridge.request({app:'numbers',operation:'read',workbookId:first.workbookId,sheet:read.activeSheetId,inspectCharts:true});reportCells(preserved,matrix);assert.equal(preserved.nativeChartCount,9);evidence.checks.existingOutputPreservesNativeReport=true;
 evidence.verified=true;
})().catch(error=>{evidence.error=error.stack||error.message;process.exitCode=1;}).finally(async()=>{evidence.finishedAt=new Date().toISOString();await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(evidence,null,2)+'\n');console.log(JSON.stringify(evidence,null,2));});
