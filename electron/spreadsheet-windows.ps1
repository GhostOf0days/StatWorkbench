param([Parameter(Mandatory=$true)][string]$RequestFile)
$ErrorActionPreference='Stop'
$p=Get-Content -LiteralPath $RequestFile -Raw -Encoding UTF8 | ConvertFrom-Json
$excel=[Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application')
if($p.excelProcessId){
 Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class StatWorkbenchExcelWindow { [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr window, out uint process); }'
 [uint32]$excelProcess=0
 [void][StatWorkbenchExcelWindow]::GetWindowThreadProcessId([intptr]([int64]$excel.Hwnd),[ref]$excelProcess)
 if($excelProcess -ne [uint32]$p.excelProcessId){throw 'This command came from another Excel process. Keep the source workbook open in the Excel instance connected to StatWorkbench, then click its ribbon command again.'}
}
if($p.operation -eq 'open'){[void]$excel.Workbooks.Open([string]$p.path);@{opened=$true}|ConvertTo-Json -Compress;exit}
if($p.operation -eq 'activate'){$excel.Visible=$true;if($p.workbook){$source=$excel.Workbooks.Item([string]$p.workbook);$source.Activate();if($p.sheet){$source.Worksheets.Item([string]$p.sheet).Activate()}};@{activated=$true}|ConvertTo-Json -Compress;exit}
if($p.workbook){$wb=$excel.Workbooks.Item([string]$p.workbook)}else{$wb=$excel.ActiveWorkbook}
function ColumnName([int]$index){$s='';while($index -gt 0){$index--;$s=[char](65+$index%26)+$s;$index=[math]::Floor($index/26)};return $s}
if($p.operation -eq 'write'){
 if($p.outputMode -eq 'workbook' -or $null -eq $wb){$wb=$excel.Workbooks.Add()}
 $sheet=$wb.Worksheets.Add();$base=([string]$p.name -replace '[\[\]:*?/\\]',' ').Substring(0,[Math]::Min(25,([string]$p.name).Length));if(!$base){$base='Results'};$name=$base;$n=2
 while(@($wb.Worksheets|ForEach-Object {$_.Name}) -contains $name){$name="$base ($n)";$n++};$sheet.Name=$name
 $rows=$p.matrix.Count;$cols=$p.matrix[0].Count;$data=New-Object 'object[,]' $rows,$cols
 for($r=0;$r -lt $rows;$r++){for($c=0;$c -lt $cols;$c++){$v=$p.matrix[$r][$c];if($v -is [string] -and $v -match '^[=+\-@]'){$v="'"+$v};$data[$r,$c]=$v}}
 $range=$sheet.Range('A1',((ColumnName $cols)+$rows));$range.Value2=$data;$range.NumberFormat=$p.numberFormat;$range.Font.Name=$p.font;$range.Font.Size=$p.fontSize
 foreach($item in $p.formats){$sheet.Range([string]$item.range).NumberFormat=[string]$item.numberFormat}
 $i=0;foreach($image in $p.images){[void]$sheet.Shapes.AddPicture($image.path,$false,$true,0,($rows+2)*18+$i*440,680,420);$i++};$excel.Visible=$true;$sheet.Activate()
 @{workbook=$wb.Name;sheet=$name;rows=$rows;columns=$cols}|ConvertTo-Json -Compress;exit
}
if($null -eq $wb){throw 'Open a workbook in Microsoft Excel first.'}
$sheet=if($p.sheet){$wb.Worksheets.Item([string]$p.sheet)}else{$wb.ActiveSheet}
$sheets=@($wb.Worksheets|ForEach-Object {@{id=$_.Name;name=$_.Name}})
$result=@{workbook=$wb.Name;path=$wb.FullName;sheets=$sheets;activeSheetId=$sheet.Name}
$selection=$excel.Selection
try{$result.selection=@{sheetId=$excel.ActiveSheet.Name;rangeA1=$selection.Address($false,$false);startRow=$selection.Row-1;startColumn=$selection.Column-1;endRow=$selection.Row+$selection.Rows.Count-2;endColumn=$selection.Column+$selection.Columns.Count-2}}catch{$result.selection=$null}
if($p.operation -eq 'read'){
 $used=$sheet.UsedRange;$rows=$used.Row+$used.Rows.Count-1;$cols=$used.Column+$used.Columns.Count-1
 if($rows -gt 100000 -or $cols -gt 1000 -or $rows*$cols -gt 2000000){throw 'The occupied worksheet rectangle exceeds transfer limits.'}
 $values=$sheet.Range('A1',((ColumnName $cols)+$rows)).Value2;$matrix=New-Object System.Collections.ArrayList
 for($r=1;$r -le $rows;$r++){$row=New-Object System.Collections.ArrayList;for($c=1;$c -le $cols;$c++){$value=if($rows -eq 1 -and $cols -eq 1){$values}else{$values[$r,$c]};[void]$row.Add($value)};[void]$matrix.Add(@($row))};$result.matrix=@($matrix)
}
$result|ConvertTo-Json -Depth 10 -Compress
