// Native Windows Excel adapter. The console protocol is data-only; no shell or PowerShell executes it.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Xml;

namespace StatWorkbench.SpreadsheetBridge
{
    [DataContract] public sealed class Format { [DataMember] public string range; [DataMember] public string numberFormat; }
    [DataContract] public sealed class Image { [DataMember] public string path; [DataMember] public string title; }
    [DataContract] public sealed class Request
    {
        [DataMember] public string app; [DataMember] public string operation;
        [DataMember] public string workbook; [DataMember] public string sheet; [DataMember] public string name; [DataMember] public string path; [DataMember] public string range;
        [DataMember] public string expectedWorkbookPath;
        [DataMember] public string reportPath; [DataMember] public int reportNativeCharts; [DataMember] public int reportImageCharts;
        [DataMember] public bool inspectCharts;
        [DataMember] public uint excelProcessId; [DataMember] public string outputMode;
        [DataMember] public object[][] matrix; [DataMember] public string numberFormat; [DataMember] public string font; [DataMember] public double fontSize;
        [DataMember] public Format[] formats; [DataMember] public Image[] images;
    }
    [DataContract] public sealed class Sheet { [DataMember] public string id; [DataMember] public string name; }
    [DataContract] public sealed class Selection
    {
        [DataMember] public string sheetId; [DataMember] public string rangeA1;
        [DataMember] public int startRow; [DataMember] public int startColumn; [DataMember] public int endRow; [DataMember] public int endColumn;
    }
    [DataContract] public sealed class ChartSeries { [DataMember] public string name; [DataMember] public object[] x; [DataMember] public object[] y; }
    [DataContract] public sealed class NativeChart { [DataMember] public string title; [DataMember] public int chartType; [DataMember] public ChartSeries[] series; }
    [DataContract] public sealed class ReportFont { [DataMember] public string name; [DataMember] public double size; }
    [DataContract] public sealed class Response
    {
        [DataMember(EmitDefaultValue=false)] public bool opened; [DataMember(EmitDefaultValue=false)] public bool activated;
        [DataMember(EmitDefaultValue=false)] public string workbook; [DataMember(EmitDefaultValue=false)] public string sheet; [DataMember(EmitDefaultValue=false)] public string path;
        [DataMember(EmitDefaultValue=false)] public string activeSheetId; [DataMember(EmitDefaultValue=false)] public Sheet[] sheets;
        [DataMember(EmitDefaultValue=false)] public Selection selection; [DataMember(EmitDefaultValue=false)] public object[][] matrix;
        [DataMember(EmitDefaultValue=false)] public int rows; [DataMember(EmitDefaultValue=false)] public int columns;
        [DataMember(EmitDefaultValue=false)] public uint excelProcessId;
        [DataMember(EmitDefaultValue=false)] public ReportFont reportFont; [DataMember(EmitDefaultValue=false)] public Format[] reportFormats;
        [DataMember] public int nativeChartsWritten; [DataMember] public int chartImagesWritten;
        [DataMember] public int nativeChartCount; [DataMember(EmitDefaultValue=false)] public NativeChart[] nativeCharts;
    }
    public static class Program
    {
        private const int MaxBytes=32*1024*1024;
        private sealed class ReferenceComparer : IEqualityComparer<object>
        {
            public new bool Equals(object a,object b){return Object.ReferenceEquals(a,b);}
            public int GetHashCode(object value){return RuntimeHelpers.GetHashCode(value);}
        }
        private static readonly List<object> OwnedCom=new List<object>();
        private static readonly HashSet<object> SeenCom=new HashSet<object>(new ReferenceComparer());
        private static object Own(object value){if(value!=null&&Marshal.IsComObject(value)&&SeenCom.Add(value))OwnedCom.Add(value);return value;}
        private static void ReleaseOwnedCom()
        {
            // Release only this helper's RCWs. ImportReport closes its private
            // generated source; user workbooks and the application stay open.
            for(int i=OwnedCom.Count-1;i>=0;i--)try{if(Marshal.IsComObject(OwnedCom[i]))Marshal.FinalReleaseComObject(OwnedCom[i]);}catch(InvalidComObjectException){}catch(COMException){}
            OwnedCom.Clear();SeenCom.Clear();
        }
        private sealed class BoundedOutput : MemoryStream
        {
            public override void Write(byte[] buffer,int offset,int count){if(Position+count>MaxBytes)throw new InvalidOperationException("Spreadsheet response exceeds 32 MiB.");base.Write(buffer,offset,count);}
            public override void WriteByte(byte value){if(Position>=MaxBytes)throw new InvalidOperationException("Spreadsheet response exceeds 32 MiB.");base.WriteByte(value);}
        }
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window,out uint process);
        [DllImport("ole32.dll",CharSet=CharSet.Unicode,PreserveSig=false)] private static extern void CLSIDFromProgID(string progid,out Guid clsid);
        [DllImport("oleaut32.dll",PreserveSig=false)] private static extern void GetActiveObject(ref Guid clsid,IntPtr reserved,[MarshalAs(UnmanagedType.IUnknown)] out object instance);
        private static object Get(object obj,string name,params object[] args) { return Own(obj.GetType().InvokeMember(name,BindingFlags.GetProperty|BindingFlags.OptionalParamBinding,null,obj,args,CultureInfo.InvariantCulture)); }
        private static object Call(object obj,string name,params object[] args) { return Own(obj.GetType().InvokeMember(name,BindingFlags.InvokeMethod|BindingFlags.OptionalParamBinding,null,obj,args,CultureInfo.InvariantCulture)); }
        private static void Set(object obj,string name,object value) { obj.GetType().InvokeMember(name,BindingFlags.SetProperty,null,obj,new object[]{value},CultureInfo.InvariantCulture); }
        private static string Text(object value) { return Convert.ToString(value,CultureInfo.InvariantCulture); }
        private static string Column(int index) { string value="";for(;index>0;index=(index-1)/26)value=(char)('A'+(index-1)%26)+value;return value; }
        private static void Reference(string value) { if(value!=null&&(value.Length>1000||value.IndexOf('\0')>=0))throw new ArgumentException("Invalid workbook or sheet reference."); }
        private static void ValidateActivationRange(string address)
        {
            var match=Regex.Match(address??"",@"^([A-Z]{1,3})([1-9][0-9]{0,5})(?::([A-Z]{1,3})([1-9][0-9]{0,5}))?$");
            if(!match.Success)throw new ArgumentException("Invalid spreadsheet range.");
            int left=0,right=0;foreach(char letter in match.Groups[1].Value)left=left*26+letter-'A'+1;
            foreach(char letter in match.Groups[3].Success?match.Groups[3].Value:match.Groups[1].Value)right=right*26+letter-'A'+1;
            int top=Int32.Parse(match.Groups[2].Value,CultureInfo.InvariantCulture),bottom=match.Groups[4].Success?Int32.Parse(match.Groups[4].Value,CultureInfo.InvariantCulture):top;
            if(left>right||top>bottom||right>1000||bottom>100000||(long)(right-left+1)*(bottom-top+1)>2000000)throw new ArgumentException("Spreadsheet range exceeds the supported limits.");
        }
        private static bool SelectionMatchesWorkbook(string selectedName,string selectedPath,string requestedName,string requestedPath)
        {
            return String.Equals(selectedName,requestedName,StringComparison.OrdinalIgnoreCase)&&String.Equals(selectedPath,requestedPath,StringComparison.OrdinalIgnoreCase);
        }
        private static string NormalizeWorkbookPath(string value)
        {
            if(String.IsNullOrEmpty(value)||value.Length>4096||value.IndexOf('\0')>=0||!Path.IsPathRooted(value))throw new ArgumentException("Invalid expected workbook path.");
            string root=Path.GetPathRoot(value);
            // .NET Framework's IsPathRooted also accepts C:relative and
            // \current-drive-relative. Neither identifies a saved workbook.
            if(Path.DirectorySeparatorChar=='\\'&&(root.Length==1||root.EndsWith(":")))throw new ArgumentException("Invalid expected workbook path.");
            return Path.GetFullPath(value).TrimEnd(Path.DirectorySeparatorChar,Path.AltDirectorySeparatorChar);
        }
        private static void RequireWorkbookPath(string expected,string actual)
        {
            if(expected==null)return;
            bool same=false;
            try{same=String.Equals(NormalizeWorkbookPath(expected),NormalizeWorkbookPath(actual),StringComparison.OrdinalIgnoreCase);}
            catch(ArgumentException){}catch(NotSupportedException){}catch(PathTooLongException){}
            if(!same)throw new InvalidOperationException("The connected Excel workbook path changed. Reconnect the source workbook in StatWorkbench before reading or writing it.");
        }
        private static string WorksheetName(string value,HashSet<string> occupied)
        {
            string basis=Regex.Replace(value??"Results",@"[\[\]:*?/\\]"," ").Trim().Trim('\'');
            if(basis.Length>25)basis=basis.Substring(0,25);if(basis.Length==0)basis="Results";
            string result=basis;int suffix=2;while(occupied.Contains(result)){string ending=" ("+(suffix++)+")";result=basis.Substring(0,Math.Min(basis.Length,31-ending.Length))+ending;}
            return result;
        }
        private static Request ReadRequest(Stream stream) { return (Request)new DataContractJsonSerializer(typeof(Request)).ReadObject(stream); }
        private static byte[] Serialize(Response value) { using(var stream=new BoundedOutput()){new DataContractJsonSerializer(typeof(Response)).WriteObject(stream,value);return stream.ToArray();} }
        private static void Validate(Request p)
        {
            if(p==null||p.app!="excel"||!(new HashSet<string>{"read","selection","write","open","activate"}).Contains(p.operation))throw new ArgumentException("Unsupported spreadsheet operation.");
            Reference(p.workbook);Reference(p.sheet);Reference(p.name);
            if(p.range!=null){if(p.operation!="activate")throw new ArgumentException("A selected range requires an activate operation.");ValidateActivationRange(p.range);}
            if(p.expectedWorkbookPath!=null)NormalizeWorkbookPath(p.expectedWorkbookPath);
            if(p.inspectCharts&&p.operation!="read")throw new ArgumentException("Chart inspection requires a read operation.");
            if(p.reportPath!=null){
                if(p.operation!="write"||!String.Equals(Path.GetExtension(p.reportPath),".xlsx",StringComparison.OrdinalIgnoreCase))throw new ArgumentException("Invalid generated report workbook.");
                NormalizeWorkbookPath(p.reportPath);
                ValidateReportPackage(p.reportPath,p.reportNativeCharts,p.reportImageCharts);
            }
            if(p.operation=="open"&&(String.IsNullOrEmpty(p.path)||p.path.Length>4096||p.path.IndexOf('\0')>=0||!Path.IsPathRooted(p.path)))throw new ArgumentException("Invalid workbook path.");
            if(p.operation!="write")return;
            if(p.matrix==null||p.matrix.Length<1||p.matrix.Length>100000||p.matrix[0]==null)throw new ArgumentException("Invalid result worksheet.");
            int cols=p.matrix[0].Length;
            if(cols<1||cols>1000||(long)cols*p.matrix.Length>2000000)throw new ArgumentException("Result exceeds worksheet transfer limits.");
            foreach(object[] row in p.matrix){if(row==null||row.Length!=cols)throw new ArgumentException("Result must be rectangular.");foreach(object value in row)Cell(value);}
            if(p.font==null||p.font.Length>100||p.fontSize<6||p.fontSize>72||Double.IsNaN(p.fontSize))throw new ArgumentException("Invalid result font.");
            if(p.numberFormat==null||!Regex.IsMatch(p.numberFormat,@"^0(?:\.[0#]{1,15})?(?:%|E\+00)?$"))throw new ArgumentException("Invalid result format.");
            if(p.formats!=null){if(p.formats.Length>100000)throw new ArgumentException("Too many result formats.");foreach(var f in p.formats)if(f==null||f.range==null||!Regex.IsMatch(f.range,@"^[A-Z]{1,3}[1-9][0-9]{0,5}(?::[A-Z]{1,3}[1-9][0-9]{0,5})?$")||f.numberFormat==null||f.numberFormat.Length>100||Regex.IsMatch(f.numberFormat,@"[\x00-\x1f]"))throw new ArgumentException("Invalid result format range.");}
            if(p.images!=null){if(p.images.Length>30)throw new ArgumentException("Too many result charts.");foreach(var image in p.images){if(image==null||image.path==null||!Path.IsPathRooted(image.path))throw new ArgumentException("Invalid chart path.");using(var stream=File.OpenRead(image.path)){if(stream.Length<8||stream.Length>8*1024*1024)throw new ArgumentException("Invalid PNG chart length.");foreach(byte b in new byte[]{137,80,78,71,13,10,26,10})if(stream.ReadByte()!=b)throw new ArgumentException("Invalid PNG chart.");}}}
        }
        private static void ValidateReportPackage(string filename,int charts,int images)
        {
            if(charts<0||images<0||charts+images>30)throw new ArgumentException("Invalid generated report chart counts.");
            using(var stream=File.OpenRead(filename)){
                if(stream.Length>64L*1024*1024)throw new ArgumentException("Generated report exceeds 64 MiB.");
                using(var archive=new ZipArchive(stream,ZipArchiveMode.Read)){
                    if(archive.Entries.Count>2000)throw new ArgumentException("Generated report has too many package entries.");
                    long expanded=0;int sheetCount=0,chartCount=0,imageCount=0;bool workbook=false;var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    foreach(var entry in archive.Entries){
                        string name=entry.FullName;
                        expanded+=entry.Length;if(expanded>256L*1024*1024||entry.Length>32L*1024*1024||!names.Add(name))throw new ArgumentException("Generated report package exceeds limits or contains duplicate entries.");
                        if(name=="xl/workbook.xml")workbook=true;
                        if(Regex.IsMatch(name,@"^xl/worksheets/sheet[0-9]+\.xml$"))sheetCount++;
                        if(Regex.IsMatch(name,@"^xl/charts/chart[0-9]+\.xml$"))chartCount++;
                        if(Regex.IsMatch(name,@"^xl/media/image[0-9]+\.png$")){imageCount++;continue;}
                        if(!(name.EndsWith(".xml",StringComparison.OrdinalIgnoreCase)||name.EndsWith(".rels",StringComparison.OrdinalIgnoreCase))||name.IndexOf("externalLinks",StringComparison.OrdinalIgnoreCase)>=0||name.IndexOf("activeX",StringComparison.OrdinalIgnoreCase)>=0||name.IndexOf("embeddings",StringComparison.OrdinalIgnoreCase)>=0)throw new ArgumentException("Generated reports cannot contain executable or linked content.");
                        var settings=new XmlReaderSettings{DtdProcessing=DtdProcessing.Prohibit,XmlResolver=null,MaxCharactersInDocument=32L*1024*1024};
                        using(var content=entry.Open())using(var reader=XmlReader.Create(content,settings)){
                            while(reader.Read())if(reader.NodeType==XmlNodeType.Element){
                                string type=reader.GetAttribute("ContentType")??"";
                                if(reader.LocalName=="f"||reader.LocalName=="definedName"||reader.GetAttribute("TargetMode")=="External"||type.IndexOf("macroEnabled",StringComparison.OrdinalIgnoreCase)>=0||type.IndexOf("vbaProject",StringComparison.OrdinalIgnoreCase)>=0)throw new ArgumentException("Generated reports must contain literal data without formulas, macros or external links.");
                            }
                        }
                    }
                    if(!workbook||sheetCount!=1||chartCount!=charts||imageCount!=images)throw new ArgumentException("Generated report worksheet or chart inventory does not match its manifest.");
                }
            }
        }
        private static object Cell(object value)
        {
            if(value==null||value is bool)return value;
            if(value is string){if(((string)value).Length>100000)throw new ArgumentException("Worksheet text exceeds transfer limits.");return value;}
            if(value is double||value is float||value is decimal||value is int||value is long||value is short||value is byte){double number=Convert.ToDouble(value,CultureInfo.InvariantCulture);if(Double.IsNaN(number)||Double.IsInfinity(number))throw new ArgumentException("A worksheet contains a nonfinite number.");return number;}
            throw new ArgumentException("A worksheet contains an unsupported cell or Excel error. Correct the cell before importing.");
        }
        private static object ExcelCell(object value)
        {
            // Excel Value2 numbers are VT_R8/Double. VT_ERROR may arrive as Int32 rather than ErrorWrapper.
            // Keep JSON's ordinary integer input valid, but never reinterpret an Excel error code as a number.
            if(value!=null&&!(value is string)&&!(value is bool)&&!(value is double))throw new ArgumentException("The worksheet contains an Excel error or unsupported cell. Correct it before importing.");
            return Cell(value);
        }
        private static object WriteCell(object value)
        {
            // Prefix every string so Excel cannot convert identifiers, dates or formula-like labels under General formatting.
            // A literal leading apostrophe becomes two apostrophes: one prefix and one preserved character.
            return value is string?"'"+(string)value:value;
        }
        private static bool CanStartExcel(string operation,int errorCode){return operation=="open"&&errorCode==unchecked((int)0x800401E3);}
        private static Response Execute(Request p)
        {
            try{return ExecuteCore(p);}finally{ReleaseOwnedCom();}
        }
        private static Response ExecuteCore(Request p)
        {
            Guid clsid;CLSIDFromProgID("Excel.Application",out clsid);object excel;
            try{GetActiveObject(ref clsid,IntPtr.Zero,out excel);Own(excel);}catch(COMException error){if(!CanStartExcel(p.operation,error.ErrorCode))throw;excel=Own(Activator.CreateInstance(Type.GetTypeFromCLSID(clsid,true)));Set(excel,"Visible",true);}
            uint pid;if(GetWindowThreadProcessId(new IntPtr(Convert.ToInt64(Get(excel,"Hwnd"))),out pid)==0||pid==0)throw new InvalidOperationException("Could not identify the connected Excel process.");
            if(p.excelProcessId!=0&&pid!=p.excelProcessId)throw new InvalidOperationException("The connected Excel process changed. Reconnect the source workbook in StatWorkbench before reading or writing it.");
            object books=Get(excel,"Workbooks");
            if(p.operation=="open"){Call(books,"Open",p.path);Set(excel,"Visible",true);return new Response{opened=true};}
            object workbook=p.workbook==null?Get(excel,"ActiveWorkbook"):Get(books,"Item",p.workbook);
            if(p.operation!="write"||p.outputMode!="workbook")RequireWorkbookPath(p.expectedWorkbookPath,workbook==null?null:Text(Get(workbook,"FullName")));
            if(p.operation=="activate"){
                Set(excel,"Visible",true);
                if(workbook==null){if(p.range!=null||p.sheet!=null)throw new InvalidOperationException("Open a workbook in Microsoft Excel first.");return new Response{activated=true};}
                Call(workbook,"Activate");object targetSheet=p.sheet==null?Get(workbook,"ActiveSheet"):Get(Get(workbook,"Worksheets"),"Item",p.sheet);
                Call(targetSheet,"Activate");if(p.range!=null)Call(excel,"Goto",Get(targetSheet,"Range",p.range),true);
                return new Response{activated=true,workbook=Text(Get(workbook,"Name")),sheet=Text(Get(targetSheet,"Name"))};
            }
            if(p.operation=="write")return Write(excel,books,workbook,p);
            if(workbook==null)throw new InvalidOperationException("Open a workbook in Microsoft Excel first.");
            object worksheets=Get(workbook,"Worksheets"),sheet=p.sheet==null?Get(workbook,"ActiveSheet"):Get(worksheets,"Item",p.sheet);
            int count=Convert.ToInt32(Get(worksheets,"Count"));if(count>1000)throw new InvalidOperationException("Workbook exceeds 1,000 worksheets.");
            var sheets=new Sheet[count];for(int i=0;i<count;i++){string name=Text(Get(Get(worksheets,"Item",i+1),"Name"));sheets[i]=new Sheet{id=name,name=name};}
            var result=new Response{workbook=Text(Get(workbook,"Name")),path=Text(Get(workbook,"FullName")),activeSheetId=Text(Get(sheet,"Name")),sheets=sheets,excelProcessId=pid};
            try{object selected=Get(excel,"Selection"),selectedSheet=Get(selected,"Parent"),selectedBook=Get(selectedSheet,"Parent");if(SelectionMatchesWorkbook(Text(Get(selectedBook,"Name")),Text(Get(selectedBook,"FullName")),result.workbook,result.path)&&Convert.ToInt32(Get(Get(selected,"Areas"),"Count"))==1){int row=Convert.ToInt32(Get(selected,"Row"))-1,column=Convert.ToInt32(Get(selected,"Column"))-1;result.selection=new Selection{sheetId=Text(Get(selectedSheet,"Name")),rangeA1=Text(Get(selected,"Address",false,false,1,Type.Missing,Type.Missing)),startRow=row,startColumn=column,endRow=row+Convert.ToInt32(Get(Get(selected,"Rows"),"Count"))-1,endColumn=column+Convert.ToInt32(Get(Get(selected,"Columns"),"Count"))-1};}}catch{result.selection=null;}
            if(p.operation=="read"){
                object used=Get(sheet,"UsedRange");long rows=Convert.ToInt64(Get(used,"Row"))+Convert.ToInt64(Get(Get(used,"Rows"),"Count"))-1,cols=Convert.ToInt64(Get(used,"Column"))+Convert.ToInt64(Get(Get(used,"Columns"),"Count"))-1;
                if(rows>100000||cols>1000||rows*cols>2000000)throw new InvalidOperationException("The occupied worksheet rectangle exceeds transfer limits.");
                object values=Get(Get(sheet,"Range","A1",Column((int)cols)+rows),"Value2");Array array=values as Array;
                result.matrix=new object[(int)rows][];for(int r=0;r<rows;r++){result.matrix[r]=new object[(int)cols];for(int c=0;c<cols;c++)result.matrix[r][c]=ExcelCell(array==null?values:array.GetValue(r+array.GetLowerBound(0),c+array.GetLowerBound(1)));}
                if(p.inspectCharts){result.nativeCharts=InspectCharts(sheet);result.nativeChartCount=result.nativeCharts.Length;}
            }
            return result;
        }
        private static Response Write(object excel,object books,object workbook,Request p)
        {
            if(p.reportPath!=null)return ImportReport(excel,books,workbook,p);
            if(p.outputMode=="workbook"||workbook==null)workbook=Call(books,"Add");
            var occupied=new HashSet<string>(StringComparer.OrdinalIgnoreCase);object all=Get(workbook,"Sheets");int count=Convert.ToInt32(Get(all,"Count"));if(count>=1000)throw new InvalidOperationException("Workbook already contains 1,000 sheets.");for(int i=1;i<=count;i++)occupied.Add(Text(Get(Get(all,"Item",i),"Name")));
            string name=WorksheetName(p.name,occupied);object sheet=Call(Get(workbook,"Worksheets"),"Add");Set(sheet,"Name",name);
            int rows=p.matrix.Length,cols=p.matrix[0].Length;var values=new object[rows,cols];
            for(int r=0;r<rows;r++)for(int c=0;c<cols;c++)values[r,c]=WriteCell(p.matrix[r][c]);
            object range=Get(sheet,"Range","A1",Column(cols)+rows);Set(range,"Value2",values);Set(range,"NumberFormat",p.numberFormat);object font=Get(range,"Font");Set(font,"Name",p.font);Set(font,"Size",p.fontSize);
            foreach(var format in p.formats??new Format[0])Set(Get(sheet,"Range",format.range),"NumberFormat",format.numberFormat);
            int imageIndex=0;foreach(var image in p.images??new Image[0]){Call(Get(sheet,"Shapes"),"AddPicture",image.path,0,-1,0,(rows+2)*18+imageIndex*440,680,420);imageIndex++;}
            Set(excel,"Visible",true);Call(sheet,"Activate");return ReportResponse(workbook,sheet,p,0,imageIndex);
        }
        private static Response ReportResponse(object workbook,object sheet,Request p,int charts,int images)
        {
            object range=Get(sheet,"Range","A1",Column(p.matrix[0].Length)+p.matrix.Length),font=Get(range,"Font");
            var formats=new List<Format>();foreach(var format in p.formats??new Format[0])formats.Add(new Format{range=format.range,numberFormat=Text(Get(Get(sheet,"Range",format.range),"NumberFormat"))});
            return new Response{workbook=Text(Get(workbook,"Name")),sheet=Text(Get(sheet,"Name")),rows=p.matrix.Length,columns=p.matrix[0].Length,nativeChartsWritten=charts,chartImagesWritten=images,reportFont=new ReportFont{name=Text(Get(font,"Name")),size=Convert.ToDouble(Get(font,"Size"),CultureInfo.InvariantCulture)},reportFormats=formats.ToArray()};
        }
        private static object[] ChartValues(object value)
        {
            var values=new List<object>();Array array=value as Array;
            if(array==null)values.Add(ExcelCell(value));
            else{if(array.LongLength>100000)throw new InvalidOperationException("Chart inspection exceeds 100,000 points.");foreach(object item in array)values.Add(ExcelCell(item));}
            return values.ToArray();
        }
        private static NativeChart[] InspectCharts(object sheet)
        {
            object objects=Call(sheet,"ChartObjects");int count=Convert.ToInt32(Get(objects,"Count"));
            if(count>100)throw new InvalidOperationException("Chart inspection exceeds 100 charts.");
            var charts=new NativeChart[count];int points=0,totalSeries=0;
            for(int i=0;i<count;i++){
                object chart=Get(Get(objects,"Item",i+1),"Chart"),collection=Call(chart,"SeriesCollection");int length=Convert.ToInt32(Get(collection,"Count"));
                totalSeries+=length;if(totalSeries>100)throw new InvalidOperationException("Chart inspection exceeds 100 series.");
                var series=new ChartSeries[length];
                for(int j=0;j<length;j++){object item=Get(collection,"Item",j+1);series[j]=new ChartSeries{name=Text(Get(item,"Name")),x=ChartValues(Get(item,"XValues")),y=ChartValues(Get(item,"Values"))};points+=Math.Max(series[j].x.Length,series[j].y.Length);if(points>100000)throw new InvalidOperationException("Chart inspection exceeds 100,000 points.");}
                charts[i]=new NativeChart{title=Convert.ToBoolean(Get(chart,"HasTitle"))?Text(Get(Get(chart,"ChartTitle"),"Text")):"",chartType=Convert.ToInt32(Get(chart,"ChartType")),series=series};
            }
            return charts;
        }
        private static Response ImportReport(object excel,object books,object target,Request p)
        {
            bool newWorkbook=p.outputMode=="workbook"||target==null;
            var occupied=new HashSet<string>(StringComparer.OrdinalIgnoreCase);object after=null;
            if(!newWorkbook){object sheets=Get(target,"Sheets");int count=Convert.ToInt32(Get(sheets,"Count"));if(count>=1000)throw new InvalidOperationException("Workbook already contains 1,000 sheets.");for(int i=1;i<=count;i++)occupied.Add(Text(Get(Get(sheets,"Item",i),"Name")));after=Get(sheets,"Item",count);}
            string name=WorksheetName(p.name,occupied);object generated=null,result=null;
            try{
                // Validated one-sheet OOXML contains only literals; disable link
                // updates and open read-only, then copy the sheet in this Excel instance.
                generated=Call(books,"Open",p.reportPath,0,true);
                object sheets=Get(generated,"Worksheets");if(Convert.ToInt32(Get(sheets,"Count"))!=1)throw new InvalidOperationException("Generated report must have exactly one worksheet.");
                object source=Get(sheets,"Item",1);
                if(newWorkbook){Call(source,"Copy");target=Get(excel,"ActiveWorkbook");}
                else Call(source,"Copy",Type.Missing,after);
                result=Get(excel,"ActiveSheet");Set(result,"Name",name);
            }finally{if(generated!=null)Call(generated,"Close",false);}
            Call(target,"Activate");Call(result,"Activate");Set(excel,"Visible",true);
            int countCharts=Convert.ToInt32(Get(Call(result,"ChartObjects"),"Count"));
            if(countCharts!=p.reportNativeCharts)throw new InvalidOperationException("Report worksheet was copied, but Excel did not retain every editable chart.");
            int countImages=Convert.ToInt32(Get(Get(result,"Shapes"),"Count"))-countCharts;
            if(countImages!=p.reportImageCharts)throw new InvalidOperationException("Report worksheet was copied, but Excel did not retain every chart image.");
            return ReportResponse(target,result,p,countCharts,countImages);
        }
        private static void WriteTestPackage(string path,Dictionary<string,string> parts)
        {
            using(var stream=File.Create(path))using(var archive=new ZipArchive(stream,ZipArchiveMode.Create))foreach(var part in parts){using(var writer=new StreamWriter(archive.CreateEntry(part.Key).Open(),new UTF8Encoding(false)))writer.Write(part.Value);}
        }
        private static void TestReportPackages()
        {
            string filename=Path.Combine(Path.GetTempPath(),"statworkbench-report-test-"+Guid.NewGuid().ToString("N")+".xlsx");
            try{
                var parts=new Dictionary<string,string>{{"xl/workbook.xml","<workbook/>"},{"xl/worksheets/sheet1.xml","<worksheet/>"}};
                WriteTestPackage(filename,parts);ValidateReportPackage(filename,0,0);
                foreach(var bad in new[]{new KeyValuePair<string,string>("xl/worksheets/sheet1.xml","<worksheet><f>1+1</f></worksheet>"),new KeyValuePair<string,string>("xl/_rels/workbook.xml.rels","<Relationships><Relationship TargetMode='External' Target='https://example.invalid'/></Relationships>"),new KeyValuePair<string,string>("xl/worksheets/sheet2.xml","<worksheet/>"),new KeyValuePair<string,string>("xl/vbaProject.bin","not executable")}){
                    var changed=new Dictionary<string,string>(parts);changed[bad.Key]=bad.Value;WriteTestPackage(filename,changed);bool rejected=false;try{ValidateReportPackage(filename,0,0);}catch(ArgumentException){rejected=true;}if(!rejected)throw new Exception("Linked, formula-bearing or multi-sheet report package was accepted.");
                }
                WriteTestPackage(filename,parts);bool countRejected=false;try{ValidateReportPackage(filename,1,0);}catch(ArgumentException){countRejected=true;}if(!countRejected)throw new Exception("An incorrect report chart manifest was accepted.");
            }finally{File.Delete(filename);}
            object[] values=ChartValues(new double[,]{{1,2},{3,4}});if(values.Length!=4||(double)values[3]!=4)throw new Exception("Chart data array flattening failed.");
            var bytes=Serialize(new Response{nativeCharts=new[]{new NativeChart{title="Measured",chartType=74,series=new[]{new ChartSeries{name="Series",x=new object[]{1d,2d},y=new object[]{3d,4d}}}}},nativeChartCount=1,nativeChartsWritten=1});
            if(Encoding.UTF8.GetString(bytes).IndexOf("nativeChartsWritten",StringComparison.Ordinal)<0)throw new Exception("Native chart response serialization failed.");
        }
        private static void SelfTest()
        {
            string json="{\"app\":\"excel\",\"operation\":\"write\",\"workbook\":\"Cohort.xlsx\",\"matrix\":[[\"=inert\",1,true,null],[\"text\",2,false,3.5]],\"numberFormat\":\"0.00\",\"font\":\"Arial\",\"fontSize\":11,\"formats\":[{\"range\":\"B1:B2\",\"numberFormat\":\"0.00%\"}]}";
            Request p;using(var stream=new MemoryStream(Encoding.UTF8.GetBytes(json)))p=ReadRequest(stream);Validate(p);
            if(p.matrix.Length!=2||!(p.matrix[0][2] is bool)||p.matrix[0][3]!=null||Convert.ToDouble(p.matrix[1][3])!=3.5||p.formats[0].range!="B1:B2")throw new Exception("JSON request contract failed.");
            if(WorksheetName("bad/name",new HashSet<string>{"bad name"})!="bad name (2)"||Column(1000)!="ALL")throw new Exception("Worksheet naming failed.");
            string longName=new string('x',25);var names=new HashSet<string>{longName};for(int i=2;i<=999;i++)names.Add(longName+" ("+i+")");if(WorksheetName(longName,names).Length>31)throw new Exception("Worksheet suffix exceeds Excel limits.");
            bool rejected=false;try{Validate(new Request{app="excel",operation="eval"});}catch(ArgumentException){rejected=true;}if(!rejected)throw new Exception("Operation validation failed.");
            foreach(string address in new[]{"A1","A2:C3","ALL100000","A1:T100000"})Validate(new Request{app="excel",operation="activate",range=address});
            foreach(string address in new[]{"=1+1","A0","B2:A1","A1:A100001","A1:ALM1","A1:U100000","Sheet1!A1","A1,B2"}){rejected=false;try{Validate(new Request{app="excel",operation="activate",range=address});}catch(ArgumentException){rejected=true;}if(!rejected)throw new Exception("An invalid activation range was accepted.");}
            rejected=false;try{Validate(new Request{app="excel",operation="read",range="A1"});}catch(ArgumentException){rejected=true;}if(!rejected)throw new Exception("A selection range was accepted for a read operation.");
            if(!SelectionMatchesWorkbook("Book1","Book1","Book1","Book1")||SelectionMatchesWorkbook("Book2","Book2","Book1","Book1")||SelectionMatchesWorkbook("Data.xlsx",@"C:\other\Data.xlsx","Data.xlsx",@"C:\source\Data.xlsx"))throw new Exception("Selection workbook identity check failed.");
            rejected=false;try{Cell(Double.NaN);}catch(ArgumentException){rejected=true;}if(!rejected)throw new Exception("Cell validation failed.");
            rejected=false;try{ExcelCell(-2146826246);}catch(ArgumentException){rejected=true;}if(!rejected)throw new Exception("Excel VT_ERROR was accepted as a number.");
            if((double)ExcelCell(-2146826246d)!=-2146826246d||Convert.ToDouble(Cell(42))!=42)throw new Exception("Legitimate double/JSON integer was rejected.");
            foreach(string text in new[]{"00123","1E10","2026-10-16","=1+1","'quoted","12345678901234567890"})if((string)WriteCell(text)!="'"+text)throw new Exception("Excel literal text preservation failed.");
            if(!Object.Equals(WriteCell(3.5),3.5)||!Object.Equals(WriteCell(true),true)||WriteCell(null)!=null)throw new Exception("Typed cells changed during writeback.");
            if(!CanStartExcel("open",unchecked((int)0x800401E3))||CanStartExcel("read",unchecked((int)0x800401E3))||CanStartExcel("open",unchecked((int)0x80070005)))throw new Exception("Excel activation conditions changed.");
            string expectedPath=Path.Combine(Path.GetTempPath(),"first","Data.xlsx");
            RequireWorkbookPath(expectedPath,expectedPath.ToUpperInvariant());
            RequireWorkbookPath(expectedPath,Path.Combine(Path.GetTempPath(),"first","nested","..","Data.xlsx"));
            foreach(string replacement in new[]{Path.Combine(Path.GetTempPath(),"second","Data.xlsx"),"Data.xlsx",null}){
                rejected=false;try{RequireWorkbookPath(expectedPath,replacement);}catch(InvalidOperationException){rejected=true;}
                if(!rejected)throw new Exception("A same-name replacement or unsaved workbook bypassed the expected-path guard.");
            }
            rejected=false;try{Validate(new Request{app="excel",operation="read",expectedWorkbookPath="Data.xlsx"});}catch(ArgumentException){rejected=true;}
            if(!rejected)throw new Exception("A relative workbook identity was accepted.");
            if(Path.DirectorySeparatorChar=='\\'){
                foreach(string relative in new[]{@"C:Data.xlsx",@"\Data.xlsx"}){rejected=false;try{NormalizeWorkbookPath(relative);}catch(ArgumentException){rejected=true;}if(!rejected)throw new Exception("A drive-relative workbook identity was accepted.");}
                RequireWorkbookPath(@"C:\Study\Data.xlsx",@"c:/Study/sub/../Data.xlsx");
                RequireWorkbookPath(@"\\server\share\Study\Data.xlsx",@"\\SERVER\SHARE\Study\nested\..\Data.xlsx");
            }
            TestReportPackages();
            var bytes=Serialize(new Response{workbook="Cohort.xlsx",sheets=new[]{new Sheet{id="Data",name="Data"}},matrix=p.matrix});
            if(Encoding.UTF8.GetString(bytes).IndexOf("Cohort.xlsx",StringComparison.Ordinal)<0)throw new Exception("JSON result contract failed.");
            Console.WriteLine("{\"verified\":true,\"managedRuntime\":true,\"protocol\":1,\"workbookPathGuardVerified\":true,\"reportPackageVerified\":true,\"excelAutomationVerified\":false}");
        }
        [STAThread] public static int Main(string[] args)
        {
            Console.OutputEncoding=new UTF8Encoding(false);
            try{
                if(args.Length==1&&args[0]=="--self-test"){SelfTest();return 0;}
                if(args.Length==4&&args[0]=="--verify-report"){int charts=Int32.Parse(args[2],CultureInfo.InvariantCulture),images=Int32.Parse(args[3],CultureInfo.InvariantCulture);ValidateReportPackage(args[1],charts,images);Console.WriteLine("{\"verified\":true,\"excelAutomationVerified\":false}");return 0;}
                if(args.Length!=1)throw new ArgumentException("Provide one spreadsheet request file.");
                Request request;using(var stream=new FileStream(args[0],FileMode.Open,FileAccess.Read,FileShare.Read)){if(stream.Length>MaxBytes)throw new ArgumentException("Spreadsheet request exceeds 32 MiB.");request=ReadRequest(stream);}
                Validate(request);byte[] result=Serialize(Execute(request));if(result.Length>MaxBytes)throw new InvalidOperationException("Spreadsheet response exceeds 32 MiB.");Console.WriteLine(Encoding.UTF8.GetString(result));return 0;
            }catch(Exception error){if(error is TargetInvocationException&&error.InnerException!=null)error=error.InnerException;Console.Error.WriteLine(error.Message);return 1;}
        }
    }
}
