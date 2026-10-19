# StatWorkbench

StatWorkbench is an open-source desktop spreadsheet and statistical analysis application for macOS, Windows, and Linux. It combines an editable workbook with a local Python analysis engine, so data and calculations stay on your computer.

## Features

- Edit worksheets, formulas, formatting, charts, and multiple tabs.
- Run descriptive statistics, hypothesis tests, ANOVA, regression, multivariate analysis, nonparametric tests, time-series methods, survival analysis, sampling, quality-control charts, and data transformations.
- Explore dependence with correlation matrices, partial and distance correlation, mutual information, tail co-exceedance, lead–lag analysis, and bivariate copulas.
- Analyze finite-state sequences with transition matrices, communicating classes, stationary distributions, periods, and ergodicity diagnostics.
- Save analysis projects and reports; import and export common spreadsheet, text, and statistics formats.
- Import and export legacy `.spjs` workbook files. See [format support](docs/SPJS_INTEROPERABILITY.md) for known limitations.
- Use Excel or Numbers as an external workbook where supported. See the [macOS](docs/MAC_SPREADSHEETS.md) and [Windows](docs/WINDOWS_EXCEL.md) setup notes.

See [supported features and formats](docs/COMPATIBILITY.md), [Dependence methods](docs/dependence.md), [Copula methods](docs/copulas.md), and [stochastic processes](docs/stochastic-processes.md).

## Downloads

Download the latest desktop installers from [GitHub Releases](https://github.com/GhostOf0days/StatWorkbench/releases/latest). Future public releases require Developer ID signing and Apple notarization on macOS, and Authenticode signing on Windows. SmartScreen may still warn about a newly published Windows app until its reputation builds; see [code signing and release trust](docs/CODE_SIGNING.md). Releases also include SHA-256 checksums. The currently published v0.1.0 installers predate these signing checks and remain unsigned.

See [the architecture guide](docs/ARCHITECTURE.md) for module boundaries and the analysis extension contract.

## Run from source

Requirements: Python 3.11 or later and Node.js 22.12 or later.

```sh
python3 -m venv .venv
# macOS / Linux
.venv/bin/python -m pip install -r requirements.txt
# Windows: use .venv\Scripts\python.exe instead
npm ci
npm start
```

Optional file-format readers are listed in `requirements-formats.txt`. The desktop application runs analyses in a local Python worker.

## Test and build

```sh
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest tests -q
npm run test:renderer
npm run test:syntax
npm run test:excel-ribbon
npm run build:renderer
```

To package the desktop application, install the backend build requirements and run `scripts/build_backend.py`, then use `npm run pack` or `npm run dist`. Build and validate packages on each target operating system. See `.github/workflows/build.yml` for the configured CI jobs.

## License

StatWorkbench source code is licensed under the MIT License. Third-party software and data-format libraries retain their respective licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and `licenses/`.
