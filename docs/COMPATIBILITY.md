# Features and formats

StatWorkbench is a spreadsheet-based statistical analysis application. The analysis catalog lists the procedures available in the current build and each procedure's input requirements and limitations.

## Workbook features

The built-in workbook supports multiple sheets, cell editing, formulas, number formats, charts, undo and redo, project save/open, and export of analysis reports. External workbook access is available through the integrations documented for [macOS](MAC_SPREADSHEETS.md) and [Windows](WINDOWS_EXCEL.md).

## File formats

| Format | Support |
|---|---|
| CSV and TSV | Import and export |
| XLSX | Import and export |
| JSON | Import and export |
| SQLite | Import tables and queries supported by the importer |
| XLS and ODS | Optional desktop import readers |
| SPSS, Stata, SAS, dBASE, and supported R data frames | Optional desktop import readers |
| `.spjs` | Legacy workbook import and export; see [format notes](SPJS_INTEROPERABILITY.md) |

Availability for optional readers depends on the packages installed with the desktop build. Unsupported fields, formulas, or drawing options are reported during import or export.

## Analysis areas

The catalog includes descriptive and inferential statistics, regression, ANOVA and experimental designs, multivariate methods, nonparametric methods, time series, survival analysis, data transformations, matrix operations, sampling, probability distributions, charts, and quality-control methods. Separate additions cover dependence analysis, bivariate copulas, and finite-state Markov chains.

Every analysis reports its accepted inputs and applicable limitations in its dialog or result. Statistical methods can make different choices about missing values, ties, degrees of freedom, and approximation rules; check the method notes when interpreting results.

## Platform targets

The application uses Electron with a Python worker. Build targets are configured for macOS, Windows, and Linux. Native integrations and packaging requirements vary by platform; use the platform-specific setup guides and validate a release on its target operating system.
