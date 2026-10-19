"""Advanced statistical procedures."""
from __future__ import annotations

import math
import warnings
from itertools import combinations

import numpy as np
import pandas as pd
from scipy import special, stats
import statsmodels.api as sm
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.tsa.holtwinters import Holt, SimpleExpSmoothing
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import acf, adfuller, kpss, pacf
from sklearn.metrics import roc_curve, roc_auc_score
from backend.common import MAX_CELLS, MAX_COLUMNS, MAX_ROWS


def _f(key, label, typ="column", default=None, **kw):
    f = {"key": key, "label": label, "type": typ, **kw}
    if typ in ("column", "columns"):
        f.setdefault("required", True)
    if default is not None:
        f["default"] = default
    return f


def _s(key, label, values, default=None):
    vals = [(x, x.replace("_", " ").title()) if isinstance(x, str) else x for x in values]
    return _f(key, label, "select", default or vals[0][0], options=[{"value": v, "label": l} for v, l in vals])


COL = _f("column", "Variable")
COLS = _f("columns", "Variables", "columns")
TIME = _f("time", "Survival time")
STATUS = _f("status", "Event status (1 = event, 0 = censored)")
GROUP = _f("group", "Group (optional)", required=False)
ALPHA = _f("alpha", "Significance level", "number", 0.05, min=0.0001, max=0.5, step=0.01)
SEED = _f("seed", "Random seed", "integer", 42, min=0)
COUNT = _f("count", "Number of observations", "integer", 10, min=1, max=100000)


def _entry(i, name, category, fields, limits=()):
    return {"id": str(i), "name": name, "category": category,
            "description": name + ". Independent implementation of the observed command.",
            "fields": [dict(field) for field in fields], "coverage": "partial" if limits else "core", "limitations": list(limits)}


def catalog():
    time = "Time series"
    surv = "Survival analysis"
    data = "Data"
    chart = "Charts"
    entries = [
        _entry(1501, "Autocorrelation and partial autocorrelation", time, [COL, _f("lags", "Number of lags", "integer", 10, min=1)], ["ACF and Yule-Walker PACF with optional preparation and report controls."]),
        _entry(1502, "Moving average", time, [COL, _f("length", "Window length", "integer", 3, min=2), _s("method", "Method", ["trailing", "centered", "weighted"]), _f("weights", "Weights (oldest to newest, comma separated)", "text", "1,2,3")], ["Simple, centered, weighted and native Spencer smoothers; optional Excel ATP errors."]),
        _entry(1503, "Interrupted time series", time, [_f("before", "Before intervention"), _f("after", "After intervention")], ["Segmented least-squares model with independent errors; no autocorrelation correction."]),
        _entry(1510, "Seasonal decomposition", time, [COL, _f("period", "Seasonal period", "integer", 12, min=2), _s("model", "Model", ["additive", "multiplicative"])], ["Original-derived seasonal decomposition; requires four complete cycles."]),
        _entry(1520, "Remove mean", time, [COL]),
        _entry(1521, "Differences", time, [COL, _f("lag", "Lag", "integer", 1, min=1), _f("order", "Difference order", "integer", 1, min=1, max=10)]),
        _entry(1522, "Single exponential smoothing", time, [COL, _f("smoothing", "Alpha", "number", 0.1, min=0.001, max=1), _s("initial", "Initial level", ["mean", "first"]), _f("steps", "Forecast steps", "integer", 10, min=1, max=10000)], ["Original-derived first-M, full mean, first observation or custom initial level."]),
        _entry(1540, "Trend exponential smoothing", time, [COL, _s("trend", "Trend", ["linear", "exponential", "damped"]), _f("smoothing", "Alpha", "number", 0.1, min=0.001, max=1), _f("beta", "Beta", "number", 0.1, min=0.001, max=1), _f("phi", "Damping phi", "number", 0.9, min=0.001, max=1), _f("steps", "Forecast steps", "integer", 10, min=1, max=10000)], ["Initial level and trend use the selected smoothing model or explicit user values."]),
        _entry(1530, "Unit root and stationarity tests", time, [COL, _s("test", "Tests", ["both", "adf", "kpss"]), _s("regression", "Deterministic terms", [("c", "Constant"), ("ct", "Constant and trend")]), _f("lags", "ADF lag count", "integer", 1, min=0), _f("differences", "Difference order", "integer", 0, min=0, max=2)], ["ADF, Phillips-Perron and KPSS with separate deterministic terms and native bandwidth choices."]),
        _entry(1523, "Fast Fourier transform", time, [_f("real", "Real component"), _f("imaginary", "Imaginary component (optional)", required=False)]),
        _entry(1524, "Inverse Fourier transform", time, [_f("real", "Real component"), _f("imaginary", "Imaginary component (optional)", required=False)]),
        _entry(1620, "Life tables", surv, [TIME, STATUS, GROUP, _f("width", "Interval width", "number", 1, min=0.000001)], ["Actuarial estimate assumes censoring occurs uniformly within each interval; no confidence bands."]),
        _entry(1621, "Kaplan-Meier survival", surv, [TIME, STATUS, GROUP, ALPHA], ["Right-censored data; native linear Greenwood confidence limits with censoring carry-forward."]),
        _entry(1622, "Nelson-Aalen cumulative hazard", surv, [TIME, STATUS, GROUP], ["Right-censored data; native hazard and survival estimates with separate linear confidence limits."]),
        _entry(1309, "Cox proportional hazards regression", surv, [TIME, STATUS, _f("predictors", "Numeric predictors", "columns"), _s("ties", "Tied event times", ["breslow", "efron"]), ALPHA], ["Numeric predictors only; no time-varying covariates, strata, left truncation or proportional-hazards diagnostics."]),
        _entry(1601, "Probit dose-response", surv, [_f("dose", "Dose"), _f("events", "Event count"), _f("total", "Group size")], ["Log-dose MLE and Finney-weighted raw-dose LS, including second-series relative potency."]),
        _entry(1610, "ROC curve", surv, [_f("score", "Test score"), _f("status", "Outcome (1 positive, 0 negative)"), _s("direction", "Positive score direction", ["higher", "lower"]), ALPHA], ["All four strict/inclusive threshold rules; DeLong AUC inference and exact binomial coordinate intervals."]),
        _entry(1611, "Compare paired ROC curves", surv, [_f("columns", "Test scores", "columns"), _f("status", "Outcome (1 positive, 0 negative)"), _s("direction", "Positive score direction", ["higher", "lower"])], ["Pairwise correlated AUC comparisons using DeLong influence covariance; no multiplicity adjustment."]),
        _entry(1630, "Bland-Altman agreement", surv, [_f("first", "Method 1"), _f("second", "Method 2")], ["Independent or repeated-subject agreement with a within/between-subject variance decomposition."]),
        _entry(3001, "Stack columns", data, [COLS]),
        _entry(3002, "Unstack column", data, [COL, _f("group", "Group")]),
        _entry(3200, "Transpose", data, [COLS]),
        _entry(3003, "Standardize variables", data, [COLS, _s("method", "Method", ["zscore", "center", "scale", "affine", "range"]), _f("a", "A", "number", 0), _f("b", "B", "number", 0), _s("ddof", "Standard deviation", [("1", "Sample (N−1)"), ("0", "Population (N)")])]),
        _entry(3005, "Box-Cox transformation", data, [COLS, _f("estimate", "Estimate lambda by maximum likelihood", "boolean", True), _f("lambda", "Lambda", "number", 0, min=-5, max=5), _f("shift", "Additive shift", "number", 0)], ["Requires positive shifted data; geometric-mean rescaling and automatic shifts not implemented."]),
        _entry(3201, "Matrix multiplication", data, [_f("left", "Left matrix columns", "columns"), _f("right", "Right matrix columns", "columns")], ["Both matrices use dataset rows; trailing empty rows trimmed separately, internal missing cells rejected."]),
        _entry(3202, "Matrix inverse", data, [COLS]),
        _entry(3203, "Matrix determinant", data, [COLS]),
        _entry(3301, "Random sample", data, [COLS, COUNT, SEED, _f("replace", "With replacement", "boolean", False)]),
        _entry(3302, "Periodic sample", data, [COLS, _f("interval", "Every Nth row", "integer", 2, min=1), _f("start", "First row (1-based)", "integer", 1, min=1)]),
        _entry(3303, "Conditional sample", data, [COLS, _f("condition_column", "Condition variable"), _s("condition", "Condition", ["eq", "ne", "lt", "le", "gt", "ge", "between", "outside"]), _f("a", "A", "number", 0), _f("b", "B", "number", 1)], ["Numeric comparison and inclusive intervals; rank/percentile conditions not implemented."]),
    ]
    rnd_fields = [COUNT, _f("variables", "Number of variables", "integer", 1, min=1, max=100), SEED, _s("sort", "Sort", ["none", "ascending", "descending"])]
    for i, name, fields in [
        (3100, "Discrete uniform", [_f("low", "Lower bound (inclusive)", "integer", 0), _f("high", "Upper bound (exclusive)", "integer", 100)]),
        (3101, "Continuous uniform", [_f("low", "Lower bound", "number", 0), _f("high", "Upper bound", "number", 1)]),
        (3102, "Normal random numbers", [_f("mean", "Mean", "number", 0), _f("sd", "Standard deviation", "number", 1, min=0)]),
        (3103, "Chi-square random numbers", [_f("df", "Degrees of freedom", "number", 5, min=0.001)]),
        (3104, "F random numbers", [_f("df", "Numerator degrees of freedom", "number", 5, min=1), _f("df2", "Denominator degrees of freedom", "number", 4, min=1), _s("help.random.f_scaling", "F scaling", [("native", "Unscaled chi-square ratio"), ("conventional", "Conventional F: divide each chi-square by its df")])]),
    ]:
        entries.append(_entry(i, name, "Random numbers", rnd_fields + fields, ["A fixed seed reproduces the sequence under the same scientific runtime."]))
    entries.extend([
        _entry(1701, "Prevalence survey sample size", "Sample size", [_f("precision", "Absolute precision (%)", "number", 5, min=0.001, max=100), _f("prevalence", "Expected prevalence (%)", "number", 50, min=0.001, max=99.999), _f("population", "Population size", "integer", 10000, min=2), ALPHA]),
        _entry(1702, "Exact binomial confidence interval", "Sample size", [_f("successes", "Successes", "integer", 5, min=0), _f("total", "Total observations", "integer", 10, min=1), ALPHA]),
        _entry(1703, "Sample size to observe events", "Sample size", [_f("prevalence", "Event probability (%)", "number", 5, min=0.00001, max=100), _f("events", "Minimum events", "integer", 1, min=1), _f("probability", "Required probability", "number", 0.95, min=0.001, max=0.999999)]),
        _entry(1704, "Case-control study sample size", "Sample size", [_f("odds_ratio", "Minimum odds ratio", "number", 2, min=0.001), _f("exposure", "Exposed controls (%)", "number", 20, min=0.001, max=99.999), _f("power", "Power (%)", "number", 80, min=1, max=99.99), _f("ratio", "Controls per case", "number", 1, min=0.01), ALPHA], ["Unmatched two-sided normal approximation; matched design and continuity correction not implemented."]),
        _entry(4001, "Box plot", chart, [COLS, GROUP], ["All four whisker and nine quantile definitions are calculated and serialized for plotting."]),
        _entry(4002, "Scatter plot", chart, [_f("x", "X variable"), _f("y", "Y variable"), GROUP], ["Separate or combined groups with confidence/prediction ellipses and axis reversal."]),
        _entry(4003, "Stem-and-leaf plot", chart, [COLS, _f("unit", "Leaf unit", "number", 1, min=0.000001)], ["Leaf units are explicit; values truncate toward zero at the chosen precision."]),
    ])
    for i, name in [(4011, "Normal"), (4012, "Beta"), (4013, "Chi-square"), (4014, "Gamma"), (4015, "Log-normal"), (4016, "Student t"), (4017, "Uniform"), (4018, "Weibull")]:
        entries.append(_entry(i, name + " Q-Q plot", chart, [COLS, _f("shape", "Shape / degrees of freedom", "number", 1, min=0.001), _f("shape2", "Beta second shape", "number", 1, min=0.001)], ["All four plotting positions and tie rules; native automatic or manual parameters, reference and detrended output."]))
    for i, name in [(4102, "Xbar-R"), (4103, "Xbar-S")]:
        entries.append(_entry(i, name + " control chart", chart, [COLS, _f("sigmas", "Control limit multiplier", "number", 3, min=0.1)], ["Four subgroup layouts, variable group size and native control-limit settings."]))
    entries.extend([
        _entry(4104, "CUSUM control chart", chart, [COL, _f("k", "Reference K (sigma units)", "number", 0.5, min=0), _f("h", "Decision H (sigma units)", "number", 4, min=0.01)], ["Native grouped CUSUM with automatic or manual target and V-mask parameters."]),
        _entry(4105, "P and NP control charts", chart, [_f("count_column", "Defectives count"), _f("size_column", "Subgroup size"), _f("sigmas", "Control limit multiplier", "number", 3, min=0.1)]),
        _entry(4106, "C control chart", chart, [_f("count_column", "Defect count"), _f("sigmas", "Control limit multiplier", "number", 3, min=0.1)]),
        _entry(4107, "U control chart", chart, [_f("count_column", "Defect count"), _f("size_column", "Subgroup size / exposure"), _f("sigmas", "Control limit multiplier", "number", 3, min=0.1)]),
        _entry(4108, "Individuals and moving range", chart, [COL, _f("sigmas", "Control limit multiplier", "number", 3, min=0.1)]),
    ])
    from .advanced_metadata import FIELDS
    from .advanced_time import ALIASES
    native_aliases = {"1620": {"width"}, "1610": {"direction"}, "1611": {"direction"}, "4104": {"k", "h"}}
    native_aliases.update({key: {"sigmas"} for key in ("4102", "4103", "4105", "4107", "4108")})
    for entry in entries:
        if entry["id"] in FIELDS:
            entry["fields"] = [field for field in entry["fields"] if field["key"] not in native_aliases.get(entry["id"], set())]
            entry["fields"] = [f for f in entry["fields"] if f["key"] not in ("shape", "shape2", *ALIASES.get(entry["id"], {}), *({"1502": ["method", "weights"], "1522": ["initial"], "1540": ["trend"], "1530": ["test", "regression"], "1510": ["model"]}.get(entry["id"], [])))] + FIELDS[entry["id"]]
            if entry["id"] == "1502": entry["fields"].append(_f("sta.time.wma.weightsvar", "Weighted MA: Weights", required=False))
            if entry["id"] == "1540":
                entry["fields"] += [_s("help.seasonal", "Holt–Winters seasonal component", ["none", "additive", "multiplicative"]), _f("help.seasonal_period", "Season length", "integer", 12, min=2), _f("help.seasonal_gamma", "Seasonal smoothing gamma", "number", .1, min=0, max=1)]
            if entry["id"] == "1521":
                for field in entry["fields"]:
                    if field["key"] == "column": field.update(type="columns", label="Time series")
            if entry["id"] in ("4102", "4103"):
                entry["fields"] += [_f("sta.cc.xbar.GROUPS", "Data layout #1 - Groups", required=False), _f("sta.cc.xbar.d2.subgrsize", "Data layout #2 - Subgroup Sizes", "integer", 2, min=2)]
            if entry["id"] == "4102":
                entry["fields"] = [{**field, "options": [*field["options"], {"value": "1", "label": "Minimum variance linear unbiased estimate"}]} if field["key"] == "sta.cc.stddevest" else field for field in entry["fields"]]
            if entry["id"] == "4108":
                entry["fields"] += [_f("help.mr_span", "Moving range span", "integer", 2, min=2, max=50), _f("help.individuals_target", "Known process mean (blank = estimate)", "text", "")]
            if entry["id"] == "1601":
                entry["fields"] += [_f("PROBIT_S_0.N", "Dose (Stimulus) #N", required=False), _f("PROBIT_S_1.N", "Count (Effect) #N", required=False), _f("PROBIT_S_3.N", "Sample Size #N", required=False)]
            if entry["id"] == "1630": entry["fields"].append(_f("ba.groups.subject", "Subject", required=False))
            if entry["id"] == "4104": entry["fields"].append(_f("GROUPS", "Groups", required=False))
            if entry["id"] in ("4105", "4107"):
                entry["fields"] = [f for f in entry["fields"] if f["key"] != "size_column"]
                entry["fields"].append(_f("sta.cc.subgr_size", "Subgroup Sizes"))
            entry["limitations"] = []
            entry["coverage"] = "core"
    from .data_controls import apply_catalog
    return apply_catalog(entries)


def _num(o, key, default, low=None, high=None, integer=False):
    raw = o.get(key, default)
    if isinstance(raw, bool):
        raise ValueError(f"{key} must be a number.")
    try:
        x = float(raw)
    except (ValueError, TypeError):
        raise ValueError(f"{key} must be a number.") from None
    if not math.isfinite(x) or (low is not None and x < low) or (high is not None and x > high) or (integer and x != math.floor(x)):
        raise ValueError(f"Invalid {key}; expected {'integer' if integer else 'number'} between {low} and {high}.")
    return int(x) if integer else x


def _choice(o, key, default, allowed):
    x = o.get(key, default)
    if x not in allowed:
        raise ValueError(f"{key} must be one of: {', '.join(allowed)}.")
    return x


def _names(data, raw, minimum=1):
    names = [raw] if isinstance(raw, str) else raw
    if not isinstance(names, list) or len(names) < minimum or len(names) != len(set(names)):
        raise ValueError(f"Select at least {minimum} distinct variable(s).")
    if any(n not in data["columns"] for n in names):
        raise ValueError("A selected variable does not exist in this dataset.")
    return names


def _frame(data):
    return pd.DataFrame(data["rows"], columns=data["columns"])


def _numeric_frame(raw):
    f = raw.apply(pd.to_numeric, errors="coerce").astype(float)
    for name in raw.columns:
        missing = raw[name].isna() | raw[name].map(lambda v: isinstance(v, str) and not v.strip())
        if (f[name].isna() & ~missing).any():
            raise ValueError(f"{name} contains nonnumeric data; correct it or mark it as missing explicitly.")
    if np.isinf(f.to_numpy()).any():
        raise ValueError("Infinite numeric values are not supported.")
    return f


def _numbers(data, names, minimum=2, strict=False):
    names = _names(data, names)
    f = _numeric_frame(_frame(data)[names])
    valid = np.isfinite(f.to_numpy()).all(axis=1)
    if strict and not valid.all():
        raise ValueError("Series/matrix contains missing or nonnumeric values. Clean it explicitly to preserve row positions.")
    if int(valid.sum()) < minimum:
        raise ValueError(f"At least {minimum} complete numeric rows are required.")
    return f.loc[valid].to_numpy(), valid


def _padded_series(data, name, minimum=3):
    """Remove only absent tail padding; preserve internal temporal positions."""
    name = _names(data, name)[0]
    raw = _frame(data)[name]
    missing = raw.isna() | raw.map(lambda v: isinstance(v, str) and not v.strip())
    positions = np.flatnonzero(~missing.to_numpy())
    if not len(positions):
        raise ValueError(f"{name} has no observations.")
    raw = raw.iloc[:positions[-1]+1]
    x = pd.to_numeric(raw, errors="coerce").to_numpy(float)
    if len(x) < minimum or not np.isfinite(x).all():
        raise ValueError(f"{name} needs at least {minimum} complete observations, with no internal gaps or nonnumeric values to preserve row positions.")
    return x


def _table(title, columns, rows):
    return {"title": title, "columns": columns, "rows": [list(x) for x in rows]}


def _series(name, x, y):
    return {"name": str(name), "x": np.asarray(x).tolist(), "y": np.asarray(y).tolist()}


def _chart(title, series, kind="line", x="Observation", y="Value"):
    return {"type": kind, "title": title, "xLabel": x, "yLabel": y, "series": series}


def _dataset(names, values, name="Result"):
    rows = values.tolist() if isinstance(values, np.ndarray) else values
    return {"columns": list(names), "rows": rows, "name": name}


def _base(i):
    entry = next((x for x in catalog() if x["id"] == i), None)
    if entry is None:
        raise ValueError("Unknown analysis identifier.")
    return {"analysis": i, "title": entry["name"], "tables": [], "charts": [],
            "notes": list(entry["limitations"]), "warnings": []}


def _missing(r, mask):
    n = len(mask) - int(np.sum(mask))
    if n:
        r["notes"].append(f"Excluded {n} rows with missing, nonnumeric or nonfinite values in the selected variables (complete-case deletion).")


def analyze(analysis_id, data, options):
    i = str(analysis_id)
    o = dict(options)
    r = _base(i)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        from . import data_controls
        if i in data_controls.HANDLED:
            data_controls.run(i, data, o, r)
        elif i.startswith("15"):
            _time(i, data, o, r)
        elif i.startswith("16") or i == "1309":
            _survival(i, data, o, r)
        elif i.startswith("17"):
            _sample_size(i, o, r)
        elif i.startswith("31"):
            _random(i, o, r)
        elif i.startswith(("30", "32", "33")):
            _data(i, data, o, r)
        elif i.startswith("4"):
            _charts(i, data, o, r)
        else:
            raise ValueError("Unknown analysis identifier.")
        r["warnings"].extend(dict.fromkeys(str(w.message) for w in caught))
    return r


def residual_diagnostics(data, o):
    """Test an existing residual sequence with auxiliary regressions.

    Native entries 0x1c5b50/0x27b840 route transformations into the common
    auxiliary OLS implementation at 0x216844, which reports N * R-squared.
    """
    residual = _names(data, o.get('residuals', o.get('sta.var.resid')))[0]
    predictors = _names(data, o.get('predictors', o.get('sta.indvar')))
    if residual in predictors:
        raise ValueError('Residuals and independent variables must use different columns.')
    raw = _numeric_frame(_frame(data)[[residual] + predictors])
    occupied = np.flatnonzero(~raw.isna().all(axis=1).to_numpy())
    if not len(occupied):
        raise ValueError('Select a nonempty residual sequence and independent variables.')
    frame = raw.iloc[:occupied[-1]+1]
    if frame.isna().any().any():
        raise ValueError('Residual diagnostics require aligned observations with no internal gaps or missing values; row order is preserved.')
    e = frame[residual].to_numpy()
    x = frame[predictors].to_numpy()
    n, k = x.shape
    if n < 3:
        raise ValueError('Residual diagnostics require at least three observations.')
    enabled = {}
    for key in ('reg.bpg', 'reg.harvey', 'reg.glejser', 'reg.arch', 'reg.white', 'sta.reg.modelsum.opt'):
        value = o.get(key, key != 'sta.reg.modelsum.opt')
        if not isinstance(value, bool):
            raise ValueError(f'{key} must be true or false.')
        enabled[key] = value
    if not any(enabled[key] for key in ('reg.bpg', 'reg.harvey', 'reg.glejser', 'reg.arch', 'reg.white')):
        raise ValueError('Select at least one heteroscedasticity test.')
    lags = _num(o, 'sta.time.lags_c', 1, 1, n-4, True) if enabled['reg.arch'] else 1
    mode = _num(o, 'sta.time.reg.include', 0, 0, 2, True) if enabled['reg.white'] else 0
    result = dict(analysis='1320', title='Heteroscedasticity Tests', tables=[], charts=[], warnings=[],
        notes=['The supplied residuals are analyzed directly; no response regression is fitted.',
               'All tests use the N × R² statistic and chi-square reference distribution for auxiliary regressions with an intercept.',
               'Rows retain their original order. Only entirely empty trailing rows are trimmed.'])
    rows, summaries = [], []
    if len(raw) != len(frame):
        result['notes'].append(f'Trimmed {len(raw)-len(frame)} entirely empty trailing rows.')
    if np.max(np.abs(e)) > np.sqrt(np.finfo(float).max)/2 or np.max(np.abs(x)) > np.sqrt(np.finfo(float).max)/2:
        raise ValueError('Residuals and predictors are too large to square safely; rescale them first.')
    squared = e*e

    def auxiliary(name, y, values, labels, problem=None):
        count = len(y)
        terms = values.shape[1]
        if problem is None and count*(terms+1) > MAX_CELLS:
            problem = 'the auxiliary design exceeds the two-million-cell limit'
        design = None
        if problem is None:
            design = np.column_stack([np.ones(count), values])
            if count <= terms+1:
                problem = 'the auxiliary regression has no residual degrees of freedom'
            elif not np.isfinite(y).all() or not np.isfinite(design).all():
                problem = 'the auxiliary transformation contains a nonfinite value'
            elif np.linalg.matrix_rank(design) < design.shape[1]:
                problem = 'the auxiliary regressors are constant or collinear'
            elif np.ptp(y) == 0:
                problem = 'the transformed residuals have zero variance'
        if problem is not None:
            rows.append([name, count, terms, None, None])
            result['warnings'].append(f'{name} unavailable: {problem}.')
            return
        fit = sm.OLS(y, design).fit()
        r2 = float(np.clip(fit.rsquared, 0, 1))
        statistic = count*r2
        probability = float(stats.chi2.sf(statistic, terms))
        rows.append([name, count, terms, statistic, probability])
        if enabled['sta.reg.modelsum.opt']:
            summaries.append(_table(name+' — Model Summary', ['N','R²','Adjusted R²','Residual df','F','F p-value'],
                [[count,r2,float(fit.rsquared_adj),int(fit.df_resid),float(fit.fvalue),float(fit.f_pvalue)]]))
            summaries.append(_table(name+' — Coefficients', ['Term','Estimate','Std. error','t','p-value'],
                zip(['Intercept']+labels,fit.params,fit.bse,fit.tvalues,fit.pvalues)))
    if enabled['reg.bpg']:
        scale = float(np.mean(squared))
        auxiliary('Breusch-Pagan-Godfrey (BPG)', squared/scale if scale>0 else squared, x, predictors,
                  None if scale>0 else 'all supplied residuals are zero')
    if enabled['reg.harvey']:
        auxiliary('Harvey', 2*np.log(np.abs(e)) if np.all(e != 0) else squared, x, predictors,
                  'log squared residuals are undefined for zero residuals' if np.any(e == 0) else None)
    if enabled['reg.glejser']:
        auxiliary('Glejser', np.abs(e), x, predictors)
    if enabled['reg.arch']:
        if (n-lags)*(lags+1) > MAX_CELLS:
            raise ValueError('ARCH auxiliary design exceeds the two-million-cell limit; use fewer lags.')
        lagged = np.column_stack([squared[lags-j:n-j] for j in range(1,lags+1)])
        auxiliary("Engle's ARCH", squared[lags:], lagged, [f'Squared residual lag {j}' for j in range(1,lags+1)])
    if enabled['reg.white']:
        terms = k if mode==2 else 2*k if mode==1 else 2*k+k*(k-1)//2
        if n*(terms+1) > MAX_CELLS:
            raise ValueError('White auxiliary design exceeds the two-million-cell limit; select fewer predictors or terms.')
        # Native order: squares, linear terms, then distinct cross-products.
        values = [x*x]
        labels = [name+'²' for name in predictors]
        if mode != 2:
            values.append(x)
            labels += predictors
        if mode == 0 and k > 1:
            pairs = list(combinations(range(k),2))
            values.append(np.column_stack([x[:,a]*x[:,b] for a,b in pairs]))
            labels += [predictors[a]+' × '+predictors[b] for a,b in pairs]
        auxiliary('White', squared, np.column_stack(values), labels)
    result['tables'] = [_table('Heteroscedasticity Tests', ['Test','N','df','Statistic (N × R²)','p-value'], rows)] + summaries
    return result


def _time(i, data, o, r):
    if i in ("1501", "1502", "1510", "1521", "1522", "1540", "1530"):
        from .advanced_time import run
        return run(i, data, o, r)
    if i == "1503":
        b = _padded_series(data, o.get("before"))
        a = _padded_series(data, o.get("after"))
        r["notes"].append("Trailing empty cells permit unequal pre/post series lengths; internal gaps are rejected to preserve time spacing.")
        y = np.r_[b, a]
        t = np.arange(len(y), dtype=float)
        intervention = (t >= len(b)).astype(float)
        x = np.column_stack([np.ones(len(y)), t, intervention, np.maximum(0, t-len(b))])
        fit = sm.OLS(y, x).fit()
        r["tables"].append(_table("Segmented regression", ["Term", "Estimate", "Std. error", "t", "p"], zip(["Intercept", "Initial slope", "Level change", "Slope change"], fit.params, fit.bse, fit.tvalues, fit.pvalues)))
        r["charts"].append(_chart("Interrupted series", [_series("Observed", t+1, y), _series("Fitted", t+1, fit.fittedvalues)]))
        for label, values in [("Before", b), ("After", a), ("Before: first differences", np.diff(b)), ("After: first differences", np.diff(a))]:
            if len(values) < 2 or np.ptp(values) == 0:
                r["notes"].append(f"{label}: autocorrelation is undefined for a constant or single-value series.")
                continue
            lags = np.arange(min(10, len(values)-1)+1)
            correlation = acf(values, nlags=lags[-1], fft=True)
            r["tables"].append(_table(label+" correlogram", ["Lag", "Autocorrelation"], zip(lags, correlation)))
            r["charts"].append(_chart(label+" correlogram", [_series("ACF", lags, correlation)], "bar", "Lag", "Correlation"))
        return
    if i in ("1523", "1524"):
        names = [o.get("real")]
        if o.get("imaginary"):
            names.append(o["imaginary"])
        a, _ = _numbers(data, names, minimum=1, strict=True)
        z = a[:, 0] + (1j*a[:, 1] if a.shape[1] == 2 else 0j)
        z = np.fft.fft(z) if i == "1523" else np.fft.ifft(z)
        rows = np.column_stack([np.arange(len(z)), z.real, z.imag, np.abs(z)])
        r["tables"].append(_table("Transform", ["Index", "Real", "Imaginary", "Magnitude"], rows))
        r["dataset"] = _dataset(["Real", "Imaginary"], np.column_stack([z.real, z.imag]), r["title"])
        r["notes"].append("Forward transform is unnormalized; inverse divides by N. Indices run from 0 to N−1.")
        return
    a, _ = _numbers(data, o.get("column"), minimum=3, strict=True)
    y = a[:, 0]
    n = len(y)
    t = np.arange(1, n+1)
    if i == "1501":
        if np.ptp(y) == 0:
            raise ValueError("Autocorrelation requires nonconstant observations.")
        lags = _num(o, "lags", min(10, n//2-1), 1, max(1, n//2-1), True)
        av = acf(y, nlags=lags, fft=True)
        pv = pacf(y, nlags=lags, method="ywm")
        r["tables"].append(_table("Correlations", ["Lag", "ACF", "PACF"], zip(range(lags+1), av, pv)))
        r["charts"].append(_chart("Correlogram", [_series("ACF", np.arange(lags+1), av), _series("PACF", np.arange(lags+1), pv)], "bar", "Lag", "Correlation"))
    elif i in ("1520", "1521", "1502"):
        if i == "1520":
            out = y-y.mean()
        elif i == "1521":
            lag = _num(o, "lag", 1, 1, n-1, True)
            order = _num(o, "order", 1, 1, 10, True)
            if lag*order >= n:
                raise ValueError("Lag × order must be smaller than the number of rows.")
            out = pd.Series(y)
            for _ in range(order):
                out = out.diff(lag)
            out = out.to_numpy()
        else:
            length = _num(o, "length", 3, 2, n, True)
            method = _choice(o, "method", "trailing", ["trailing", "centered", "weighted"])
            if method == "weighted":
                try:
                    weights = np.array([float(x.strip()) for x in o.get("weights", "1,2,3").split(",")])
                except (ValueError, AttributeError):
                    raise ValueError("Weights must be comma-separated numbers.") from None
                if len(weights) != length or not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() <= 0:
                    raise ValueError("Provide one finite nonnegative weight per window position, with a positive sum.")
                weights /= weights.sum()
                out = pd.Series(y).rolling(length).apply(lambda z: np.dot(z, weights), raw=True).to_numpy()
            else:
                out = pd.Series(y).rolling(length, center=method == "centered").mean().to_numpy()
        r["tables"].append(_table("Series", ["Observation", "Original", "Result"], zip(t, y, out)))
        r["dataset"] = _dataset(["Original", "Result"], np.column_stack([y, out]), r["title"])
        r["charts"].append(_chart(r["title"], [_series("Original", t, y), _series("Result", t, out)]))
    elif i in ("1522", "1540"):
        alpha = _num(o, "smoothing", 0.1, 0.000001, 1)
        steps = _num(o, "steps", 10, 1, 10000, True)
        if i == "1522":
            initial = _choice(o, "initial", "mean", ["mean", "first"])
            fit = SimpleExpSmoothing(y, initialization_method="known", initial_level=y.mean() if initial == "mean" else y[0]).fit(smoothing_level=alpha, optimized=False)
        else:
            trend = _choice(o, "trend", "linear", ["linear", "exponential", "damped"])
            if trend == "exponential" and np.any(y <= 0):
                raise ValueError("Exponential trend requires positive data.")
            beta = _num(o, "beta", 0.1, 0.000001, 1)
            phi = _num(o, "phi", 0.9, 0.000001, 1)
            fit = Holt(y, exponential=trend == "exponential", damped_trend=trend == "damped", initialization_method="estimated").fit(smoothing_level=alpha, smoothing_trend=beta, damping_trend=phi if trend == "damped" else None, optimized=True)
        forecast = fit.forecast(steps)
        r["tables"].extend([_table("Fitted observations", ["Observation", "Actual", "One-step fit", "Residual"], zip(t, y, fit.fittedvalues, fit.resid)), _table("Forecast", ["Observation", "Forecast"], zip(range(n+1, n+steps+1), forecast))])
        r["charts"].append(_chart(r["title"], [_series("Actual", t, y), _series("One-step fit", t, fit.fittedvalues), _series("Forecast", np.arange(n+1, n+steps+1), forecast)]))
    elif i == "1510":
        period = _num(o, "period", 12, 2, n//2, True)
        model = _choice(o, "model", "additive", ["additive", "multiplicative"])
        if model == "multiplicative" and np.any(y <= 0):
            raise ValueError("Multiplicative decomposition requires positive data.")
        fit = seasonal_decompose(y, model=model, period=period)
        r["tables"].append(_table("Components", ["Observation", "Observed", "Trend", "Seasonal", "Residual"], zip(t, y, fit.trend, fit.seasonal, fit.resid)))
        r["dataset"] = _dataset(["Observed", "Trend", "Seasonal", "Residual"], np.column_stack([y, fit.trend, fit.seasonal, fit.resid]), r["title"])
        for label, v in [("Observed", y), ("Trend", fit.trend), ("Seasonal", fit.seasonal), ("Residual", fit.resid)]:
            r["charts"].append(_chart(label, [_series(label, t, v)]))
    elif i == "1530":
        order = _num(o, "differences", 0, 0, 2, True)
        y = np.diff(y, n=order)
        if len(y) < 8 or np.ptp(y) == 0:
            raise ValueError("Unit-root tests require at least eight nonconstant observations after differencing.")
        test = _choice(o, "test", "both", ["both", "adf", "kpss"])
        regression = _choice(o, "regression", "c", ["c", "ct"])
        rows = []
        if test in ("both", "adf"):
            maxlag = _num(o, "lags", 1, 0, max(0, len(y)//2-3), True)
            z = adfuller(y, maxlag=maxlag, regression=regression, autolag=None)
            rows.append(["ADF", z[0], z[1], z[2], "Unit root"])
        if test in ("both", "kpss"):
            z = kpss(y, regression=regression, nlags="auto")
            rows.append(["KPSS", z[0], z[1], z[2], "Stationary around deterministic terms"])
        r["tables"].append(_table("Tests", ["Test", "Statistic", "p-value", "Lags", "Null hypothesis"], rows))


def _random(i, o, r):
    from .native_random import NativeRandom
    r["notes"] = ["A fixed seed reproduces the sequence under the same scientific runtime."]
    n = _num(o, "count", 10, 1, 100000, True)
    k = _num(o, "variables", 1, 1, 100, True)
    if n*k > 2000000:
        raise ValueError("Generated dataset exceeds two million cells.")
    seed = _num(o, "seed", 42, 0, 2**53-1, True)
    rng = NativeRandom(seed)
    if seed != rng.seed:
        r["notes"].append(f"The effective 32-bit seed is {rng.seed}.")
    total = n*k
    if i in ("3100", "3101"):
        low = _num(o, "low", 0, integer=i == "3100")
        high = _num(o, "high", 100 if i == "3100" else 1, integer=i == "3100")
        if high <= low:
            raise ValueError("Upper bound must be greater than lower bound.")
        if i == "3101" and high-low < 1e-6:
            raise ValueError("Continuous uniform interval must be at least 0.000001 wide.")
        out = rng.integers(low, high, total) if i == "3100" else low+rng.uniform(total)*(high-low)
        r["notes"].append("The lower bound is included; the upper bound is excluded.")
    elif i == "3102":
        out = rng.normal(total)*_num(o, "sd", 1, 1e-6)+_num(o, "mean", 0)
    elif i == "3103":
        df = int(_num(o, "df", 5, 1, 2**31-1))
        out = rng.sum_squares(total, df)
        if float(o.get("df",5)) != df:
            r["notes"].append(f"Degrees of freedom truncated to {df}.")
    else:
        df = int(_num(o, "df", 5, 1, 2**31-1))
        df2 = int(_num(o, "df2", 4, 1, 2**31-1))
        if float(o.get("df",5)) != df or float(o.get("df2",4)) != df2:
            r["notes"].append(f"Degrees of freedom truncated to {df} and {df2}.")
        out = rng.sum_squares(total, df, df2)
        scaling = _choice(o, "help.random.f_scaling", "native", ["native", "conventional"])
        if scaling == "conventional":
            out *= df2/df
            r["notes"].append("Conventional F scaling: each chi-square is divided by its degrees of freedom.")
        else:
            r["notes"].append("This method uses an unscaled chi-square ratio. Select Conventional F to divide each component by its degrees of freedom.")
    # The native caller completes each variable before drawing the next one.
    out = out.reshape(k, n).T
    sort = _choice(o, "sort", "none", ["none", "ascending", "descending"])
    if sort != "none":
        out = np.sort(out, axis=0)
        if sort == "descending":
            out = out[::-1]
    names = [f"Random {j+1}" for j in range(k)]
    r["dataset"] = _dataset(names, out, r["title"])
    generation = _table("Generation", ["Rows", "Variables", "Seed", "Generator"], [[n, k, seed, "MT19937"]])
    generation["columnFormats"] = {"0": "0", "1": "0", "2": "0"}
    r["tables"].append(generation)


def _data(i, data, o, r):
    if i == "3002":
        names = _names(data, [o.get("column"), o.get("group")])
        f = _frame(data)[names]
        groups = list(pd.unique(f.iloc[:, 1].dropna()))
        if not groups:
            raise ValueError("No nonmissing groups found.")
        longest = int(f.iloc[:, 1].value_counts().max())
        if len(groups) > MAX_COLUMNS or len(groups)*longest > MAX_CELLS:
            raise ValueError("Unstacked result exceeds the dataset column/cell limit.")
        out = pd.DataFrame({str(g): pd.Series(f.loc[f.iloc[:, 1] == g].iloc[:, 0].to_list()) for g in groups})
        if len(out.columns) != len(groups):
            raise ValueError("Group labels collide after conversion to text.")
        r["dataset"] = _dataset(list(out.columns), out.where(pd.notna(out), None).values.tolist(), r["title"])
        return
    if i == "3201":
        mats = []
        for key in ("left", "right"):
            names = _names(data, o.get(key))
            f = _numeric_frame(_frame(data)[names])
            # Padding at the end of a smaller matrix is not data.
            while len(f) and f.iloc[-1].isna().all():
                f = f.iloc[:-1]
            a = f.to_numpy(dtype=float)
            if not a.size or not np.isfinite(a).all():
                raise ValueError("Matrix has missing or nonnumeric interior cells.")
            mats.append(a)
        if mats[0].shape[1] != mats[1].shape[0]:
            raise ValueError("Left column count must equal right row count.")
        if mats[0].shape[0]*mats[1].shape[1] > MAX_CELLS:
            raise ValueError("Matrix product exceeds the dataset cell limit.")
        out = mats[0] @ mats[1]
        r["dataset"] = _dataset([f"C{j+1}" for j in range(out.shape[1])], out, r["title"])
        r["tables"].append(_table("Product", r["dataset"]["columns"], out))
        return
    names = _names(data, o.get("columns"))
    f = _frame(data)[names]
    if i == "3001":
        if len(f)*len(names) > MAX_ROWS or len(f)*len(names)*2 > MAX_CELLS:
            raise ValueError("Stacked result exceeds the dataset row/cell limit.")
        rows = [[name, value] for name in names for value in f[name].to_list()]
        r["dataset"] = _dataset(["Variable", "Value"], rows, r["title"])
    elif i == "3200":
        if len(f) > MAX_COLUMNS:
            raise ValueError("Transpose would exceed 1000 columns.")
        columns=[f"Row {j+1}" for j in range(len(f))]
        r["dataset"] = _dataset(columns, f.to_numpy().T, r["title"])
        r["tables"].append(_table("Transposed matrix", ["Source variable", *columns], [[name,*f[name].to_list()] for name in names]))
    elif i in ("3003", "3005"):
        out = _numeric_frame(f)
        rows = []
        for name in names:
            valid = np.isfinite(out[name].to_numpy())
            x = out.loc[valid, name].to_numpy()
            if len(x) < 2:
                raise ValueError(f"{name} requires at least two finite numbers.")
            if i == "3003":
                ddof = int(_choice(o, "ddof", "1", ["0", "1"]))
                method = _choice(o, "method", "zscore", ["zscore", "center", "scale", "affine", "range"])
                a, b = _num(o, "a", 0), _num(o, "b", 0)
                sd = x.std(ddof=ddof)
                if method in ("zscore", "scale") and sd == 0:
                    raise ValueError(f"{name} has zero standard deviation.")
                if method == "zscore": y = (x-x.mean())/sd
                elif method == "center": y = x-x.mean()
                elif method == "scale": y = x/sd
                elif method == "affine":
                    if b == 0: raise ValueError("B must be nonzero for an affine transformation.")
                    y = (x-a)/b
                else:
                    if b <= a or np.ptp(x) == 0: raise ValueError("Range scaling requires B > A and nonconstant data.")
                    y = a + (x-x.min())*(b-a)/np.ptp(x)
                rows.append([name, len(x), x.mean(), sd])
            else:
                x = x+_num(o, "shift", 0)
                if np.any(x <= 0) or np.ptp(x) == 0:
                    raise ValueError("Box-Cox requires positive, nonconstant shifted values.")
                if o.get("estimate", True):
                    y, lam = stats.boxcox(x)
                else:
                    lam = _num(o, "lambda", 0, -5, 5)
                    y = stats.boxcox(x, lmbda=lam)
                rows.append([name, len(x), lam])
            out.loc[valid, name] = y
            out.loc[~valid, name] = np.nan
        r["tables"].append(_table("Transformation", ["Variable", "N", "Mean", "SD"] if i == "3003" else ["Variable", "N", "Lambda"], rows))
        r["dataset"] = _dataset(names, out.to_numpy(), r["title"])
        r["notes"].append("Missing/nonnumeric values remain empty; parameters are estimated per column from finite values.")
    elif i in ("3202", "3203"):
        a, _ = _numbers(data, names, minimum=1, strict=True)
        if a.shape[0] != a.shape[1]:
            raise ValueError("Matrix must be square.")
        if a.shape[0] > 300:
            raise ValueError("Matrix operations are limited to 300 × 300.")
        if i == "3203":
            r["tables"].append(_table("Determinant", ["Value"], [[np.linalg.det(a)]]))
        else:
            if np.linalg.matrix_rank(a) < len(a):
                raise ValueError("Matrix is singular and has no inverse.")
            inv = np.linalg.inv(a)
            r["dataset"] = _dataset(names, inv, r["title"])
            r["tables"].append(_table("Inverse", names, inv))
            r["notes"].append(f"2-norm condition number: {np.linalg.cond(a):.6g}.")
    elif i in ("3301", "3302", "3303"):
        if i == "3301":
            count = _num(o, "count", 100, 1, 100000, True)
            if count*len(names) > MAX_CELLS:
                raise ValueError("Sample exceeds the dataset cell limit.")
            replace = bool(o.get("replace", False))
            if not len(f) or (not replace and count > len(f)):
                raise ValueError("Sample size exceeds available rows; enable replacement or reduce it.")
            rng = np.random.Generator(np.random.MT19937(_num(o, "seed", 42, 0, 2**53-1, True)))
            sampled={}
            for name in names:
                values=f[name].dropna().to_numpy()
                values=np.asarray([value for value in values if not isinstance(value,str) or value.strip()!=''],dtype=object)
                if not len(values) or (not replace and count>len(values)):
                    raise ValueError(f"Sample size exceeds the available observations in {name}; enable replacement or reduce it.")
                sampled[name]=values[rng.choice(len(values),size=count,replace=replace)]
            out = pd.DataFrame(sampled)
            r["notes"].append("Each selected variable is sampled independently; selected columns do not preserve original row pairings.")
        elif i == "3302":
            interval = _num(o, "interval", 2, 1, 100000, True)
            start = _num(o, "start", 1, 1, max(1, len(f)), True)-1
            out = f.iloc[start::interval]
        else:
            col = _names(data, o.get("condition_column"))[0]
            x = _numeric_frame(_frame(data)[[col]])[col].to_numpy(float)
            a, b = _num(o, "a", 0), _num(o, "b", 0)
            condition = _choice(o, "condition", "eq", ["eq", "ne", "lt", "le", "gt", "ge", "between", "outside"])
            if condition in ("between", "outside") and a > b:
                raise ValueError("A must be ≤ B for interval conditions.")
            mask = {"eq": x == a, "ne": x != a, "lt": x < a, "le": x <= a, "gt": x > a, "ge": x >= a, "between": (x >= a) & (x <= b), "outside": (x < a) | (x > b)}[condition]
            out = f.loc[mask & np.isfinite(x)]
        r["dataset"] = _dataset(names, out.values.tolist(), r["title"])
        r["tables"].append(_table("Sampling", ["Input rows", "Output rows"], [[len(f), len(out)]]))


def _sample_size(i, o, r):
    alpha = _num(o, "alpha", 0.05, 1e-9, 0.999999)
    z = stats.norm.isf(alpha/2)
    if i == "1701":
        p = _num(o, "prevalence", 50, 0.000001, 99.999999)/100
        d = _num(o, "precision", 5, 0.000001, 100)/100
        pop = _num(o, "population", 10000, 2, 10**12, True)
        n0 = z*z*p*(1-p)/(d*d)
        n = n0/(1+(n0-1)/pop)
        r["tables"].append(_table("Sample size", ["Uncorrected", "Finite-population corrected", "Required integer"], [[n0, n, min(pop, max(1, math.ceil(n)))]]))
        r["notes"].append("Normal-approximation precision for simple random sampling; finite-population correction uses N−1.")
    elif i == "1702":
        n = _num(o, "total", 10, 1, 10**9, True)
        k = _num(o, "successes", 5, 0, n, True)
        low = 0.0 if k == 0 else stats.beta.ppf(alpha/2, k, n-k+1)
        high = 1.0 if k == n else stats.beta.isf(alpha/2, k+1, n-k)
        r["tables"].append(_table("Clopper-Pearson interval", ["Proportion", "Lower", "Upper", "Confidence"], [[k/n, low, high, 1-alpha]]))
    elif i == "1703":
        p = _num(o, "prevalence", 5, 1e-9, 100)/100
        k = _num(o, "events", 1, 1, 10**6, True)
        confidence = _num(o, "probability", 0.95, 1e-9, 0.999999999)
        lower, upper = k-1, k
        while stats.binom.sf(k-1, upper, p) < confidence:
            upper *= 2
            if upper > 10**12:
                raise ValueError("Required sample size exceeds supported range.")
        while upper-lower > 1:
            mid = (upper+lower)//2
            if stats.binom.sf(k-1, mid, p) >= confidence: upper = mid
            else: lower = mid
        r["tables"].append(_table("Minimum sample size", ["N", "P(events ≥ minimum)", "Minimum events"], [[upper, stats.binom.sf(k-1, upper, p), k]]))
    elif i == "1704":
        odds = _num(o, "odds_ratio", 2, 1e-9)
        if odds == 1:
            raise ValueError("Odds ratio 1 has no effect and requires unbounded sample size.")
        p0 = _num(o, "exposure", 20, 1e-8, 99.999999)/100
        power = _num(o, "power", 80, 1, 99.999)/100
        ratio = _num(o, "ratio", 1, 0.000001, 10000)
        p1 = odds*p0/(1-p0+odds*p0)
        mean = (p1+ratio*p0)/(1+ratio)
        n = (z*np.sqrt((1+1/ratio)*mean*(1-mean)) + stats.norm.ppf(power)*np.sqrt(p1*(1-p1)+p0*(1-p0)/ratio))**2/(p1-p0)**2
        cases = math.ceil(n)
        r["tables"].append(_table("Sample size", ["Cases", "Controls", "Expected case exposure", "Expected control exposure"], [[cases, math.ceil(cases*ratio), p1, p0]]))


def _roc_influences(scores, status):
    """DeLong placement values via sorted ranks, O(n log n), including ties."""
    positive = scores[status == 1]
    negative = scores[status == 0]
    if len(positive) < 2 or len(negative) < 2:
        raise ValueError("ROC inference requires at least two positive and two negative observations.")
    sn = np.sort(negative)
    sp = np.sort(positive)
    vp = (np.searchsorted(sn, positive, side="left")+np.searchsorted(sn, positive, side="right"))/(2*len(sn))
    vn = 1-(np.searchsorted(sp, negative, side="left")+np.searchsorted(sp, negative, side="right"))/(2*len(sp))
    return vp.mean(), vp, vn


def _survival(i, data, o, r):
    from .advanced_survival import run
    return run(i, data, o, r)


def _survival_base(i, data, o, r):
    if i in ("1610", "1611"):
        names = _names(data, o.get("columns") if i == "1611" else o.get("score"), 2 if i == "1611" else 1)
        status_name = _names(data, o.get("status"))[0]
        if status_name in names:
            raise ValueError("Outcome and score variables must differ.")
        a, mask = _numbers(data, names+[status_name], minimum=4)
        _missing(r, mask)
        status = a[:, -1]
        if not np.isin(status, [0, 1]).all():
            raise ValueError("Outcome must use 0 and 1 only.")
        direction = _choice(o, "direction", "higher", ["higher", "lower"])
        scores = a[:, :-1] * (1 if direction == "higher" else -1)
        influence = [_roc_influences(scores[:, j], status) for j in range(len(names))]
        charts = []
        rows = []
        alpha = _num(o, "alpha", .05, 1e-6, .999999)
        zcrit = stats.norm.isf(alpha/2)
        for j, name in enumerate(names):
            auc, vp, vn = influence[j]
            se = math.sqrt(vp.var(ddof=1)/len(vp)+vn.var(ddof=1)/len(vn))
            if se <= 1e-9:
                low = high = None
                r["warnings"].append(f"{name}: estimated AUC variance is zero; a normal confidence interval is unavailable.")
            else:
                low, high = max(0, auc-zcrit*se), min(1, auc+zcrit*se)
            rows.append([name, auc, se, low, high])
            fpr, tpr, thresholds = roc_curve(status, scores[:, j], drop_intermediate=False)
            charts.append(_series(name, fpr, tpr))
            if i == "1610":
                r["tables"].append(_table("ROC coordinates", ["Threshold", "Sensitivity", "Specificity"], zip(thresholds*(1 if direction == "higher" else -1), tpr, 1-fpr)))
        r["tables"].insert(0, _table("Areas under ROC curve", ["Test", "AUC", "Std. error", "Lower", "Upper"], rows))
        r["charts"].append(_chart("ROC curves", charts, "line", "False-positive rate", "True-positive rate"))
        if i == "1611":
            paired = []
            for j, k in combinations(range(len(names)), 2):
                aj, vpj, vnj = influence[j]; ak, vpk, vnk = influence[k]
                vp, vn = vpj-vpk, vnj-vnk
                variance = vp.var(ddof=1)/len(vp)+vn.var(ddof=1)/len(vn)
                if variance <= 1e-18:
                    if abs(aj-ak) < 1e-15:
                        stat, pvalue = 0.0, 1.0
                    else:
                        stat, pvalue = None, None
                        r["warnings"].append(f"{names[j]} versus {names[k]}: estimated DeLong variance is zero despite unequal AUCs; normal z/p inference is unavailable.")
                else:
                    stat = (aj-ak)/math.sqrt(variance)
                    pvalue = 2*stats.norm.sf(abs(stat))
                paired.append([names[j], names[k], aj-ak, math.sqrt(max(0, variance)), stat, pvalue])
            r["tables"].append(_table("Paired DeLong comparisons", ["Test A", "Test B", "AUC difference", "Std. error", "z", "p"], paired))
        return
    if i == "1630":
        a, mask = _numbers(data, [o.get("first"), o.get("second")], minimum=3)
        _missing(r, mask)
        mean, diff = a.mean(axis=1), a[:, 0]-a[:, 1]
        bias, sd = diff.mean(), diff.std(ddof=1)
        limit = stats.norm.ppf(.975)*sd
        r["tables"].append(_table("Agreement", ["N", "Bias", "SD of differences", "Lower agreement limit", "Upper agreement limit"], [[len(a), bias, sd, bias-limit, bias+limit]]))
        r["charts"].append(_chart("Bland-Altman", [_series("Paired difference", mean, diff), {**_series("Bias", [mean.min(), mean.max()], [bias]*2), "type": "line"}, {**_series("Lower agreement", [mean.min(), mean.max()], [bias-limit]*2), "type": "line"}, {**_series("Upper agreement", [mean.min(), mean.max()], [bias+limit]*2), "type": "line"}], "scatter", "Pair mean", "Method 1 − Method 2"))
        return
    if i == "1601":
        a, mask = _numbers(data, [o.get("dose"), o.get("events"), o.get("total")], minimum=4)
        _missing(r, mask)
        dose, events, total = a.T
        if (dose <= 0).any() or (total <= 0).any() or (events < 0).any() or (events > total).any() or np.any(total != np.floor(total)) or np.any(events != np.floor(events)):
            raise ValueError("Dose and group size must be positive; event/group counts must be integers with 0 ≤ events ≤ total.")
        if np.ptp(dose) == 0:
            raise ValueError("Probit regression requires varying doses.")
        from statsmodels.tools.sm_exceptions import PerfectSeparationWarning, PerfectSeparationError
        design = sm.add_constant(np.log(dose), has_constant="add")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", PerfectSeparationWarning)
                fit = sm.GLM(np.column_stack([events, total-events]), design, family=sm.families.Binomial(link=sm.families.links.Probit())).fit()
        except (PerfectSeparationWarning, PerfectSeparationError, np.linalg.LinAlgError) as exc:
            raise ValueError("Probit fit is separated or singular; finite coefficients cannot be reliably estimated.") from exc
        if not fit.converged or not np.isfinite(fit.params).all() or not np.isfinite(fit.bse).all():
            raise ValueError("Probit regression did not converge to finite estimates.")
        r["tables"].append(_table("Probit coefficients", ["Term", "Estimate", "Std. error", "z", "p"], zip(["Intercept", "Log dose"], fit.params, fit.bse, fit.tvalues, fit.pvalues)))
        if abs(fit.params[1]) > 1e-15:
            levels = [0.1, 0.5, 0.9]
            r["tables"].append(_table("Effective dose", ["Response probability", "Dose"], [[p, np.exp((stats.norm.ppf(p)-fit.params[0])/fit.params[1])] for p in levels]))
        xs = np.linspace(dose.min(), dose.max(), 100)
        r["charts"].append(_chart("Dose response", [_series("Observed", dose, events/total), {**_series("Fitted", xs, fit.predict(sm.add_constant(np.log(xs)))), "type": "line"}], "scatter", "Dose", "Response probability"))
        return
    names = [o.get("time"), o.get("status")]
    if i == "1309":
        predictors = _names(data, o.get("predictors"))
        names += predictors
    a, mask = _numbers(data, names, minimum=3)
    _missing(r, mask)
    time, status = a[:, 0], a[:, 1]
    if (time < 0).any() or not np.isin(status, [0, 1]).all():
        raise ValueError("Survival times must be nonnegative and event status must be 0 or 1.")
    if i == "1309":
        if len(a) <= len(predictors)+2 or status.sum() <= len(predictors):
            raise ValueError("More observations and events than predictors are required.")
        fit = PHReg(time, a[:, 2:], status=status, ties=_choice(o, "ties", "breslow", ["breslow", "efron"])).fit(disp=0)
        ci = fit.conf_int(alpha=_num(o, "alpha", .05, 1e-6, .999999))
        if not np.isfinite(fit.params).all() or not np.isfinite(fit.bse).all():
            raise ValueError("Cox fit did not produce finite estimates; check collinearity and separation.")
        r["tables"].append(_table("Hazard ratios", ["Predictor", "Coefficient", "Std. error", "Hazard ratio", "Lower HR", "Upper HR", "p", "Wald chi-square", "Lower coefficient", "Upper coefficient"], [[n, b, se, np.exp(b), np.exp(c[0]), np.exp(c[1]), p, (b/se)**2, c[0], c[1]] for n, b, se, c, p in zip(predictors, fit.params, fit.bse, ci, fit.pvalues)]))
        null_ll = fit.model.loglike(np.zeros(len(predictors)))
        likelihood_ratio = 2*(fit.llf-null_ll)
        r["tables"].append(_table("Model fit", ["Null −2 log likelihood", "Fitted −2 log likelihood", "Likelihood-ratio chi-square", "df", "p", "N", "Events"], [[-2*null_ll, -2*fit.llf, likelihood_ratio, len(predictors), stats.chi2.sf(likelihood_ratio, len(predictors)), len(time), int(status.sum())]]))
        centered_predictor = (a[:, 2:]-a[:, 2:].mean(axis=0)) @ fit.params
        hazard, baseline = 0., []
        for event_time in np.unique(time):
            deaths = int(status[time == event_time].sum())
            if deaths:
                hazard += deaths / np.exp(centered_predictor[time >= event_time]).sum()
            baseline.append([event_time, deaths, hazard, np.exp(-hazard)])
        r["tables"].append(_table("Baseline survival at mean covariates", ["Time", "Events", "Cumulative hazard", "Survival"], baseline))
        r["charts"].append(_chart("Baseline survival at mean covariates", [_series("Survival", [row[0] for row in baseline], [row[3] for row in baseline])], "step", "Time", "Survival"))
        r["notes"].append("Baseline survival uses Breslow cumulative-hazard increments at the sample mean of the covariates, evaluated after events at each time. The coefficient fit uses the selected tied-event method.")
        return
    if o.get("group"):
        groupname = _names(data, o.get("group"))[0]
        groups = _frame(data).loc[mask, groupname].to_numpy()
        groupmask = pd.notna(groups)
        if not groupmask.all():
            r["notes"].append(f"Excluded {int((~groupmask).sum())} rows with missing group labels.")
        time, status, groups = time[groupmask], status[groupmask], groups[groupmask]
    else:
        groups = np.repeat("All", len(time))
    if not len(time):
        raise ValueError("No observations remain after excluding missing group labels.")
    for group in pd.unique(groups):
        use = groups == group
        t, d = time[use], status[use]
        if i == "1620":
            width = _num(o, "width", 1, 1e-12)
            intervals = int(math.floor(t.max()/width))+1
            if intervals > 10000:
                raise ValueError("More than 10000 intervals; increase interval width.")
            rows, s = [], 1.0
            for j in range(intervals):
                lo, hi = j*width, (j+1)*width
                at_risk = int(np.sum(t >= lo))
                deaths = int(np.sum((t >= lo) & (t < hi) & (d == 1)))
                censored = int(np.sum((t >= lo) & (t < hi) & (d == 0)))
                effective = at_risk-censored/2
                q = deaths/effective if effective else 0
                s *= 1-q
                rows.append([lo, hi, at_risk, deaths, censored, effective, q, s])
            r["tables"].append(_table(f"Life table: {group}", ["From", "To", "At risk", "Events", "Censored", "Effective risk", "Failure probability", "Survival"], rows))
            r["charts"].append(_chart(f"Survival: {group}", [_series(group, [0]+[x[1] for x in rows], [1]+[x[-1] for x in rows])], x="Time", y="Survival probability"))
        else:
            rows, s, cumulative, greenwood, varh = [], 1.0, 0.0, 0.0, 0.0
            low = high = np.nan
            z = stats.norm.isf(_num(o, "alpha", .05, 1e-6, .999999)/2)
            for tm in np.unique(t):
                risk = int(np.sum(t >= tm))
                deaths = int(np.sum((t == tm) & (d == 1)))
                censored = int(np.sum((t == tm) & (d == 0)))
                s *= 1-deaths/risk
                cumulative += deaths/risk
                varh += deaths/risk**2
                if risk > deaths:
                    greenwood += deaths/(risk*(risk-deaths))
                if deaths and risk > deaths:
                    se = s * math.sqrt(greenwood)
                    low, high = max(0., s-z*se), min(1., s+z*se)
                # The native report carries the last limits over censoring rows
                # and rows where Greenwood's standard error is undefined.
                rows.append([tm, risk, deaths, censored, s, low, high, cumulative, math.sqrt(varh)])
            if i == "1621":
                r["tables"].append(_table(f"Survival: {group}", ["Time", "At risk", "Events", "Censored", "Survival", "Lower", "Upper"], [x[:7] for x in rows]))
                r["charts"].append(_chart(f"Kaplan-Meier: {group}", [_series(group, [0]+[x[0] for x in rows], [1]+[x[4] for x in rows])], kind="step", x="Time", y="Survival probability"))
            else:
                r["tables"].append(_table(f"Cumulative hazard: {group}", ["Time", "At risk", "Events", "Censored", "Cumulative hazard", "Hazard std. error", "exp(−hazard)"], [[*x[:4], x[7], x[8], np.exp(-x[7])] for x in rows]))
                r["charts"].append(_chart(f"Nelson-Aalen: {group}", [_series(group, [0]+[x[0] for x in rows], [0]+[x[7] for x in rows])], kind="step", x="Time", y="Cumulative hazard"))


def _control(r, label, values, center, low, high):
    values = np.asarray(values, dtype=float)
    x = np.arange(1, len(values)+1)
    center, low, high = [np.broadcast_to(v, values.shape) for v in (center, low, high)]
    r["tables"].append(_table(label, ["Subgroup", "Value", "Center", "Lower", "Upper", "Outside limits"], zip(x, values, center, low, high, (values < low) | (values > high))))
    r["charts"].append(_chart(label, [_series("Observed", x, values), _series("Center", x, center), _series("Lower limit", x, low), _series("Upper limit", x, high)]))


def _charts(i, data, o, r):
    if i in ("4102", "4103", "4104", "4105", "4107", "4108"):
        from .advanced_controlcharts import run
        return run(i, data, o, r)
    return _charts_base(i, data, o, r)


def _charts_base(i, data, o, r):
    if i in ("4001", "4002", "4003") or i.startswith("401"):
        from .advanced_charts import run
        return run(i, data, o, r)
    if i in ("4102", "4103"):
        names = _names(data, o.get("columns"), 2)
        a, mask = _numbers(data, names, minimum=2)
        _missing(r, mask)
        n = a.shape[1]
        k = _num(o, "sigmas", 3, .001, 20)
        means = a.mean(axis=1)
        center = means.mean()
        if i == "4102":
            # Published normal-range constants, subgroup sizes 2–10.
            d2 = {2:1.128,3:1.693,4:2.059,5:2.326,6:2.534,7:2.704,8:2.847,9:2.970,10:3.078}
            d3 = {2:.8525,3:.8884,4:.8798,5:.8641,6:.8480,7:.8332,8:.8198,9:.8078,10:.7971}
            if n not in d2:
                raise ValueError("Xbar-R supports 2–10 measurements per subgroup.")
            v = np.ptp(a, axis=1); avg = v.mean(); sigma = avg/d2[n]
            spread_sd = d3[n]*sigma
            spread_name = "Range"
        else:
            c4 = np.sqrt(2/(n-1))*np.exp(special.gammaln(n/2)-special.gammaln((n-1)/2))
            v = a.std(axis=1, ddof=1); avg = v.mean(); sigma = avg/c4
            spread_sd = sigma*np.sqrt(1-c4*c4)
            spread_name = "Standard deviation"
        _control(r, "Subgroup means", means, center, center-k*sigma/np.sqrt(n), center+k*sigma/np.sqrt(n))
        _control(r, spread_name, v, avg, max(0, avg-k*spread_sd), avg+k*spread_sd)
        return
    if i in ("4105", "4106", "4107"):
        names = [o.get("count_column")]
        if i != "4106": names.append(o.get("size_column"))
        a, mask = _numbers(data, names, minimum=2)
        _missing(r, mask)
        counts = a[:, 0]
        if np.any(counts < 0) or np.any(counts != np.floor(counts)):
            raise ValueError("Counts must be nonnegative integers.")
        k = _num(o, "sigmas", 3, .001, 20)
        if i == "4106":
            mean = counts.mean()
            lower=mean-k*np.sqrt(mean)
            _control(r, "C chart", counts, mean, lower if lower>=0 else np.nan, mean+k*np.sqrt(mean))
            if lower<0:r["notes"].append("No lower control limit is drawn because its Poisson approximation is negative.")
        else:
            sizes = a[:, 1]
            if np.any(sizes <= 0): raise ValueError("Subgroup sizes/exposures must be positive.")
            if i == "4105":
                if np.any(counts > sizes) or np.any(sizes != np.floor(sizes)):
                    raise ValueError("Defectives cannot exceed positive integer subgroup sizes.")
                p = counts.sum()/sizes.sum()
                se = np.sqrt(p*(1-p)/sizes)
                _control(r, "P chart", counts/sizes, p, np.maximum(0, p-k*se), np.minimum(1, p+k*se))
                _control(r, "NP chart", counts, p*sizes, np.maximum(0, (p-k*se)*sizes), np.minimum(sizes, (p+k*se)*sizes))
            else:
                u = counts.sum()/sizes.sum(); se = np.sqrt(u/sizes)
                _control(r, "U chart", counts/sizes, u, np.maximum(0, u-k*se), u+k*se)
        return
    if i in ("4104", "4108"):
        a, _ = _numbers(data, o.get("column"), minimum=3, strict=True)
        y = a[:, 0]
        if i == "4108":
            k = _num(o, "sigmas", 3, .001, 20)
            mr = np.abs(np.diff(y)); avg = mr.mean(); sigma = avg/1.128
            _control(r, "Individuals", y, y.mean(), y.mean()-k*sigma, y.mean()+k*sigma)
            _control(r, "Moving range", mr, avg, max(0, avg-k*.8525*sigma), avg+k*.8525*sigma)
        else:
            if y.std(ddof=1) == 0: raise ValueError("CUSUM requires nonconstant data.")
            k, h = _num(o, "k", .5, 0), _num(o, "h", 4, .000001)
            z = (y-y.mean())/y.std(ddof=1)
            cp, cm, pos, neg = 0., 0., [], []
            for value in z:
                cp = max(0, cp+value-k); cm = max(0, cm-value-k)
                pos.append(cp); neg.append(cm)
            _control(r, "Upper CUSUM", pos, 0, 0, h)
            _control(r, "Lower CUSUM magnitude", neg, 0, 0, h)
        return
    if i == "4002":
        a, mask = _numbers(data, [o.get("x"), o.get("y")], minimum=2)
        _missing(r, mask)
        if o.get("group"):
            group = _names(data, o.get("group"))[0]
            groups = _frame(data).loc[mask, group].to_numpy()
        else: groups = np.repeat("Points", len(a))
        ss = [_series(g, a[groups == g, 0], a[groups == g, 1]) for g in pd.unique(groups) if pd.notna(g)]
        r["charts"].append(_chart("Scatter plot", ss, "scatter", o["x"], o["y"]))
        return
    names = _names(data, o.get("columns"))
    for name in names:
        a, mask = _numbers(data, name, minimum=2)
        _missing(r, mask)
        x = a[:, 0]
        if i == "4001":
            if o.get("group"):
                group = _names(data, o.get("group"))[0]
                g = _frame(data).loc[mask, group].to_numpy()
            else: g = np.repeat(name, len(x))
            series = []
            rows = []
            for level in pd.unique(g):
                if pd.isna(level): continue
                v = x[g == level]; q1, med, q3 = np.quantile(v, [.25, .5, .75]); iqr = q3-q1
                inside = v[(v >= q1-1.5*iqr) & (v <= q3+1.5*iqr)]
                rows.append([str(level), len(v), q1, med, q3, inside.min(), inside.max()])
                series.append(_series(level, np.arange(len(v)), v))
            r["tables"].append(_table(name, ["Group", "N", "Q1", "Median", "Q3", "Lower whisker", "Upper whisker"], rows))
            r["charts"].append(_chart(name, series, "box", "Group", name))
        elif i == "4003":
            unit = _num(o, "unit", 1, 1e-12)
            scaled = np.trunc(x/unit).astype(np.int64)
            rows = {}
            for v in np.sort(scaled):
                stem = ("−" if v < 0 else "") + str(abs(int(v))//10)
                rows.setdefault(stem, []).append(str(abs(int(v)) % 10))
            r["tables"].append(_table(name, ["Stem", "Leaves"], [[stem, " ".join(leaves)] for stem, leaves in rows.items()]))
            r["notes"].append(f"Leaf unit = {unit:g}; for example, stem 2 and leaf 3 represent {23*unit:g}.")
        elif i.startswith("401"):
            y = np.sort(x)
            probs = (np.arange(1, len(y)+1)-.375)/(len(y)+.25)
            shape = _num(o, "shape", 1, 1e-8)
            shape2 = _num(o, "shape2", 1, 1e-8)
            if np.ptp(y) == 0: raise ValueError("Q-Q fitting requires nonconstant data.")
            if i == "4011": theo = stats.norm.ppf(probs, loc=y.mean(), scale=y.std(ddof=1))
            elif i == "4012":
                if np.any((y < 0) | (y > 1)): raise ValueError("Beta Q-Q values must lie in [0, 1].")
                theo = stats.beta.ppf(probs, shape, shape2)
            elif i == "4013": theo = stats.chi2.ppf(probs, shape)
            elif i in ("4014", "4015", "4018"):
                if np.any(y <= 0): raise ValueError("This distribution requires positive observations.")
                dist = {"4014": stats.gamma, "4015": stats.lognorm, "4018": stats.weibull_min}[i]
                params = dist.fit(y, floc=0)
                theo = dist.ppf(probs, *params)
            elif i == "4016": theo = stats.t.ppf(probs, shape)
            else: theo = stats.uniform.ppf(probs, loc=y.min(), scale=np.ptp(y))
            r["tables"].append(_table(name, ["Probability", "Theoretical quantile", "Observed quantile"], zip(probs, theo, y)))
            r["charts"].append(_chart(f"{r['title']}: {name}", [_series("Quantiles", theo, y), {**_series("Reference", [min(theo.min(), y.min()), max(theo.max(), y.max())], [min(theo.min(), y.min()), max(theo.max(), y.max())]), "type": "line"}], "scatter", "Theoretical quantile", "Observed quantile"))
