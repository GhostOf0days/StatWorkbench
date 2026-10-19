// SPDX-License-Identifier: MIT
// Chart definitions follow the actual drawing source and placement, including
// undo/redo. The registry stores only the chart definitions it creates.
const clone=value=>JSON.parse(JSON.stringify(value));
const key=(sheetId,drawingId)=>JSON.stringify([sheetId,drawingId]);
function cellAt(offset,count,size){
 let position=0;
 for(let i=0;i<count;i++){
  const extent=Math.max(0,Number(size(i))||0);
  if(position+extent>offset||i===count-1)return i;
  position+=extent;
 }
 return 0;
}
function position(sheet,drawing,fallback){
 const p=drawing.placement||{},bounds=drawing.bounds||{};
 const row=p.from?.row??cellAt(Math.max(0,bounds.top||0),sheet.getMaxRows(),i=>sheet.getRowHeight(i));
 const column=p.from?.column??cellAt(Math.max(0,bounds.left||0),sheet.getMaxColumns(),i=>sheet.getColumnWidth(i));
 return {row,column,width:bounds.width??p.width??fallback.width,height:bounds.height??p.height??fallback.height};
}

export class WorkbookChartRegistry {
 constructor(){this.records=new Map();}
 register(sheetId,drawingId,chart,placement,source,originalIndex){
  const identity=key(sheetId,drawingId),previous=this.records.get(identity);
  const entry={sheetId,drawingId,chart:clone(chart),position:clone(placement)};
  const original=originalIndex??previous?.entry.originalIndex;
  if(Number.isInteger(original)&&original>=0)entry.originalIndex=original;
  const versions=previous?.versions||new Map();
  versions.set(source,entry);
  this.records.set(identity,{entry,versions});
 }
 restore(entries,sheets){
  this.records.clear();
  if(!Array.isArray(entries))return;
  const byId=new Map(sheets.map(sheet=>[sheet.getSheetId(),sheet]));
  for(const entry of entries.slice(0,1000)){
   if(!entry||typeof entry.sheetId!=='string'||typeof entry.drawingId!=='string'||!entry.chart||typeof entry.chart!=='object')continue;
   const image=byId.get(entry.sheetId)?.getImages().find(image=>image.getId()===entry.drawingId);
   if(image)this.register(entry.sheetId,entry.drawingId,entry.chart,entry.position||{},image.toBuilder().getSource(),entry.originalIndex);
  }
 }
 snapshot(sheets){
  const result=[];
  for(const sheet of sheets){
   const sheetId=sheet.getSheetId(),images=new Map(sheet.getImages().map(image=>[image.getId(),image]));
   if(!images.size)continue;
   for(const drawing of sheet.getDrawingLayout().drawings){
    const image=images.get(drawing.drawingId);if(!image)continue;
    const source=image.toBuilder().getSource(),record=this.records.get(key(sheetId,drawing.drawingId));
    let entry=record?.versions.get(source);
    if(!record){
     // Copied chart drawings are new charts, never replacements for an
     // imported original. Arbitrary pictures have no registered source.
     for(const candidate of this.records.values())if(candidate.versions.has(source)){
      entry={...candidate.versions.get(source),sheetId,drawingId:drawing.drawingId};delete entry.originalIndex;break;
     }
    }
    if(!entry)continue;
    result.push({...clone(entry),position:position(sheet,drawing,entry.position)});
   }
  }
  return result;
 }
}

/** Track imported picture identity while reading source and geometry from the
 * live drawings. Chart images have their own semantic registry and are omitted.
 */
export class WorkbookImageRegistry {
 constructor(){this.records=new Map();}
 register(sheetId,drawingId,source,placement,native={},originalIndex,displaySource=source){
  const entry={sheetId,drawingId,source,position:clone(placement),native:clone(native)};
  if(Number.isInteger(originalIndex)&&originalIndex>=0)entry.originalIndex=originalIndex;
  this.records.set(key(sheetId,drawingId),{entry,displaySource});
 }
 restore(entries,sheets){
  this.records.clear();
  if(!Array.isArray(entries))return;
  const byId=new Map(sheets.map(sheet=>[sheet.getSheetId(),sheet]));
  for(const entry of entries.slice(0,1000)){
   if(!entry||typeof entry.sheetId!=='string'||typeof entry.drawingId!=='string'||typeof entry.source!=='string')continue;
   const image=byId.get(entry.sheetId)?.getImages().find(image=>image.getId()===entry.drawingId);
   if(image)this.register(entry.sheetId,entry.drawingId,entry.source,entry.position||{},entry.native||{},entry.originalIndex,image.toBuilder().getSource());
  }
 }
 snapshot(sheets,charts=[]){
  const excluded=new Set(charts.map(chart=>key(chart.sheetId,chart.drawingId))),result=[];
  for(const sheet of sheets){
   const sheetId=sheet.getSheetId(),images=new Map(sheet.getImages().map(image=>[image.getId(),image]));
   if(!images.size)continue;
   for(const drawing of sheet.getDrawingLayout().drawings){
    const drawingId=drawing.drawingId,image=images.get(drawingId);
    if(!image||excluded.has(key(sheetId,drawingId)))continue;
    const source=image.toBuilder().getSource(),record=this.records.get(key(sheetId,drawingId));
    let matched=record,entry=record?.entry;
    if(!record){
     for(const candidate of this.records.values())if(candidate.displaySource===source){
      matched=candidate;entry={...candidate.entry,sheetId,drawingId};delete entry.originalIndex;break;
     }
    }
    const bounds=drawing.bounds||{};
    const current={...clone(entry||{}),sheetId,drawingId,source:entry&&(!record||record.displaySource===source)?entry.source:source,
     position:{left:bounds.left??entry?.position.left??0,top:bounds.top??entry?.position.top??0,width:bounds.width??entry?.position.width,height:bounds.height??entry?.position.height},native:clone(entry?.native||{})};
    const anchor=drawing.placement?.kind;
    if(['0','1','2'].includes(anchor)){
     current.native.dynamicMove=anchor!=='2';current.native.dynamicSize=anchor==='1';current.native.fixedPosition=false;
    }
    // The canvas display scales with a drawing resize. Reapplying its original
    // contain/center/border rules at the new dimensions would look different.
    // Export those changed pictures as the displayed pixels stretched to their
    // current bounds. Keep the original model for undo until the next reload.
    const resized=entry&&['width','height'].some(axis=>Math.abs(current.position[axis]-entry.position[axis])>0.11);
    if(resized&&matched&&matched.displaySource===source&&source!==entry.source&&entry.native?.isVisible!==false){
     current.source=source;
     Object.assign(current.native,{pictureStretch:0,borderStyle:'none',borderWidth:0,borderRadius:-1,backColor:null,borderColor:null});
     current.flattenedStyle=true;
    }
    result.push(current);
   }
  }
  return result;
 }
}
