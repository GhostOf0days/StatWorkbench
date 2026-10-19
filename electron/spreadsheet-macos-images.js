// Fixed JXA adapter: arguments are data, never evaluated as source.
// Excel's file-based picture insertion fails on some sandboxed Mac builds.
// Its native paste command accepts an image; preserve every clipboard item/type.
ObjC.import('AppKit');
function run(args){
 var app=Application('com.microsoft.Excel'),sheet=app.workbooks.byName(args[0]).worksheets.byName(args[1]);
 if(!sheet.exists())throw Error('The target Excel result worksheet is no longer open.');
 var data=$.NSData.dataWithContentsOfFile($(args[2]));if(!data)throw Error('The report image is unavailable.');
 var bitmap=$.NSImage.alloc.initWithData(data);if(!bitmap)throw Error('The report image is invalid.');
 var board=$.NSPasteboard.generalPasteboard,saved=[],originalChangeCount=Number(board.changeCount),items=board.pasteboardItems;
 for(var i=0;i<items.count;i++){
  var source=items.objectAtIndex(i),copy=$.NSPasteboardItem.alloc.init,types=source.types;
  for(var j=0;j<types.count;j++){var type=types.objectAtIndex(j),bytes=source.dataForType(type);if(!bytes||!copy.setDataForType(bytes,type))throw Error('Could not preserve the existing clipboard. Copy a simple item and retry.');}
  saved.push(copy);
 }
 var image=$.NSPasteboardItem.alloc.init;image.setDataForType(data,$('public.png'));image.setDataForType(bitmap.TIFFRepresentation,$('public.tiff'));
 var before=sheet.shapes.name()||[],changeCount=null,result;
 if(Number(board.changeCount)!==originalChangeCount)throw Error('The clipboard changed during chart transfer. Retry the report.');
 try{
  board.clearContents;changeCount=Number(board.changeCount);var written=board.writeObjects($([image]));changeCount=Number(board.changeCount);if(!written)throw Error('Could not transfer the report image.');
  app.pasteWorksheet(sheet);
  var created=sheet.shapes().filter(function(shape){return before.indexOf(shape.name())<0;});
  if(created.length!==1)throw Error('Excel did not create one report image.');
  var picture=created[0];picture.leftPosition=0;picture.top=Number(args[3]);picture.width=680;picture.height=420;
  result={inserted:true,name:picture.name()};
 }finally{
  // A user copy during the request takes priority over restoring older content.
  if(changeCount!==null&&Number(board.changeCount)===changeCount){board.clearContents;if(saved.length&&!board.writeObjects($(saved)))throw Error('The report was pasted, but the original clipboard could not be restored.');if(result)result.clipboardRestored=true;}
 }
 return JSON.stringify(result);
}
