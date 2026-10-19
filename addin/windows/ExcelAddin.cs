// Original MIT-licensed COM adapter. No Office interop assembly or VSTO runtime is required.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Xml;
using Microsoft.Win32;

[assembly: ComVisible(false)]
[assembly: AssemblyVersion("0.1.0.0")]
namespace StatWorkbench.ExcelAddin
{
    [ComVisible(true), Guid("B65AD801-ABAF-11D0-BB8B-00A0C90F2744"), InterfaceType(ComInterfaceType.InterfaceIsDual)]
    public interface IDTExtensibility2
    {
        [DispId(1)] void OnConnection([MarshalAs(UnmanagedType.IDispatch)] object application, int connectMode, [MarshalAs(UnmanagedType.IDispatch)] object addInInstance, [In, Out, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType=VarEnum.VT_VARIANT)] ref Array custom);
        [DispId(2)] void OnDisconnection(int removeMode, [In, Out, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType=VarEnum.VT_VARIANT)] ref Array custom);
        [DispId(3)] void OnAddInsUpdate([In, Out, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType=VarEnum.VT_VARIANT)] ref Array custom);
        [DispId(4)] void OnStartupComplete([In, Out, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType=VarEnum.VT_VARIANT)] ref Array custom);
        [DispId(5)] void OnBeginShutdown([In, Out, MarshalAs(UnmanagedType.SafeArray, SafeArraySubType=VarEnum.VT_VARIANT)] ref Array custom);
    }
    [ComVisible(true), Guid("000C0396-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsDual)]
    public interface IRibbonExtensibility
    {
        [DispId(1)] [return: MarshalAs(UnmanagedType.BStr)] string GetCustomUI([MarshalAs(UnmanagedType.BStr)] string ribbonId);
    }
    [ComVisible(true), Guid("1D20F128-D1E1-42AA-8A94-A501851B6255"), InterfaceType(ComInterfaceType.InterfaceIsIDispatch)]
    public interface IRibbonCallbacks
    {
        [DispId(1)] void OnAction([MarshalAs(UnmanagedType.IDispatch)] object control);
    }
    [DataContract]
    public sealed class LaunchRequest
    {
        [DataMember] public int version=1;
        [DataMember] public string requestId;
        [DataMember] public long createdAt;
        [DataMember] public string command;
        [DataMember] public uint excelProcessId;
        [DataMember] public string workbook;
        [DataMember] public string sheet;
        [DataMember] public string rangeA1;
    }
    [ComVisible(true), Guid("C67ACBA9-7FE2-486A-A448-747CA2BDDF2A"), ProgId("StatWorkbench.ExcelAddin"), ClassInterface(ClassInterfaceType.None), ComDefaultInterface(typeof(IRibbonCallbacks))]
    public sealed class Connect : IDTExtensibility2, IRibbonExtensibility, IRibbonCallbacks
    {
        private object application;
        private static readonly string Ribbon = ReadRibbon();
        private static readonly HashSet<string> Commands = ReadCommands();
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int MessageBox(IntPtr window, string text, string caption, uint type);
        private static object Get(object target, string property, params object[] args)
        {
            return target.GetType().InvokeMember(property, BindingFlags.GetProperty, null, target, args);
        }
        private static string ReadRibbon()
        {
            using (Stream stream=typeof(Connect).Assembly.GetManifestResourceStream("StatWorkbench.ExcelAddin.Ribbon.xml"))
            using (StreamReader reader=new StreamReader(stream)) return reader.ReadToEnd();
        }
        private static HashSet<string> ReadCommands()
        {
            XmlDocument xml=new XmlDocument(); xml.XmlResolver=null; xml.LoadXml(Ribbon);
            HashSet<string> commands=new HashSet<string>(StringComparer.Ordinal);
            foreach(XmlElement button in xml.GetElementsByTagName("button")) commands.Add(button.GetAttribute("tag"));
            return commands;
        }
        public string GetCustomUI(string ribbonId) { return Ribbon; }
        public void OnConnection(object app, int mode, object instance, ref Array custom) { application=app; }
        public void OnDisconnection(int mode, ref Array custom) { application=null; }
        public void OnAddInsUpdate(ref Array custom) { }
        public void OnStartupComplete(ref Array custom) { }
        public void OnBeginShutdown(ref Array custom) { application=null; }
        public void OnAction(object control)
        {
            try
            {
                string command=Convert.ToString(Get(control, "Tag"));
                if (!Commands.Contains(command)) throw new InvalidOperationException("Unknown ribbon command.");
                if (application==null) throw new InvalidOperationException("Reconnect the StatWorkbench COM add-in.");
                object selection=Get(application,"Selection");
                if (selection==null || Convert.ToInt32(Get(Get(selection,"Areas"),"Count"))!=1)
                    throw new InvalidOperationException("Select one rectangular cell range in an Excel worksheet first.");
                object sheet=Get(selection,"Parent"), workbook=Get(sheet,"Parent");
                uint pid;
                if (GetWindowThreadProcessId(new IntPtr(Convert.ToInt64(Get(application,"Hwnd"))),out pid)==0)
                    throw new InvalidOperationException("Could not identify this Excel process.");
                string executable;
                using (RegistryKey key=Registry.CurrentUser.OpenSubKey(@"Software\StatWorkbench\ExcelAddin"))
                    executable=key==null?null:key.GetValue("Executable") as string;
                if (String.IsNullOrWhiteSpace(executable)||!Path.IsPathRooted(executable)||!File.Exists(executable)||!String.Equals(Path.GetExtension(executable),".exe",StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("The desktop executable has moved. Run Install.ps1 again with its new path.");
                LaunchRequest request=new LaunchRequest {
                    requestId=Guid.NewGuid().ToString("D"),
                    createdAt=(long)(DateTime.UtcNow-new DateTime(1970,1,1,0,0,0,DateTimeKind.Utc)).TotalMilliseconds,
                    command=command, excelProcessId=pid, workbook=Convert.ToString(Get(workbook,"Name")),
                    sheet=Convert.ToString(Get(sheet,"Name")),
                    rangeA1=Convert.ToString(Get(selection,"Address",false,false,1,Type.Missing,Type.Missing))
                };
                string directory=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"StatWorkbench","ExcelAddin","Requests");
                Directory.CreateDirectory(directory);
                string filename=Path.Combine(directory,request.requestId+".json");
                try
                {
                    using(FileStream stream=new FileStream(filename,FileMode.CreateNew,FileAccess.Write,FileShare.None))
                        new DataContractJsonSerializer(typeof(LaunchRequest)).WriteObject(stream,request);
                    Process.Start(new ProcessStartInfo(executable,"--excel-addin="+request.requestId) { UseShellExecute=false, WorkingDirectory=Path.GetDirectoryName(executable) });
                }
                catch { if(File.Exists(filename)) File.Delete(filename); throw; }
            }
            catch(Exception error)
            {
                Exception detail=error is TargetInvocationException && error.InnerException!=null?error.InnerException:error;
                MessageBox(IntPtr.Zero,"Could not open the Excel analysis. "+detail.Message,"StatWorkbench",0x10);
            }
        }
    }
}
