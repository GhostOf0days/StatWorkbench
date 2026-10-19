# Architecture

StatWorkbench keeps the desktop shell, workbook UI, numerical engine, and file-format adapters behind separate interfaces. The Electron renderer never imports Python modules, and the Python worker communicates through bounded newline-delimited JSON requests.

## Main boundaries

- `electron/` owns application lifecycle, IPC, preferences, project persistence, and operating-system spreadsheet adapters. `preload.cjs` exposes the small renderer API; renderer code does not access Node.js directly.
- `renderer/` owns workbook state and UI. `workbook.js` composes focused workbook data, chart, import, and external-workbook modules. Analysis input and result-chart rendering are separate from workbook editing.
- `backend/worker.py` validates requests and dispatches through analysis catalogs. Each analysis family exposes its own catalog and `analyze` function under `backend/analyses/`.
- `backend/analyses/basic_catalog.py` defines core procedure metadata; numerical implementations stay in `basic.py`, with options, reports, model controls, native numerical helpers, and design-of-experiments procedures in their own modules.
- `backend/analyses/advanced_metadata.py`, `advanced_time.py`, `advanced_survival.py`, `advanced_controlcharts.py`, and `advanced_charts.py` keep advanced procedure metadata and specialized report logic out of the main dispatcher.
- `dependence.py`, `copulas.py`, and `stochastic.py` are independent analysis families. They share the worker contract without depending on one another.
- `backend/file_io.py` handles external data formats; `spjs_import.py` handles project translation and serialization; `report_xlsx.py` writes analysis reports.
- `scripts/` contains build, packaging, and verification entry points. `tests/` checks numerical methods, protocol boundaries, workbook behavior, and platform adapters.

## Dependency rules

Analysis modules should depend on shared numerical or report helpers, not on Electron or renderer modules. Platform-specific integration belongs in the Electron adapters or `addin/`. New analysis families should add a catalog and `analyze(analysis_id, data, options)` implementation and register once in `backend/worker.py`. Keep IPC payloads and analysis results JSON-serializable and validate them at the worker boundary.

## Verification

Run `python -m pytest tests -q`, `npm run test:renderer`, `npm run test:syntax`, and `npm run test:excel-ribbon`. The GitHub Actions workflow also builds and smoke-checks native packages on macOS, Windows, and Linux; native Microsoft Excel automation requires a runner with Excel installed.
