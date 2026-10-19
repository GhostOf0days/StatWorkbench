// Global output preferences from the documented desktop workflow.
export const DEFAULT_PREFERENCES=Object.freeze({alpha:.05,decimals:5,font:'Arial',fontSize:10,labels:true,hideTrailingZeros:false,scientific:false,percentProbabilities:false,timestamp:false,missingValues:'automatic',randomSeed:0,outputMode:'worksheet',language:'en',quickAccess:[]});
export function safePreferences(value={}) {
 const p={...DEFAULT_PREFERENCES};
 if(!value||typeof value!=='object')return p;
 if(Number.isFinite(value.alpha)&&value.alpha>0&&value.alpha<1)p.alpha=value.alpha;
 // Older projects permitted 0–1 places. Preserve those files; the current UI follows 2–15.
 if(Number.isInteger(value.decimals)&&value.decimals>=0&&value.decimals<=15)p.decimals=value.decimals;
 if(typeof value.font==='string'&&value.font.trim()&&value.font.length<=100)p.font=value.font;
 if(Number.isFinite(value.fontSize)&&value.fontSize>=6&&value.fontSize<=72)p.fontSize=value.fontSize;
 for(const key of ['labels','hideTrailingZeros','scientific','percentProbabilities','timestamp'])if(typeof value[key]==='boolean')p[key]=value[key];
 if(['automatic','casewise'].includes(value.missingValues))p.missingValues=value.missingValues;
 if(Number.isSafeInteger(value.randomSeed)&&value.randomSeed>=0&&value.randomSeed<=4294967295)p.randomSeed=value.randomSeed;
 if(['worksheet','workbook'].includes(value.outputMode))p.outputMode=value.outputMode;
 if(Array.isArray(value.quickAccess)&&value.quickAccess.length<=20&&value.quickAccess.every(key=>typeof key==='string'&&/^(analysis:(?:[0-9]{4,5}|copula\.bivariate)|category:[A-Za-z /-]+)$/.test(key)))p.quickAccess=[...new Set(value.quickAccess)];
 return p;
}
export function numberFormat(preferences=DEFAULT_PREFERENCES,{probability=false}={}) {
 const p=safePreferences(preferences),digits=(p.hideTrailingZeros?'#':'0').repeat(p.decimals);
 return '0'+(digits?'.'+digits:'')+(probability&&p.percentProbabilities?'%':p.scientific?'E+00':'');
}
export function formatNumber(value,format) {
 if(typeof value!=='number'||!Number.isFinite(value))return String(value??'');
 const match=String(format).match(/^0(?:\.([0#]+))?(%|E\+00)?$/i);
 if(!match)return String(value);
 const digits=match[1]?.length||0,percent=match[2]==='%',scientific=/^E/i.test(match[2]||'');
 let rendered=scientific?value.toExponential(digits).replace(/e([+-])(\d+)$/i,(_,sign,exponent)=>'E'+sign+exponent.padStart(2,'0')):(value*(percent?100:1)).toFixed(digits);
 if(match[1]?.includes('#'))rendered=rendered.replace(/(\.[0-9]*?)0+(?=E|$)/,'$1').replace(/\.(?=E|$)/,'');
 return rendered+(percent?'%':'');
}
export function isProbabilityLabel(value){return /(^|\b)(p|p[ -]?value|p[ -]?level|probability|significance|alpha|confidence level)(\b|$)/i.test(String(value));}
