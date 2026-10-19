param([Parameter(Mandatory=$true)][string]$Executable)
$ErrorActionPreference='Stop'
if(Get-Process EXCEL -ErrorAction SilentlyContinue){throw 'Close Excel before installing the add-in.'}
$exe=(Resolve-Path -LiteralPath $Executable).Path
if([IO.Path]::GetExtension($exe) -ne '.exe'){throw 'Choose the installed StatWorkbench executable (.exe).'}
$source=Join-Path $PSScriptRoot 'StatWorkbench.ExcelAddin.dll'
if(!(Test-Path -LiteralPath $source -PathType Leaf)){throw 'Build the add-in first, or extract its complete distribution ZIP.'}
$folder=Join-Path $env:LOCALAPPDATA 'StatWorkbench\ExcelAddin'
[void](New-Item -ItemType Directory -Path $folder -Force)
$dll=Join-Path $folder 'StatWorkbench.ExcelAddin.dll'
if([IO.Path]::GetFullPath($source) -ne [IO.Path]::GetFullPath($dll)){Copy-Item -LiteralPath $source -Destination $dll -Force}
$assembly=[Reflection.AssemblyName]::GetAssemblyName($dll).FullName
$clsid='{C67ACBA9-7FE2-486A-A448-747CA2BDDF2A}'
$views=@([Microsoft.Win32.RegistryView]::Registry32)
if([Environment]::Is64BitOperatingSystem){$views+= [Microsoft.Win32.RegistryView]::Registry64}
foreach($view in $views){
 $root=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,$view)
 try{
  $prog=$root.CreateSubKey('Software\Classes\StatWorkbench.ExcelAddin');$prog.SetValue('','StatWorkbench Excel Add-in');$prog.Close()
  $key=$root.CreateSubKey('Software\Classes\StatWorkbench.ExcelAddin\CLSID');$key.SetValue('',$clsid);$key.Close()
  $key=$root.CreateSubKey("Software\Classes\CLSID\$clsid");$key.SetValue('','StatWorkbench Excel Add-in');$key.Close()
  $key=$root.CreateSubKey("Software\Classes\CLSID\$clsid\ProgId");$key.SetValue('','StatWorkbench.ExcelAddin');$key.Close()
  foreach($suffix in @('', '\0.1.0.0')){
   $key=$root.CreateSubKey("Software\Classes\CLSID\$clsid\InprocServer32$suffix")
   if(!$suffix){$key.SetValue('','mscoree.dll');$key.SetValue('ThreadingModel','Both')}
   $key.SetValue('Class','StatWorkbench.ExcelAddin.Connect');$key.SetValue('Assembly',$assembly);$key.SetValue('RuntimeVersion','v4.0.30319');$key.SetValue('CodeBase',([uri]$dll).AbsoluteUri);$key.Close()
  }
  $key=$root.CreateSubKey('Software\Microsoft\Office\Excel\Addins\StatWorkbench.ExcelAddin')
  $key.SetValue('FriendlyName','StatWorkbench');$key.SetValue('Description','Run StatWorkbench analyses using the selected Excel workbook.');$key.SetValue('LoadBehavior',3,[Microsoft.Win32.RegistryValueKind]::DWord);$key.Close()
  $key=$root.CreateSubKey('Software\StatWorkbench\ExcelAddin');$key.SetValue('Executable',$exe);$key.Close()
 }finally{$root.Close()}
}
Write-Output 'Installed for the current user. Open Excel and select the StatWorkbench ribbon tab.'
