param([string]$Assembly=(Join-Path $PSScriptRoot 'StatWorkbench.ExcelAddin.dll'),[switch]$ExcelHost,[string]$VerificationPath)
$ErrorActionPreference='Stop'
$dll=(Resolve-Path -LiteralPath $Assembly).Path
$loaded=[Reflection.Assembly]::LoadFile($dll)
$type=$loaded.GetType('StatWorkbench.ExcelAddin.Connect',$true)
$addin=[Activator]::CreateInstance($type)
[xml]$ribbon=$addin.GetCustomUI('Microsoft.Excel.Workbook')
$buttons=@($ribbon.SelectNodes('//*[local-name()="button"]'))
$analyses=@($buttons|Where-Object {$_.tag -like 'analysis:*'})
if($analyses.Count -ne 125){throw "Expected 125 analysis buttons; found $($analyses.Count)."}
if(@($analyses.tag|Select-Object -Unique).Count -ne 125){throw 'Ribbon analysis tags are duplicated.'}
if(@($buttons.id|Select-Object -Unique).Count -ne $buttons.Count){throw 'Ribbon button IDs are duplicated.'}
foreach($button in $buttons){if($button.onAction -ne 'OnAction' -or [string]::IsNullOrWhiteSpace($button.label)){throw 'A ribbon button has no visible label or action callback.'}}
foreach($tag in @('open','preferences')){if(@($buttons|Where-Object {$_.tag -eq $tag}).Count -ne 1){throw "Ribbon utility command $tag is missing or duplicated."}}
$peKind=[Reflection.PortableExecutableKinds]::NotAPortableExecutableImage
$machine=[Reflection.ImageFileMachine]::I386
$loaded.ManifestModule.GetPEKind([ref]$peKind,[ref]$machine)
if(($peKind -band [Reflection.PortableExecutableKinds]::ILOnly) -eq 0 -or ($peKind -band [Reflection.PortableExecutableKinds]::Required32Bit) -ne 0){throw 'The Excel add-in must be an AnyCPU managed assembly.'}
if(!($type.GetInterfaces().GUID -contains [guid]'B65AD801-ABAF-11D0-BB8B-00A0C90F2744') -or !($type.GetInterfaces().GUID -contains [guid]'000C0396-0000-0000-C000-000000000046')){throw 'Office COM interfaces are missing.'}
foreach($name in @('IDTExtensibility2','IRibbonExtensibility')){
 $interface=$loaded.GetType("StatWorkbench.ExcelAddin.$name",$true)
 $attribute=[Attribute]::GetCustomAttribute($interface,[Runtime.InteropServices.InterfaceTypeAttribute])
 if($attribute.Value -ne [Runtime.InteropServices.ComInterfaceType]::InterfaceIsDual){throw 'Office interfaces must expose the documented dual-interface vtable.'}
}
$request=[Activator]::CreateInstance($loaded.GetType('StatWorkbench.ExcelAddin.LaunchRequest',$true))
$request.requestId='ac3fa1dd-e035-4bb2-8d11-cd9be1fdbb92';$request.createdAt=1234567890000;$request.command='analysis:1001';$request.excelProcessId=1234;$request.workbook='Cohort.xlsx';$request.sheet="Patients' data";$request.rangeA1='B2:D15'
$serializer=[System.Runtime.Serialization.Json.DataContractJsonSerializer]::new($request.GetType())
$stream=[IO.MemoryStream]::new()
try{$serializer.WriteObject($stream,$request);$serialized=[Text.Encoding]::UTF8.GetString($stream.ToArray())|ConvertFrom-Json}finally{$stream.Dispose()}
if($serialized.version -ne 1 -or $serialized.createdAt -ne 1234567890000 -or $serialized.excelProcessId -ne 1234 -or $serialized.rangeA1 -ne 'B2:D15' -or $serialized.sheet -ne "Patients' data"){throw 'The C# handoff serialization contract changed.'}
if($ExcelHost){
 $excel=[Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application')
 $installed=$excel.COMAddIns.Item('StatWorkbench.ExcelAddin')
 if(!$installed.Connect){throw 'The add-in is installed but Excel has not connected it.'}
 Write-Output 'Excel reports the add-in is connected. Manually verify ribbon commands and numerical writeback using README.md.'
}else{Write-Output 'Compiled assembly, request serialization and 125 ribbon commands verified; Excel loading and UI have not been exercised.'}
if(!$VerificationPath){$VerificationPath=Join-Path (Split-Path -Parent $dll) 'build-verification.json'}
$hashAlgorithm=[Security.Cryptography.SHA256]::Create()
$assemblyStream=[IO.File]::OpenRead($dll)
try{$assemblySha256=([BitConverter]::ToString($hashAlgorithm.ComputeHash($assemblyStream))).Replace('-','').ToLowerInvariant()}finally{$assemblyStream.Dispose();$hashAlgorithm.Dispose()}
$verification=[ordered]@{
 verified=$true
 scope='Compiled assembly, ribbon XML, COM interface metadata and serialized launch request'
 platform='win32'
 runtime=[Environment]::Version.ToString()
 assemblySha256=$assemblySha256
 analysisCommands=$analyses.Count
 utilityCommands=2
 anyCpu=$true
 excelInstalled=($null -ne [Type]::GetTypeFromProgID('Excel.Application',$false))
 excelConnectionVerified=[bool]$ExcelHost
 excelAutomationVerified=$false
}
$parent=Split-Path -Parent ([IO.Path]::GetFullPath($VerificationPath))
[void](New-Item -ItemType Directory -Path $parent -Force)
$verification | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $VerificationPath -Encoding UTF8
