const savedPath=value=>typeof value==='string'&&/^(?:\/|[A-Za-z]:[\\/]|\\\\)/.test(value);
const pathKey=value=>/^(?:[A-Za-z]:[\\/]|\\\\)/.test(value)?value.replaceAll('\\','/').toLowerCase():value;
export class ExternalWorkbook {
 constructor(api,app,source={}){this.api=api;this.app=app;this.snapshot=null;this.source=source;}
 remember(value){
  if(this.source.expectedWorkbookPath&&(!savedPath(value.path)||pathKey(value.path)!==pathKey(this.source.expectedWorkbookPath)))throw new Error('The connected workbook was replaced or moved. Reconnect the spreadsheet before continuing.');
  this.snapshot=value;
  this.source={...this.source,workbook:value.workbook};
  if(value.activeSheetId)this.source.sheet=value.activeSheetId;
  if(this.app==='excel'&&value.excelProcessId)this.source.excelProcessId=value.excelProcessId;
  if(this.app==='numbers'&&value.workbookId)this.source.workbookId=value.workbookId;
  if(this.app==='excel'&&savedPath(value.path))this.source.expectedWorkbookPath=value.path;
 }
 async connect(){const value=await this.api.externalSpreadsheet({...this.source,app:this.app,operation:'read'});this.remember(value);return value;}
 getSheets(){return this.snapshot?.sheets||[];}
 getActiveSheetId(){return this.snapshot?.activeSheetId;}
 getName(){return this.snapshot?.workbook||'';}
 async readSheet(sheet){const value=await this.api.externalSpreadsheet({...this.source,app:this.app,operation:'read',workbook:this.getName(),sheet});this.remember(value);return value.matrix;}
 async activate(){return this.api.externalSpreadsheet({...this.source,app:this.app,operation:'activate'});}
 async selection(){
  const value=await this.api.externalSpreadsheet({...(this.source.excelProcessId?{excelProcessId:this.source.excelProcessId}:{}),...(this.source.expectedWorkbookPath?{expectedWorkbookPath:this.source.expectedWorkbookPath}:{}),app:this.app,operation:'selection'});
  const same=this.app==='numbers'&&this.source.workbookId?value.workbookId===this.source.workbookId:value.workbook===this.getName();
  if(!same)throw new Error('Select cells in '+this.getName()+' before returning.');
  if(!value.selection)throw new Error('Select one rectangular range in the spreadsheet.');
  this.remember({...value,activeSheetId:value.selection.sheetId});return value.selection;
 }
 async write(matrix,name,preferences,format,chartImages=[],destination=this.getName(),formats=[]){
  const target=typeof destination==='string'?{workbook:destination}:destination;
  const source={...this.source};
  // A generated dataset may follow a report into a newly created workbook.
  // Do not let the original document's ID override that explicit destination.
  if(target.workbookId||target.workbook!==this.getName()){delete source.workbookId;delete source.expectedWorkbookPath;}
  return this.api.externalSpreadsheet({...source,...target,app:this.app,operation:'write',matrix,name,outputMode:preferences.outputMode,font:preferences.font,fontSize:preferences.fontSize,numberFormat:format,chartImages,formats});
 }
}
