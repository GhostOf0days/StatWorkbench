import {createSpreadsheet,chartImageSource} from './workbook.js';
import {columnLabel,quoteSheet,prepareAnalysis,parseReference,splitReferences} from './analysis-input.js';
import {orderedFields,controlEnabled,numericOptionError} from './dialog-controls.js';
import {renderChart} from './charts.js';
import layouts from './procedure-layouts.json';
import coreProcedureNames from '../electron/procedures.json';
import extensionProcedureNames from '../electron/extension-procedures.json';
const procedureNames=[...coreProcedureNames,...extensionProcedureNames];
import {ExternalWorkbook} from './external-workbook.mjs';
import {loadOriginalWorkbook} from './import-workbook.mjs';
import {excelLaunchRanges,applyExcelCommand} from './excel-addin.mjs';
import {DEFAULT_PREFERENCES,safePreferences,numberFormat,formatNumber,isProbabilityLabel} from './preferences.mjs';
const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api=window.workbench;
let book,catalog=[],activeProcedure=null,activeField=null,picking=null,busy=false,revision=0,dirty=false,restoring=false,results=[],savedOptions={},favoritePresets=[],recentPresets=[],prefs={...DEFAULT_PREFERENCES},toastTimer,pendingFormula=null;
const state={ranges:{},options:{},sheetId:null};
let externalBook=null,externalApps=[];
const analysisBook=()=>externalBook||book;
async function selectSpreadsheet(source,hint={}){
 if(busy)throw new Error('Wait for the analysis or spreadsheet connection to finish.');
 busy=true;
 try{if(source==='standalone'){externalBook=null;}else{if(!api.externalSpreadsheet)throw new Error('Live spreadsheet connections require the desktop app.');status('Connecting to '+(source==='excel'?'Microsoft Excel':'Apple Numbers')+'…');const next=new ExternalWorkbook(api,source,hint);await next.connect();externalBook=next;}await api.setSpreadsheetSource?.(source);status(externalBook?`Connected to ${source==='excel'?'Microsoft Excel':'Apple Numbers'} — ${externalBook.getName()}`:'Built-in spreadsheet');}
 finally{busy=false;}
}
let processingExcelCommand=false;
async function processExcelCommand(){
 if(!api.takeExcelCommand||processingExcelCommand||busy)return;
 processingExcelCommand=true;let handled=false;
 try{
  const request=await api.takeExcelCommand();if(!request)return;handled=true;
  await applyExcelCommand(request,{
   preferences,
   resetAnalysis(){ $('analysis-dialog').close();$('utility-dialog').close();picking=null;activeProcedure=null;activeField=null;state.ranges={};state.options={};state.sheetId=null;$('range-selection-bar').hidden=true; },
   connect:hint=>selectSpreadsheet('excel',hint),
   async openAnalysis(id,request){const procedure=catalog.find(p=>p.id===id);if(!procedure)throw new Error('This Excel command is unavailable in this app version.');const fields=orderedFields(procedure.fields,layouts[id]);await openAnalysis(id,{ranges:excelLaunchRanges(request,fields,quoteSheet)});}
  });
 }finally{processingExcelCommand=false;if(handled)queueMicrotask(guard(processExcelCommand));}
}
async function reconnectSpreadsheet(){if(externalBook)await selectSpreadsheet(externalBook.app,externalBook.source);else status('Using built-in spreadsheet.');}
const categories=[['Basic','Basic statistics','basic'],['ANOVA','ANOVA and multivariate','anova'],['Regression','Regression','regression'],['Nonparametric','Nonparametric statistics','nonparametric'],['Time Series','Time series','time'],['Survival','Survival analysis','survival'],['Dependence','Dependence models','regression'],['Data','Data','data'],['Charts','Charts','charts']];
function status(text){$('status').textContent=text;}
function toast(text,error=false){clearTimeout(toastTimer);$('toast').textContent=text;$('toast').classList.toggle('error',error);$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,error?12000:5000);}
function changed(){if(restoring)return;revision++;dirty=true;api.setDirty(true);$('dirty-marker').textContent='— Edited';}
function clean(){dirty=false;api.setDirty(false);$('dirty-marker').textContent='';}
function guard(fn){return (...args)=>Promise.resolve().then(()=>fn(...args)).catch(e=>{toast(e.message,true);status(e.message);});}
const icon=(kind)=>{
 const axes='<path d="M4 4V31H44" fill="none" stroke="#777" stroke-width=".8"/>';
 const curves='<path d="M5 30C15 30 16 4 24 4S31 30 44 30" fill="#80a9d250" stroke="#375f9c"/><path d="M4 30C18 30 18 10 26 10S34 30 45 30" fill="none" stroke="#a5457a"/>';
 const content={basic:axes+curves,anova:'<rect x="9" y="3" width="29" height="24" fill="#fff" stroke="#9f437d"/><path d="M10 10H38M16 4V27M24 4V27" stroke="#aaa" stroke-width=".6"/><rect x="17" y="11" width="28" height="23" fill="#fff" stroke="#274d9c"/><path d="M17 18H45M24 11V34M33 11V34" stroke="#aaa" stroke-width=".6"/>',regression:axes+'<path d="M7 26L43 8M7 21L43 14" stroke="#3766a8"/><path d="M9 26L40 9" stroke="#a63e79"/><g fill="#a94378"><circle cx="12" cy="23" r="1.3"/><circle cx="18" cy="24" r="1.3"/><circle cx="23" cy="17" r="1.3"/><circle cx="31" cy="10" r="1.3"/><circle cx="35" cy="13" r="1.3"/></g>',nonparametric:axes+'<path d="M7 28L13 6L20 19L29 9L39 28L44 5M7 10L17 30L25 11L33 24L42 15M7 28L44 5" stroke="#8569aa" fill="none"/><path d="M7 29L44 7" stroke="#ad4d81"/>',time:axes+'<path d="M6 29l3 -7l3 4l3 -9l3 7l3 -12l3 4l3 -9l3 6l3 -11l3 5l3 -4l3 -1" fill="none" stroke="#7e71b0"/><path d="M6 28L44 4" stroke="#ac527f"/>',survival:axes+'<path d="M6 30C15 30 20 29 24 17S30 3 43 3" fill="none" stroke="#6164a6" stroke-width="1.5"/><text x="33" y="22" font-size="7">LD</text>',data:'<rect x="5" y="2" width="38" height="31" fill="#fff" stroke="#494b9b" stroke-width="2"/><path d="M6 9H42M6 17H42M6 25H42M14 3V33M23 3V33M33 3V33" stroke="#b3b5bf"/>',charts:'<path d="M15 3V31M7 4H23M7 30H23M34 8V31M27 8H41M27 30H41" stroke="#5e55a7"/><rect x="7" y="12" width="16" height="10" fill="#d5d5e9" stroke="#5e55a7"/><rect x="27" y="17" width="14" height="8" fill="#e3d9e8" stroke="#5e55a7"/><path d="M7 17H23M27 21H41" stroke="#a74484"/>',format:'<path d="M9 29L24 12L20 8L25 3L39 16L34 22L29 18L14 34Z" fill="#666"/><path d="M26 5L36 15M24 8L33 17M29 4L39 14" stroke="white" stroke-width="2"/>',edit:'<path d="M9 8H42M9 14H42M17 20H42M17 26H42M9 32H42" stroke="#777" stroke-width="2"/><path d="M4 18L12 23L4 28Z" fill="#777"/>'};
 return `<svg viewBox="0 0 48 37" aria-hidden="true">${content[kind]||content.data}</svg>`;
};
function closeMenu(){$('dropdown').hidden=true;document.querySelectorAll('.open').forEach(e=>e.classList.remove('open'));}
function menu(anchor,items){closeMenu();anchor.classList.add('open');const popup=$('dropdown');popup.innerHTML=items.map((item,i)=>item===null?'<div class="menu-separator"></div>':item.heading?`<div class="menu-heading">${esc(item.heading)}</div>`:`<button class="menu-item ${item.pending?'unavailable':''}" role="menuitem" data-item="${i}"><span>${esc(item.label)}</span><span class="key">${esc(item.key||'')}</span></button>`).join('');popup.hidden=false;const r=anchor.getBoundingClientRect();popup.style.top=`${r.bottom+2}px`;popup.style.left=`${Math.min(r.left,window.innerWidth-popup.offsetWidth-5)}px`;popup.querySelectorAll('[data-item]').forEach(button=>{const item=items[Number(button.dataset.item)];button.onclick=guard(()=>{closeMenu();return item.action?.();});if(item.quickKey)button.oncontextmenu=event=>{event.preventDefault();closeMenu();guard(()=>addQuickAccess(item.quickKey))();};});}
function procedureMenu(category){let items=catalog.filter(p=>p.category===category);if(category==='ANOVA and multivariate')items=items.concat(catalog.filter(p=>p.category==='Design of experiments'));if(category==='Data')items=catalog.filter(p=>/data|transform|random|sample size|matrix/i.test(p.category));if(category==='Charts')items=catalog.filter(p=>/chart|plot/i.test(p.category)||p.id==='1015');return items.map(p=>({quickKey:'analysis:'+p.id,label:p.name+'…',pending:p.coverage==='unsupported',action:()=>openAnalysis(p.id)}));}
function setupMenus(){
 $('category-buttons').innerHTML=[...categories.map(([label,category,kind])=>`<button class="category-button" data-category="${esc(category)}"><span class="category-icon">${icon(kind)}<span class="chevron">⌄</span></span><span>${label}</span></button>`),...['Format','Edit'].map(name=>`<button class="category-button" data-panel="${name}"><span class="category-icon">${icon(name.toLowerCase())}<span class="chevron">⌄</span></span><span>${name}</span></button>`)].join('');
 $('category-buttons').querySelectorAll('[data-category]').forEach(b=>{b.onclick=()=>menu(b,procedureMenu(b.dataset.category));b.oncontextmenu=e=>{e.preventDefault();guard(()=>addQuickAccess('category:'+b.dataset.category))();};});renderQuickAccess();
 $('category-buttons').querySelectorAll('[data-panel]').forEach(b=>b.onclick=()=>showPanel(b.dataset.panel));
 const definitions={File:()=>[{label:'New Workbook',key:'⌘N',action:newWorkbook},{label:'Open…',key:'⌘O',action:importData},{label:'Open Project…',action:openProject},null,{label:'Save Project…',key:'⌘S',action:saveProject},{label:'Export Worksheet…',action:exportData},{label:'Export Legacy .spjs…',action:exportOriginalProject},{label:'Export Analysis Report…',action:exportReport},null,{label:'Example Data…',action:exampleData}],Edit:()=>[{label:'Undo',key:'⌘Z',action:()=>book.undo()},{label:'Redo',key:'⇧⌘Z',action:()=>book.redo()},null,{label:'Find…',key:'⌘F',action:()=>showPanel('Find')},{label:'Edit Cells…',action:()=>showPanel('Edit')},{label:'Format Cells…',action:()=>showPanel('Format')}],Statistics:()=>categories.filter(c=>!['Data','Charts'].includes(c[0])).flatMap(([label,category])=>[{heading:label},...procedureMenu(category)]),Data:()=>procedureMenu('Data'),Charts:()=>[...procedureMenu('Charts'),null,{label:'View Last Analysis Charts…',action:showCharts}],Spreadsheet:()=>[{label:(externalBook?'':'✓ ')+'Built-in spreadsheet',action:()=>selectSpreadsheet('standalone')},...externalApps.filter(a=>a.supported).map(a=>({label:(externalBook?.app===a.id?'✓ ':'')+a.name,action:()=>selectSpreadsheet(a.id)})),null,{label:'Reconnect Spreadsheet…',action:reconnectSpreadsheet},{label:'Workbook Preferences…',action:preferences}],Window:()=>[{label:'Customize Quick Access Toolbar…',action:customizeQuickAccess},{label:'Close Side Panel',action:()=>{$('side-panel').hidden=true;}},{label:'Analysis History…',action:history}],Help:()=>[{label:'Analysis ToolPak Migration Guide…',action:migrationGuide},{label:'About StatWorkbench…',action:about}]};
 definitions.Recent=()=>recentPresets.slice().reverse().map(r=>({label:r.name+'…',action:()=>openRecent(r.favoriteId)}));
 definitions.Favorites=()=>[{label:'Save Analysis As…',action:saveFavorite},null,...favoritePresets.map(f=>({label:f.name+'…',action:()=>openFavorite(f.favoriteId)})),null,{label:'Organize Favorites…',action:manageFavorites}];
 $('app-menu').innerHTML=['File','Edit','Spreadsheet','Statistics','Data','Charts','Recent','Favorites','Window','Help'].map(name=>`<button data-menu="${name}">${name}</button>`).join('');$('app-menu').querySelectorAll('button').forEach(b=>b.onclick=()=>menu(b,definitions[b.dataset.menu]()));
}
function quickAccessLabel(key){return key.startsWith('analysis:')?catalog.find(p=>p.id===key.slice(9))?.name:categories.find(c=>c[1]===key.slice(9))?.[0];}
async function addQuickAccess(key){if(prefs.quickAccess.includes(key))return;if(prefs.quickAccess.length>=20)throw new Error('Quick Access Toolbar holds up to20 commands or menus.');prefs.quickAccess=[...prefs.quickAccess,key];await api.savePreferences?.(prefs);renderQuickAccess();}
function renderQuickAccess(){const toolbar=$('quick-access');toolbar.innerHTML=prefs.quickAccess.filter(quickAccessLabel).map(key=>`<button data-quick="${esc(key)}" title="Right-click to remove">${esc(quickAccessLabel(key))}${key.startsWith('category:')?' ▾':''}</button>`).join('')+'<button id="quick-access-customize" aria-label="Customize Quick Access Toolbar">⚙</button>';toolbar.hidden=!prefs.quickAccess.length;toolbar.querySelectorAll('[data-quick]').forEach(button=>{const key=button.dataset.quick;button.onclick=guard(()=>key.startsWith('analysis:')?openAnalysis(key.slice(9)):menu(button,procedureMenu(key.slice(9))));button.oncontextmenu=e=>{e.preventDefault();guard(async()=>{prefs.quickAccess=prefs.quickAccess.filter(k=>k!==key);await api.savePreferences?.(prefs);renderQuickAccess();})();};});$('quick-access-customize').onclick=customizeQuickAccess;}
function customizeQuickAccess(){const choices=[...categories.map(c=>['category:'+c[1],c[0]+' menu']),...catalog.map(p=>['analysis:'+p.id,p.name])];utility('Quick Access Toolbar','<p>Select up to20 commands or menus. Right-click any analysis in the toolbar menus to add it; right-click a shortcut to remove it.</p><div class="quick-access-options">'+choices.map(([key,label])=>`<label><input type="checkbox" data-quick-choice="${esc(key)}" ${prefs.quickAccess.includes(key)?'checked':''}>${esc(label)}</label>`).join('')+'</div>');$('utility-close').onclick=guard(async()=>{const selected=[...document.querySelectorAll('[data-quick-choice]:checked')].map(input=>input.dataset.quickChoice);if(selected.length>20)throw new Error('Select up to20 shortcuts.');prefs.quickAccess=selected;await api.savePreferences?.(prefs);renderQuickAccess();$('utility-dialog').close();});}
function migrationGuide(){const mappings=[['ANOVA: Single Factor','1102','Select unstacked numeric columns, or use1103 with a group variable.'],['ANOVA: Two-Factor With Replication','1104','Stack the response and supply both factor columns.'],['ANOVA: Two-Factor Without Replication','1104','Stack the table and enable No Interactions.'],['Correlation','1009','Select the variable columns.'],['Covariance','1010','Select numeric variable columns.'],['Descriptive Statistics','1001','Select columns; enable the desired summary statistics.'],['Exponential Smoothing','1522','Choose model and smoothing coefficient.'],['F-Test Two-Sample for Variances','1008','Select two samples and test direction.'],['Fourier Analysis','1523','Provide the real part; imaginary part is optional.'],['Histogram','1015','Choose bins and optional Pareto/cumulative outputs.'],['Moving Average','1502','Choose the window size.'],['Random Number Generation','3100','Choose a distribution from Data → Random numbers.'],['Rank and Percentile','1403','Select numeric columns.'],['Regression','1301','Select response and predictor columns.'],['Sampling','3301','Choose the sampling method and size.'],['t-Test','1005','Choose the appropriate two-sample or paired test.'],['z-Test','1007','Supply known population variances.']];utility('Analysis ToolPak Migration Guide','<div class="native-help"><p>Worksheet variables are columns. For grouped ANOVA, use Data → Stack to convert rows or blocks into response and factor columns. Labels In First Row excludes headers.</p>'+mappings.map(([name,id,help])=>`<p><b>${esc(name)}</b><br>${esc(help)} <button data-migration="${id}">Open analysis…</button></p>`).join('')+'</div>');document.querySelectorAll('[data-migration]').forEach(button=>button.onclick=guard(async()=>{$('utility-dialog').close();await openAnalysis(button.dataset.migration);}));}
function onSelection(selection){if(pendingFormula&&document.activeElement===$('formula-value'))return;$('cell-address').value=selection.rangeA1||'A1';$('formula-value').value=selection.formula||(selection.value??'');$('selection-status').textContent=selection.rangeA1||'';}
async function commitInput(){
 if(pendingFormula){const edit=pendingFormula;pendingFormula=null;book.setCellValue(edit.value,edit);}
 await book.commitEditing();
}
function rangeFields(){return orderedFields(activeProcedure?.fields.filter(f=>['column','columns'].includes(f.type))||[],layouts[activeProcedure?.id]);}
async function refreshVariableList(){state.sheetId=$('analysis-sheet').value;const matrix=await analysisBook().readSheet(state.sheetId);const max=matrix.reduce((max,row)=>Math.max(max,row.length),26);$('variable-list').innerHTML=Array.from({length:max},(_,i)=>{const label=$('labels-first-row').checked?matrix[0]?.[i]:null;return `<option value="${i}">${esc(label!==null&&label!==undefined&&String(label).trim()?label:`Column ${columnLabel(i)}`)}</option>`;}).join('');}
function optionInput(field,value){
 const info=layouts[activeProcedure.id]?.[field.key]||{},attrs=`data-option="${esc(field.key)}" id="option-${esc(field.key)}"`;
 if(field.type==='boolean')return `<input ${attrs} type="checkbox" ${value?'checked':''}>`;
 if(field.type==='select')return `<select ${attrs}>${(field.options||[]).map(o=>typeof o==='object'?o:{value:o,label:o}).map(o=>`<option value="${esc(o.value)}" ${String(value)===String(o.value)?'selected':''}>${esc(o.label)}</option>`).join('')}</select>`;
 const input=`<input ${attrs} type="${['number','integer'].includes(field.type)&&!info.cellReference?'number':'text'}" value="${esc(value??'')}" ${field.required?'required':''} ${field.min!==undefined?`min="${esc(field.min)}"`:''} ${field.max!==undefined?`max="${esc(field.max)}"`:''} ${info.fill?`list="levels-${esc(field.key)}"`:''} step="${field.type==='integer'?1:field.step??'any'}">`;
 return input+(info.cellReference?`<button type="button" class="scalar-picker" data-pick-scalar="${esc(field.key)}" title="Select a value from a worksheet cell" aria-label="Select cell for ${esc(field.label)}">▦</button>`:'')+(info.fill?`<datalist id="levels-${esc(field.key)}"></datalist>`:'');
}
function rangeInput(field){
 const info=layouts[activeProcedure.id]?.[field.key]||{},label=info.sourceLabel||field.label;
 return `<div class="range-field ${info.indent?'indent':''}" data-option-row="${esc(field.key)}"><label for="range-${esc(field.key)}">${esc(label)} ${field.required?'[*]':''}</label><div class="range-entry"><button type="button" data-assign="${esc(field.key)}" title="Add or remove selected variables">➜</button><input id="range-${esc(field.key)}" data-range="${esc(field.key)}" value="${esc(state.ranges[field.key]||'')}" placeholder="${info.constantSubstitute?'Range or constant value':field.required?'Select variables. [Required]':'Optional range'}"><button type="button" data-pick="${esc(field.key)}" title="Select a worksheet range">▦</button><button type="button" data-clear="${esc(field.key)}" title="Clear this input">⌫</button></div><p class="range-help">${info.constantSubstitute?'Select a variable or enter a constant.':field.type==='columns'?'Select variable(s) for analysis.':'Select one variable for analysis.'}</p></div>`;
}
function wireRangeInputs(){
 $('analysis-form').querySelectorAll('[data-range]').forEach(input=>{input.onfocus=()=>activeField=input.dataset.range;input.oninput=()=>{state.ranges[input.dataset.range]=input.value;guard(refreshGroupLevels)();};});
 $('analysis-form').querySelectorAll('[data-assign]').forEach(b=>b.onclick=()=>assignVariables(b.dataset.assign));
 $('analysis-form').querySelectorAll('[data-clear]').forEach(b=>b.onclick=()=>setRange(b.dataset.clear,''));
 $('analysis-form').querySelectorAll('[data-pick]').forEach(b=>b.onclick=guard(()=>pickRange(b.dataset.pick)));
 $('analysis-form').querySelectorAll('[data-pick-scalar]').forEach(b=>b.onclick=guard(()=>pickRange(b.dataset.pickScalar,true)));
}
async function refreshGroupLevels(){
 const p=activeProcedure;if(!p)return;const layout=layouts[p.id]||{},sheets=analysisBook().getSheets();
 const inputs=rangeFields().filter(f=>layout[f.key]?.placement==='input');
 for(const f of p.fields.filter(f=>layout[f.key]?.fill)){
  const source=inputs[Number(layout[f.key].fill.match(/V\.(\d+)\.LEVELS/)?.[1]||1)-1];
  const values=new Set();
  for(const token of splitReferences(state.ranges[source?.key]||'')){
   try{const ref=parseReference(token,sheets,state.sheetId),m=await analysisBook().readSheet(ref.sheetId);for(let c=ref.startColumn;c<=ref.endColumn;c++)for(let r=ref.startRow+($('labels-first-row').checked?1:0);r<=(ref.endRow??m.length-1);r++){const v=m[r]?.[c];if(v!==null&&v!==undefined&&v!=='')values.add(String(v));}}catch{/* Partially typed ranges do not interrupt editing. */}
  }
  if(p!==activeProcedure)return;
  const list=$(`levels-${f.key}`);if(list)list.innerHTML=[...values].slice(0,10000).map(v=>`<option value="${esc(v)}"></option>`).join('');
 }
}
function renderOptions(reset=false){
 const all=orderedFields(activeProcedure.fields,layouts[activeProcedure.id]);
 const layout=layouts[activeProcedure.id]||{};
 const fields=all.filter(f=>f.key!=='confidence'&&(f.key!=='alpha'||layout.alpha));
 const isRange=f=>['column','columns'].includes(f.type);
 if(reset){state.options=Object.fromEntries(all.filter(f=>!isRange(f)).map(f=>[f.key,f.key==='confidence'?1-prefs.alpha:f.key==='alpha'&&!layout.alpha?prefs.alpha:f.default]));all.filter(f=>isRange(f)&&layout[f.key]?.placement==='advanced').forEach(f=>state.ranges[f.key]='');}
 const row=f=>isRange(f)?rangeInput(f):`<div class="option-row ${layout[f.key]?.indent?'indent':''}" data-option-row="${esc(f.key)}"><label for="option-${esc(f.key)}">${esc(layout[f.key]?.sourceLabel||f.label)}</label><div class="option-control">${optionInput(f,state.options[f.key]??(f.key==='alpha'&&!layout.alpha?prefs.alpha:f.default))}</div></div>`;
 const parameters=fields.filter(f=>!isRange(f)&&layout[f.key]?.placement==='input');
 const advanced=fields.filter(f=>isRange(f)?layout[f.key]?.placement==='advanced':layout[f.key]?.placement!=='input');
 $('parameter-fields').innerHTML=parameters.map(row).join('');
 const tabs=[...new Set(advanced.map(f=>layout[f.key]?.tab||'Options'))];
 $('option-tabs').innerHTML=tabs.length>1?tabs.map((tab,i)=>`<button type="button" role="tab" aria-selected="${i===0}" class="${i===0?'active':''}" data-option-tab="${esc(tab)}">${esc(tab)}</button>`).join(''):'';
 $('option-fields').innerHTML=tabs.map((tab,i)=>`<div data-option-page="${esc(tab)}" ${i?'hidden':''}>${advanced.filter(f=>(layout[f.key]?.tab||'Options')===tab).map(row).join('')}</div>`).join('');
 $('option-tabs').querySelectorAll('button').forEach(button=>button.onclick=()=>{document.querySelectorAll('[data-option-tab]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-selected',String(b===button));});document.querySelectorAll('[data-option-page]').forEach(page=>page.hidden=page.dataset.optionPage!==button.dataset.optionTab);});
 const dependencies=()=>{const options={};document.querySelectorAll('[data-option]').forEach(input=>options[input.dataset.option]=input.type==='checkbox'?input.checked:input.value);fields.forEach(f=>{const row=document.querySelector(`[data-option-row="${CSS.escape(f.key)}"]`);if(!row)return;const enabled=controlEnabled(f.key,options,layout);row.classList.toggle('dependent-disabled',!enabled);row.querySelectorAll('input,select,button').forEach(input=>{input.disabled=!enabled;});});};
 document.querySelectorAll('[data-option]').forEach(input=>input.addEventListener('change',()=>{input.dataset.userEdited='true';dependencies();}));dependencies();wireRangeInputs();guard(refreshGroupLevels)();
 document.querySelector('.advanced-options').hidden=!advanced.length;
}
async function openAnalysis(id,previous){
 if(busy)return toast('Wait for the current analysis to finish.');await commitInput();activeProcedure=catalog.find(p=>p.id===String(id));if(!activeProcedure)return;
 const p=activeProcedure,sheets=analysisBook().getSheets();state.sheetId=analysisBook().getActiveSheetId();$('analysis-source').textContent=externalBook?(externalBook.app==='excel'?'Microsoft Excel':'Apple Numbers'):'Built-in';$('analysis-workbook').textContent=externalBook?.getName()||book.getSnapshot().name||'Untitled';state.ranges=previous?.ranges?structuredClone(previous.ranges):{};state.options=structuredClone(previous?.options||savedOptions[p.id]||{});
 $('analysis-title').textContent=p.name;$('analysis-sheet').innerHTML=sheets.map(s=>`<option value="${esc(s.id)}" ${s.id===state.sheetId?'selected':''}>${esc(s.name)}</option>`).join('');$('labels-first-row').checked=previous?.labels??prefs.labels;
 $('range-fields').innerHTML=rangeFields().filter(f=>layouts[p.id]?.[f.key]?.placement!=='advanced').map(rangeInput).join('');
 if(p.coverage==='unsupported')$('range-fields').innerHTML+=`<p class="unimplemented-message">${esc(p.description)} ${(p.limitations||[]).map(esc).join(' ')}</p>`;
 activeField=rangeFields()[0]?.key;renderOptions();$('analysis-description').textContent=p.id==='1001'?'Calculate descriptive statistics for one or more variables.':p.id==='1002'?'Calculate descriptive statistics for each group in the selected variables.':p.name;$('analysis-error').hidden=true;$('run-analysis').disabled=p.coverage==='unsupported';
 await refreshVariableList();$('analysis-dialog').showModal();
 wireRangeInputs();
}
function setRange(key,value){state.ranges[key]=value;const input=document.querySelector(`[data-range="${CSS.escape(key)}"]`);if(input)input.value=value;activeField=key;guard(refreshGroupLevels)();}
function assignVariables(key=activeField){if(!key)return;const selected=Array.from($('variable-list').selectedOptions,o=>Number(o.value)),name=analysisBook().getSheets().find(s=>s.id===state.sheetId)?.name;const f=rangeFields().find(f=>f.key===key);if(f.type==='column'&&selected.length>1)return toast(`${f.label} accepts one variable.`);const incoming=selected.map(i=>`${quoteSheet(name)}!${columnLabel(i)}:${columnLabel(i)}`),existing=splitReferences(state.ranges[key]||'');setRange(key,f.type==='column'?incoming.join(', '):(incoming.every(ref=>existing.includes(ref))?existing.filter(ref=>!incoming.includes(ref)):[...new Set([...existing,...incoming])]).join(', '));}
async function pickRange(key,scalar=false){picking={key,scalar};$('analysis-dialog').close();$('range-selection-bar').hidden=false;$('range-selection-bar').querySelector('span').textContent=scalar?'Select one numeric cell, then click Return.':'Select a range in the worksheet, then click Return.';if(externalBook)await externalBook.activate();else book.selectSheet(state.sheetId);status('Select cells in the worksheet, then return to the analysis.');}
async function finishPicking(cancel=false){
 if(!picking)return;const {key,scalar}=picking;
 if(!cancel){const s=externalBook?await externalBook.selection():book.getSelection(),name=analysisBook().getSheets().find(x=>x.id===s.sheetId)?.name;
  if(scalar&&(s.startRow!==s.endRow||s.startColumn!==s.endColumn))return toast('Select a single cell for this parameter.',true);
  const value=`${quoteSheet(name)}!${s.rangeA1}`;
  if(scalar){const input=document.querySelector(`[data-option="${CSS.escape(key)}"]`);if(input)input.value=value;}else setRange(key,value);
 }
 picking=null;$('range-selection-bar').hidden=true;$('analysis-dialog').showModal();
}
function readOptions(){
 const options={missingValues:prefs.missingValues,randomSeed:prefs.randomSeed,...(activeProcedure.fields.some(f=>f.key==='confidence')?{confidence:1-prefs.alpha}:{})};
 if(activeProcedure.fields.some(f=>f.key==='alpha'))options.alpha=prefs.alpha;
 activeProcedure.fields.filter(f=>!['column','columns'].includes(f.type)).forEach(f=>{
  const input=document.querySelector(`[data-option="${CSS.escape(f.key)}"]`);if(!input)return;
  if(f.key==='seed'&&!Object.hasOwn(state.options,'seed')&&input.dataset.userEdited!=='true'&&String(input.value)===String(f.default))return;
  if(input.disabled){if(f.type==='boolean')options[f.key]=false;else if(f.default!==undefined)options[f.key]=f.default;return;}
  if(f.type==='boolean')options[f.key]=input.checked;
  else if(['number','integer'].includes(f.type)){
   const error=numericOptionError(f,input.value,layouts[activeProcedure.id]?.[f.key]);if(error)throw new Error(error);
   if(input.value!=='')options[f.key]=Number.isFinite(Number(input.value))?Number(input.value):input.value;
  }else options[f.key]=input.value;
 });return options;
}
async function runAnalysis(){
 if(busy||!activeProcedure||activeProcedure.coverage==='unsupported')return;
 if(!$('analysis-form').reportValidity())return;
 if(results.length>=200)throw new Error('This project already has 200 analyses. Save and start another project.');
 const p=activeProcedure,run={ranges:structuredClone(state.ranges),options:readOptions(),labels:$('labels-first-row').checked,sourceSheetId:state.sheetId,preferences:{...prefs}};
 busy=true;$('run-analysis').disabled=true;$('run-analysis').textContent='Working…';$('analysis-error').hidden=true;
 try{
  await commitInput();
  const request=await prepareAnalysis(analysisBook(),{...p,fields:p.fields.map(f=>({...f,...layouts[p.id]?.[f.key],enabled:controlEnabled(f.key,run.options,layouts[p.id])}))},run.ranges,run.options,run.labels,run.sourceSheetId);
  run.preferences.alpha=Number.isFinite(request.options.alpha)?request.options.alpha:Number.isFinite(request.options.confidence)?1-request.options.confidence:prefs.alpha;status(`Running ${p.name}…`);const result=await api.analyze(request);
  const outputSheetId=result.dataset?await book.addMatrix(result.dataset.name||p.name,[result.dataset.columns,...result.dataset.rows],{headerRows:[0]}):null;
  const resultSheetId=await writeResults(result,request.data.name,run.preferences,{ranges:run.ranges,date:new Date().toISOString(),workbook:externalBook?.getName()||book.getSnapshot().name});
  if(externalBook){const report=await book.readSheet(resultSheetId);const chartImages=await Promise.all((result.charts||[]).map(chartForSpreadsheet));const written=await externalBook.write(report,result.title,run.preferences,numberFormat(run.preferences),chartImages,externalBook.getName(),result.outputFormats||[]);if(written.warnings?.length)result.warnings=[...(result.warnings||[]),...written.warnings];if(result.dataset)await externalBook.write([result.dataset.columns,...result.dataset.rows],result.dataset.name||p.name,{...run.preferences,outputMode:'worksheet'},numberFormat(run.preferences),[],{workbook:written.workbook,...(written.workbookId?{workbookId:written.workbookId}:{})});}
  if(outputSheetId)await book.selectSheet(outputSheetId);
  savedOptions[p.id]=structuredClone(run.options);
  results.push({id:p.id,result,...run,date:new Date().toISOString(),resultSheetId,outputSheetId});
  if(api.rememberAnalysis){await api.rememberAnalysis({name:p.name,id:p.id,options:run.options,ranges:run.ranges,labels:run.labels,source:currentSource()});recentPresets=await api.listRecent();}
  changed();$('analysis-dialog').close();status(`${p.name} complete`);
  if(result.warnings?.length)toast(result.warnings.join('\n'));return result;
 }catch(e){$('analysis-error').textContent=e.message;$('analysis-error').hidden=false;throw e;}
 finally{busy=false;$('run-analysis').disabled=false;$('run-analysis').textContent='OK';guard(processExcelCommand)();}
}
async function writeResults(result,source,format=prefs,provenance={}){
 const matrix=[[result.title],["Input",source],["Alpha (significance level)",format.alpha],[]],styles=[];
 if(format.timestamp)matrix.push(['Generated',provenance.date||new Date().toISOString()],['Workbook',provenance.workbook||'Untitled'],['Input ranges',Object.values(provenance.ranges||{}).filter(Boolean).join('; ')],[]);
 const widths=[Math.min(300,Math.max(...matrix.filter(row=>row.length>1).map(row=>String(row[0]).length))*7.3+12)];
 styles.push({range:'A1:H1',style:{bold:true,fontSize:13,merge:true}});
 for(const table of result.tables||[]){
  const start=matrix.length+1,wide=table.layout?.kind==='separate_wide',separate=wide||table.layout?.kind==='separate_two_columns'||table.layout?.hideColumnHeaders;
  matrix.push([table.displayTitle||table.title||'Results']);styles.push({range:`A${start}:${columnLabel(Math.max(1,table.columns.length)-1)}${start}`,style:{bold:true,borderBottom:true}});
  if(!separate){matrix.push(table.columns);styles.push({range:`A${start+1}:${columnLabel(table.columns.length-1)}${start+1}`,style:{italic:true,borderBottom:true}});}
  const dataStart=matrix.length+1;
  for(const row of table.rows)matrix.push([...row]);matrix.push([]);
  if(format.percentProbabilities){table.columns.forEach((label,c)=>{if(isProbabilityLabel(label)&&table.rows.length)styles.push({range:`${columnLabel(c)}${dataStart}:${columnLabel(c)}${dataStart+table.rows.length-1}`,style:{numberFormat:numberFormat(format,{probability:true})}});});table.rows.forEach((row,r)=>row.forEach((value,c)=>{if(isProbabilityLabel(value)&&typeof row[c+1]==='number')styles.push({range:`${columnLabel(c+1)}${dataStart+r}`,style:{numberFormat:numberFormat(format,{probability:true})}});}));}
  for(const [column,numberFormat]of Object.entries(table.columnFormats||{})){const c=Number(column);if(Number.isInteger(c)&&c>=0&&c<table.columns.length&&table.rows.length&&typeof numberFormat==='string')styles.push({range:`${columnLabel(c)}${dataStart}:${columnLabel(c)}${dataStart+table.rows.length-1}`,style:{numberFormat}});}
  for(const [row,numberFormat]of Object.entries(table.rowFormats||{})){const r=Number(row);if(Number.isInteger(r)&&r>=0&&r<table.rows.length&&typeof numberFormat==='string')styles.push({range:`A${dataStart+r}:${columnLabel(table.columns.length-1)}${dataStart+r}`,style:{numberFormat}});}
  table.columns.forEach((label,c)=>{const texts=[...(!separate?[label]:[]),...table.rows.map((row,r)=>{
   const probability=format.percentProbabilities&&(isProbabilityLabel(label)||(c>0&&isProbabilityLabel(row[c-1])));
   const cellFormat=table.rowFormats?.[r]??table.columnFormats?.[c]??numberFormat(format,{probability});
   return typeof row[c]==='number'?formatNumber(row[c],cellFormat):String(row[c]??'');
  })];const chars=Math.max(0,...texts.map(v=>String(v).length));widths[c]=Math.max(widths[c]||110,Math.min(300,chars*7.3+12));});
 }
 const noteMeasure=document.createElement('canvas').getContext('2d');noteMeasure.font=`italic ${format.fontSize*4/3}px ${JSON.stringify(format.font)}`;
 const noteWidth=Array.from({length:8},(_,c)=>widths[c]??115).reduce((a,b)=>a+b,0)-16;
 for(const note of [...(result.notes||[]),...(result.warnings||[])]){
  let lines=0;for(const paragraph of String(note).split('\n')){let used=0;lines++;for(const word of paragraph.split(/\s+/)){const width=noteMeasure.measureText(word+' ').width;if(used&&used+width>noteWidth){lines++;used=0;}lines+=Math.max(0,Math.ceil(width/noteWidth)-1);used=width>noteWidth?width%noteWidth:used+width;}}
  const row=matrix.length+1;matrix.push([note]);styles.push({range:`A${row}:H${row}`,style:{italic:true,merge:true,wrap:true,verticalAlignment:'top',rowHeight:Math.min(1000,Math.ceil(lines*format.fontSize*4/3*1.3+6))}});
 }
 const chartRow=matrix.length+1,id=await book.addMatrix('Results',matrix);result.chartDrawingIds=[];
 await book.setRangeStyle(id,`A1:${columnLabel(matrix.reduce((max,row)=>Math.max(max,row.length),8)-1)}${matrix.length}`,{fontFamily:format.font,fontSize:format.fontSize,numberFormat:numberFormat(format),columnWidth:115});
 for(const[c,width]of widths.entries())await book.setRangeStyle(id,`${columnLabel(c)}1:${columnLabel(c)}${matrix.length}`,{columnWidth:width});
 for(const item of styles)await book.setRangeStyle(id,item.range,item.style);result.outputFormats=styles.filter(item=>item.style.numberFormat).map(item=>({range:item.range,numberFormat:item.style.numberFormat}));
 for(const[index,chart]of(result.charts||[]).entries()){
  try{result.chartDrawingIds[index]=await book.addChart(id,chart,{row:chartRow+index*21,column:0,width:680,height:420});}
  catch(e){const warning=`Chart “${chart.title||'Chart'}” could not be inserted: ${e.message}`;(result.warnings||=[]).push(warning);toast(warning,true);}
 }
 await book.selectSheet(id);return id;
}
async function chartForSpreadsheet(chart){
 const content=document.createElement('div');content.innerHTML=renderChart(chart);const svg=content.querySelector('svg');if(!svg)throw new Error('This chart could not be rendered for the external spreadsheet.');svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
 const image=new Image(),url=chartImageSource(chart).source;try{await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(new Error('Chart image conversion failed.'));image.src=url;});const canvas=document.createElement('canvas');canvas.width=1360;canvas.height=840;const context=canvas.getContext('2d');context.fillStyle='#ffffff';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(image,0,0,canvas.width,canvas.height);return {title:chart.title||'Chart',png:canvas.toDataURL('image/png'),chart:structuredClone(chart)};}finally{image.onload=null;image.onerror=null;}
}
async function promptText(title,label,initial=''){return new Promise(resolve=>{const dialog=$('utility-dialog');$('utility-content').innerHTML=`<h2>${esc(title)}</h2><form id="prompt-form"><p><label for="prompt-input">${esc(label)}</label></p><input id="prompt-input" value="${esc(initial)}" style="width:100%" required><div class="dialog-actions"><button id="prompt-cancel" type="button">Cancel</button><button class="default-button" type="submit">OK</button></div></form>`;let done=false;const finish=v=>{if(done)return;done=true;dialog.close();resolve(v);};dialog.oncancel=()=>finish(null);$('prompt-cancel').onclick=()=>finish(null);$('prompt-form').onsubmit=e=>{e.preventDefault();finish($('prompt-input').value);};dialog.showModal();$('prompt-input').focus();});}
function utility(title,html){$('utility-content').innerHTML=`<h2>${esc(title)}</h2>${html}<div class="dialog-actions"><button id="utility-close" class="default-button">OK</button></div>`;$('utility-dialog').showModal();$('utility-close').onclick=()=>$('utility-dialog').close();}
function analysisHelp(){if(!activeProcedure)return;utility(activeProcedure.name,`<div class="native-help"><p>${esc(activeProcedure.description)}</p><p>Select variables from the list and press the arrow next to the target field, or enter a range such as Sheet1!B2:D30. Labels In First Row uses the first row of each selected range as column names.</p><p>${(activeProcedure.limitations||[]).map(esc).join('</p><p>')}</p></div>`);}
function preferences(){
 const numeric=(key,label,min,max,step=1)=>`<div class="option-row"><label for="pref-${key}">${label}</label><input type="number" id="pref-${key}" value="${prefs[key]}" min="${min}" max="${max}" step="${step}"></div>`;
 const check=(key,label)=>`<label class="check-label"><input type="checkbox" id="pref-${key}" ${prefs[key]?'checked':''}>${label}</label>`;
 utility('Preferences',`<div class="native-help"><h3>General</h3><div class="option-row"><label>Language</label><select disabled aria-label="Language"><option>English</option></select></div><h3>Output Options</h3><div class="option-row"><label for="pref-font">Default font</label><input id="pref-font" value="${esc(prefs.font)}" maxlength="100"></div>${numeric('fontSize','Size',6,72)}${numeric('decimals','Decimal places (Precision)',2,15)}${check('hideTrailingZeros','Hide trailing zeros')}${check('scientific','Use scientific notation (1.23E4)')}${check('percentProbabilities','Percent-style cells for probabilities')}${check('timestamp','Add a timestamp and input ranges to reports')}<div class="option-row"><label for="pref-outputMode">External spreadsheet output</label><select id="pref-outputMode"><option value="worksheet" ${prefs.outputMode==='worksheet'?'selected':''}>New worksheet in source workbook</option><option value="workbook" ${prefs.outputMode==='workbook'?'selected':''}>New workbook</option></select></div><h3>Statistics</h3>${numeric('alpha','Alpha (significance level)',0,1,'any')}<div class="option-row"><label for="pref-missingValues">Missing values removal</label><select id="pref-missingValues"><option value="automatic" ${prefs.missingValues==='automatic'?'selected':''}>Automatic</option><option value="casewise" ${prefs.missingValues==='casewise'?'selected':''}>Force casewise deletion</option></select></div>${numeric('randomSeed','Random Seed (0 = random)',0,4294967295)}<p>Number formatting changes reports, not calculation precision.</p></div>`);
 $('utility-close').onclick=guard(async()=>{const next={...prefs};for(const key of ['alpha','decimals','fontSize','randomSeed']){const input=$('pref-'+key);if(!input.reportValidity())return;next[key]=Number(input.value);}if(next.alpha<=0||next.alpha>=1||!Number.isInteger(next.decimals)||!Number.isInteger(next.randomSeed))throw new Error('Check alpha, precision and random seed.');for(const key of ['hideTrailingZeros','scientific','percentProbabilities','timestamp'])next[key]=$('pref-'+key).checked;for(const key of ['font','missingValues','outputMode'])next[key]=$('pref-'+key).value;prefs=safePreferences(next);await api.savePreferences?.(prefs);changed();$('utility-dialog').close();});
}
async function importData(){
 if(busy)throw new Error('Wait for the analysis to finish.');let data=await api.importData();if(!data)return;
 if(data.workbook){
  await commitInput();if(dirty){await saveProject();if(dirty)return;}
  await selectSpreadsheet('standalone');
  restoring=true;
  try{
   data.notes=await loadOriginalWorkbook(book,data);results=[];savedOptions={};
   await api.clearProjectSource?.();
  }finally{restoring=false;}
 }else{
  if(data.requires_sheet||data.sheets?.length>1){const choice=await promptText('Import worksheet',`Worksheet or table: ${data.sheets.join(', ')}`,data.selected_sheet||data.sheets[0]);if(choice===null)return;data=await api.importData({path:data.importPath,sheet:choice});}
  await book.addMatrix(data.name,[data.columns,...data.rows],{formatMetadata:data.formatMetadata});
 }
 changed();if(data.notes?.length)toast(data.notes.join('\n'));status(`Opened ${data.workbook?.name||data.name}`);
}
async function sheetDataset(){await commitInput();const matrix=await book.readSheet(book.getActiveSheetId());if(!matrix.length)throw new Error('This worksheet is empty.');const width=matrix.reduce((max,row)=>Math.max(max,row.length),0),seen=new Set();const columns=Array.from({length:width},(_,c)=>{const base=String(matrix[0]?.[c]??columnLabel(c));let n=base||columnLabel(c),i=2;while(seen.has(n))n=`${base} (${i++})`;seen.add(n);return n;});return{...(book.getSnapshot().sheets[book.getActiveSheetId()].custom?.statworkbenchFormatMetadata?{formatMetadata:book.getSnapshot().sheets[book.getActiveSheetId()].custom.statworkbenchFormatMetadata}:{}),name:book.getSheets().find(s=>s.id===book.getActiveSheetId())?.name||'Sheet',columns,rows:matrix.slice(1).map(r=>columns.map((_,c)=>r[c]??null))};}
async function exportOriginalProject(){await commitInput();if(!api.exportOriginalProject)throw new Error('Original project export requires the desktop app.');const exported=await api.exportOriginalProject(book.getSnapshot());if(exported){status('Original project exported.');if(exported.notes?.length)toast(exported.notes.join(' '));}}
async function exportData(){if(await api.exportData(await sheetDataset()))status('Worksheet exported.');}
async function saveProject(){await commitInput();const savedRevision=revision;const project={format:'statworkbench',version:2,workbook:book.getSnapshot(),results:structuredClone(results),preferences:{...prefs},analysisOptions:structuredClone(savedOptions)};const path=await api.saveProject(project);if(path){if(savedRevision===revision)clean();status('Project saved');}}
async function openProject(){if(busy)throw new Error('Wait for the analysis to finish.');if(dirty){await saveProject();if(dirty)return;}const project=await api.openProject();if(!project)return;await selectSpreadsheet('standalone');await loadProjectData(project);status('Project opened.');}
async function loadProjectData(project){restoring=true;try{if(project.version===2){await book.loadSnapshot(project.workbook);prefs={...prefs,...safePreferences(project.preferences)};results=project.results||[];savedOptions=project.analysisOptions||{};}else{await book.loadSnapshot(null);for(const data of project.sheets)await book.addMatrix(data.name,[data.columns,...data.rows],{formatMetadata:data.formatMetadata});results=[];}await book.commitEditing();clean();revision++;}finally{restoring=false;}status('Project opened.');}
async function newWorkbook(){if(busy)throw new Error('Wait for the analysis to finish.');if(dirty){await saveProject();if(dirty)return;}await selectSpreadsheet('standalone');await api.clearProjectSource?.();restoring=true;try{await book.loadSnapshot(null);results=[];savedOptions={};clean();revision++;}finally{restoring=false;}status('Ready');}
async function exampleData(){const matrix=[['Group','Before','After','Age'],['Treatment',142,128,34],['Control',138,136,41],['Treatment',151,134,29],['Control',145,141,56],['Treatment',148,132,47],['Control',139,140,38],['Treatment',156,140,62],['Control',143,138,44],['Treatment',149,130,51],['Control',136,134,33],['Treatment',144,133,45],['Control',153,150,58]];await book.addMatrix('Data',matrix);changed();}
function history(){utility('Recent Analyses',results.length?results.slice().reverse().map((r,i)=>`<button class="sample-choice" data-history="${results.length-1-i}">${esc(r.result.title)} — ${esc(new Date(r.date).toLocaleString())}</button>`).join(''):'<p>No analyses in this workbook.</p>');document.querySelectorAll('[data-history]').forEach(b=>b.onclick=guard(async()=>{const record=results[Number(b.dataset.history)];$('utility-dialog').close();if(book.getSheets().some(s=>s.id===record.sourceSheetId))book.selectSheet(record.sourceSheetId);await openAnalysis(record.id,record);}));}
async function saveFavorite(){
 if(busy)throw new Error('Wait for the analysis to finish.');
 const current=$('analysis-dialog').open&&activeProcedure;
 const record=current?{id:activeProcedure.id,options:readOptions(),ranges:structuredClone(state.ranges),labels:$('labels-first-row').checked}:results.at(-1);
 if(!record)throw new Error('Open an analysis dialog or run an analysis before saving a favorite.');
 const name=await promptText('Add to Favorites','Name',catalog.find(p=>p.id===record.id)?.name||'Analysis');if(name===null)return;
 if(!externalBook){await saveProject();if(dirty)return;}else await externalBook.readSheet(state.sheetId||externalBook.getActiveSheetId());await api.saveFavorite({name:name.trim(),id:record.id,options:record.options,ranges:record.ranges,labels:record.labels,source:currentSource()});favoritePresets=await api.listFavorites();status('Favorite saved.');
}
function currentSource(){return externalBook?{app:externalBook.app,sheet:state.sheetId}:{app:'standalone'};}
async function restorePresetSource(openSource,id){if(!openSource)return true;if(dirty){await saveProject();if(dirty)return false;}const opened=await openSource(id);if(opened?.source?.app&&opened.source.app!=='standalone'){await selectSpreadsheet(opened.source.app,{...(opened.source.workbook?{workbook:opened.source.workbook}:{}),...(opened.source.sheet?{sheet:opened.source.sheet}:{}),...(opened.source.workbookId?{workbookId:opened.source.workbookId}:{}),...(opened.source.app==='excel'&&opened.source.path?{expectedWorkbookPath:opened.source.path}:{})});if(opened.source.sheet)externalBook.snapshot.activeSheetId=opened.source.sheet;}else{await selectSpreadsheet('standalone');if(opened?.project)await loadProjectData(opened.project);}return true;}
async function openRecent(id){recentPresets=await api.listRecent();const preset=recentPresets.find(item=>item.favoriteId===id);if(!preset)throw new Error('Recent analysis not found.');if(!await restorePresetSource(api.openRecentSource,id))return;await openAnalysis(preset.id,preset);}
async function openFavorite(favoriteId){favoritePresets=await api.listFavorites();const preset=favoritePresets.find(f=>f.favoriteId===favoriteId);if(!preset)throw new Error('This favorite is no longer available.');if(!await restorePresetSource(api.openFavoriteSource,favoriteId))return;await openAnalysis(preset.id,preset);}
async function manageFavorites(){
 favoritePresets=await api.listFavorites();utility('Favorites',favoritePresets.length?favoritePresets.map(f=>`<div class="favorite-row"><button class="sample-choice" data-favorite="${esc(f.favoriteId)}">${esc(f.name)}</button><button data-delete-favorite="${esc(f.favoriteId)}" aria-label="Remove ${esc(f.name)}">Remove</button></div>`).join(''):'<p>No saved favorites. Open an analysis dialog, set its options, then choose Add to Favorites.</p>');
 document.querySelectorAll('[data-favorite]').forEach(b=>b.onclick=guard(async()=>{$('utility-dialog').close();await openFavorite(b.dataset.favorite);}));
 document.querySelectorAll('[data-delete-favorite]').forEach(b=>b.onclick=guard(async()=>{await api.deleteFavorite(b.dataset.deleteFavorite);$('utility-dialog').close();await manageFavorites();}));
}
function showCharts(){
 const choices=results.flatMap((record,ri)=>(record.result.charts||[]).map((chart,ci)=>({record,chart,ri,ci})));if(!choices.length)return utility('Analysis Charts','<p>No charts in this workbook.</p>');
 utility('Analysis Charts',`<div class="chart-gallery">${choices.map(({chart,ri,ci})=>`<div>${renderChart(chart)}<button data-edit-chart="${ri}:${ci}">Edit chart…</button></div>`).join('')}</div>`);
 document.querySelectorAll('[data-edit-chart]').forEach(button=>button.onclick=()=>{const[ri,ci]=button.dataset.editChart.split(':').map(Number);$('utility-dialog').close();editChart(ri,ci);});
}
function editChart(ri,ci){
 const record=results[ri],chart=record.result.charts[ci];const text=(key,label)=>`<div class="option-row"><label for="chart-${key}">${label}</label><input id="chart-${key}" value="${esc(chart[key]??'')}" maxlength="200"></div>`;const bound=(key,label)=>`<div class="option-row"><label for="chart-${key}">${label}</label><input id="chart-${key}" type="number" step="any" placeholder="Automatic" value="${chart[key]??''}"></div>`;
 utility('Edit Chart',text('title','Title')+text('xLabel','X axis label')+text('yLabel','Y axis label')+bound('xMin','X minimum')+bound('xMax','X maximum')+bound('yMin','Y minimum')+bound('yMax','Y maximum')+`<label><input id="chart-legend" type="checkbox" ${chart.legend===false?'':'checked'}>Show legend</label>`+chart.series.map((series,index)=>`<div class="option-row"><label for="chart-color-${index}">${esc(series.name||'Series '+(index+1))}</label><input type="color" id="chart-color-${index}" value="${/^#[0-9a-f]{6}$/i.test(series.color||'')?series.color:['#4869df','#28a494','#e3a64f','#b274ca','#d96d80','#579bc1'][index%6]}"></div>`).join(''));
 $('utility-close').onclick=guard(async()=>{const next=structuredClone(chart);for(const key of ['title','xLabel','yLabel'])next[key]=$('chart-'+key).value;for(const axis of ['x','y']){const low=$('chart-'+axis+'Min').value,high=$('chart-'+axis+'Max').value;if(low===''&&high===''){delete next[axis+'Min'];delete next[axis+'Max'];}else if(low!==''&&high!==''&&Number.isFinite(Number(low))&&Number.isFinite(Number(high))&&Number(high)>Number(low)){next[axis+'Min']=Number(low);next[axis+'Max']=Number(high);}else throw new Error('Enter both axis limits with maximum greater than minimum, or leave both automatic.');}next.legend=$('chart-legend').checked;next.series.forEach((series,index)=>series.color=$('chart-color-'+index).value);const drawing=record.result.chartDrawingIds?.[ci]||book.getChartImages(record.resultSheetId)[ci];await book.updateChart(record.resultSheetId,drawing,next);record.result.charts[ci]=next;changed();$('utility-dialog').close();showCharts();});
}

function reportValue(value,format,preferences=prefs){return esc(formatNumber(value,format||numberFormat(preferences)));}
async function exportReport(){
 if(!results.length)throw new Error('Run an analysis first.');
 const reports=results.map(record=>{
  const r=record.result,format=safePreferences(record.preferences||prefs);
  const tables=r.tables.map(t=>{
   const hide=t.layout?.hideColumnHeaders||['separate_wide','separate_two_columns'].includes(t.layout?.kind);
   return `<h3>${esc(t.displayTitle||t.title)}</h3><table>${hide?'':`<tr>${t.columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr>`}${t.rows.map((row,ri)=>`<tr>${row.map((value,ci)=>`<td>${reportValue(value,t.rowFormats?.[ri]||t.columnFormats?.[ci]||numberFormat(format,{probability:isProbabilityLabel(t.columns[ci])||isProbabilityLabel(row[ci-1])}),format)}</td>`).join('')}</tr>`).join('')}</table>`;
  }).join('');
  return `<section style="font-family:${esc(format.font)};font-size:${format.fontSize}pt"><h2>${esc(r.title)}</h2>${format.timestamp?`<p>${esc(record.date)} — ${esc(Object.values(record.ranges||{}).join('; '))}</p>`:''}${tables}${r.charts.map(renderChart).join('')}${[...(r.notes||[]),...(r.warnings||[])].map(n=>`<p>${esc(n)}</p>`).join('')}</section>`;
 }).join('<hr>');
 const html=`<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:"><title>Statistical analysis</title><style>body{font:13px Arial;margin:32px}table{border-collapse:collapse;margin:15px 0}th,td{border:1px solid #aaa;padding:4px 8px;text-align:left}h2{font-size:17px}svg{width:700px;max-width:100%}.legend{display:flex;gap:14px}</style></head><body>${reports}</body></html>`;
 if(await api.saveReport(html))status('Report exported.');
}
function about(){utility('About StatWorkbench',`<p>StatWorkbench is an open-source desktop spreadsheet and statistical analysis application.</p><p>It combines an editable workbook with a local analysis engine. See Help for each procedure's inputs, assumptions, and limitations.</p><p>Source code is licensed under the MIT License. Third-party components retain their respective licenses.</p>`);}
function showPanel(name){
 $('side-panel').hidden=false;$('panel-heading').textContent=name;const body=$('panel-body');
 const section=(title,html)=>`<div class="panel-section"><h3>${title}</h3>${html}</div>`;
 const actions=(items)=>`<div class="panel-actions">${items.map(([action,label])=>`<button data-panel-action="${action}">${label}</button>`).join('')}</div>`;
 if(name==='Format'){
  body.innerHTML=section('Font',`<div class="panel-row"><select id="format-font"><option>Arial</option><option>Helvetica</option><option>Times New Roman</option><option>Courier New</option></select><input id="format-size" aria-label="Font size" type="number" min="6" max="72" value="11" style="width:45px"></div>${actions([['bold','<b>B</b>'],['italic','<i>I</i>'],['align-left','Left'],['align-center','Center'],['align-right','Right']])}<div class="panel-row"><label>Text color</label><input type="color" id="format-color" value="#000000"></div><div class="panel-row"><label>Fill color</label><input type="color" id="format-fill" value="#ffffff"></div>`)
   +section('Number',`<select id="format-number" aria-label="Number format" style="width:100%"><option value="General">General</option><option value="0.00">Number (2 decimals)</option><option value="0.0000">Number (4 decimals)</option><option value="0%">Percentage</option><option value="0.00E+00">Scientific</option><option value="yyyy-mm-dd">Date</option></select>`)
   +section('Cells',actions([['merge','Merge'],['unmerge','Unmerge'],['border','Bottom Border']]))
   +section('Insert',actions([['insert-rows','Rows'],['insert-columns','Columns'],['new-sheet','Worksheet']]))
   +section('Delete',actions([['delete-rows','Rows'],['delete-columns','Columns']]))
   +section('Clear',actions([['clear','Contents'],['clear-format','Formatting']]));
  $('format-font').onchange=guard(()=>book.formatSelection({fontFamily:$('format-font').value}));
  $('format-size').onchange=guard(()=>book.formatSelection({fontSize:Number($('format-size').value)}));
  $('format-color').onchange=guard(()=>book.formatSelection({textColor:$('format-color').value}));
  $('format-fill').onchange=guard(()=>book.formatSelection({fillColor:$('format-fill').value}));
  $('format-number').onchange=guard(()=>book.formatSelection({numberFormat:$('format-number').value}));
 }else if(name==='Edit'){
  body.innerHTML=section('Fill',actions([['fill-down','Down'],['fill-right','Right'],['fill-up','Up'],['fill-left','Left']]))
   +section('Functions',actions([['aggregate-SUM','Sum'],['aggregate-AVERAGE','Average'],['aggregate-COUNT','Count'],['aggregate-MAX','Max'],['aggregate-MIN','Min']]))
   +section('Sort',`<label class="panel-check"><input type="checkbox" id="sort-header" checked>First row contains labels</label>${actions([['sort-asc','Ascending'],['sort-desc','Descending']])}`)
   +section('Edit',actions([['undo','Undo'],['redo','Redo'],['clear','Clear Contents']]))
   +section('Worksheet',actions([['new-sheet','Insert Worksheet']]))
   +section('Analysis',actions([['history','Recent Analyses…']]));
 }else{
  body.innerHTML=`<input id="find-text" aria-label="Find" style="width:100%"><div class="panel-row"><label>Within</label><select id="find-within"><option>Worksheet</option><option>Workbook</option></select></div><div class="panel-row"><label>Search by</label><select id="find-order"><option>Rows</option><option>Columns</option></select></div><div class="panel-row"><label>Look in</label><select id="find-look"><option>Values</option><option>Formulas</option></select></div><div class="panel-row"><label><input id="find-case" type="checkbox">Match case</label></div><div class="panel-row"><label><input id="find-exact" type="checkbox">Match exactly</label></div><div class="panel-row"><label><input id="find-wildcards" type="checkbox">Use wildcards (* and ?)</label></div><div class="panel-actions"><button id="find-next">Find Next</button><button id="find-cancel">Cancel</button></div>`;
  $('find-cancel').onclick=()=>$('side-panel').hidden=true;$('find-next').onclick=guard(findNext);$('find-text').onkeydown=e=>{if(e.key==='Enter')guard(findNext)();};$('find-text').focus();
 }
 body.querySelectorAll('[data-panel-action]').forEach(button=>button.onclick=guard(()=>panelAction(button.dataset.panelAction)));
}
async function panelAction(action){
 if(action.startsWith('fill-'))return book.fillSelection(action.slice(5));
 if(action.startsWith('aggregate-'))return book.aggregateSelection(action.slice(10));
 if(action.startsWith('align-'))return book.formatSelection({horizontalAlignment:action.slice(6)});
 const commands={undo:()=>book.undo(),redo:()=>book.redo(),clear:()=>book.clearSelection(),'clear-format':()=>book.clearFormatting(),merge:()=>book.mergeSelection(true),unmerge:()=>book.mergeSelection(false),border:()=>book.formatSelection({borderBottom:true}),'insert-rows':()=>book.insertSelectionRows(),'delete-rows':()=>book.deleteSelectionRows(),'insert-columns':()=>book.insertSelectionColumns(),'delete-columns':()=>book.deleteSelectionColumns(),'sort-asc':()=>book.sortSelection(true,{hasHeader:$('sort-header').checked}),'sort-desc':()=>book.sortSelection(false,{hasHeader:$('sort-header').checked}),bold:()=>book.formatSelection({bold:!book.getSelectionStyle?.().bold}),italic:()=>book.formatSelection({italic:!book.getSelectionStyle?.().italic}),history,'new-sheet':async()=>{const name=await promptText('Insert Worksheet','Name','Sheet');if(name)await book.addMatrix(name,[]);}};
 return commands[action]?.();
}
let lastFind=null;
async function findNext(){
 const query=$('find-text').value;if(!query)return;
 const sensitive=$('find-case').checked,exact=$('find-exact').checked,wildcards=$('find-wildcards').checked,formula=$('find-look').value==='Formulas';
 const sheets=$('find-within').value==='Workbook'?book.getSheets():book.getSheets().filter(s=>s.id===book.getActiveSheetId()),found=[];
 const pattern=wildcards?new RegExp((exact?'^':'')+[...query].map(c=>c==='*'?'.*':c==='?'?'.':c.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('')+(exact?'$':''),sensitive?'':'i'):null;
 const match=value=>{if(value===null||value===undefined)return false;const text=String(value);if(pattern)return pattern.test(text);const a=sensitive?text:text.toLowerCase(),b=sensitive?query:query.toLowerCase();return exact?a===b:a.includes(b);};
 const snapshot=formula?book.getSnapshot():null;
 for(const s of sheets){
  if(formula){for(const [r,row] of Object.entries(snapshot.sheets[s.id].cellData||{}))for(const [c,cell]of Object.entries(row))if(cell?.f&&match(cell.f))found.push({id:s.id,row:Number(r),col:Number(c)});}
  else{const m=await book.readSheet(s.id);m.forEach((row,r)=>row.forEach((v,c)=>{if(match(v))found.push({id:s.id,row:r,col:c});}));}
 }
 if(!found.length)return toast('No matching cells.');
 if($('find-order').value==='Columns')found.sort((a,b)=>a.id.localeCompare(b.id)||a.col-b.col||a.row-b.row);
 const signature=[query,sensitive,exact,wildcards,formula,$('find-within').value,$('find-order').value].join('|');
 const previous=signature===lastFind?.signature?found.findIndex(f=>f.id===lastFind.id&&f.row===lastFind.row&&f.col===lastFind.col):-1;
 lastFind={...found[(previous+1)%found.length],signature};await book.selectRange(lastFind.id,`${columnLabel(lastFind.col)}${lastFind.row+1}`);
}
$('zoom').onchange=guard(()=>book.setZoom(Number.parseInt($('zoom').value)/100));
$('formula-value').oninput=()=>{const {sheetId,row,column}=book.getSelection();pendingFormula={sheetId,row,column,value:$('formula-value').value};changed();};
$('formula-value').onkeydown=guard(async e=>{if(e.key==='Enter'){e.preventDefault();await commitInput();$('formula-value').blur();}else if(e.key==='Escape'){pendingFormula=null;onSelection(book.getSelection());$('formula-value').blur();}});
$('formula-value').onblur=guard(()=>commitInput());
$('panel-close').onclick=()=>$('side-panel').hidden=true;
$('analysis-sheet').onchange=guard(async()=>{await refreshVariableList();await refreshGroupLevels();});$('labels-first-row').onchange=guard(async()=>{await refreshVariableList();await refreshGroupLevels();});$('variable-list').ondblclick=()=>assignVariables();$('reset-options').onclick=()=>renderOptions(true);$('analysis-form').onsubmit=e=>{e.preventDefault();guard(runAnalysis)();};for(const id of ['analysis-close','cancel-analysis'])$(id).onclick=()=>{if(!busy)$('analysis-dialog').close();};$('analysis-help').onclick=analysisHelp;$('preferences').onclick=preferences;$('range-selection-return').onclick=guard(()=>finishPicking());$('range-selection-cancel').onclick=guard(()=>finishPicking(true));
document.addEventListener('pointerdown',e=>{if(!e.target.closest('#dropdown,#app-menu,.category-button'))closeMenu();});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu();if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='s'){e.preventDefault();guard(saveProject)();}if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='f'){e.preventDefault();showPanel('Find');}});
api.onMenu(action=>{const commands={toolbar:customizeQuickAccess,migration:migrationGuide,new:newWorkbook,import:importData,'open-project':openProject,save:saveProject,export:exportData,'export-original':exportOriginalProject,report:exportReport,about,run:runAnalysis,find:()=>showPanel('Find'),format:()=>showPanel('Format'),preferences,'spreadsheet-reconnect':reconnectSpreadsheet,history,favorites:manageFavorites,'favorite-save':saveFavorite,charts:showCharts,example:exampleData,undo:()=>book.undo(),redo:()=>book.redo()};if(action==='excel-addin')guard(async()=>{await ready;await processExcelCommand();})();else if(action.startsWith('spreadsheet:'))guard(()=>selectSpreadsheet(action.slice(12)))();else if(action.startsWith('analysis:'))guard(()=>openAnalysis(action.slice(9)))();else if(action.startsWith('recent:'))guard(()=>openRecent(action.slice(7)))();else if(action.startsWith('favorite:'))guard(()=>openFavorite(action.slice(9)))();else if(commands[action])guard(commands[action])();});
if(api.environment?.desktop){$('app-menu').hidden=true;$('browser-title').hidden=true;}
const ready=(async()=>{try{prefs=safePreferences(await api.loadPreferences?.()||{});externalApps=await api.listSpreadsheets?.()||[];}catch(error){toast('Could not load Preferences: '+error.message,true);}catalog=(await api.catalog()).map(p=>({...p,name:procedureNames.find(n=>n.id===p.id)?.name||p.name})).sort((a,b)=>procedureNames.findIndex(n=>n.id===a.id)-procedureNames.findIndex(n=>n.id===b.id));book=await createSpreadsheet($('spreadsheet'),{onChange:changed,onSelection});try{favoritePresets=await api.listFavorites();recentPresets=await api.listRecent?.()||[];}catch(error){toast('Could not load Favorites: '+error.message,true);}setupMenus();clean();status('Ready');await guard(processExcelCommand)();})();ready.catch(e=>{status(`Startup failed: ${e.message}`);toast(e.message,true);});
window.runDesktopSmokeTest=async()=>{
 await ready;prefs={...DEFAULT_PREFERENCES,quickAccess:[]};await api.savePreferences?.(prefs);await exampleData();const dataSheet=book.getActiveSheetId();
 await addQuickAccess('analysis:10052');if($('quick-access').hidden||!$('quick-access').textContent.includes('summarized'))throw new Error('Quick Access command did not render');if(!(await api.loadPreferences()).quickAccess.includes('analysis:10052'))throw new Error('Quick Access did not persist');prefs.quickAccess=[];await api.savePreferences(prefs);renderQuickAccess();
 migrationGuide();if([...document.querySelectorAll('[data-migration]')].some(button=>!catalog.some(p=>p.id===button.dataset.migration)))throw new Error('Migration guide targets a missing procedure');$('utility-dialog').close();
 preferences();$('pref-decimals').value='15';$('pref-percentProbabilities').checked=true;$('pref-randomSeed').value='17';await $('utility-close').onclick();if((await api.loadPreferences()).decimals!==15||prefs.randomSeed!==17)throw new Error('Preferences did not persist');prefs={...DEFAULT_PREFERENCES,quickAccess:[]};await api.savePreferences(prefs);

 let renderedControls=0;
 for(const p of catalog){
  console.log('Checking dialog '+p.id);
  await openAnalysis(p.id);const layout=layouts[p.id]||{};
  for(const f of p.fields){
   if(f.key==='confidence'||(f.key==='alpha'&&!layout.alpha))continue;
   const range=['column','columns'].includes(f.type),selector=`[data-${range?'range':'option'}="${CSS.escape(f.key)}"]`,inputs=$('analysis-form').querySelectorAll(selector);
   if(inputs.length!==1)throw new Error(`${p.id}: expected one control for ${f.key}, found ${inputs.length}`);
   const input=inputs[0];if(f.type==='select'&&input.options.length!==f.options.length)throw new Error(`${p.id}: missing choices in ${f.key}`);
   if(layout[f.key]?.cellReference&&!document.querySelector(`[data-pick-scalar="${CSS.escape(f.key)}"]`))throw new Error(`${p.id}: missing scalar picker ${f.key}`);
   if(!range&&f.default!==undefined){const actual=input.type==='checkbox'?input.checked:input.value;if(String(actual)!==String(f.default))throw new Error(`${p.id}: default differs for ${f.key}: ${actual}`);}
   renderedControls++;
  }
  const footer=$('run-analysis').getBoundingClientRect();if(footer.bottom>innerHeight||footer.top<0)throw new Error(`${p.id}: dialog action buttons are outside the window`);
  if(p.id==='1102'||p.id==='1301'){
   const parentKey=p.id==='1102'?'sta.show.DS':'sta.reg.ao.residuals',parent=document.querySelector(`[data-option="${parentKey}"]`);parent.checked=false;parent.dispatchEvent(new Event('change'));
   const options=readOptions();for(const f of p.fields.filter(f=>f.type==='boolean'&&layout[f.key]?.parent===parentKey))if(options[f.key]!==false)throw new Error(`${p.id}: disabled child ${f.key} would still run`);
  }
  if(p.id==='1530'){
   const lag=document.querySelector('[data-option="sta.time.adf.lag.selection"]');lag.value='0';lag.dispatchEvent(new Event('change'));const order=document.querySelector('[data-option="p"]');if(!order.disabled)throw new Error('DF zero-lag mode leaves p active');order.value='invalid';readOptions();
  }
  $('analysis-dialog').close();
 }
 const preset=await api.saveFavorite({name:'Desktop verification',id:'1001',options:{'sta.bst.ds.ao.0':true},ranges:{columns:"'Data'!B:D"},labels:true});
 await openFavorite(preset.favoriteId);if(state.ranges.columns!=="'Data'!B:D"||!document.querySelector('[data-option="sta.bst.ds.ao.0"]').checked)throw new Error('Favorite lost its options or range');$('analysis-dialog').close();
 await api.deleteFavorite(preset.favoriteId);favoritePresets=await api.listFavorites();if(favoritePresets.some(f=>f.favoriteId===preset.favoriteId))throw new Error('Favorite was not removed');
 await openAnalysis('1001');setRange('columns',"'Data'!B:D");
 const hist=document.querySelector('[data-option="sta.bst.ds.ao.0"]');if(hist)hist.checked=true;
 const result=await runAnalysis();if(!result.tables.length)throw new Error('No descriptive results');
 if(result.charts.length){const ids=book.getChartImages(results.at(-1).resultSheetId);editChart(results.length-1,0);$('chart-title').value='Edited verification chart';$('chart-color-0').value='#aa2244';await $('utility-close').onclick();$('utility-dialog').close();if(result.charts[0].title!=='Edited verification chart'||result.charts[0].series[0].color!=='#aa2244'||book.getChartImages(results.at(-1).resultSheetId).length!==ids.length)throw new Error('Chart edit was not retained in worksheet');const chartRecord=book.getSnapshot().custom?.statworkbenchCharts?.find(item=>item.drawingId===ids[0]);if(chartRecord?.chart.title!=='Edited verification chart')throw new Error('Edited chart definition was not retained in snapshot');}
 if(!(await api.listRecent()).some(item=>item.id==='1001'))throw new Error('Recent analysis did not persist');

 if(book.getActiveSheetId()===dataSheet)throw new Error('Result worksheet was not selected');
 await book.selectRange(dataSheet,'F1');$('formula-value').value='=SUM(B2:B4)';$('formula-value').dispatchEvent(new Event('input'));await commitInput();
 const values=await book.readSheet(dataSheet);if(values[0]?.[5]!==431)throw new Error('Formula did not calculate');
 await saveProject();await openProject();
 if(book.getSheets().length<3||results.length!==1)throw new Error('Project lost sheets or analyses');
 if((await book.readSheet(dataSheet))[0]?.[5]!==431)throw new Error('Project lost computed formula');
 if(!book.getSnapshot().custom?.statworkbenchCharts?.some(item=>item.chart.title==='Edited verification chart'))throw new Error('Project lost editable chart definitions');
 await exportReport();await importData();await importData();
 const importedSheet=book.getSheets().find(sheet=>sheet.name==='Data'),parameters=book.getSheets().find(sheet=>sheet.name==='Parameters');
 if(!importedSheet||!parameters||book.getSheets().length!==2||results.length!==0)throw new Error('SPJS import did not restore the complete workbook');
 const imported=await book.readSheet(importedSheet.id);
 const namedArray=await book.readSheet(parameters.id);if(namedArray[0]?.[1]!==15||namedArray[3]?.[0]!==4||namedArray[4]?.[0]!==6)throw new Error('Original named or array formula failed recalculation');
 if(imported[0]?.[0]!=='Original cell'||imported[0]?.[1]!==42||imported[1]?.[1]!==84||imported[1]?.[3]!=='=1+1')throw new Error('SPJS import shifted cells, used stale formula cache, or evaluated literal text');
 if(imported[1]?.[2]!=='#N/A'||imported[2]?.[3]!=='#N/A')throw new Error('Unsupported imported formula cache leaked into current calculations');
 const importedSnapshot=book.getSnapshot().sheets[importedSheet.id];
 if(!importedSnapshot.mergeData.some(range=>range.startRow===3&&range.endColumn===3)||book.getChartImages(importedSheet.id).length!==1)throw new Error('Project merge or chart was not restored');
 book.selectRange(importedSheet.id,'B1');if(book.getSelectionStyle().numberFormat!=='0.00')throw new Error('Named number format was not restored');
 await exportData();
 await openAnalysis('3100');document.querySelector('[data-option="count"]').value='20';document.querySelector('[data-option="variables"]').value='2';const generated=await runAnalysis();
 if(!generated.dataset||generated.dataset.rows.length!==20||(await book.readSheet(book.getActiveSheetId())).length!==21)throw new Error('Generated data was not retained in a worksheet');
 await saveProject();await openProject();
 const restored=book.getSnapshot().sheets[importedSheet.id],importMetadata=restored.cellData[1][2].custom?.statplusImport;
 if(importMetadata?.formula!=='UNKNOWN_FUNCTION(1)'||importMetadata.cachedValue!==999||importMetadata.formulaStatus!=='unsupported')throw new Error('Imported formula metadata did not survive project save/open');
 if((await book.readRange(importedSheet.id,'B2'))[0][0]!==84||book.getChartImages(importedSheet.id).length!==1)throw new Error('Imported formulas or chart did not survive project save/open');
 if(results.length!==1||!book.getSheets().some(sheet=>sheet.id===results[0].resultSheetId))throw new Error('New analysis results were lost after original-project import');
 await book.selectSheet(results[0].resultSheetId);
 const copulaData={name:'Copula verification',columns:['x','y'],rows:Array.from({length:48},(_,i)=>[i+1,Math.sin(i*.7)+i*.08])};
 const copula=await api.analyze({analysis:'copula.bivariate',data:copulaData,options:{x:'x',y:'y',family:'gaussian',samples:24,seed:17,diagnostics:false}});
 if(copula.dataset?.rows.length!==24||!copula.tables.length||!copula.charts.length)throw new Error('Copula worker/report integration failed');
 for(const chart of copula.charts)if(!renderChart(chart).includes('<svg'))throw new Error('Copula chart did not render');
 await exportOriginalProject();
 clearTimeout(toastTimer);$('toast').hidden=true;status('Desktop verification complete');
 await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
 return {ok:true,catalog:catalog.length,coreCatalog:catalog.filter(p=>coreProcedureNames.some(n=>n.id===p.id)).length,extensions:catalog.filter(p=>extensionProcedureNames.some(n=>n.id===p.id)).map(p=>p.id),copulas:true,legacyProjectExport:true,originalNamedArrayFormulas:true,renderedControls,preferences:true,quickAccess:true,chartEditing:true,migrationGuide:true,recent:true,favorites:true,worksheetReports:true,rangeInputs:true,savedProject:true,imports:true,legacyProject:true,originalFormulaRecalculation:true,originalFormulaProvenance:true,export:true,generatedData:true,formulaCell:431};
};
