const palette=['#4869df','#28a494','#e3a64f','#b274ca','#d96d80','#579bc1'];
const escape = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tick = n => Math.abs(n)>=10000 || (Math.abs(n)<.001 && n!==0) ? n.toExponential(1) : Number(n.toPrecision(4)).toString();
let clipSequence=0;
function axisTicks(min,max,unit){
 if(!Number.isFinite(unit)||unit<=0||(max-min)/unit>500)return null;
 const count=Math.floor((max-min)/unit+1e-8);
 return Array.from({length:count+1},(_,i)=>min+i*unit);
}
const preciseTick=n=>Number(n.toPrecision(12)).toString();
function quantile(a,p){const i=(a.length-1)*p,j=Math.floor(i);return a[j]+(a[Math.min(j+1,a.length-1)]-a[j])*(i-j);}
function extent(values){let min=Infinity,max=-Infinity;for(const v of values){if(Number.isFinite(v)){min=Math.min(min,v);max=Math.max(max,v);}}return [min,max];}
// Parametric Catmull–Rom interpolation also handles closed factor-loading circles.
// It passes through every retained point; missing values start a separate path.
function splinePath(points,tension=0){
 const p=points.map(point=>point.split(',').map(Number));
 if(p.length<2)return `M${points[0]||'0,0'}`;
 const closed=p.length>3&&Math.abs(p[0][0]-p.at(-1)[0])<1e-8&&Math.abs(p[0][1]-p.at(-1)[1])<1e-8;
 let path=`M${p[0].join(',')}`;
 for(let i=0;i<p.length-1;i++){
  const a=p[i-1]||(closed?p.at(-2):p[i]),b=p[i],c=p[i+1],d=p[i+2]||(closed?p[1]:c);
  const factor=(1-tension)/6;
  path+=` C${b[0]+(c[0]-a[0])*factor},${b[1]+(c[1]-a[1])*factor} ${c[0]-(d[0]-b[0])*factor},${c[1]-(d[1]-b[1])*factor} ${c.join(',')}`;
 }
 return path;
}
const validX = value => typeof value==='string'||(typeof value==='number'&&Number.isFinite(value));
export function renderChart(chart){
 const W=680,H=280,L=60,R=20,T=15,B=48,PW=W-L-R,PH=H-T-B;
 const omitted=reason=>`<div class="result-chart"><h4>${escape(chart.title||'Chart')}</h4><p>Chart omitted: ${escape(reason)}. Use the result table.</p></div>`;
 if(!['line','spline','step','scatter','bar','histogram','box'].includes(chart.type))return omitted('unsupported chart type');
 const boxes=chart.type==='box',histogram=chart.type==='histogram',bar=['bar','histogram'].includes(chart.type),stacked=chart.type==='bar'&&['normal','percent'].includes(chart.stack);
 const series=[],issues=[];
 const allowedSeriesTypes=boxes?['box']:histogram?['histogram','line','spline']:bar?(stacked?['bar']:['bar','line','spline','scatter']):['line','spline','step','scatter'];
 for(const [i,s] of (chart.series||[]).entries()){
  if(!s||!Array.isArray(s.y)||!s.y.length)continue;
  if(s.x!==undefined&&(!Array.isArray(s.x)||s.x.length!==s.y.length)){issues.push('A series with mismatched X/Y dimensions was omitted.');continue;}
  if(s.type!==undefined&&!allowedSeriesTypes.includes(s.type)){issues.push('A series with an unsupported display type was omitted.');continue;}
  const kind=s.type||chart.type,edges=s.binEdges||chart.binEdges;
  if(histogram){
   if(!Array.isArray(s.x)||s.x.some(x=>!Number.isFinite(x))){issues.push('A histogram series without finite numeric X coordinates was omitted.');continue;}
   if(kind==='histogram'&&(!Array.isArray(edges)||edges.length!==s.y.length+1||edges.some((edge,j)=>!Number.isFinite(edge)||(j>0&&edge<=edges[j-1]))||s.x.some((x,j)=>x<edges[j]||x>edges[j+1]))){issues.push('A histogram series with invalid bin edges was omitted.');continue;}
   if(kind==='histogram'&&s.y.length>500){issues.push('A histogram with more than 500 bins was omitted.');continue;}
  }
  series.push({...s,x:s.x||s.y.map((_,j)=>j+1),binEdges:edges,color:/^#[0-9a-f]{6}$/i.test(s.color||'')?s.color:palette[i%palette.length]});
 }
 if(!series.length)return issues.length?omitted(issues[0]):'';
 const barSeries=series.filter(s=>(s.type||chart.type)==='bar'),barIndex=new Map(barSeries.map((s,i)=>[s,i]));
 if(bar&&!histogram&&!barSeries.length)return omitted('no bar series');
 const categories=new Set(),yVals=[];
 for(const s of series)for(let i=0;i<s.y.length;i++)if(Number.isFinite(s.y[i])&&(boxes||validX(s.x[i]))){yVals.push(s.y[i]);if(!boxes&&(!bar||histogram||(s.type||chart.type)==='bar'))categories.add(s.x[i]);}
 if(boxes)for(const s of series)if(s.box)yVals.push(...[s.box.low,s.box.high,s.box.q1,s.box.median,s.box.mean,s.box.q3,...(s.box.outliers||[]),...(s.box.mildOutliers||[]),...(s.box.extremeOutliers||[])].filter(Number.isFinite));
 if(!yVals.length)return '';
 const categoryValues=[...categories];
 if(bar&&!histogram&&!categoryValues.length)return omitted('no finite bar values');
 if(bar&&!histogram&&categoryValues.length>500)return omitted('more than 500 categories');
 const numericBarValues=bar&&!histogram?categoryValues.filter(Number.isFinite).sort((a,b)=>a-b):[];
 const numericBarGaps=numericBarValues.slice(1).map((value,i)=>value-numericBarValues[i]).filter(gap=>gap>0),barStep=numericBarGaps.length?numericBarGaps.reduce((minimum,gap)=>Math.min(minimum,gap),Infinity):1;
 const totals=new Map(),positive=new Map(),negative=new Map();
 if(stacked){
  for(const s of series)for(let i=0;i<s.y.length;i++)if(Number.isFinite(s.y[i]))totals.set(s.x[i],(totals.get(s.x[i])||0)+Math.abs(s.y[i]));
  for(const s of series){s.y=s.y.map((v,i)=>Number.isFinite(v)&&chart.stack==='percent'?(totals.get(s.x[i])?100*v/totals.get(s.x[i]):0):v);for(let i=0;i<s.y.length;i++){const v=s.y[i];if(!Number.isFinite(v))continue;const side=v>=0?positive:negative;side.set(s.x[i],(side.get(s.x[i])||0)+v);}}
  yVals.length=0;yVals.push(0,...positive.values(),...negative.values());positive.clear();negative.clear();
 }
 const categorical=boxes||categoryValues.some(x=>typeof x!=='number');
 let [ymin,ymax]=extent(yVals);
 if(bar){ymin=Math.min(0,ymin);ymax=Math.max(0,ymax);}
 if(ymax===ymin){ymin-=1;ymax+=1;}
 const pad=(ymax-ymin)*.08;ymax+=pad;if(!bar)ymin-=pad;
 if(bar&&!histogram&&categoryValues.length>500)return omitted('more than 500 categories');
 const categoryIndex=new Map(categoryValues.map((v,i)=>[v,i]));
 let [xmin,xmax]=categorical?[0,Math.max(1,categoryValues.length-1)]:extent(categoryValues);
 if(histogram){for(const s of series)if((s.type||chart.type)==='histogram'){xmin=Math.min(xmin,s.binEdges[0]);xmax=Math.max(xmax,s.binEdges.at(-1));}}
 if(bar&&!histogram&&!categorical){xmin-=barStep/2;xmax+=barStep/2;}
 if(xmin===xmax){xmin-=.5;xmax+=.5;}
 if(Number.isFinite(chart.yMin)&&Number.isFinite(chart.yMax)&&chart.yMax>chart.yMin){ymin=chart.yMin;ymax=chart.yMax;}
 if(!categorical&&Number.isFinite(chart.xMin)&&Number.isFinite(chart.xMax)&&chart.xMax>chart.xMin){xmin=chart.xMin;xmax=chart.xMax;}
 const Y=y=>T+(chart.reverseY?(y-ymin):(ymax-y))/(ymax-ymin)*PH;
 const X=x=>{const fraction=((categorical?categoryIndex.get(x):x)-xmin)/(xmax-xmin);return L+(chart.reverseX?1-fraction:fraction)*PW;};
 let content='';
 const yTicks=axisTicks(ymin,ymax,chart.yMajorUnit);
 for(const v of yTicks||Array.from({length:5},(_,i)=>ymin+(ymax-ymin)*i/4)){const y=Y(v);content+=`<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="#e7edf5"/><text x="${L-10}" y="${y+3}" text-anchor="end" font-size="9" fill="#8a99af">${yTicks?preciseTick(v):tick(v)}</text>`;}
 const baseline=Y(Math.max(ymin,Math.min(ymax,0)));
 if(boxes){
  series.forEach((s,i)=>{const values=s.y.filter(Number.isFinite).sort((a,b)=>a-b);if(!values.length)return;const q1=s.box?.q1??quantile(values,.25),q2=s.box?.median??quantile(values,.5),q3=s.box?.q3??quantile(values,.75),iqr=q3-q1,lo=s.box?.low??values.find(v=>v>=q1-1.5*iqr),hi=s.box?.high??values.findLast(v=>v<=q3+1.5*iqr),x=L+(i+.5)*PW/series.length,bw=Math.min(50,PW/series.length*.45);for(const value of (s.box?.mildOutliers??s.box?.outliers??values.filter(v=>v<lo||v>hi)).filter(Number.isFinite).slice(0,1000))content+=`<circle data-outlier="mild" cx="${x}" cy="${Y(value)}" r="3" fill="none" stroke="${s.color}"/>`;for(const value of (s.box?.extremeOutliers||[]).filter(Number.isFinite).slice(0,1000))content+=`<text data-outlier="extreme" x="${x}" y="${Y(value)+4}" text-anchor="middle" fill="${s.color}" font-size="14">*</text>`;content+=`<line x1="${x}" y1="${Y(lo)}" x2="${x}" y2="${Y(hi)}" stroke="${s.color}"/><line x1="${x-bw/3}" y1="${Y(lo)}" x2="${x+bw/3}" y2="${Y(lo)}" stroke="${s.color}"/><line x1="${x-bw/3}" y1="${Y(hi)}" x2="${x+bw/3}" y2="${Y(hi)}" stroke="${s.color}"/><rect x="${x-bw/2}" y="${Math.min(Y(q3),Y(q1))}" width="${bw}" height="${Math.max(1,Math.abs(Y(q1)-Y(q3)))}" fill="${s.color}30" stroke="${s.color}"/><line x1="${x-bw/2}" y1="${Y(q2)}" x2="${x+bw/2}" y2="${Y(q2)}" stroke="#2563eb" stroke-width="2"/>${Number.isFinite(s.box?.mean)?`<line data-statistic="mean" x1="${x-bw/2}" y1="${Y(s.box.mean)}" x2="${x+bw/2}" y2="${Y(s.box.mean)}" stroke="#dc2626" stroke-width="2"/>`:""}<text x="${x}" y="${H-B+20}" text-anchor="middle" font-size="9" fill="#8a99af">${escape(s.name)}</text>`;});
 }else{
  if(chart.clip){const clipId=`chart-plot-${++clipSequence}`;content+=`<defs><clipPath id="${clipId}"><rect x="${L}" y="${T}" width="${PW}" height="${PH}"/></clipPath></defs><g clip-path="url(#${clipId})">`;}
  for(const s of [...series].sort((a,b)=>(Number.isFinite(a.layer)?a.layer:0)-(Number.isFinite(b.layer)?b.layer:0))){
   const kind=s.type||chart.type,drawBars=['bar','histogram'].includes(kind),xs=s.x,segments=[],stride=drawBars?1:Math.max(1,Math.ceil(s.y.length/3000));let points=[],last=null;
   const endSegment=()=>{if(points.length)segments.push(points);points=[];last=null;};
   s.y.forEach((y,i)=>{
    // Check gaps even when display sampling would otherwise skip the row.
    if(!Number.isFinite(y)||!validX(xs[i])||(categorical&&!categoryIndex.has(xs[i]))){endSegment();return;}
    if(i%stride&&i!==s.y.length-1)return;
    let x=X(xs[i]);
    if(drawBars){let w,base=baseline,top=Y(y);
     if(histogram){const left=X(s.binEdges[i]),right=X(s.binEdges[i+1]),fraction=Number.isFinite(s.barWidth)?Math.max(1,Math.min(100,s.barWidth))/100:.98;x=Math.min(left,right);w=Math.abs(right-left);x+=w*(1-fraction)/2;w*=fraction;}
     else{let idx=categoryIndex.get(xs[i]);if(chart.reverseX)idx=categoryValues.length-1-idx;const slot=categorical?PW/categoryValues.length:Math.abs(X(xs[i]+barStep)-X(xs[i])),center=categorical?L+slot*(idx+.5):X(xs[i]);w=Math.max(1,slot*.75/(stacked?1:barSeries.length));x=center-slot*.375+(stacked?0:barIndex.get(s)*w)+w*.04;w*=.92;
      if(stacked){const side=y>=0?positive:negative,start=side.get(xs[i])||0;side.set(xs[i],start+y);base=Y(start);top=Y(start+y);}}
     content+=`<rect x="${x}" y="${Math.min(top,base)}" width="${w}" height="${Math.max(.5,Math.abs(base-top))}" fill="${s.color}" opacity="${Number.isFinite(s.opacity)?Math.max(0,Math.min(1,s.opacity)):.82}"><title>${escape(s.name)}: ${histogram?`${tick(s.binEdges[i])}–${tick(s.binEdges[i+1])}`:escape(xs[i])}, ${tick(y)}${chart.stack==='percent'?'%':''}</title></rect>`;}
    else{if(kind==='step'&&last)points.push(`${x},${last[1]}`);points.push(`${x},${Y(y)}`);last=[x,Y(y)];if(s.markers?.visible!==false&&(s.markers?.visible===true||kind==='scatter'||xs.length<45)){const hollow=s.markers?.style==='nofill';content+=`<circle cx="${x}" cy="${Y(y)}" r="${Number.isFinite(s.markers?.radius)?Math.max(1,Math.min(20,s.markers.radius)):kind==='scatter'?3:2.2}" fill="${hollow?'#ffffff':s.color}"${hollow?` stroke="${s.color}"`:''} opacity="${hollow?1:.8}"><title>${escape(s.name)}: ${escape(xs[i])}, ${tick(y)}</title></circle>`;}}
   });
   endSegment();
   if(!drawBars&&kind!=='scatter')for(const segment of segments){
    const width=Number.isFinite(s.width)?Math.max(.25,Math.min(12,s.width)):1.7,dash=['dash','dot','dashdot'].includes(s.dash)?` stroke-dasharray="${{dash:'6 4',dot:'2 3',dashdot:'6 3 2 3'}[s.dash]}"`:'';
    content+=kind==='spline'?`<path data-interpolation="catmull-rom" d="${splinePath(segment,Number.isFinite(s.splineTension)?Math.max(0,Math.min(1,s.splineTension)):0)}" fill="none" stroke="${s.color}" stroke-width="${width}"${dash}/>`:`<polyline points="${segment.join(' ')}" fill="none" stroke="${s.color}" stroke-width="${width}"${dash}/>`;
   }
  }
  if(chart.clip)content+='</g>';
  const explicitTicks=!categorical&&Array.isArray(chart.xTicks)?chart.xTicks.filter(t=>t&&Number.isFinite(t.value)&&typeof t.label==='string'&&t.value>=xmin&&t.value<=xmax).slice(0,500):[];
  const xTicks=!categorical?axisTicks(xmin,xmax,chart.xMajorUnit):null;
  if(explicitTicks.length){const step=Math.max(1,Math.ceil(explicitTicks.length/8));explicitTicks.forEach((t,i)=>{if(i%step===0)content+=`<text x="${X(t.value)}" y="${H-B+19}" text-anchor="middle" font-size="9" fill="#8a99af">${escape(t.label.slice(0,40))}</text>`;});}
  else if(xTicks){const stride=Math.max(1,Math.ceil(xTicks.length/20));xTicks.forEach((x,i)=>{if(i%stride===0||i===xTicks.length-1)content+=`<text x="${X(x)}" y="${H-B+19}" text-anchor="middle" font-size="9" fill="#8a99af">${preciseTick(x)}</text>`;});}
  else if(categorical||(bar&&!histogram)){const step=Math.max(1,Math.ceil(categoryValues.length/8));categoryValues.forEach((v,i)=>{if(i%step===0){const x=bar?L+((chart.reverseX?categoryValues.length-1-i:i)+.5)*PW/categoryValues.length:X(v);content+=`<text x="${x}" y="${H-B+19}" text-anchor="middle" font-size="9" fill="#8a99af">${escape(String(v).slice(0,14))}</text>`;}});}else{for(let i=0;i<5;i++){const x=xmin+(xmax-xmin)*i/4;content+=`<text x="${X(x)}" y="${H-B+19}" text-anchor="middle" font-size="9" fill="#8a99af">${tick(x)}</text>`;}}
 }
 if(chart.xLabel)content+=`<text x="${L+PW/2}" y="${H-4}" text-anchor="middle" font-size="10" fill="#8492a8">${escape(chart.xLabel)}</text>`;
 if(chart.yLabel)content+=`<text transform="translate(12 ${T+PH/2}) rotate(-90)" text-anchor="middle" font-size="10" fill="#8492a8">${escape(chart.yLabel)}</text>`;
 return `<div class="result-chart"><h4>${escape(chart.title||'Chart')}</h4><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${escape(chart.title||'Chart')}">${content}</svg>${chart.legend===false?'':`<div class="legend">${series.map(s=>`<span><i style="background:${s.color}"></i>${escape(s.name||'Series')}</span>`).join('')}</div>`}${[...new Set(issues)].map(issue=>`<div class="help">${escape(issue)}</div>`).join('')}${!boxes&&series.some(s=>s.y.length>3000)?'<div class="help">Chart samples up to 3,001 points per series for display. Full values remain in the result tables.</div>':''}${boxes?'<div class="help">Box: quartiles, blue median and red mean (when supplied). Whiskers follow the selected definition. Outliers shown separately (up to 1,000 per group).</div>':''}</div>`;
}
