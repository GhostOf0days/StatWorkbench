#!/usr/bin/env node
// Actual Excel integration check. Only newly created synthetic workbooks are edited.
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {createExternalSpreadsheetBridge}=require('../electron/external-spreadsheet.cjs');
const root=path.resolve(__dirname,'..');
const output=path.resolve(process.argv[2]||'test-artifacts/spreadsheet-excel-native-charts.json');
const evidence={startedAt:new Date().toISOString(),platform:process.platform,verified:false,checks:{},created:[]};
function compileReport(reportPath,report){return new Promise((resolve,reject)=>{
 const python=process.env.STATWORKBENCH_PYTHON||path.join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
 const child=spawn(python,['-u','-m','backend.worker'],{cwd:root,stdio:['pipe','pipe','pipe'],windowsHide:true});let out='',err='';
 const timeout=setTimeout(()=>{child.kill();reject(Error('Chart workbook generation timed out.'));},120000);
 child.stdout.on('data',data=>{out+=data;});child.stderr.on('data',data=>{err+=data;});
 child.on('error',error=>{clearTimeout(timeout);reject(error);});child.on('close',code=>{clearTimeout(timeout);try{if(code!==0)throw Error(err||'Chart worker failed.');const response=JSON.parse(out.trim());if(!response.ok)throw Error(response.error);resolve(response.result);}catch(error){reject(error);}});
 child.stdin.end(JSON.stringify({id:'chart-test',method:'export_report_xlsx',params:{path:reportPath,report}})+'\n');
});}
const flatten=value=>Array.isArray(value)?value.flat(Infinity):[value];
function verifySeries(chart,expected){
 assert.equal(chart.title,expected.title);assert(chart.chartType!==undefined);assert.equal(chart.series.length,expected.series.length);
 for(let i=0;i<expected.series.length;i++){
  assert.equal(chart.series[i].name,expected.series[i].name);
  assert.deepEqual(flatten(chart.series[i].x),expected.series[i].x);
  assert.deepEqual(flatten(chart.series[i].y),expected.series[i].y);
 }
}
(async()=>{
 if(!['darwin','win32'].includes(process.platform))throw Error('An installed desktop Excel is required.');
 const bridge=createExternalSpreadsheetBridge({createReportWorkbook:compileReport});
 const png='data:image/png;base64,'+(await fs.readFile(path.join(root,'assets','statworkbench.png'))).toString('base64');
 const charts=[{title:'Editable scatter verification',type:'scatter',xLabel:'Input',yLabel:'Output',xMin:0,xMax:4,yMin:0,yMax:5,series:[{name:'Measured',x:[1,2,3],y:[2,4,3],color:'#3366aa'}]},{title:'Editable columns verification',type:'bar',series:[{name:'Groups',x:['A','B','C'],y:[2,-1,0],color:'#3366aa'}]}];
 const matrix=[['Editable charts','Value'],['Literal =1+1',42],['=1+1','001']];
 const first=await bridge.request({app:'excel',operation:'write',outputMode:'workbook',name:'Native chart verification',matrix,chartImages:charts.map(chart=>({png,title:chart.title,chart}))});
 evidence.created.push(first);assert.equal(first.nativeChartsWritten,2);assert.equal(first.chartImagesWritten||0,0);evidence.checks.createdNativeCharts=true;
 const read=await bridge.request({app:'excel',operation:'read',workbook:first.workbook,sheet:first.sheet,inspectCharts:true});
 assert.deepEqual(read.matrix,matrix);assert.equal(read.nativeChartCount,2);evidence.checks.valuesAndLiteralText=true;
 assert.equal(read.nativeCharts[0].title,charts[0].title);assert.deepEqual(flatten(read.nativeCharts[0].series[0].x),[1,2,3]);assert.deepEqual(flatten(read.nativeCharts[0].series[0].y),[2,4,3]);
 assert.equal(read.nativeCharts[1].title,charts[1].title);assert.deepEqual(flatten(read.nativeCharts[1].series[0].x),['A','B','C']);assert.deepEqual(flatten(read.nativeCharts[1].series[0].y),[2,-1,0]);evidence.checks.nativeSeriesReadback=true;
 const second=await bridge.request({app:'excel',operation:'write',outputMode:'worksheet',workbook:first.workbook,name:first.sheet,matrix:[['Second result'],[7]],chartImages:[{png,title:charts[0].title,chart:charts[0]},{png,title:'Fallback verification',chart:{type:'histogram',series:[{name:'Unequal bins',x:[.5,2],y:[2,3],binEdges:[0,1,3]}]}}]});
 evidence.created.push(second);assert.equal(second.workbook,first.workbook);assert.notEqual(second.sheet,first.sheet);assert.equal(second.nativeChartsWritten,1);assert.equal(second.chartImagesWritten,1);assert(second.warnings?.length);evidence.checks.nativeAndImageChartsCopiedTogether=true;
 const preserved=await bridge.request({app:'excel',operation:'read',workbook:first.workbook,sheet:first.sheet,inspectCharts:true});assert.deepEqual(preserved.matrix,matrix);assert.equal(preserved.nativeChartCount,2);evidence.checks.secondWorksheetPreservesSource=true;
 const variants=[
  {title:'Editable line verification',type:'line',xMin:0,xMax:5,xMajorUnit:1,yMin:0,yMax:8,yMajorUnit:2,series:[{name:'Line',x:[1,2,3,4],y:[2,5,3,6],dash:'dash',markers:{visible:false}}]},
  {title:'Editable spline verification',type:'spline',series:[{name:'Spline',x:[0,1,2,3],y:[0,2,1,4],markers:{visible:true}}]},
  {title:'Editable step verification',type:'step',series:[{name:'Step',x:[0,2,5],y:[1,.75,.25],markers:{visible:true}}]},
  {title:'Editable stacked columns verification',type:'bar',stack:'normal',series:[{name:'First',x:['A','B'],y:[2,-1]},{name:'Second',x:['A','B'],y:[3,-2]}]},
  {title:'Editable percent columns verification',type:'bar',stack:'percent',series:[{name:'First',x:['A','B'],y:[-1,1]},{name:'Second',x:['A','B'],y:[3,1]}]},
  {title:'Editable category line verification',type:'line',series:[{name:'Category line',x:['A','B','C'],y:[4,2,5]}]},
  {title:'Editable histogram verification',type:'histogram',series:[{name:'Frequency',x:[.5,1.5,2.5],y:[2,5,3],binEdges:[0,1,2,3]}]},
  {title:'Editable custom ticks verification',type:'scatter',xMin:0,xMax:4,yMin:0,yMax:10,xTicks:[{value:1,label:'First'},{value:2.5,label:'Second'}],series:[{name:'Measurements',x:[1,2.5,3],y:[2,7,4]}]},
  {title:'Editable box verification',type:'box',yMin:-2,yMax:20,series:[{name:'Group',y:[1,2,7,9],box:{q1:3,median:5,q3:8,low:1,high:10,mean:6,mildOutliers:[12],extremeOutliers:[18]}}]},
 ];
 const expected=variants.map(chart=>({title:chart.title,series:chart.series.map(series=>({name:series.name,x:[...(series.x||[])],y:[...series.y]}))}));
 expected[2].series[0].x=[0,2,2,5,5];expected[2].series[0].y=[1,1,.75,.75,.25];
 expected[4].series[0].y=[-25,50];expected[4].series[1].y=[75,50];
 expected[7].series.push({name:'Axis labels',x:[1,2.5],y:[0,0]});
 const third=await bridge.request({app:'excel',operation:'write',outputMode:'worksheet',workbook:first.workbook,name:'Native chart variants',matrix:[['Native chart variants','Count'],['Supported variants',variants.length]],chartImages:variants.map(chart=>({png,title:chart.title,chart}))});
 evidence.created.push(third);assert.equal(third.workbook,first.workbook);assert.equal(third.nativeChartsWritten,variants.length);assert.equal(third.chartImagesWritten||0,0);
 const variantRead=await bridge.request({app:'excel',operation:'read',workbook:first.workbook,sheet:third.sheet,inspectCharts:true});
 assert.equal(variantRead.nativeChartCount,variants.length);assert.deepEqual(variantRead.matrix,[['Native chart variants','Count'],['Supported variants',variants.length]]);
 for(let i=0;i<variants.length-1;i++)verifySeries(variantRead.nativeCharts[i],expected[i]);
 const box=variantRead.nativeCharts.at(-1);assert.equal(box.title,variants.at(-1).title);assert.equal(box.series.length,6);
 for(const [index,ys] of [[1,[5,5]],[2,[6,6]],[3,[12]],[4,[18]],[5,[-2]]])assert.deepEqual(flatten(box.series[index].y),ys);
 assert.deepEqual(flatten(box.series[0].y).filter(value=>typeof value==='number'),[1,10,1,1,10,10,3,8,8,3,3]);
 assert.deepEqual(flatten(box.series[5].x),[.5]);evidence.checks.boxStatisticsAndOutliersReadback=true;
 for(const key of ['lineSeriesReadback','splineControlPointsReadback','stepExpandedSeriesReadback','normalStackSeriesReadback','percentStackSeriesReadback','categoryLineSeriesReadback','histogramSeriesReadback','customTickCoordinatesReadback'])evidence.checks[key]=true;
 evidence.nativeCharts=read.nativeCharts;evidence.variantCharts=variantRead.nativeCharts;
 evidence.nativeChartsVerified=read.nativeChartCount+variantRead.nativeChartCount;
 evidence.nativeChartsCopied=evidence.created.reduce((total,item)=>total+item.nativeChartsWritten,0);
 evidence.imageChartsCopied=evidence.created.reduce((total,item)=>total+(item.chartImagesWritten||0),0);
 evidence.verified=true;
})().catch(error=>{evidence.error=error.message;process.exitCode=1;}).finally(async()=>{evidence.finishedAt=new Date().toISOString();await fs.mkdir(path.dirname(output),{recursive:true});await fs.writeFile(output,JSON.stringify(evidence,null,2)+'\n');console.log(JSON.stringify(evidence,null,2));});
