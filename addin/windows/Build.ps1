param([string]$OutputDirectory=(Join-Path $PSScriptRoot '..\..\release\excel-addin'))
$ErrorActionPreference='Stop'
$project=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
& python (Join-Path $project 'scripts\generate_excel_ribbon.py') --check
if($LASTEXITCODE -ne 0){throw 'The generated ribbon is stale.'}
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
if(!(Test-Path -LiteralPath $compiler)){throw '.NET Framework 4.x C# compiler was not found.'}
[void](New-Item -ItemType Directory -Path $OutputDirectory -Force)
$output=(Resolve-Path -LiteralPath $OutputDirectory).Path
$dll=Join-Path $output 'StatWorkbench.ExcelAddin.dll'
$ribbon=Join-Path $PSScriptRoot 'Ribbon.xml'
& $compiler /nologo /target:library /platform:anycpu /optimize+ /reference:System.Runtime.Serialization.dll "/resource:$ribbon,StatWorkbench.ExcelAddin.Ribbon.xml" "/out:$dll" (Join-Path $PSScriptRoot 'ExcelAddin.cs')
if($LASTEXITCODE -ne 0){throw 'Excel COM add-in compilation failed.'}
foreach($name in @('Install.ps1','Uninstall.ps1','Verify.ps1','README.md')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $output -Force}
Copy-Item -LiteralPath (Join-Path $project 'LICENSE') -Destination $output -Force
& (Join-Path $PSScriptRoot 'Verify.ps1') -Assembly $dll
$evidence=Join-Path $project 'test-artifacts\windows-excel-addin'
[void](New-Item -ItemType Directory -Path $evidence -Force)
Copy-Item -LiteralPath (Join-Path $output 'build-verification.json') -Destination $evidence -Force
$version=(Get-Content -LiteralPath (Join-Path $project 'package.json') -Raw | ConvertFrom-Json).version
# Use the installed framework directly; nested Windows PowerShell can inherit
# a PowerShell Core module path without Get-FileHash or Compress-Archive.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive=Join-Path $project "release\statworkbench-$version-excel-addin-windows.zip"
[IO.File]::Delete($archive)
[IO.Compression.ZipFile]::CreateFromDirectory($output,$archive,[IO.Compression.CompressionLevel]::Optimal,$false)
Write-Output "Built and checked $dll. Excel-hosted loading remains a separate verification step."
