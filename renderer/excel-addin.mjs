// A single-column field receives the first selected column; other inputs remain explicit.
export function excelLaunchRanges(request,fields,quoteSheet){
 const first=fields.find(f=>['column','columns'].includes(f.type));
 if(!first)return {};
 const firstColumn=request.rangeA1.match(/^[A-Z]+/)[0];
 const range=first.type==='column'?request.rangeA1.replace(/:[A-Z]+([0-9]*)$/,(whole,row)=>':'+firstColumn+row):request.rangeA1;
 return {[first.key]:`${quoteSheet(request.sheet)}!${range}`};
}

export async function applyExcelCommand(request,actions){
 // Preferences belong to the app, so they must not silently change an open analysis's source.
 if(request.command==='preferences')return actions.preferences();
 // Invalidate the old dialog before the asynchronous source change can complete.
 actions.resetAnalysis();
 await actions.connect({workbook:request.workbook,sheet:request.sheet,excelProcessId:request.excelProcessId});
 if(request.command.startsWith('analysis:'))await actions.openAnalysis(request.command.slice(9),request);
}
