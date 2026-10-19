# Excel integration on Windows

The Windows desktop app connects to desktop Excel through a small .NET Framework bridge. To build the bridge on Windows before packaging, run:

```powershell
python scripts/build_windows_bridge.py
```

The app can use the workbook and range selected in Excel, then write output to the current workbook or a new workbook. The optional [Excel ribbon add-in](../addin/windows/README.md) provides a StatWorkbench tab and opens analysis dialogs from Excel selections.

The bridge preserves typed values, protects formula-like text, identifies the connected workbook, and keeps the user's workbook open after an operation. Editable line, scatter, spline, step, bar, stacked-bar, and standard histogram charts are supported where the selected Excel version accepts them. Box plots and unsupported chart geometry may be inserted as rendered images.

Install and validate the packaged app on a Windows machine with desktop Excel before relying on the integration. Excel automation requires a local desktop installation; hosted build runners alone do not exercise that workflow.
