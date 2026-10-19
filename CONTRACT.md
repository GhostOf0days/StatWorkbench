# Development contract

StatWorkbench uses an Electron interface and a local Python analysis worker. Keep analysis behavior deterministic where a seed is provided, validate user inputs at the worker boundary, and report unsupported cases with actionable messages.

## Dataset

The worker dataset shape is `{"columns":["Name","Value"],"rows":[["A",1],["B",2]],"name":"Dataset"}`. Cells are strings, numbers, booleans, or null. Column references use column names. Missing-value policies must be explicit in each procedure.

## Analysis modules

Analysis modules expose catalog entries and calculation functions. Catalog entries describe an analysis identifier, name, category, description, accepted fields, and limitations. Field types include multi-column selection, single-column selection, numbers, integers, text, enumerated choices, and booleans.

Results use tables, charts, notes, and warnings. Numeric results remain numbers until presentation; the worker converts non-finite values to JSON null. The renderer escapes all returned text. The backend does not return executable HTML.

## Worker protocol

The worker accepts one JSON request per stdin line and emits one JSON response per request. Supported methods include catalog lookup, analysis, file import/export, and health checks. Diagnostic output belongs on stderr. Never evaluate arbitrary Python or shell input.

## Quality

Add meaningful numerical checks for statistical calculations, validation tests for invalid or degenerate inputs, and integration coverage for worker protocol changes. Document unsupported inputs and methodological assumptions in the catalog or feature guide.
