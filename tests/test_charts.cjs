/* Dependency-free UI logic checks. Run: node --test tests/test_renderer.cjs */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const chartSource = fs.readFileSync(path.join(root, 'renderer/charts.js'), 'utf8').replace('export function renderChart', 'function renderChart');
const renderChart = vm.runInNewContext(chartSource + '\nrenderChart;');
const lineSegments = html => [...html.matchAll(/<polyline points="([^"]*)"/g)].map(match => match[1].trim().split(' ').map(point => point.split(',').map(Number)));

test('histogram bars use numeric bin widths and share an axis with the normal overlay',()=>{
  const html=renderChart({type:'histogram',binEdges:[0,1,3],series:[{name:'Count',x:[.5,2],y:[2,4]},{name:'Normal',type:'line',x:[0,1,2,3],y:[0,2,3,0]}]});
  const rects=[...html.matchAll(/<rect x="([^"]+)" y="[^"]+" width="([^"]+)"/g)].map(m=>[Number(m[1]),Number(m[2])]);
  assert.equal(rects.length,2);
  assert.ok(Math.abs(rects[1][1]/rects[0][1]-2)<1e-8);
  const [points]=lineSegments(html);
  assert.equal(points.length,4);
  assert.equal(points[0][0],60);
  assert.equal(points.at(-1)[0],660);
  assert.ok(Math.abs(points[1][0]-260)<1e-8);
  assert.doesNotMatch(html,/unsupported display type|NaN|Infinity/);
});
test('native descriptive histogram labels and marker styles render without changing bin geometry',()=>{
 const html=renderChart({type:'histogram',xMin:1,xMax:3,yMin:0,yMax:3,legend:false,binEdges:[1,2,3],xTicks:[{value:1.5,label:'1 To 2'},{value:2.5,label:'2 and over'}],series:[{name:'Value',x:[1.5,2.5],y:[1,2],barWidth:95,color:'#386D9E',opacity:1},{name:'Expected Normal',type:'spline',x:[1,2,3],y:[.5,1,.5],color:'#9F386D',markers:{visible:false}}]});
 const widths=[...html.matchAll(/<rect[^>]+width="([^"]+)"/g)].map(match=>Number(match[1]));assert.deepEqual(widths,[285,285]);
 assert.match(html,/1 To 2/);assert.match(html,/2 and over/);assert.match(html,/fill="#386D9E" opacity="1"/);assert.doesNotMatch(html,/<circle|class="legend"/);
 const qq=renderChart({type:'scatter',series:[{x:[1,2],y:[1,2],color:'#386D9E',markers:{style:'nofill',radius:4}},{type:'line',x:[0,3],y:[0,3],color:'#000000',markers:{visible:false}}]});
 assert.equal([...qq.matchAll(/<circle /g)].length,2);assert.match(qq,/r="4" fill="#ffffff" stroke="#386D9E"/);assert.match(qq,/<polyline[^>]+stroke="#000000"/);
});

test('histogram overlay point count does not create categories or shrink bars',()=>{
  const x=Array.from({length:200},(_,i)=>i/199*3);
  const html=renderChart({type:'histogram',binEdges:[0,1,2,3],series:[{name:'Count',x:[.5,1.5,2.5],y:[2,3,2]},{name:'Normal',type:'line',x,y:x.map(v=>Math.exp(-((v-1.5)**2)))}]});
  assert.equal([...html.matchAll(/<rect /g)].length,3);
  assert.equal(lineSegments(html)[0].length,200);
  assert.doesNotMatch(html,/omitted/);
});

test('histograms reject invalid bin geometry instead of misrepresenting it',()=>{
  for(const edges of [undefined,[0,1],[0,2,1],[0,1,Infinity]]) {
    const html=renderChart({type:'histogram',binEdges:edges,series:[{x:[.5,1.5],y:[1,2]}]});
    assert.match(html,/invalid bin edges/);
    assert.doesNotMatch(html,/<rect/);
  }
});

test('histogram line overlays still respect missing observations',()=>{
  const html=renderChart({type:'histogram',binEdges:[0,1,2],series:[{x:[.5,1.5],y:[3,4]},{type:'line',x:[0,.5,1,1.5,2],y:[0,2,null,2,0]}]});
  assert.equal(lineSegments(html).length,2);
});

test('line charts have separate paths across missing observations',()=>{
  const html=renderChart({type:'line',series:[{name:'x',x:[0,1,2,3,4],y:[1,2,null,4,5]}]});
  const segments=lineSegments(html);
  assert.equal(segments.length,2);
  assert.deepEqual(segments.map(s=>s.length),[2,2]);
});

test('display sampling cannot conceal an intervening gap',()=>{
  const y=Array.from({length:6001},(_,i)=>i);y[2]=null;
  const html=renderChart({type:'line',series:[{name:'x',y}]});
  assert.equal(lineSegments(html).length,2);
});

test('step chart holds the previous value until the event time',()=>{
  const [points]=lineSegments(renderChart({type:'step',series:[{name:'Survival',x:[0,1,2],y:[1,.5,0]}]}));
  assert.equal(points.length,5);
  assert.equal(points[0][1],points[1][1]);
  assert.equal(points[1][0],points[2][0]);
  assert.equal(points[2][1],points[3][1]);
});

test('scatter references can render as lines',()=>{
  const html=renderChart({type:'scatter',series:[{name:'Observed',x:[0,1],y:[1,2]},{name:'Reference',type:'line',x:[0,1],y:[0,1]}]});
  assert.equal(lineSegments(html).length,1);
});

test('categorical coordinates are shared consistently between series',()=>{
  const html=renderChart({type:'scatter',series:[{name:'First',x:['B','A'],y:[1,2]},{name:'Second',x:['A','B'],y:[3,4]}]});
  const x=[...html.matchAll(/<circle cx="([^"]+)"/g)].map(m=>Number(m[1]));
  assert.equal(x.length,4);assert.equal(x[0],x[3]);assert.equal(x[1],x[2]);assert.notEqual(x[0],x[1]);
});

test('invalid dimensions and chart kinds are reported instead of guessed',()=>{
  assert.match(renderChart({type:'line',series:[{name:'bad',x:[1],y:[1,2]}]}),/mismatched X\/Y/);
  assert.match(renderChart({type:'pie',series:[{y:[1,2]}]}),/unsupported chart type/);
  const html=renderChart({type:'line',series:[{name:'gaps',x:[0,null,1],y:[1,1000,2]}]});
  assert.equal(lineSegments(html).length,2);
  assert.doesNotMatch(html,/NaN|Infinity/);
  assert.doesNotMatch(html,/>1000</);
});

test('chart titles, series names and category labels remain inert text',()=>{
  const html=renderChart({type:'bar',title:'<script>alert(1)</script>',series:[{name:'<img src=x>',x:['"><img src=x onerror=alert(1)>'],y:[1]}]});
  assert.doesNotMatch(html,/<script|<img/);
  assert.match(html,/&lt;script&gt;/);
});

test('stacked categories share a bar position and percentages normalize independently',()=>{
 const html=renderChart({type:'bar',stack:'percent',series:[{name:'A',x:['one','two'],y:[1,6]},{name:'B',x:['one','two'],y:[3,4]}]});
 const rects=[...html.matchAll(/<rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)"/g)].map(m=>m.slice(1).map(Number));
 assert.equal(rects.length,4);assert.equal(rects[0][0],rects[2][0]);assert.equal(rects[1][0],rects[3][0]);
 assert.match(html,/one, 25%/);assert.match(html,/two, 60%/);
 assert.ok(Math.abs(rects[0][3]*3-rects[2][3])<1e-8);
 assert.doesNotMatch(html,/NaN|Infinity/);
});
test('axis reversal preserves numeric positions and histogram widths',()=>{
 const base={type:'line',series:[{x:[0,1],y:[0,1]}]};
 const normal=lineSegments(renderChart(base))[0],reverse=lineSegments(renderChart({...base,reverseX:true,reverseY:true}))[0];
 assert.equal(normal[0][0],reverse[1][0]);assert.ok(Math.abs(normal[1][1]-reverse[0][1])<1e-8);
 const html=renderChart({type:'histogram',reverseX:true,binEdges:[0,1,3],series:[{x:[.5,2],y:[2,4]}]});
 for(const match of html.matchAll(/<rect[^>]+width="([^"]+)"/g))assert.ok(Number(match[1])>0);
});
test('box plots use the selected numerical quartiles and whiskers',()=>{
 const base={type:'box',legend:false,series:[{name:'Sample',y:[1,2,3,4,100],box:{q1:2,median:3,q3:4,low:1,high:100,outliers:[]}}]};
 const explicit=renderChart(base),tukey=renderChart({...base,series:[{name:'Sample',y:[1,2,3,4,100]}]});
 assert.equal([...explicit.matchAll(/<circle /g)].length,0);assert.equal([...tukey.matchAll(/<circle /g)].length,1);
 assert.doesNotMatch(explicit,/class="legend"/);assert.doesNotMatch(explicit,/NaN|Infinity/);
});


test('edited titles, axes and colors render while unsafe colors remain inert',()=>{
 const html=renderChart({type:'line',title:'Edited',xLabel:'Time',yLabel:'Value',xMin:0,xMax:10,yMin:0,yMax:20,series:[{x:[0,10],y:[0,20],color:'#aa2244'}]});assert.match(html,/#aa2244/);assert.match(html,/Edited/);assert.match(html,/Time/);assert.equal(lineSegments(html)[0][0][0],60);assert.equal(lineSegments(html)[0][1][0],660);
 assert.doesNotMatch(renderChart({type:'line',series:[{y:[1,2],color:'red" onload="x'}]}),/onload/);
});
test('box plots distinguish mean, median, mild and extreme outliers',()=>{
 const html=renderChart({type:'box',series:[{y:[1,2,3,5,9],box:{q1:2,q3:4,median:3,mean:4,low:1,high:5,outliers:[8,9],mildOutliers:[8],extremeOutliers:[9]}}]});assert.match(html,/data-statistic="mean"/);assert.match(html,/data-outlier="mild"/);assert.match(html,/data-outlier="extreme"/);assert.match(html,/#2563eb/);assert.match(html,/#dc2626/);
});

test('box plots include separate outlier arrays inside the automatic plot bounds',()=>{
 const html=renderChart({type:'box',series:[{name:'Group',y:[1,2,3],box:{mildOutliers:[-10],extremeOutliers:[20]}}]});
 const mild=Number(html.match(/data-outlier="mild"[^>]*cy="([^"]+)"/)[1]);
 const extreme=Number(html.match(/data-outlier="extreme"[^>]*y="([^"]+)"/)[1])-4;
 assert(mild>15&&mild<232,`mild outlier must remain inside plot: ${mild}`);
 assert(extreme>15&&extreme<232,`extreme outlier must remain inside plot: ${extreme}`);
 assert(extreme<mild,'larger outlier must be drawn above the smaller outlier');
});

test('mixed bar and line charts align confidence limits with category centers',()=>{
 const chart={type:'bar',xMin:0,xMax:3,yMin:-1,yMax:1,xTicks:[{value:.5,label:'1'},{value:1.5,label:'2'},{value:2.5,label:'3'}],series:[{name:'ACF',type:'bar',x:[.5,1.5,2.5],y:[.4,.2,-.1]},{name:'Upper',type:'line',x:[.5,1.5,2.5],y:[.6,.5,.4]},{name:'Lower',type:'line',x:[.5,1.5,2.5],y:[-.6,-.5,-.4]}]};
 const html=renderChart(chart),alone=renderChart({...chart,series:chart.series.slice(0,1)});
 const rects=value=>[...value.matchAll(/<rect x="([^"]+)" y="[^"]+" width="([^"]+)"/g)].map(m=>m.slice(1).map(Number));
 assert.deepEqual(rects(html),rects(alone));
 assert.equal(rects(html).length,3);
 assert.deepEqual(rects(html).map(([left,width])=>left+width/2),[160,360,560]);
 const segments=lineSegments(html);assert.equal(segments.length,2);
 assert.deepEqual(segments[0].map(point=>point[0]),[160,360,560]);
 assert.match(html,/<text x="160"[^>]*>1<\/text>/);
 assert.doesNotMatch(html,/omitted|NaN|Infinity/);
});

test('numeric category labels preserve means-plot geometry and escaped names',()=>{
 const html=renderChart({type:'line',xMin:0,xMax:2,xTicks:[{value:.5,label:'Control'},{value:1.5,label:'<Treatment>'}],series:[{type:'line',x:[.3,.7,.5,.5,.3,.7,null,1.3,1.7],y:[1,1,1,3,3,3,null,2,2]},{type:'scatter',x:[.5,1.5],y:[2,3]}]});
 assert.equal(lineSegments(html).length,2);
 assert.match(html,/<text x="210"[^>]*>Control<\/text>/);
 assert.match(html,/<text x="510"[^>]*>&lt;Treatment&gt;<\/text>/);
 assert.doesNotMatch(html,/<Treatment>|NaN|Infinity/);
});


test('dense line overlays do not create extra bar categories or change bar widths',()=>{
 const bars={name:'Counts',type:'bar',x:[1,2,3],y:[3,4,2]};
 const overlay={name:'Reference',type:'line',x:[1,1.5,2,2.5,3],y:[1,2,3,2,1]};
 const rects=html=>[...html.matchAll(/<rect x="([^"]+)" y="[^"]+" width="([^"]+)"/g)].map(m=>m.slice(1).map(Number));
 const alone=renderChart({type:'bar',series:[bars]}),mixed=renderChart({type:'bar',series:[bars,overlay]});
 assert.deepEqual(rects(mixed),rects(alone));
 const points=lineSegments(mixed)[0];assert.equal(points.length,5);
 assert.deepEqual(rects(mixed).map(([left,width])=>left+width/2),points.filter((_,i)=>i%2===0).map(point=>point[0]));
});

test('spline charts use curved paths through endpoints without inventing points across gaps',()=>{
 const html=renderChart({type:'spline',series:[{x:[0,1,2,3,4],y:[1,3,null,2,1],markers:{visible:false}}]});
 const paths=[...html.matchAll(/<path data-interpolation="catmull-rom" d="([^"]+)"/g)].map(m=>m[1]);
 assert.equal(paths.length,2);assert.ok(paths.every(path=>path.includes(' C')));
 assert.match(paths[0],/^M60,/);assert.match(paths[1],/660,[0-9.]+$/);
 assert.doesNotMatch(html,/<circle|NaN|Infinity/);
});

test('closed factor loading splines retain tangent continuity and marker/line controls',()=>{
 const html=renderChart({type:'line',series:[{type:'spline',x:[0,1,0,-1,0],y:[1,0,-1,0,1],width:3,markers:{visible:false},dash:'dash'}]});
 assert.equal([...html.matchAll(/ C/g)].length,4);
 assert.match(html,/stroke-width="3" stroke-dasharray="6 4"/);
 assert.doesNotMatch(html,/<polyline|<circle|NaN|Infinity/);
});

test('native fixed axes retain close decimal labels and clip reference lines below hollow points',()=>{
 const html=renderChart({type:'scatter',clip:true,xMin:100,xMax:100.06,yMin:100.01,yMax:100.06,xMajorUnit:.01,yMajorUnit:.005,series:[
  {type:'scatter',x:[100.02,100.04],y:[100.02,100.04],color:'#386D9E',layer:1,markers:{visible:true,style:'nofill',radius:4}},
  {type:'line',x:[99.9,100.1],y:[99.9,100.1],color:'#000000',markers:{visible:false}}
 ]});
 assert.match(html,/>100\.015<\/text>/);assert.match(html,/>100\.03<\/text>/);
 assert.match(html,/<g clip-path="url\(#chart-plot-\d+\)">/);
 assert.ok(html.indexOf('<polyline')<html.indexOf('<circle'));
 assert.doesNotMatch(html,/NaN|Infinity/);
 const other=renderChart({type:'line',clip:true,series:[{y:[1,2]}]});
 assert.notEqual(html.match(/id="(chart-plot-\d+)"/)[1],other.match(/id="(chart-plot-\d+)"/)[1]);
});

test('invalid or excessively dense major units use bounded fallback ticks',()=>{
 for(const unit of [0,-1,NaN,Infinity,1e-20]){
  const html=renderChart({type:'line',xMajorUnit:unit,yMajorUnit:unit,series:[{y:[1,2]}]});
  assert.ok(html.length<5000);assert.doesNotMatch(html,/NaN|Infinity/);
 }
});
