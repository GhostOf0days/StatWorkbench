$ErrorActionPreference='Stop'
if(Get-Process EXCEL -ErrorAction SilentlyContinue){throw 'Close Excel before removing the add-in.'}
$views=@([Microsoft.Win32.RegistryView]::Registry32)
if([Environment]::Is64BitOperatingSystem){$views+=[Microsoft.Win32.RegistryView]::Registry64}
foreach($view in $views){
 $root=[Microsoft.Win32.RegistryKey]::OpenBaseKey([Microsoft.Win32.RegistryHive]::CurrentUser,$view)
 try{foreach($subkey in @('Software\Classes\StatWorkbench.ExcelAddin','Software\Classes\CLSID\{C67ACBA9-7FE2-486A-A448-747CA2BDDF2A}','Software\Microsoft\Office\Excel\Addins\StatWorkbench.ExcelAddin','Software\StatWorkbench\ExcelAddin')){$root.DeleteSubKeyTree($subkey,$false)}}finally{$root.Close()}
}
$dll=Join-Path $env:LOCALAPPDATA 'StatWorkbench\ExcelAddin\StatWorkbench.ExcelAddin.dll'
if(Test-Path -LiteralPath $dll){Remove-Item -LiteralPath $dll}
Write-Output 'The StatWorkbench Excel add-in has been removed for the current user.'
