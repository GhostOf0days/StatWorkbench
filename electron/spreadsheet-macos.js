// JavaScript for Automation. This fixed script receives data from a private JSON file.
ObjC.import('Foundation');
var bridgeStage='initialization';
function letters(index){var s='';for(index++;index;index=Math.floor((index-1)/26))s=String.fromCharCode(65+(index-1)%26)+s;return s;}
function column(name){var n=0;for(var i=0;i<name.length;i++)n=n*26+name.charCodeAt(i)-64;return n-1;}
function bounds(address){var clean=String(address).replace(/\$/g,'').split('!').pop(),m=clean.match(/^([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?$/i);if(!m)throw Error('Select one rectangular cell range.');return {startRow:+m[2]-1,startColumn:column(m[1].toUpperCase()),endRow:+(m[4]||m[2])-1,endColumn:column((m[3]||m[1]).toUpperCase()),rangeA1:clean};}
function limit(rows,cols){if(rows>100000||cols>1000||rows*cols>2000000)throw Error('The occupied spreadsheet rectangle exceeds100,000 rows,1,000 columns or two million cells.');}
function scalar(v){if(v===undefined||v===null)return null;if(v instanceof Date)return v.toISOString();if(typeof v==='number')return isFinite(v)?v:null;return ['string','boolean'].indexOf(typeof v)>=0?v:String(v);}
function canonicalPath(value){var text=String(value);if(/^file:\/\//i.test(text))text=ObjC.unwrap($.NSURL.URLWithString($(text)).path);return ObjC.unwrap($(text).stringByStandardizingPath.stringByResolvingSymlinksInPath);}
function literal(v){return typeof v==='string'?"'"+v:v===null?'':v;}
function unique(base,names){base=String(base||'Results').replace(/[\[\]:*?\/\\]/g,' ').slice(0,25)||'Results';var name=base,n=2,lower=names.map(function(value){return String(value).toLowerCase();});while(lower.indexOf(name.toLowerCase())>=0){var suffix=' ('+(n++)+')';name=base.slice(0,31-suffix.length)+suffix;}return name;}
function excel(p){
 var app=Application('com.microsoft.Excel');
 if(p.operation==='open'){app.open(Path(p.path));return {opened:true};}
 if(p.operation==='activate'&&!p.range&&!p.workbook&&!p.sheet&&!p.expectedWorkbookPath){app.activate();return {activated:true};}
 if(!app.running())throw Error('Open Microsoft Excel and a workbook before connecting.');
 bridgeStage='list Excel workbooks';var workbooks=app.workbooks();if(!workbooks.length&&p.operation!=='write')throw Error('Open a workbook in Microsoft Excel first.');
 bridgeStage='resolve Excel workbook';var wb=p.workbook?app.workbooks.byName(p.workbook):app.activeWorkbook;
 if(p.expectedWorkbookPath&&!(p.operation==='write'&&p.outputMode==='workbook')){var actualPath='';try{actualPath=wb.fullName();}catch(e){}if(!actualPath||canonicalPath(actualPath)!==canonicalPath(p.expectedWorkbookPath))throw Error('The connected Excel workbook was replaced or moved. Reconnect to the intended workbook.');}
 if(p.operation==='write'){
  if(p.outputMode==='workbook'||!workbooks.length){bridgeStage='create Excel workbook';wb=app.make({new:'workbook'});}
  if(!wb.exists())throw Error('The source Excel workbook is no longer open.');
  if(p.reportPath){
   // Copy a generated, macro-free OOXML worksheet so Excel owns editable chart objects.
   // Pin the target by name before opening the temporary workbook changes activeWorkbook.
   wb=app.workbooks.byName(wb.name());var destinationName=unique(p.name,wb.worksheets.name()),imported=null;
   try{
    bridgeStage='open generated Excel chart report';
    // The standard file-open event carries a file reference through macOS;
    // Excel's string-only openWorkbook command cannot access a fresh temp file.
    app.open(Path(p.reportPath));var opened=app.workbooks().filter(function(candidate){try{return canonicalPath(candidate.fullName())===canonicalPath(p.reportPath);}catch(e){return false;}});
    if(opened.length!==1)throw Error('The generated report workbook could not be identified.');imported=opened[0];
    if(canonicalPath(imported.fullName())!==canonicalPath(p.reportPath)||imported.worksheets().length!==1)throw Error('The generated report workbook could not be identified.');
    var sourceSheet=imported.worksheets[0];sourceSheet.name=destinationName;
    bridgeStage='copy editable Excel chart report';app.copyWorksheet(sourceSheet,{after:wb.worksheets[wb.worksheets().length-1]});
    var copied=wb.worksheets.byName(destinationName),nativeCount=(copied.chartObjects()||[]).length;
    if(nativeCount!==p.reportNativeCharts)throw Error('Excel did not retain every editable chart.');
    var imageCount=(copied.shapes()||[]).length-nativeCount;
    if(imageCount!==(p.reportImageCharts||0))throw Error('Excel did not retain every chart image.');
    var written=copied.ranges.byName('A1:'+letters(p.matrix[0].length-1)+p.matrix.length);
    var outcome={workbook:wb.name(),sheet:destinationName,rows:p.matrix.length,columns:p.matrix[0].length,reportFont:{name:written.fontObject.name(),size:written.fontObject.fontSize()},reportFormats:(p.formats||[]).map(function(item){return {range:item.range,numberFormat:copied.ranges.byName(item.range).numberFormat()};}),nativeChartsWritten:nativeCount,chartImagesWritten:imageCount};
   }finally{if(imported){var previousStage=bridgeStage;bridgeStage='close generated Excel chart source';imported.close({saving:'no'});bridgeStage=previousStage;}}
   bridgeStage='activate editable Excel chart report';app.activate();app.goto({reference:copied.ranges.byName('A1'),scroll:true});return outcome;
  }
  bridgeStage='create Excel worksheet';var names=wb.worksheets.name(),name=unique(p.name,names),sheet=app.make({new:'worksheet',at:wb,withProperties:{name:name}});
  var matrix=p.matrix,range=sheet.ranges.byName('A1:'+letters(matrix[0].length-1)+matrix.length);
  bridgeStage='write Excel cell values';range.value=matrix.map(function(row){return row.map(literal);});range.numberFormat=p.numberFormat;
  (p.formats||[]).forEach(function(item){sheet.ranges.byName(item.range).numberFormat=item.numberFormat;});
  bridgeStage='format Excel font';range.fontObject.name=p.font;range.fontObject.fontSize=p.fontSize;
  // The host inserts image-only reports with a fixed JXA handler after this data transfer.
  bridgeStage='activate Excel result worksheet';app.activate();app.goto({reference:sheet.ranges.byName('A1'),scroll:true});return {workbook:wb.name(),sheet:name,rows:matrix.length,columns:matrix[0].length,reportFont:{name:range.fontObject.name(),size:range.fontObject.fontSize()},reportFormats:(p.formats||[]).map(function(item){return {range:item.range,numberFormat:sheet.ranges.byName(item.range).numberFormat()};}),chartImagesWritten:0};
 }
 if(!wb.exists())throw Error('The selected Excel workbook is no longer open.');
 bridgeStage='resolve Excel worksheet';var sheets=wb.worksheets().map(function(s){return {id:s.name(),name:s.name()};}),sheet=p.sheet?wb.worksheets.byName(p.sheet):wb.activeSheet;
 if(!sheet.exists())throw Error('The selected Excel worksheet is no longer available.');
 if(p.operation==='activate'){var activationRange=p.range||'A1';if(!p.range)try{if(app.activeWorkbook.name()===wb.name()&&app.activeSheet.name()===sheet.name())activationRange=app.getAddress(app.selection,{rowAbsolute:false,columnAbsolute:false});}catch(e){}app.activate();app.goto({reference:sheet.ranges.byName(activationRange),scroll:true});return {activated:true,workbook:wb.name(),sheet:sheet.name(),range:activationRange};}
 bridgeStage='read Excel workbook metadata';var result={workbook:wb.name(),sheets:sheets,activeSheetId:sheet.name()};try{result.nativeShapeCount=sheet.shapes().length;}catch(e){}try{result.path=wb.fullName();}catch(e){}
 if(p.inspectCharts){
  bridgeStage='inspect editable Excel charts';var objects=sheet.chartObjects()||[];if(objects.length>100)throw Error('Too many charts to inspect.');
  result.nativeChartCount=objects.length;result.nativeCharts=objects.map(function(object){var chart=object.chart,series=chart.seriesCollection()||[];if(series.length>100)throw Error('Too many chart series to inspect.');return {title:chart.hasTitle()?chart.chartTitle.chartTitleText():'',chartType:String(chart.chartType()),series:series.map(function(s){var x=s.xvalues(),y=s.seriesValues();if(Array.isArray(x)&&x.length>100000||Array.isArray(y)&&y.length>100000)throw Error('Chart series exceeds inspection limit.');return {name:s.name(),x:x,y:y};})};});
 }
 try{var selected=app.selection,selection=bounds(app.getAddress(selected,{rowAbsolute:false,columnAbsolute:false}));selection.sheetId=app.activeSheet.name();result.selection=app.activeWorkbook.name()===wb.name()?selection:null;}catch(e){result.selection=null;result.selectionError=String(e);}
 if(p.operation==='read'){
  bridgeStage='read Excel used range';var used=bounds(app.getAddress(sheet.usedRange,{rowAbsolute:false,columnAbsolute:false}));limit(used.endRow+1,used.endColumn+1);
  bridgeStage='read Excel cell values';var values=sheet.ranges.byName('A1:'+letters(used.endColumn)+(used.endRow+1)).value();
  if(!Array.isArray(values))values=[[values]];else if(!Array.isArray(values[0]))values=[values];
  result.matrix=values.map(function(row){return row.map(scalar);});
 }
 return result;
}
function numbers(p){
 var app=Application('com.apple.iWork.Numbers');
 if(p.operation==='open'){bridgeStage='open Numbers document';app.open(Path(p.path));var expected=canonicalPath(p.path),matches=app.documents().filter(function(candidate){try{return canonicalPath(candidate.file().toString())===expected;}catch(e){return false;}});if(matches.length!==1)throw Error('The document opened, but its exact file identity could not be resolved. Connect to it explicitly.');return {opened:true,workbook:matches[0].name(),workbookId:matches[0].id(),path:p.path};}
 if(p.operation==='activate'&&!p.range&&!p.workbook&&!p.workbookId&&!p.sheet){app.activate();return {activated:true};}
 if(!app.running())throw Error('Open Apple Numbers and a document before connecting.');
 bridgeStage='list Numbers documents';var documents=app.documents();if(!documents.length&&p.operation!=='write')throw Error('Open a document in Apple Numbers first.');
 var doc=p.operation==='selection'?documents[0]:p.workbookId?app.documents.byId(p.workbookId):p.workbook?app.documents.byName(p.workbook):documents[0];
 if(p.operation==='write'){
  if(p.reportPath){
   if(p.outputMode!=='workbook')throw Error('Editable Numbers chart import requires a new output workbook.');
   bridgeStage='import editable Numbers report';var priorIds=app.documents().map(function(candidate){return candidate.id();});app.open(Path(p.reportPath));
   var imported=app.documents().filter(function(candidate){return priorIds.indexOf(candidate.id())<0;});
   if(imported.length!==1)throw Error('Could not identify the imported Numbers chart report.');doc=app.documents.byId(imported[0].id());
   if(doc.sheets().length!==1)throw Error('The imported Numbers report must contain exactly one sheet.');
   var nativeSheet=doc.sheets[0],nativeName=unique(p.name,[]);nativeSheet.name=nativeName;
   var nativeCount=nativeSheet.charts().length,imageCount=nativeSheet.images().length;
   if(nativeCount!==p.reportNativeCharts||imageCount!==(p.reportImageCharts||0))throw Error('Numbers did not retain every report chart.');
   var importedTables=nativeSheet.tables();if(!importedTables.length)throw Error('Numbers did not retain the report cells.');
   doc.activeSheet=nativeSheet;app.activate();
   return {workbook:doc.name(),workbookId:doc.id(),sheet:nativeName,rows:p.matrix.length,columns:p.matrix[0].length,nativeChartsWritten:nativeCount,chartImagesWritten:imageCount,reportFont:{name:importedTables[0].cellRange.fontName(),size:importedTables[0].cellRange.fontSize()}};
  }
  if(p.outputMode==='workbook'||!documents.length){bridgeStage='create Numbers document';var beforeIds=app.documents().map(function(candidate){return candidate.id();}),creationError=null;try{app.Document().make();}catch(error){creationError=error;}var created=app.documents().filter(function(candidate){return beforeIds.indexOf(candidate.id())<0;});if(created.length!==1)throw creationError||Error('Could not identify the newly created Numbers document.');doc=app.documents.byId(created[0].id());}
  if(!doc.exists())throw Error('The source Numbers document is no longer open.');
  bridgeStage='create Numbers sheet';var name=unique(p.name,doc.sheets.name()),sheet=app.Sheet({name:name}),matrix=p.matrix;doc.sheets.push(sheet);
  bridgeStage='create Numbers table';var table;if(sheet.tables.length){table=sheet.tables[0];table.headerRowCount=0;table.headerColumnCount=0;table.rowCount=Math.max(1,matrix.length);table.columnCount=Math.max(1,matrix[0].length);table.name='Results';}else{table=app.Table({name:'Results',rowCount:Math.max(1,matrix.length),columnCount:Math.max(1,matrix[0].length),headerRowCount:0,headerColumnCount:0});sheet.tables.push(table);}
  bridgeStage='write Numbers cell values';for(var r=0;r<matrix.length;r++)for(var c=0;c<matrix[r].length;c++)if(matrix[r][c]!==null)table.cells.byName(letters(c)+(r+1)).value=literal(matrix[r][c]);
  table.cellRange.fontName=p.font;table.cellRange.fontSize=p.fontSize;
  function applyFormat(range,format){range.format=/%/.test(format)?'percent':/E[+-]0/i.test(format)?'scientific':'number';}applyFormat(table.cellRange,p.numberFormat);(p.formats||[]).forEach(function(item){applyFormat(table.ranges.byName(item.range),item.numberFormat);});
  bridgeStage='write Numbers chart images';for(var br=0;br<matrix.length;br++)for(var bc=0;bc<matrix[br].length;bc++){var original=matrix[br][bc],cell=table.cells.byName(letters(bc)+(br+1));if(typeof original==='boolean'){cell.format='checkbox';cell.value=original;}else if(typeof original==='string'){cell.format='text';cell.value=original;}}
  (p.images||[]).forEach(function(image,index){var picture=app.Image({file:Path(image.path),position:[0,(matrix.length+2)*24+index*440],width:680,height:420,description:image.title});sheet.images.push(picture);});
  doc.activeSheet=sheet;app.activate();return {workbook:doc.name(),workbookId:doc.id(),sheet:name,rows:matrix.length,columns:matrix[0].length,reportFont:{name:table.cellRange.fontName(),size:table.cellRange.fontSize()},chartImagesWritten:(p.images||[]).length,reportFormats:(p.formats||[]).map(function(item){return {range:item.range,format:scalar(table.ranges.byName(item.range).format())};}),warnings:['Numbers scripting exposes number-format type but not decimal precision; numeric values are preserved, and requested decimal-place formatting may differ.'].concat((p.images||[]).length?['Charts added to an existing Numbers document are images. Choose a new output workbook for supported editable native charts.']:[])};
 }
 if(!doc||!doc.exists())throw Error('The selected Numbers document is no longer open.');
 var sheets=[],selected=null,target=null,targetSheet=null;doc.sheets().forEach(function(sheet){sheet.tables().forEach(function(table){var id=JSON.stringify([sheet.name(),table.name()]);sheets.push({id:id,name:sheet.name()+' · '+table.name()});if(id===p.sheet){target=table;targetSheet=sheet;}try{var range=table.selectionRange();if(range&&range.exists()){selected=bounds(range.name());selected.sheetId=id;if(!p.sheet){target=table;targetSheet=sheet;}}}catch(e){}if(!target&&!p.sheet){target=table;targetSheet=sheet;}});});
 if(!target)throw Error('Choose a table in the Numbers document.');var id=p.sheet||(selected&&selected.sheetId)||sheets[0].id;
 if(p.operation==='activate'){var activationRange=p.range||'A1';if(!p.range)try{var previous=target.selectionRange();if(previous&&previous.exists())activationRange=previous.name();}catch(e){}doc.activeSheet=targetSheet;target.selectionRange=target.ranges.byName(activationRange);app.windows().forEach(function(window){try{if(window.document.id()===doc.id())window.index=1;}catch(e){}});app.activate();return {activated:true,workbook:doc.name(),workbookId:doc.id(),sheet:id,range:activationRange};}
 var result={workbook:doc.name(),workbookId:doc.id(),sheets:sheets,activeSheetId:id,selection:selected};try{result.path=doc.file().toString();}catch(e){}
 if(p.inspectCharts){var chartObjects=targetSheet.charts();if(chartObjects.length>100)throw Error('Too many Numbers charts to inspect.');result.nativeChartCount=chartObjects.length;result.chartImageCount=targetSheet.images().length;result.nativeCharts=chartObjects.map(function(chart){return {width:chart.width(),height:chart.height(),position:chart.position()};});}
 if(p.operation==='read'){var rows=target.rowCount(),cols=target.columnCount();limit(rows,cols);var values=target.cells.value(),formats=target.cells.format(),matrix=[];for(var r=0;r<rows;r++){var row=[];for(var c=0;c<cols;c++){var item=values[r*cols+c];row.push(formats[r*cols+c]==='checkbox'&&item!==null&&item!==undefined?Boolean(item):scalar(item));}matrix.push(row);}while(matrix.length&&matrix[matrix.length-1].every(function(v){return v===null||v==='';}))matrix.pop();result.matrix=matrix;}
 return result;
}
function run(args){var input=ObjC.unwrap($.NSString.stringWithContentsOfFileEncodingError(args[0],$.NSUTF8StringEncoding,null)),p=JSON.parse(input);try{return JSON.stringify(p.app==='excel'?excel(p):numbers(p));}catch(error){throw Error(bridgeStage+': '+String(error));}}
