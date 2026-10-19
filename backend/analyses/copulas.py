"""Bivariate dependence models, an independent StatWorkbench extension.

Fits continuous copula densities to average ranks/(n+1). These are
maximum pseudo-likelihood fits, not likelihoods for the original marginals.
"""
from __future__ import annotations

import copy
import math
import numpy as np
import pandas as pd
from scipy import optimize, special, stats

COMMAND = 'copula.bivariate'
FAMILIES = ('independence', 'gaussian', 'student', 'clayton', 'frank', 'gumbel')
LABELS = dict(independence='Independence', gaussian='Gaussian', student='Student t',
              clayton='Clayton (positive dependence)', frank='Frank', gumbel='Gumbel')
BOUNDS = dict(gaussian=[(-.995, .995)], student=[(-.995, .995), (2.01, 100.)],
              clayton=[(0., 30.)], frank=[(-35., 35.)], gumbel=[(1., 25.)])
_ENTRY = dict(id=COMMAND, name='Bivariate Copulas', category='Dependence models',
    description='Fit, compare and simulate continuous bivariate dependence models with empirical marginal distributions.',
    coverage='extension', provenance='Independent StatWorkbench extension',
    limitations=['Bivariate continuous marginals; ties use average ranks with an explicit warning.',
                 'Clayton and Gumbel model positive dependence only. Student t degrees of freedom are bounded to 2.01–100.',
                 'Model selection and diagnostics are exploratory; simulation uses empirical margins and does not extrapolate beyond observed extremes.'],
    fields=[dict(key='x', label='Variable X', type='column', required=True),
            dict(key='y', label='Variable Y', type='column', required=True),
            dict(key='family', label='Copula family', type='select', required=True, default='auto',
                 options=[dict(value='auto', label='Compare all (choose lowest BIC)')]+[dict(value=k,label=v) for k,v in LABELS.items()]),
            dict(key='samples', label='Simulated pairs (0 to skip)', type='integer', required=True, default=1000, min=0, max=10000),
            dict(key='seed', label='Simulation seed', type='integer', required=True, default=0, min=0, max=9007199254740991),
            dict(key='tail_probability', label='Tail probability', type='number', required=True, default=.05, min=.01, max=.25, step=.01),
            dict(key='diagnostics', label='Holdout and split-window diagnostics', type='boolean', required=True, default=True)])


def catalog():
    return [copy.deepcopy(_ENTRY)]


def pseudo_observations(values):
    a = np.asarray(values, dtype=float)
    return np.column_stack([stats.rankdata(a[:, j], method='average') for j in range(2)])/(len(a)+1.)


def _log_sum_clayton(u, theta):
    a = np.logaddexp(-theta*np.log(u[:, 0]), -theta*np.log(u[:, 1]))
    return a + np.log1p(-np.exp(-a))


def _gumbel_parts(u, theta):
    logs = np.log(-np.log(u))
    log_s = np.logaddexp(theta*logs[:, 0], theta*logs[:, 1])
    return logs, log_s, np.exp(log_s/theta)


def _frank_log_den(u, theta):
    x, y = u[:, 0], u[:, 1]
    # Sum of two positive terms avoids catastrophic subtraction at large theta.
    return np.logaddexp(-theta*x+np.log(-np.expm1(-theta*y)),
                       -theta*y+np.log(-np.expm1(-theta*(1-y))))


def log_density(family, u, parameters):
    """Log copula density on the open unit square (not a marginal density)."""
    u = np.asarray(u, dtype=float)
    if u.ndim != 2 or u.shape[1] != 2 or not np.all(np.isfinite(u)) or np.any((u <= 0) | (u >= 1)):
        raise ValueError('Copula observations must be finite pairs strictly between zero and one.')
    p = np.asarray(parameters, dtype=float)
    if family == 'independence':
        return np.zeros(len(u))
    if family not in BOUNDS or len(p) != len(BOUNDS[family]) or any(not lo <= v <= hi for v,(lo,hi) in zip(p,BOUNDS[family])):
        raise ValueError('Copula parameters are outside the supported bounds.')
    if family in ('gaussian', 'student'):
        rho = p[0]
        if family == 'gaussian':
            z = stats.norm.ppf(u)
            q = rho*rho*(z[:, 0]**2+z[:, 1]**2)-2*rho*z[:, 0]*z[:, 1]
            return -.5*np.log1p(-rho*rho)-q/(2*(1-rho*rho))
        nu = p[1]
        z = stats.t.ppf(u, nu)
        q = (z[:, 0]**2+z[:, 1]**2-2*rho*z[:, 0]*z[:, 1])/(1-rho*rho)
        joint = special.gammaln((nu+2)/2)-special.gammaln(nu/2)-np.log(nu*np.pi)-.5*np.log1p(-rho*rho)-(nu+2)/2*np.log1p(q/nu)
        return joint-stats.t.logpdf(z, nu).sum(axis=1)
    theta = p[0]
    if family == 'clayton':
        if theta < 1e-7:
            return np.zeros(len(u))
        return np.log1p(theta)-(theta+1)*np.log(u).sum(axis=1)-(2+1/theta)*_log_sum_clayton(u, theta)
    if family == 'gumbel':
        if theta == 1:
            return np.zeros(len(u))
        logs, log_s, a = _gumbel_parts(u, theta)
        return -a+(theta-1)*logs.sum(axis=1)-np.log(u).sum(axis=1)+(2/theta-2)*log_s+np.log1p((theta-1)/a)
    if abs(theta) < 1e-7:
        return np.zeros(len(u))
    if theta < 0:
        u = np.column_stack([u[:, 0], 1-u[:, 1]])
        theta = -theta
    return np.log(theta)+np.log(-np.expm1(-theta))-theta*u.sum(axis=1)-2*_frank_log_den(u, theta)


def fit(family, u):
    """Bounded maximum pseudo-likelihood; failed optimizations are unavailable."""
    n = len(u)
    if family == 'independence':
        return dict(family=family, parameters=[], logLikelihood=0., aic=0., bic=0., boundary=False)
    if family not in BOUNDS:
        raise ValueError('Unknown copula family.')
    def objective(p):
        v = log_density(family, u, np.atleast_1d(p))
        return -float(v.sum()) if np.isfinite(v).all() else 1e100
    bounds = BOUNDS[family]
    candidates = []
    if family == 'student':
        tau = float(stats.kendalltau(u[:, 0], u[:, 1]).statistic)
        rho = float(np.clip(np.sin(np.pi*tau/2), -.98, .98))
        for degrees in (4., 20.):
            r = optimize.minimize(objective, [rho, degrees], method='L-BFGS-B', bounds=bounds,
                                  options=dict(maxiter=120, ftol=1e-10, gtol=1e-5))
            if r.success and np.isfinite(r.fun):
                candidates.append((float(r.fun), r.x.tolist()))
    else:
        segments = [bounds[0]] if family != 'frank' else [(-35., -1e-5), (1e-5, 35.)]
        for interval in segments:
            r = optimize.minimize_scalar(lambda t: objective([t]), bounds=interval,
                                         method='bounded', options=dict(xatol=1e-7, maxiter=150))
            if r.success and np.isfinite(r.fun):
                candidates.append((float(r.fun), [float(r.x)]))
        for endpoint in bounds[0]:
            candidates.append((objective([endpoint]), [endpoint]))
        if family in ('gaussian', 'clayton', 'frank'):
            candidates.append((objective([0.]), [0.]))
    if not candidates:
        raise ValueError(f'{LABELS[family]} optimization did not converge.')
    cost, p = min(candidates, key=lambda c: c[0])
    if not np.isfinite(cost) or cost > 1e90:
        raise ValueError(f'{LABELS[family]} has no finite fitted likelihood.')
    boundary = any(min(abs(v-lo), abs(v-hi)) < 1e-4*(hi-lo) for v,(lo,hi) in zip(p,bounds))
    k = len(p)
    return dict(family=family, parameters=p, logLikelihood=-cost, aic=2*k+2*cost,
                bic=math.log(n)*k+2*cost, boundary=bool(boundary))


def tail_dependence(family, p):
    if family == 'student':
        rho, nu = p
        value = 2*stats.t.cdf(-math.sqrt((nu+1)*(1-rho)/(1+rho)), nu+1)
        return float(value), float(value)
    if family == 'clayton':
        return (float(2**(-1/p[0])) if p[0] > 0 else 0.), 0.
    if family == 'gumbel':
        return 0., float(2-2**(1/p[0]))
    return 0., 0.


def _conditional(family, u, v, p):
    pairs = np.column_stack([u, v])
    theta = p[0]
    if family == 'clayton':
        return np.exp(-(theta+1)*np.log(u)-(1+1/theta)*_log_sum_clayton(pairs, theta))
    if family == 'gumbel':
        logs, log_s, a = _gumbel_parts(pairs, theta)
        return np.exp(-a+(1/theta-1)*log_s+(theta-1)*logs[:, 0]-np.log(u))
    if theta < 0:
        return 1-_conditional('frank', u, 1-v, [-theta])
    return np.exp(-theta*u+np.log(-np.expm1(-theta*v))-_frank_log_den(pairs, theta))


def simulate(family, parameters, size, seed):
    """Seeded simulation without touching NumPy's global random state."""
    log_density(family, np.array([[.5, .5]]), parameters)
    if isinstance(size, bool) or int(size) != size or not 0 <= size <= 10000:
        raise ValueError('Simulated pair count must be an integer from 0 to 10000.')
    rng = np.random.default_rng(seed)
    p = parameters
    if family == 'independence' or (family in ('clayton', 'frank') and abs(p[0]) < 1e-7) or (family == 'gumbel' and p[0] == 1):
        samples = rng.random((int(size), 2))
    elif family in ('gaussian', 'student'):
        z = rng.multivariate_normal([0., 0.], [[1., p[0]], [p[0], 1.]], size=int(size))
        if family == 'student':
            z /= np.sqrt(rng.chisquare(p[1], int(size))/p[1])[:, None]
            samples = stats.t.cdf(z, p[1])
        else:
            samples = stats.norm.cdf(z)
    else:
        u, target = rng.random((2, int(size)))
        low = np.full(int(size), np.finfo(float).eps)
        high = np.full(int(size), 1-np.finfo(float).eps)
        for _ in range(54):
            middle = (low+high)/2
            below = _conditional(family, u, middle, p) < target
            low = np.where(below, middle, low)
            high = np.where(below, high, middle)
        samples = np.column_stack([u, (low+high)/2])
    return np.clip(samples, np.finfo(float).eps, 1-np.finfo(float).eps)


def _number(options, key, default, lo, hi, integer=False):
    raw = options.get(key, default)
    if isinstance(raw, bool):
        raise ValueError(f'{key} must be numeric.')
    try:
        v = float(raw)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'{key} must be numeric.') from None
    if not np.isfinite(v) or not lo <= v <= hi or (integer and int(v) != v):
        raise ValueError(f'{key} must be {"an integer " if integer else ""}between {lo} and {hi}.')
    return int(v) if integer else v


def _table(title, columns, rows):
    return dict(title=title, columns=columns, rows=rows)


def _score_holdout(values, families):
    # Training margins only: never rank the holdout against future observations.
    split = int(len(values)*.8)
    train, test = values[:split], values[split:]
    u_train = pseudo_observations(train)
    u_test = np.column_stack([(np.searchsorted(np.sort(train[:, j]), test[:, j], side='left')+
                               np.searchsorted(np.sort(train[:, j]), test[:, j], side='right')+1)/(2*(len(train)+1)) for j in range(2)])
    rows = []
    for family in families:
        try:
            model = fit(family, u_train)
            score = float(np.mean(log_density(family, u_test, model['parameters'])))
            rows.append([LABELS[family], split, len(test), model['logLikelihood']/split, score, 'Converged'])
        except ValueError as e:
            rows.append([LABELS[family], split, len(test), None, None, str(e)])
    return rows


def analyze(analysis_id, data, options=None):
    if str(analysis_id) != COMMAND:
        raise ValueError('Unknown copula analysis identifier.')
    o = options or {}
    x, y = o.get('x'), o.get('y')
    if x not in data['columns'] or y not in data['columns'] or x == y:
        raise ValueError('Select two distinct numeric variables.')
    family = o.get('family', 'auto')
    if family not in (*FAMILIES, 'auto'):
        raise ValueError('Unknown copula family.')
    size = _number(o, 'samples', 1000, 0, 10000, True)
    seed = _number(o, 'seed', 0, 0, 9007199254740991, True)
    tail = _number(o, 'tail_probability', .05, .01, .25)
    diagnostics = o.get('diagnostics', True)
    if not isinstance(diagnostics, bool):
        raise ValueError('diagnostics must be true or false.')
    frame = pd.DataFrame(data['rows'], columns=data['columns'])[[x, y]].apply(pd.to_numeric, errors='coerce')
    raw = frame.to_numpy(dtype=float)
    values = raw[np.isfinite(raw).all(axis=1)]
    n = len(values)
    if not 20 <= n <= 20000:
        raise ValueError('Copula fitting requires 20 to 20000 complete numeric pairs.')
    if any(len(np.unique(values[:, j])) < 3 for j in range(2)):
        raise ValueError('Each copula variable requires at least three distinct numeric values.')
    u = pseudo_observations(values)
    tau = float(stats.kendalltau(u[:, 0], u[:, 1]).statistic)
    if abs(tau) > 1-1e-12:
        raise ValueError('Perfect rank dependence has a singular copula; finite density fitting is unavailable.')
    warning_list = []
    if n < len(raw):
        warning_list.append(f'Excluded {len(raw)-n} rows with missing, nonnumeric or nonfinite selected values.')
    if any(len(np.unique(values[:, j])) < n for j in range(2)):
        warning_list.append('Ties use average ranks. Continuous copula likelihoods and information criteria are approximate for tied or discrete data.')
    families = FAMILIES if family == 'auto' else tuple(dict.fromkeys(['independence', 'gaussian', family]))
    models, failed = {}, []
    for name in families:
        try:
            models[name] = fit(name, u)
        except ValueError as e:
            failed.append([LABELS[name], None, None, None, None, None, None, None, str(e)])
            warning_list.append(str(e))
    if family != 'auto' and family not in models:
        raise ValueError('The requested copula could not be fitted; choose a different family.')
    chosen = min(models.values(), key=lambda m: m['bic']) if family == 'auto' else models[family]
    selected = chosen['family']
    if chosen['boundary']:
        warning_list.append('The selected fit reached a numerical parameter bound; inspect holdout scores and split-window stability before interpreting it.')
    comparison = []
    for name, model in sorted(models.items(), key=lambda item: item[1]['bic']):
        lower, upper = tail_dependence(name, model['parameters'])
        p = model['parameters']
        comparison.append([LABELS[name], p[0] if p else None, p[1] if len(p)>1 else None,
                           model['logLikelihood'], model['aic'], model['bic'], lower, upper,
                           'Selected; boundary' if name==selected and model['boundary'] else 'Selected' if name==selected else 'Boundary' if model['boundary'] else 'Converged'])
    r = dict(analysis=COMMAND, title='Bivariate Copulas', tables=[], charts=[], warnings=warning_list,
             notes=['Exploratory bivariate copula analysis; estimates depend on family selection and pseudo-likelihood fitting.',
                    'Average ranks/(N+1) estimate continuous marginal probabilities. Fits maximize copula pseudo-likelihood.',
                    'AIC/BIC describe rank-based copula fits only; they do not compare fitted marginal distributions or establish goodness of fit.',
                    'Lower/upper tail dependence coefficients are asymptotic limits. Finite-tail probabilities below describe a different quantity.',
                    'Simulation uses empirical quantiles (linear interpolation), so simulated marginal values stay within observed extrema.'],
             copula=dict(selectedFamily=selected, models=models, observations=n, seed=seed))
    r['tables'].append(_table('Model comparison', ['Family', 'Rho / theta', 't degrees of freedom', 'Log pseudo-likelihood', 'AIC', 'BIC', 'Lower tail dependence', 'Upper tail dependence', 'Status'], comparison+failed))
    r['tables'].append(_table('Dependence summary', ['Measure', 'Value'], [['Complete pairs', n], ['Kendall tau-b', tau],
                          ['Spearman rho', float(stats.spearmanr(values[:, 0], values[:, 1]).statistic)], ['Selected family', LABELS[selected]], ['Simulation seed', seed]]))
    # Fixed-size independent Monte Carlo diagnostic keeps tail checks available even when output simulation is disabled.
    diagnostic_samples = simulate(selected, chosen['parameters'], 10000, seed)
    rows = []
    for label, mask, simulated_mask in [('Lower', (u[:, 0] <= tail)&(u[:, 1] <= tail), (diagnostic_samples[:, 0] <= tail)&(diagnostic_samples[:, 1] <= tail)),
                                         ('Upper', (u[:, 0] >= 1-tail)&(u[:, 1] >= 1-tail), (diagnostic_samples[:, 0] >= 1-tail)&(diagnostic_samples[:, 1] >= 1-tail))]:
        observed = float(mask.mean())
        predicted = float(simulated_mask.mean())
        se = math.sqrt(predicted*(1-predicted)/len(diagnostic_samples))
        rows.append([label, tail, int(mask.sum()), observed, predicted, se, observed-predicted])
        if int(mask.sum()) < 5:
            warning_list.append(f'{label} tail contains fewer than five observed joint events; the tail comparison is imprecise.')
    r['tables'].append(_table('Finite-tail joint events (10000 simulated pairs)', ['Tail', 'Marginal tail probability', 'Observed joint count', 'Observed joint probability', 'Model joint probability (Monte Carlo)', 'Monte Carlo SE', 'Observed minus model'], rows))
    if diagnostics and n >= 40:
        holdout = _score_holdout(values, families)
        r['tables'].append(_table('Chronological holdout (first 80% training)', ['Family', 'Training pairs', 'Holdout pairs', 'Training mean log density', 'Holdout mean log density', 'Status'], holdout))
        selected_score = next(row[4] for row in holdout if row[0] == LABELS[selected])
        if selected_score is None or selected_score < 0:
            warning_list.append('The selected family did not outperform independence on chronological holdout data. Review the independence/Gaussian challengers before using simulated dependence.')
        split_rows = []
        for label, part in [('First half', values[:n//2]), ('Second half', values[n//2:])]:
            part_u = pseudo_observations(part)
            try:
                model = fit(selected, part_u)
                p = model['parameters']
                split_rows.append([label, len(part), float(stats.kendalltau(part[:, 0], part[:, 1]).statistic), p[0] if p else None,
                                   p[1] if len(p)>1 else None, model['logLikelihood']/len(part), 'Boundary' if model['boundary'] else 'Converged'])
            except ValueError as e:
                split_rows.append([label, len(part), None, None, None, None, str(e)])
        r['tables'].append(_table('Split-window parameter stability (selected family)', ['Window', 'Pairs', 'Kendall tau-b', 'Rho / theta', 't degrees of freedom', 'Mean log density', 'Status'], split_rows))
        if all(row[2] is not None and np.isfinite(row[2]) for row in split_rows) and abs(split_rows[0][2]-split_rows[1][2]) > .3:
            warning_list.append('Split-window Kendall tau differs by more than 0.3. A single stationary copula may not describe both windows.')
        r['notes'].append('Holdout preserves input row order and transforms test values using training margins only. Split-window fits use each window’s own ranks. These diagnostics are descriptive, not formal drift tests.')
    elif diagnostics:
        warning_list.append('Holdout and split-window diagnostics require at least 40 complete pairs.')
    r['charts'].append(dict(type='scatter', title='Observed rank dependence', xLabel=f'{x} probability rank', yLabel=f'{y} probability rank', xMin=0, xMax=1, yMin=0, yMax=1,
                            series=[dict(name='Observed', x=u[:2000, 0].tolist(), y=u[:2000, 1].tolist())]))
    if size:
        s = simulate(selected, chosen['parameters'], size, seed)
        simulated = np.column_stack([s, np.quantile(values[:, 0], s[:, 0]), np.quantile(values[:, 1], s[:, 1])])
        r['dataset'] = dict(name='Copula simulation', columns=['U (X)', 'U (Y)', f'{x} (simulated X)', f'{y} (simulated Y)'], rows=simulated.tolist())
        r['charts'].append(dict(type='scatter', title=f'Simulated dependence: {LABELS[selected]}', xLabel=f'{x} probability', yLabel=f'{y} probability', xMin=0, xMax=1, yMin=0, yMax=1,
                                series=[dict(name='Simulated', x=s[:2000, 0].tolist(), y=s[:2000, 1].tolist())]))
    if max(n, size) > 2000:
        r['notes'].append('Scatter charts show the first 2000 pairs; fitting and generated data use all requested pairs.')
    return r
