import {numericOptionError} from './dialog-controls.js';
export function columnLabel(index) {let name='';for(index++;index>0;index=Math.floor((index-1)/26))name=String.fromCharCode(65+(index-1)%26)+name;return name;}
export function columnIndex(label) {let index=0;for(const c of label.toUpperCase())index=index*26+c.charCodeAt(0)-64;return index-1;}
export function quoteSheet(name) {return `'${String(name).replaceAll("'","''")}'`;}
export function splitReferences(text) {
  const parts=[];let current='',quote=false;
  for(let i=0;i<text.length;i++) {const c=text[i];if(c==="'"){current+=c;if(quote&&text[i+1]==="'"){current+=text[++i];continue;}quote=!quote;}else if((c===','||c===';')&&!quote){if(current.trim())parts.push(current.trim());current='';}else current+=c;}
  if(quote)throw new Error('The worksheet name has an unmatched quote.');if(current.trim())parts.push(current.trim());return parts;
}
export function parseReference(text,sheets,defaultId) {
  const match=text.trim().match(/^(?:(?:'((?:[^']|'')+)'|([^!]+))!)?\$?([A-Za-z]+)(?:\$?(\d+))?(?::\$?([A-Za-z]+)(?:\$?(\d+))?)?$/);
  if(!match)throw new Error(`Invalid range “${text}”. Use A:C or A1:C25.`);
  const name=match[1]?.replaceAll("''","'")??match[2];const sheet=name?sheets.find(s=>s.name===name):sheets.find(s=>s.id===defaultId);
  if(!sheet)throw new Error(`Worksheet ${name||defaultId} was not found.`);
  const startColumn=columnIndex(match[3]),endColumn=columnIndex(match[5]||match[3]);
  if(Boolean(match[4])!==Boolean(match[6])&&match[5])throw new Error('Use two complete cell addresses or two column letters.');
  const startRow=match[4]?Number(match[4])-1:0,endRow=match[6]?Number(match[6])-1:match[4]?startRow:null;
  if(startColumn>endColumn||startRow<0||endRow!==null&&endRow<startRow||endColumn>=1000||endRow>=100000)throw new Error('Range is outside supported worksheet bounds.');
  return {sheetId:sheet.id,sheetName:sheet.name,startColumn,endColumn,startRow,endRow};
}
export async function prepareAnalysis(adapter,procedure,ranges,options,labels=true,defaultSheetId) {
  const sheets=adapter.getSheets(),cache=new Map(),columns=[],vectors=[],inputOptions={...options},references=new Map(),constants=[];
  for(const field of procedure.fields.filter(f=>['column','columns'].includes(f.type))) {
    if(field.enabled===false){inputOptions[field.key]=field.type==='columns'?[]:null;continue;}
    const raw=String(ranges[field.key]??'').trim();
    if(field.constantSubstitute&&raw!==''&&Number.isFinite(Number(raw))){constants.push({field,value:Number(raw)});continue;}
    const tokens=splitReferences(ranges[field.key]||'');
    if(!tokens.length){if(field.required)throw new Error(`Select ${field.label}.`);if(field.type==='columns')inputOptions[field.key]=[];continue;}
    const names=[];
    for(const token of tokens) {
      const ref=parseReference(token,sheets,defaultSheetId||adapter.getActiveSheetId());
      if(!cache.has(ref.sheetId))cache.set(ref.sheetId,await adapter.readSheet(ref.sheetId));
      const matrix=cache.get(ref.sheetId),end=ref.endRow??matrix.length-1;
      if(end<ref.startRow)throw new Error(`${field.label} has no data.`);
      if((end-ref.startRow+1)*(ref.endColumn-ref.startColumn+1)>2000000)throw new Error('Selected range is too large.');
      for(let c=ref.startColumn;c<=ref.endColumn;c++) {
        const identity=`${ref.sheetId}:${c}:${ref.startRow}:${end}:${labels}`;
        let name=references.get(identity);
        if(!name) {
          const raw=labels?matrix[ref.startRow]?.[c]:null,base=raw!==null&&raw!==undefined&&String(raw).trim()?String(raw):columnLabel(c);
          name=base;let suffix=2;while(columns.includes(name))name=`${base} (${suffix++})`;
          const first=ref.startRow+(labels?1:0),values=[];
          for(let r=first;r<=end;r++)values.push(matrix[r]?.[c]??null);
          columns.push(name);vectors.push(values);references.set(identity,name);
        }
        if(!names.includes(name))names.push(name);
      }
    }
    if(field.type==='column'&&names.length!==1)throw new Error(`${field.label} requires one column.`);
    inputOptions[field.key]=field.type==='column'?names[0]:names;
  }
  for(const field of procedure.fields.filter(f=>f.cellReference&&['number','integer'].includes(f.type))) {
    if(field.enabled===false)continue;
    const value=inputOptions[field.key];
    if(typeof value!=='string'||value.trim()==='')continue;
    if(Number.isFinite(Number(value))){inputOptions[field.key]=Number(value);continue;}
    const ref=parseReference(value,sheets,defaultSheetId||adapter.getActiveSheetId());
    if(ref.endRow===null||ref.startRow!==ref.endRow||ref.startColumn!==ref.endColumn)throw new Error(`${field.label} requires a single cell or a number.`);
    if(!cache.has(ref.sheetId))cache.set(ref.sheetId,await adapter.readSheet(ref.sheetId));
    const scalar=cache.get(ref.sheetId)[ref.startRow]?.[ref.startColumn];
    if(typeof scalar!=='number'||!Number.isFinite(scalar))throw new Error(`${field.label} must refer to a numeric cell.`);
    const error=numericOptionError(field,scalar,field);if(error)throw new Error(error);
    inputOptions[field.key]=scalar;
  }
  // A constant range uses the same row alignment as the measured data. It is
  // never interpreted as a cell address or discarded as a first-row label.
  const constantCount=vectors.length?Math.max(...vectors.map(v=>v.length)):1;
  for(const {field,value} of constants){
    const base=`Constant (${field.label})`;let name=base,suffix=2;
    while(columns.includes(name))name=`${base} (${suffix++})`;
    columns.push(name);vectors.push(Array(constantCount).fill(value));
    inputOptions[field.key]=field.type==='columns'?[name]:name;
  }
  // Parameter-only procedures still use the same valid worker dataset boundary.
  if(!columns.length)return {analysis:procedure.id,data:{name:'Parameters',columns:['Value'],rows:[]},options:inputOptions};
  const count=Math.max(...vectors.map(v=>v.length));
  if(count*columns.length>2000000)throw new Error('Combined input exceeds two million cells.');
  const rows=Array.from({length:count},(_,r)=>vectors.map(v=>v[r]??null));
  return {analysis:procedure.id,data:{name:sheets.find(s=>s.id===(defaultSheetId||adapter.getActiveSheetId()))?.name||'Data',columns,rows},options:inputOptions};
}
