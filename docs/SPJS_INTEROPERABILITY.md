# Legacy `.spjs` workbook files

StatWorkbench can import and export `.spjs` workbook files. Import creates an editable workbook while retaining supported cell formatting, merged headings, dimensions, formulas, and chart data. Export writes current workbook values and supported formatting, formulas, and chart definitions.

## Formulas

Common A1 references, named ranges, and supported functions are converted to live formulas. Array formulas are expanded across their result ranges. Unsupported formulas are retained as inert metadata and displayed as an error rather than presenting an old cached result as a current calculation. External-workbook references, unknown functions, malformed formulas, and unsupported reference syntax may not calculate.

## Charts and layout

Supported line, spline, step, scatter, bar, and combined charts retain their numeric series, axes, and placement as worksheet drawings. Newly created box plots and unequal-width histograms can be exported as editable geometry; some styling such as translucent fill may be omitted. Unsupported chart features are reported in import/export notes.

The importer treats unknown workbook metadata as data. It does not execute formulas from external links, macros, scripts, or custom functions. Import and export preserve only the structures documented above; keep a backup when converting a workbook that uses unsupported features.
