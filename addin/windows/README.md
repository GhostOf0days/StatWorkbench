# Excel ribbon add-in for Windows

The optional COM add-in adds a **StatWorkbench** tab to desktop Excel. It opens the desktop application with the selected workbook, worksheet, and cell range, then writes analysis results back to Excel.

## Build

On Windows, from the project root:

```powershell
python scripts/generate_excel_ribbon.py --check
npm run build:excel-addin
```

The build uses the .NET Framework 4.x C# compiler supplied with Windows. It produces an AnyCPU COM assembly for desktop Excel and does not require Office interop packages.

## Install

1. Extract the add-in package to a stable folder.
2. Close Excel and run the included installer with the absolute path to the StatWorkbench desktop executable:

   ```powershell
   .\Install.ps1 -Executable 'C:\Apps\StatWorkbench\StatWorkbench.exe'
   ```

3. Reopen Excel and use the StatWorkbench tab.

Installation writes per-user COM and Excel add-in registrations and copies the adapter DLL to `%LOCALAPPDATA%\StatWorkbench\ExcelAddin`. It does not require administrator privileges. To remove the add-in, close Excel and run `Uninstall.ps1`.

Organizations may require signed scripts or add-ins. Use the approved signing and deployment process for managed Windows devices. The installer does not change PowerShell execution policy or other security settings.

## Workbook handling

The bridge attaches to the Excel instance that launched the request and checks the workbook identity before reading or writing. Multiple independent Excel processes are not supported. It preserves typed values and protects formula-like text. Supported charts can be inserted as editable objects; unsupported geometry is written as a rendered image with a warning.

Actual ribbon operation requires desktop Excel. Validate installation, selection, analysis, and writeback on the Windows systems where the add-in will be used.
