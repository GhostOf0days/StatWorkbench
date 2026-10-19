"""Data preparation and study-size analyses."""
import math

import numpy as np
import pandas as pd
from scipy import optimize, stats

from backend.common import MAX_CELLS, MAX_COLUMNS, MAX_ROWS
from .data_control_fields import FIELDS

HANDLED = {'3001', '3002', '3005', '3303', '1703', '1704'}
REPLACED = {'3005': {'estimate', 'lambda', 'shift'}, '3303': {'condition', 'a', 'b'}}


def apply_catalog(entries):
    for entry in entries:
        aid = entry['id']
        if aid in FIELDS:
            new_keys = {f['key'] for f in FIELDS[aid]}
            entry['fields'] = [f for f in entry['fields'] if f['key'] not in REPLACED.get(aid, set()) | new_keys] + FIELDS[aid]
            entry['limitations'] = []
            entry['coverage'] = 'core'
        if aid == '1703':
            entry['fields'] = [f for f in entry['fields'] if f['key'] != 'probability'] + [{'key': 'PROB', 'label': 'p-value', 'type': 'number', 'default': .95, 'min': 0, 'max': .999999999}]
            entry['limitations'] = ['The probability input is truncated to an integer before sample-size calculation; the result may not attain the requested probability.']
    return entries


def conditional_mask(x, condition, a, b):
    """Evaluate the supported predicates while preserving row order."""
    valid = np.isfinite(x)
    result = np.zeros(len(x), dtype=bool)
    y = np.asarray(x)[valid]
    if condition in range(6, 10) and a >= b:
        raise ValueError('A must be less than B for an interval condition.')
    if condition < 10:
        result[valid] = [lambda: y == a, lambda: y != a, lambda: y < a,
                         lambda: y <= a, lambda: y > a, lambda: y >= a,
                         lambda: (y >= a) & (y <= b), lambda: (y > a) & (y < b),
                         lambda: (y < a) | (y > b), lambda: (y <= a) | (y >= b)][condition]()
    elif condition < 18:
        a = math.trunc(a)
        if not 1 <= a <= len(y):
            raise ValueError('Rank A must be between 1 and the number of observations.')
        ranks = stats.rankdata(-y if condition % 2 else y, method='min')
        result[valid] = [lambda: ranks < a, lambda: ranks <= a,
                         lambda: ranks > a, lambda: ranks >= a][(condition - 10) // 2]()
    else:
        if not 0 <= a <= 1:
            raise ValueError('Percentile A must be a fraction between 0 and 1 (for example, 0.5).')
        if len(y) < 2:
            raise ValueError('Percentile sampling requires at least two observations.')
        percentile = (stats.rankdata(y, method='min') - 1) / (len(y) - 1)
        result[valid] = [lambda: percentile < a, lambda: percentile <= a,
                         lambda: percentile > a, lambda: percentile >= a][condition - 18]()
    return result


def run(i, data, o, r):
    from . import advanced as ad
    if i == '1703':
        if 'PROB' not in o:
            return ad._sample_size(i, o, r)
        raw = ad._num(o, 'PROB', .95, 0, .999999999)
        p = ad._num(o, 'prevalence', 5, 1e-9, 100) / 100
        k = ad._num(o, 'events', 1, 1, 10**6, True)
        # The probability is truncated to an integer before calculation.
        target = math.trunc(raw)
        if k > 1:
            raise ValueError('After truncating the probability to an integer, this method cannot calculate a sample size for more than one required success.')
        n = 1
        r['tables'].append(ad._table('Minimum sample size', ['N', 'P(events ≥ minimum)', 'Minimum events', 'Used probability'], [[n, stats.binom.sf(k - 1, n, p), k, target]]))
        if target != raw:
            r['warnings'].append('The probability was truncated to an integer before calculation; this sample size does not attain the requested probability.')
        return
    if i == '1704':
        alpha = ad._num(o, 'alpha', .05, 1e-9, .999999)
        z = stats.norm.isf(alpha if o.get('sta.onesided', False) else alpha / 2)
        odds = ad._num(o, 'odds_ratio', 2, 1e-9)
        if odds == 1:
            raise ValueError('Odds ratio 1 has no effect and requires unbounded sample size.')
        p0 = ad._num(o, 'exposure', 20, 1e-8, 99.999999) / 100
        power = ad._num(o, 'power', 80, 1, 99.999) / 100
        ratio = ad._num(o, 'ratio', 1, .000001, 10000)
        p1 = odds * p0 / (1 - p0 + odds * p0)
        if o.get('sta.pass.matched_design', False):
            discordance = p1 * (1 - p0) + p0 * (1 - p1)
            theta = odds / (odds + 1)
            discordant_n = (z / 2 + stats.norm.ppf(power) * math.sqrt(theta * (1 - theta))) ** 2 / (theta - .5) ** 2
            n = discordant_n / discordance
            ratio = 1
            r['tables'].append(ad._table('Matched pairs', ['Exposure-discordant pair probability', 'Discordant pairs', 'Pairs', 'Total'], [[discordance, math.ceil(discordant_n), math.ceil(n), 2 * math.ceil(n)]]))
            r['tables'][-1]['columnFormats'] = {'0': '0.00%'}
            r['notes'].append('Matched design uses the native discordant-pair calculation and one control per case; pair count is rounded after dividing the unrounded discordant estimate by its probability.')
        else:
            mean = (p1 + ratio * p0) / (1 + ratio)
            n = (z * math.sqrt((1 + 1 / ratio) * mean * (1 - mean)) + stats.norm.ppf(power) * math.sqrt(p1 * (1 - p1) + p0 * (1 - p0) / ratio)) ** 2 / (p1 - p0) ** 2
        cases = math.ceil(n)
        r['tables'].append(ad._table('Sample size', ['Cases', 'Controls', 'Expected case exposure', 'Expected control exposure'], [[cases, math.ceil(cases * ratio), p1, p0]]))
        return
    if i == '3002':
        names = ad._names(data, [o.get('column'), o.get('group')])
        frame = ad._frame(data)[names]
        groups = list(pd.unique(frame.iloc[:, 1].dropna()))
        if not groups:
            raise ValueError('No nonmissing groups found.')
        sort = int(ad._choice(o, 'data.sort', '0', ['0', '1', '2', '3']))
        if sort < 2:
            # Keep numeric codes numeric; mixed codes sort numbers before text.
            key = lambda g: (0, float(g)) if isinstance(g, (float, int, np.number)) else (1, str(g))
        else:
            key = lambda g: int((frame.iloc[:, 1] == g).sum())
        groups.sort(key=key, reverse=sort in (1, 3))
        labels = [str(g) for g in groups]
        if len(set(labels)) != len(groups):
            raise ValueError('Group labels collide after conversion to text.')
        vectors = [frame.loc[frame.iloc[:, 1] == g].iloc[:, 0].to_list() for g in groups]
        count = max(map(len, vectors))
        if len(groups) > MAX_COLUMNS or len(groups) * count > MAX_CELLS:
            raise ValueError('Unstacked result exceeds the dataset column/cell limit.')
        r['dataset'] = ad._dataset(labels, [[v[row] if row < len(v) else None for v in vectors] for row in range(count)], r['title'])
        return
    names = ad._names(data, o.get('columns'))
    frame = ad._frame(data)[names]
    if i == '3001':
        if len(frame) * len(names) > MAX_ROWS or len(frame) * len(names) * 2 > MAX_CELLS:
            raise ValueError('Stacked result exceeds the dataset row/cell limit.')
        numbered = bool(o.get('sta.data.stackcols.numgroups', False))
        rows = [[index + 1 if numbered else name, value] for index, name in enumerate(names) for value in frame[name].to_list()]
        r['dataset'] = ad._dataset(['Variable', 'Value'], rows, r['title'])
    elif i == '3303':
        col = ad._names(data, o.get('condition_column'))[0]
        x = ad._numeric_frame(ad._frame(data)[[col]])[col].to_numpy(float)
        legacy = {'eq': '0', 'ne': '1', 'lt': '2', 'le': '3', 'gt': '4', 'ge': '5', 'between': '6', 'outside': '8'}
        condition = int(ad._choice(o, 'sta.data.samp.cond.cond', legacy.get(o.get('condition'), '0'), [str(i) for i in range(22)]))
        a, b = ad._num(o, 'A', o.get('a', 0)), ad._num(o, 'B', o.get('b', 0))
        mask = conditional_mask(x, condition, a, b)
        out = frame.loc[mask]
        r['dataset'] = ad._dataset(names, out.values.tolist(), r['title'])
        r['tables'].append(ad._table('Sampling', ['Input rows', 'Output rows'], [[len(frame), len(out)]]))
        if condition >= 10:
            r['notes'].append('Ties receive the minimum rank. Percentile conditions compare (rank − 1)/(N − 1) with A, entered as a fraction from 0 to 1.')
    elif i == '3005':
        out = ad._numeric_frame(frame)
        rows, transformed = [], {}
        for name in names:
            valid = np.isfinite(out[name].to_numpy())
            original = out.loc[valid, name].to_numpy()
            if len(original) < 2:
                raise ValueError(f'{name} requires at least two finite numbers.')
            use_shift = o.get('data.boxcox.values.addconst', 'shift' in o)
            shift = ad._num(o, 'data.boxcox.shift.const.ui', o.get('shift', 0)) if use_shift else 0
            if use_shift and o.get('data.boxcox.values.addconstmin', False) and original.min() < 0:
                shift -= original.min()
            x = original + shift
            positive = x > 0
            if not positive.all():
                r['warnings'].append(f'{name}: {int((~positive).sum())} nonpositive shifted observations were removed before Box-Cox transformation; the transformed column is compacted.')
                x = x[positive]
            if len(x) < 2:
                rows.append([name, len(original), None, float(shift), None, 0])
                r['warnings'].append(f'{name}: fewer than two positive observations remain; this column has no transformed output.')
                continue
            estimate = o.get('data.boxcox.lambda.estimate.ui', o.get('estimate', True))
            if estimate:
                if np.ptp(x) == 0:
                    raise ValueError('Estimating lambda requires nonconstant data.')
                # Native Brent minimization has a fixed [-2, 2] interval.
                fit = optimize.minimize_scalar(lambda value: -stats.boxcox_llf(value, x), bounds=(-2, 2), method='bounded', options={'xatol': 3e-11})
                if not fit.success:
                    raise ValueError('Box-Cox lambda estimation did not converge.')
                lam = fit.x
                y = stats.boxcox(x, lmbda=lam)
            else:
                lam = ad._num(o, 'data.boxcox.lambda.ui', o.get('lambda', 0), -5, 5)
                y = stats.boxcox(x, lmbda=lam)
            gm = np.exp(np.log(x).mean())
            if o.get('data.boxcox.gm.ui', False):
                y /= gm ** (lam - 1)
            if not np.isfinite(y).all():
                raise ValueError('The selected Box-Cox parameters overflow; use a smaller lambda or rescale the input.')
            transformed[name] = list(y)
            rows.append([name, len(original), float(lam), float(shift), float(gm), len(x)])
            if o.get('data.boxcox.qq.ui', False):
                for label, values in [('Original (shifted)', x), ('Transformed', y)]:
                    (theoretical, observed), (slope, intercept, _) = stats.probplot(values)
                    r['charts'].append(ad._chart(f'{name}: {label} normal Q-Q', [ad._series('Quantiles', theoretical, observed), {**ad._series('Reference', theoretical, intercept + slope * theoretical), 'type': 'line'}], 'scatter', 'Normal quantile', 'Observed quantile'))
        r['tables'].append(ad._table('Transformation', ['Variable', 'N', 'Lambda', 'Shift', 'Geometric mean', 'Used'], rows))
        if transformed:
            output_names = list(transformed)
            height = max(map(len, transformed.values()))
            r['dataset'] = ad._dataset(output_names, [[values[row] if row < len(values) else None for values in transformed.values()] for row in range(height)], r['title'])
        r['notes'].append('Each variable is compacted independently after discarding nonpositive shifted values. Automatic lambda is optimized on [−2, 2].')
