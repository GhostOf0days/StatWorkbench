"""Additional pairwise dependence analyses for StatWorkbench.

These procedures favor explicit sample counts and descriptive diagnostics where
inferential assumptions would be fragile.
"""
from __future__ import annotations

import copy
import math
import numpy as np
import pandas as pd
from scipy import stats


def _f(key, label, kind="column", **kwargs):
    required = kwargs.pop("required", True)
    return dict(key=key, label=label, type=kind, required=required, **kwargs)


def _select(key, label, values, default):
    return _f(key, label, "select", default=default,
              options=[dict(value=value, label=label) for value, label in values])


_entries = [
    dict(id="dependence.association", name="Correlation Matrix", category="Dependence models",
         description="Compare Pearson, Spearman, or Kendall correlation coefficients with pairwise or listwise missing-data handling and optional Benjamini–Hochberg adjustment.",
         coverage="extension", provenance="Independent StatWorkbench extension",
         limitations=["P-values assume independent observations; adjust the design for clustered or serially dependent data."],
         fields=[_f("columns", "Variables", "columns"),
                 _select("method", "Correlation measure", [("pearson", "Pearson correlation"), ("spearman", "Spearman rank correlation"), ("kendall", "Kendall tau-b")], "spearman"),
                 _select("missing", "Missing-value handling", [("pairwise", "Pairwise complete observations"), ("listwise", "Listwise complete observations")], "pairwise"),
                 _select("alternative", "Alternative hypothesis", [("two-sided", "Not equal to zero"), ("less", "Less than zero"), ("greater", "Greater than zero")], "two-sided"),
                 _select("adjustment", "P-value adjustment", [("none", "None"), ("bh", "Benjamini–Hochberg FDR")], "bh")]),
    dict(id="dependence.partial", name="Partial Correlation", category="Dependence models",
         description="Estimate the correlation between two variables after linear adjustment for selected numeric controls.",
         coverage="extension", provenance="Independent StatWorkbench extension",
         limitations=["The test uses the usual independent, approximately normal residual model. It describes linear adjustment, not general conditional independence."],
         fields=[_f("x", "Variable X"), _f("y", "Variable Y"), _f("controls", "Control variables", "columns", required=False),
                 _f("confidence", "Confidence level", "number", default=.95, min=.5, max=.999, step=.01)]),
    dict(id="dependence.distance", name="Distance Correlation", category="Dependence models",
         description="Measure linear and nonlinear dependence with distance correlation and an optional permutation test.",
         coverage="extension", provenance="Independent StatWorkbench extension",
         limitations=["The reported distance correlation is the biased sample estimator. Permutation inference assumes exchangeable independent rows and is limited by a computation budget."],
         fields=[_f("x", "Variable X"), _f("y", "Variable Y"),
                 _f("permutations", "Permutation samples (0 to skip)", "integer", default=199, min=0, max=999),
                 _f("seed", "Permutation seed", "integer", default=0, min=0, max=9007199254740991)]),
    dict(id="dependence.mutual_information", name="Binned Mutual Information", category="Dependence models",
         description="Estimate dependence in nats from quantile-binned variables; optionally compare with a permutation null distribution.",
         coverage="extension", provenance="Independent StatWorkbench extension",
         limitations=["The estimate depends on the chosen bin count and has positive finite-sample bias. Permutation inference assumes exchangeable independent rows."],
         fields=[_f("x", "Variable X"), _f("y", "Variable Y"),
                 _f("bins", "Quantile bins", "integer", default=8, min=2, max=30),
                 _f("permutations", "Permutation samples (0 to skip)", "integer", default=199, min=0, max=999),
                 _f("seed", "Permutation seed", "integer", default=0, min=0, max=9007199254740991)]),
    dict(id="dependence.tail_coexceedance", name="Empirical Tail Co-exceedance", category="Dependence models",
         description="Compare joint upper and lower threshold events across four tail quadrants, including empirical marginal rates and independence benchmarks.",
         coverage="extension", provenance="Independent StatWorkbench extension",
         limitations=["This is a descriptive finite-threshold diagnostic, not an asymptotic tail-dependence coefficient. Threshold ties can make realized tail rates exceed the requested probability."],
         fields=[_f("x", "Variable X"), _f("y", "Variable Y"),
                 _f("tail_probability", "Marginal tail probability", "number", default=.10, min=.01, max=.25, step=.01)]),
    dict(id="dependence.lead_lag", name="Lead–Lag Cross-Correlation", category="Dependence models",
         description="Measure Pearson cross-correlation across positive and negative lags while preserving worksheet row alignment.",
         coverage="extension", provenance="Independent StatWorkbench extension",
         limitations=["Cross-correlations are descriptive. Serial dependence and searching many lags invalidate ordinary single-lag significance interpretations; no p-values are reported."],
         fields=[_f("x", "Leading series X"), _f("y", "Following series Y"),
                 _f("max_lag", "Maximum lag in either direction", "integer", default=10, min=1, max=100)]),
]
_by_id = {item["id"]: item for item in _entries}


def catalog():
    return copy.deepcopy(_entries)


def _base(identifier):
    entry = _by_id[identifier]
    return {"analysis": identifier, "title": entry["name"], "tables": [], "charts": [],
            "notes": list(entry["limitations"]),
            "warnings": []}


def _frame(data):
    columns = data.get("columns", [])
    if not columns or len(set(columns)) != len(columns):
        raise ValueError("Dataset needs unique, nonempty column names.")
    return pd.DataFrame(data.get("rows", []), columns=columns)


def _numeric(frame, names):
    if isinstance(names, str):
        names = [names]
    if not isinstance(names, list) or not names or len(set(names)) != len(names):
        raise ValueError("Select distinct numeric variables for the analysis.")
    missing_names = [name for name in names if name not in frame.columns]
    if missing_names:
        raise ValueError("Selected variable was not found in the dataset.")
    result = pd.DataFrame(index=frame.index)
    for name in names:
        source = frame[name]
        values = pd.to_numeric(source, errors="coerce")
        nonblank = source.notna() & source.astype(str).str.strip().ne("")
        if (nonblank & values.isna()).any():
            raise ValueError(f'Column "{name}" has nonnumeric values; choose numeric variables.')
        if np.isinf(values.to_numpy(dtype=float, na_value=np.nan)).any():
            raise ValueError(f'Column "{name}" contains infinity.')
        result[name] = values.astype(float)
    return result


def _pair(frame, options, minimum=3):
    x_name, y_name = options.get("x"), options.get("y")
    if not isinstance(x_name, str) or not isinstance(y_name, str) or x_name == y_name:
        raise ValueError("Choose two different variables.")
    values = _numeric(frame, [x_name, y_name])
    before = len(values)
    values = values.dropna()
    if len(values) < minimum:
        raise ValueError(f"At least {minimum} complete pairs are required.")
    warning = []
    if len(values) < before:
        warning.append(f"Excluded {before-len(values)} rows with missing values from the selected pair.")
    return x_name, y_name, values.to_numpy(dtype=float), warning


def _option_int(options, key, default, low, high):
    raw = options.get(key, default)
    if isinstance(raw, bool):
        raise ValueError(f"{key} must be an integer.")
    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{key} must be an integer.") from None
    if not np.isfinite(value) or int(value) != value or not low <= value <= high:
        raise ValueError(f"{key} must be an integer between {low} and {high}.")
    return int(value)


def _table(title, columns, rows):
    return dict(title=title, columns=list(columns), rows=[list(row) for row in rows])


def _matrix_table(title, names, matrix, digits=6):
    rows = [[name] + [None if not np.isfinite(value) else round(float(value), digits) for value in row]
            for name, row in zip(names, matrix)]
    return _table(title, ["Variable"] + list(names), rows)


def _bh_adjust(values):
    """Benjamini-Hochberg adjusted p-values, preserving missing entries."""
    p = np.asarray(values, dtype=float)
    valid = np.isfinite(p)
    out = np.full(p.shape, np.nan)
    if not valid.any():
        return out
    subset = p[valid]
    order = np.argsort(subset)
    ranked = subset[order] * len(subset) / np.arange(1, len(subset) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    restored = np.empty_like(ranked)
    restored[order] = np.clip(ranked, 0, 1)
    out[valid] = restored
    return out


def _correlation(method, x, y, alternative="two-sided"):
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return None, None
    if method == "pearson":
        result = stats.pearsonr(x, y, alternative=alternative)
    elif method == "spearman":
        result = stats.spearmanr(x, y, alternative=alternative)
    elif method == "kendall":
        result = stats.kendalltau(x, y, method="auto", variant="b", alternative=alternative)
    else:
        raise ValueError("Correlation method must be pearson, spearman, or kendall.")
    value = float(result.statistic)
    pvalue = float(result.pvalue)
    if not np.isfinite(value):
        return None, None
    return value, pvalue if np.isfinite(pvalue) else None


def _association(data, options):
    frame = _frame(data)
    names = options.get("columns", [])
    if isinstance(names, str):
        names = [names]
    if not isinstance(names, list) or len(names) < 2 or len(names) > 100 or len(set(names)) != len(names):
        raise ValueError("Select between 2 and 100 distinct variables.")
    values = _numeric(frame, names)
    method = options.get("method", "spearman")
    alternative = options.get("alternative", "two-sided")
    missing = options.get("missing", "pairwise")
    adjustment = options.get("adjustment", "bh")
    if method not in ("pearson", "spearman", "kendall"):
        raise ValueError("Correlation method must be pearson, spearman, or kendall.")
    if alternative not in ("two-sided", "less", "greater"):
        raise ValueError("Alternative hypothesis must be two-sided, less, or greater.")
    if missing not in ("pairwise", "listwise") or adjustment not in ("none", "bh"):
        raise ValueError("Invalid missing-value or p-value adjustment option.")
    listwise = values.dropna() if missing == "listwise" else None
    k = len(names)
    coefficients = np.full((k, k), np.nan)
    pvalues = np.full((k, k), np.nan)
    counts = np.zeros((k, k), dtype=int)
    for i in range(k):
        for j in range(i, k):
            pair = listwise[[names[i], names[j]]] if listwise is not None else values[[names[i], names[j]]].dropna()
            n = len(pair)
            counts[i, j] = counts[j, i] = n
            if i == j:
                coefficients[i, j] = 1.0
                pvalues[i, j] = 0.0
            elif n >= 3:
                value, pvalue = _correlation(method, pair.iloc[:, 0].to_numpy(), pair.iloc[:, 1].to_numpy(), alternative)
                if value is not None:
                    coefficients[i, j] = coefficients[j, i] = value
                    pvalues[i, j] = pvalues[j, i] = pvalue
    adjusted = np.full_like(pvalues, np.nan)
    tri = np.triu_indices(k, 1)
    adjusted_values = _bh_adjust(pvalues[tri]) if adjustment == "bh" else pvalues[tri].copy()
    adjusted[tri] = adjusted_values
    adjusted[(tri[1], tri[0])] = adjusted_values
    np.fill_diagonal(adjusted, 0.)
    result = _base("dependence.association")
    result["tables"] = [_matrix_table(f"{method.title()} correlation coefficients", names, coefficients),
                        _matrix_table("Raw p-values", names, pvalues),
                        _matrix_table("Adjusted p-values (BH)" if adjustment == "bh" else "P-values used", names, adjusted),
                        _matrix_table("Pairwise complete sample sizes", names, counts)]
    if method == "kendall":
        result["notes"].append("Kendall estimates use tau-b to account for ties.")
    if method in ("spearman", "kendall"):
        result["notes"].append("Rank-correlation p-values use SciPy's asymptotic approximation; interpret small-sample p-values with care.")
    if adjustment == "bh":
        result["notes"].append("Benjamini–Hochberg adjustment is applied once to the unique off-diagonal tests, then mirrored in the matrix.")
    return result


def _partial(data, options):
    frame = _frame(data)
    x_name, y_name = options.get("x"), options.get("y")
    controls = options.get("controls", [])
    if isinstance(controls, str):
        controls = [controls]
    if x_name == y_name or x_name in controls or y_name in controls or len(set(controls)) != len(controls):
        raise ValueError("X, Y, and control variables must be distinct.")
    names = [x_name, y_name] + controls
    values = _numeric(frame, names).dropna()
    if len(values) < 5:
        raise ValueError("At least 5 complete observations are required for partial correlation.")
    x, y = values[x_name].to_numpy(), values[y_name].to_numpy()
    if controls:
        design = np.column_stack([np.ones(len(values)), values[controls].to_numpy()])
        rank = int(np.linalg.matrix_rank(design))
        if rank < 1:
            raise ValueError("The control-variable design could not be estimated.")
        rx = x - design @ np.linalg.lstsq(design, x, rcond=None)[0]
        ry = y - design @ np.linalg.lstsq(design, y, rcond=None)[0]
    else:
        design = np.ones((len(values), 1))
        rank = 1
        rx, ry = x - x.mean(), y - y.mean()
    df = len(values) - rank - 1
    if df <= 0:
        raise ValueError("There are too few observations for the number of independent controls.")
    if np.std(rx) == 0 or np.std(ry) == 0:
        raise ValueError("Partial correlation is undefined because one residual series is constant.")
    r = float(np.corrcoef(rx, ry)[0, 1])
    clipped = float(np.clip(r, -1 + np.finfo(float).eps, 1 - np.finfo(float).eps))
    t_stat = clipped * math.sqrt(df / max(np.finfo(float).tiny, 1 - clipped * clipped))
    pvalue = float(2 * stats.t.sf(abs(t_stat), df))
    confidence = options.get("confidence", .95)
    if isinstance(confidence, bool):
        raise ValueError("confidence must be between 0.5 and 0.999.")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("confidence must be between 0.5 and 0.999.") from None
    if not np.isfinite(confidence) or not .5 <= confidence <= .999:
        raise ValueError("confidence must be between 0.5 and 0.999.")
    fisher_df = len(values) - rank - 2
    if fisher_df > 0:
        margin = stats.norm.ppf((1 + confidence) / 2) / math.sqrt(fisher_df)
        low, high = np.tanh(np.arctanh(clipped) + np.array([-margin, margin]))
    else:
        low = high = None
    result = _base("dependence.partial")
    result["tables"] = [_table("Partial correlation", ["Variable X", "Variable Y", "Controls", "N", "Control design rank", "Partial r", "Test df", "t statistic", "p-value", f"{confidence:.1%} CI lower", f"{confidence:.1%} CI upper"],
                               [[x_name, y_name, ", ".join(controls) if controls else "None", len(values), rank, r, df, t_stat, pvalue, low, high]])]
    result["notes"].append("Controls are removed by ordinary least-squares projection with an intercept. Confidence limits use Fisher's z approximation.")
    if len(values) < len(frame):
        result["warnings"].append(f"Excluded {len(frame)-len(values)} rows with missing values in the selected variables.")
    if rank < len(controls) + 1:
        result["warnings"].append("Some control columns were linearly dependent; effective control degrees of freedom use the design-matrix rank.")
    return result


def _centered_distances(values):
    distances = np.abs(values[:, None] - values[None, :])
    return distances - distances.mean(axis=0, keepdims=True) - distances.mean(axis=1, keepdims=True) + distances.mean()


def _distance_statistic(a, b):
    cross2 = float(np.mean(a * b))
    var_a2 = float(np.mean(a * a))
    var_b2 = float(np.mean(b * b))
    if var_a2 <= 0 or var_b2 <= 0:
        return 0.0
    return float(math.sqrt(max(0., cross2) / math.sqrt(var_a2 * var_b2)))


def _distance(data, options):
    x_name, y_name, pairs, warnings_ = _pair(_frame(data), options, minimum=4)
    x, y = pairs.T
    n = len(x)
    if n > 1800:
        raise ValueError("Distance correlation is limited to 1,800 complete pairs to bound its quadratic memory use.")
    permutations = _option_int(options, "permutations", 199, 0, 999)
    if n * n * permutations > 80_000_000:
        raise ValueError("Permutation request exceeds the computation budget. Reduce the permutation count or select fewer rows.")
    a, b = _centered_distances(x), _centered_distances(y)
    observed = _distance_statistic(a, b)
    pvalue = None
    if permutations:
        rng = np.random.default_rng(_option_int(options, "seed", 0, 0, 9007199254740991))
        exceed = 0
        for _ in range(permutations):
            order = rng.permutation(n)
            permuted = b[order][:, order]
            exceed += _distance_statistic(a, permuted) >= observed - 1e-15
        pvalue = (exceed + 1) / (permutations + 1)
    result = _base("dependence.distance")
    result["tables"] = [_table("Distance correlation", ["Variable X", "Variable Y", "N", "Distance correlation", "Permutation samples", "Permutation p-value"],
                               [[x_name, y_name, n, observed, permutations, pvalue]])]
    result["notes"].append("Permutation p-values use the +1 correction; zero permutation samples report the effect estimate only.")
    result["warnings"].extend(warnings_)
    return result


def _quantile_codes(values, bins):
    edges = np.quantile(values, np.linspace(0, 1, bins + 1)[1:-1])
    return np.searchsorted(edges, values, side="right"), len(np.unique(edges)) + 1


def _mi_codes(x, y):
    table = np.histogram2d(x, y, bins=(int(x.max()) + 1, int(y.max()) + 1))[0]
    pxy = table / table.sum()
    px, py = pxy.sum(axis=1), pxy.sum(axis=0)
    expected = px[:, None] * py[None, :]
    positive = pxy > 0
    mi = float(np.sum(pxy[positive] * np.log(pxy[positive] / expected[positive])))
    hx = float(-np.sum(px[px > 0] * np.log(px[px > 0])))
    hy = float(-np.sum(py[py > 0] * np.log(py[py > 0])))
    normalized = mi / math.sqrt(hx * hy) if hx > 0 and hy > 0 else None
    return mi, normalized


def _mutual_information(data, options):
    x_name, y_name, pairs, warnings_ = _pair(_frame(data), options, minimum=10)
    bins = _option_int(options, "bins", 8, 2, 30)
    permutations = _option_int(options, "permutations", 199, 0, 999)
    if len(pairs) * permutations > 20_000_000:
        raise ValueError("Permutation request exceeds the computation budget. Reduce the permutation count or select fewer rows.")
    x, y = pairs.T
    bx, nxb = _quantile_codes(x, bins)
    by, nyb = _quantile_codes(y, bins)
    observed, normalized = _mi_codes(bx, by)
    pvalue = None
    if permutations:
        rng = np.random.default_rng(_option_int(options, "seed", 0, 0, 9007199254740991))
        exceed = 0
        for _ in range(permutations):
            null, _ = _mi_codes(bx, rng.permutation(by))
            exceed += null >= observed - 1e-15
        pvalue = (exceed + 1) / (permutations + 1)
    result = _base("dependence.mutual_information")
    result["tables"] = [_table("Quantile-binned mutual information", ["Variable X", "Variable Y", "N", "Requested bins", "Occupied bins X", "Occupied bins Y", "Mutual information (nats)", "Normalized MI", "Permutation samples", "Permutation p-value"],
                               [[x_name, y_name, len(pairs), bins, nxb, nyb, observed, normalized, permutations, pvalue]])]
    result["notes"].append("Quantile boundaries are empirical; duplicate boundaries caused by ties can reduce the number of occupied bins. Normalized MI is MI divided by the geometric mean of marginal entropies.")
    if nxb < bins or nyb < bins:
        result["warnings"].append("Ties at quantile boundaries reduced the number of distinct bins.")
    result["warnings"].extend(warnings_)
    return result


def _tail(data, options):
    x_name, y_name, pairs, warnings_ = _pair(_frame(data), options, minimum=30)
    q = options.get("tail_probability", .10)
    if isinstance(q, bool):
        raise ValueError("tail_probability must be between 0.01 and 0.25.")
    try:
        q = float(q)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("tail_probability must be between 0.01 and 0.25.") from None
    if not np.isfinite(q) or not .01 <= q <= .25:
        raise ValueError("tail_probability must be between 0.01 and 0.25.")
    x, y = pairs.T
    tails = [("Upper", x >= np.quantile(x, 1-q)), ("Lower", x <= np.quantile(x, q))]
    y_tails = [("Upper", y >= np.quantile(y, 1-q)), ("Lower", y <= np.quantile(y, q))]
    rows = []
    for x_label, x_event in tails:
        for y_label, y_event in y_tails:
            nx, ny = int(x_event.sum()), int(y_event.sum())
            joint = int(np.sum(x_event & y_event))
            rate_x, rate_y = nx / len(x), ny / len(y)
            rate_joint = joint / len(x)
            conditional = joint / nx if nx else None
            expected = rate_x * rate_y
            enrichment = rate_joint / expected if expected else None
            rows.append([x_label, y_label, nx, ny, joint, rate_x, rate_y, rate_joint, conditional, expected, enrichment])
    result = _base("dependence.tail_coexceedance")
    result["tables"] = [_table("Empirical tail co-exceedance", ["X tail", "Y tail", "X events", "Y events", "Joint events", "P(X tail)", "P(Y tail)", "P(both)", "P(Y tail | X tail)", "Independence benchmark", "Enrichment vs independence"], rows)]
    result["notes"].append(f"Thresholds use empirical quantiles at nominal tail probability {q:.3g}; realized event counts are reported because ties can change the rates.")
    if any(row[2] / len(x) > q + 1 / len(x) or row[3] / len(x) > q + 1 / len(y) for row in rows):
        result["warnings"].append("Ties at a quantile threshold caused realized tail rates to exceed the nominal probability.")
    result["warnings"].extend(warnings_)
    return result


def _lead_lag(data, options):
    frame = _frame(data)
    x_name, y_name = options.get("x"), options.get("y")
    if not isinstance(x_name, str) or not isinstance(y_name, str) or x_name == y_name:
        raise ValueError("Choose two different variables.")
    values = _numeric(frame, [x_name, y_name])
    maximum = _option_int(options, "max_lag", 10, 1, 100)
    if len(values) < 2 * maximum + 4:
        raise ValueError("Select at least 2 × maximum lag + 4 rows.")
    x, y = values[x_name].to_numpy(), values[y_name].to_numpy()
    rows, xs, ys, lags = [], [], [], []
    for lag in range(-maximum, maximum + 1):
        if lag < 0:
            xa, ya = x[-lag:], y[:len(y)+lag]
        elif lag > 0:
            xa, ya = x[:-lag], y[lag:]
        else:
            xa, ya = x, y
        keep = np.isfinite(xa) & np.isfinite(ya)
        xa, ya = xa[keep], ya[keep]
        coefficient = float(stats.pearsonr(xa, ya).statistic) if len(xa) >= 3 and np.std(xa) and np.std(ya) else None
        rows.append([lag, len(xa), coefficient])
        lags.append(lag)
        xs.append(coefficient)
    result = _base("dependence.lead_lag")
    result["tables"] = [_table("Lead–lag cross-correlation", ["Lag", "Aligned pairs", "Pearson correlation"], rows)]
    result["charts"] = [dict(type="line", title=f"Lead–lag cross-correlation: {x_name} and {y_name}", xLabel="Lag (positive: X leads Y)", yLabel="Pearson correlation", series=[dict(name="Correlation", x=lags, y=xs, markers={"visible": True})])]
    result["notes"].append("Positive lag k correlates X(t) with Y(t+k), so X leads Y by k worksheet rows. The full row order is treated as equally spaced time steps.")
    missing_count = int((~np.isfinite(x) | ~np.isfinite(y)).sum())
    if missing_count:
        result["warnings"].append(f"Missing values were excluded separately at each aligned lag; {missing_count} rows contain at least one missing input.")
    return result


def analyze(analysis_id, data, options=None):
    identifier = str(analysis_id)
    if identifier not in _by_id:
        raise ValueError("Unknown dependence analysis identifier.")
    options = options or {}
    if not isinstance(options, dict):
        raise ValueError("Analysis options must be an object.")
    if identifier == "dependence.association":
        return _association(data, options)
    if identifier == "dependence.partial":
        return _partial(data, options)
    if identifier == "dependence.distance":
        return _distance(data, options)
    if identifier == "dependence.mutual_information":
        return _mutual_information(data, options)
    if identifier == "dependence.tail_coexceedance":
        return _tail(data, options)
    if identifier == "dependence.lead_lag":
        return _lead_lag(data, options)
    raise ValueError("Unknown dependence analysis identifier.")
