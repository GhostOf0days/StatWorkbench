# Excel and Numbers on macOS

StatWorkbench can read a worksheet from Microsoft Excel or Apple Numbers and write analysis output to a new sheet or workbook. The app uses macOS automation permissions to communicate with these applications. Approve the operating-system prompt when connecting to a workbook; denied permissions are reported by the app.

## Charts and formatting

Supported charts can be inserted as editable objects in Excel and in new Numbers workbooks. Numbers may use a rendered image for charts added to an existing workbook when its automation interface cannot transfer editable chart objects. Box-plot fills, custom point labels, and unequal-width histogram geometry may also use rendered images. Numeric values remain numeric even when a spreadsheet application cannot apply the requested display precision.

Analysis output is written into the selected workbook or a new workbook according to the output preference. The integration does not close or quit the user's spreadsheet application. Review the output and save the workbook from Excel or Numbers when ready.
