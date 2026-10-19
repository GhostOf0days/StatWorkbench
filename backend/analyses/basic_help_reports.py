"""Report calculations and statistical reference methods."""
from __future__ import annotations
import math
import numpy as np
from scipy import stats
from scipy.special import gammaln
from statsmodels.stats.diagnostic import normal_ad


def native_lilliefors(values):
    """Compute the Lilliefors statistic with the large-sample rescaling."""
    x=np.sort(np.asarray(values,dtype=float));n=len(x)
    cdf=stats.norm.cdf(x,np.mean(x),np.std(x,ddof=1))
    raw=float(max(np.max(np.arange(1,n+1)/n-cdf),np.max(cdf-np.arange(n)/n)))
    d=raw*(n/100)**.49 if n>100 else raw;effective=min(n,100)
    p=math.exp(-7.01256*d*d*(effective+2.78019)+2.99587*d*math.sqrt(effective+2.78019)-.122119+.974598/math.sqrt(effective)+1.67997/effective)
    if p>.1:
        z=(math.sqrt(n)-.01+.85/math.sqrt(n))*d
        if z<=.302:p=1.
        elif z<=.5:p=2.76773-19.828315*z+80.709644*z*z-138.55152*z**3+81.218052*z**4
        elif z<=.9:p=-4.901232+40.662806*z-97.490286*z*z+94.029866*z**3-32.355711*z**4
        elif z<=1.31:p=6.198765-19.558097*z+23.186922*z*z-12.234627*z**3+2.423045*z**4
        else:p=0.
    return d,p,raw


def mann_whitney_report(x, y, names):
    """Build the four approximation rows for the Mann–Whitney report.

    The report shows both normal and Student-t approximations; it does not
    choose one inference method based on sample size. One-tailed cells use the
    smaller tail, independently of sample direction.
    """
    from .basic import _table
    n1, n2 = len(x), len(y)
    if min(n1, n2) < 2:
        raise ValueError('Each independent sample must contain at least two observations.')
    n = n1 + n2
    ranks = stats.rankdata(np.concatenate([x, y]))
    sums = [float(ranks[:n1].sum()), float(ranks[n1:].sum())]
    # The native per-sample U has the opposite orientation from SciPy's U1.
    u = [n1*n2 + n1*(n1+1)/2 - sums[0], sums[0] - n1*(n1+1)/2]
    _, counts = np.unique(np.concatenate([x, y]), return_counts=True)
    variance = n1*n2/12 * (n+1 - float(np.sum(counts**3-counts))/(n*(n-1)))
    sd = math.sqrt(max(0., variance))
    z = (min(u) - n1*n2/2)/sd if sd else None
    corrected = z + .5/sd if z is not None and z != 0 else None
    rows = []
    for label, statistic, distribution in (
        ('Normal approximation', z, stats.norm),
        ('Normal approximation with continuity correction', corrected, stats.norm),
        ('Student-t approximation (df = N−1)', z, stats.t(n-1)),
        ('Student-t approximation with continuity correction (df = N−1)', corrected, stats.t(n-1)),
    ):
        tail = float(distribution.sf(abs(statistic))) if statistic is not None else None
        rows.append([label, statistic, tail, min(1., 2*tail) if tail is not None else None])
    summaries = [[name, size, us, rank_sum, size*(n+1)/2, sd, rank_sum/size]
                 for name, size, us, rank_sum in zip(names, [n1, n2], u, sums)]
    tables = [
        _table('Mann–Whitney sample ranks', ['Variable', 'N', 'U', 'Rank sum', 'Expected rank sum (H0)', 'SD (H0)', 'Mean rank'], summaries),
        _table('Mann–Whitney statistics', ['Statistic', 'Value'], [['U', min(u)], ['W', min(sums)], ['Tied value sets', int(np.sum(counts > 1))]]),
        _table('Mann–Whitney inference', ['Method', 'Statistic', 'p-value (one-tailed)', 'p-value (two-tailed)'], rows),
    ]
    return min(u), tables


# Numerical reference tables addressed by native 0x4b4570. Rows/columns are
# sample sizes 11..26. These are compatibility facts, not executable source.
_ROSENBAUM_95 = [list(map(int,s)) for s in (
    '6667787777888888','6667777777777888','6666677777777888','7766677777777888',
    '7766667777777888','8777667777777888','7777777777777888','7777777777777888',
    '7777777777777888','7777777777777878','8777777777777777','8777777777777777',
    '8877777777777777','8888888888777777','8888888887777777','8888888888777777')]
_ROSENBAUM_99 = [list(map(int,s.split())) for s in (
    '9 9 9 9 9 9 10 10 10 10 11 11 11 12 12 12',
    '9 9 9 9 9 9 9 10 10 10 10 11 11 11 11 12',
    '9 9 9 9 9 9 9 9 10 10 10 10 10 11 11 11',
    '9 9 9 9 9 9 9 9 9 10 10 10 10 10 10 11',
    '9 9 9 9 9 9 9 9 9 9 9 10 10 10 10 10',
    '9 9 9 9 9 9 9 9 9 9 9 9 10 10 10 10',
    '10 9 9 9 9 9 9 9 9 9 9 9 9 10 10 10',
    '10 10 9 9 9 9 9 9 9 9 9 9 9 9 10 10',
    '10 10 10 9 9 9 9 9 9 9 9 9 9 9 9 10',
    '10 10 10 10 9 9 9 9 9 9 9 9 9 9 9 9',
    '11 10 10 10 9 9 9 9 9 9 9 9 9 9 9 9',
    '11 11 10 10 10 9 9 9 9 9 9 9 9 9 9 9',
    '11 11 10 10 10 10 9 9 9 9 9 9 9 9 9 9',
    '12 11 11 10 10 10 10 9 9 9 9 9 9 9 9 9',
    '12 11 11 10 10 10 10 10 9 9 9 9 9 9 9 9',
    '12 12 11 11 10 10 10 10 10 9 9 9 9 9 9 9')]


def rosenbaum(x,y,confidence):
    high,low=(y,x) if np.max(x)<=np.max(y) else (x,y)
    q=int(np.sum(high>np.max(low))+np.sum(low<np.min(high)))
    critical=None
    if 11<=len(x)<=26 and 11<=len(y)<=26:
        if abs(confidence-.95)<1e-10:critical=_ROSENBAUM_95[len(x)-11][len(y)-11]
        elif abs(confidence-.99)<1e-10:critical=_ROSENBAUM_99[len(x)-11][len(y)-11]
    return q,critical


def native_run_counts(x,y):
    """Return deterministic lower- and upper-order tied-block sequences."""
    values=np.concatenate([x,y]);labels=np.r_[np.ones(len(x),dtype=int),np.full(len(y),2)]
    order=np.argsort(values,kind='stable');values=values[order];labels=labels[order]
    low=[];high=[];tie_sets=tie_values=0
    boundaries=np.r_[0,np.flatnonzero(values[1:]!=values[:-1])+1,len(values)]
    for start,end in zip(boundaries[:-1],boundaries[1:]):
        block=labels[start:end]
        if end-start==1:
            low.append(int(block[0]));high.append(int(block[0]));continue
        ones=int(np.sum(block==1));twos=len(block)-ones
        if ones and twos:tie_sets+=1;tie_values+=len(block)
        first=low[-1] if low else 1
        grouped=([1]*ones+[2]*twos) if first==1 else ([2]*twos+[1]*ones)
        low.extend(grouped)
        # Alternate the grouped block's ends using the prior upper ordering
        # to select which end goes first.
        reverse_first=not high or high[-1]==2
        left,right=0,len(grouped)-1
        while left<=right:
            if reverse_first:high.append(grouped[right]);right-=1
            else:high.append(grouped[left]);left+=1
            reverse_first=not reverse_first
    count=lambda seq:1+sum(a!=b for a,b in zip(seq,seq[1:]))
    a,b=count(low),count(high)
    return [a,b] if b>a else [1+int(np.sum(labels[1:]!=labels[:-1]))],tie_sets,tie_values


def runs_exact_distribution(n1,n2):
    """Unconditional binary-label run probabilities in log-combination space."""
    possible=np.arange(2,2*min(n1,n2)+(n1!=n2)+1,dtype=int)
    half=possible//2
    def logchoose(n,k):
        valid=(k>=0)&(k<=n)
        return np.where(valid,gammaln(n+1)-gammaln(k+1)-gammaln(n-k+1),-np.inf)
    a=logchoose(n1-1,half-1);b=logchoose(n2-1,half-1)
    counts=np.where(possible%2==0,math.log(2)+a+b,
        np.logaddexp(logchoose(n1-1,half)+b,a+logchoose(n2-1,half)))
    denominator=gammaln(n1+n2+1)-gammaln(n1+1)-gammaln(n2+1)
    return possible,np.exp(counts-denominator)


def runs_report(x,y):
    """Native normal/continuity and exact tails; calls mirror 0xe81f0."""
    n1,n2=len(x),len(y);n=n1+n2;mean=1+2*n1*n2/n
    variance=2*n1*n2*(2*n1*n2-n)/(n*n*(n-1));sd=math.sqrt(variance)
    counts,tie_sets,tie_values=native_run_counts(x,y)
    possible,probabilities=runs_exact_distribution(n1,n2)
    rows=[]
    for i,runs in enumerate(counts):
        z=(runs-mean)/sd;zcc=z+.5/sd
        lower=float(stats.norm.cdf(z));lower_cc=float(stats.norm.cdf(zcc))
        # Native exact two-tail definition uses distance from the expected
        # run count, rather than twice the smaller inclusive tail.
        extreme=np.abs(possible-mean)>=abs(runs-mean)-1e-12
        exact2=min(1.,float(np.sum(probabilities[extreme])))
        lower_exact=min(1.,float(np.sum(probabilities[possible<=runs])))
        upper_exact=min(1.,float(np.sum(probabilities[possible>=runs])))
        rows.append(['Minimum' if len(counts)>1 and i==0 else 'Maximum' if len(counts)>1 else 'Observed',runs,n1,n2,z,lower,min(1.,2*lower),zcc,lower_cc,min(1.,2*lower_cc),lower_exact,upper_exact,exact2])
    table={'title':'Wald–Wolfowitz runs test','columns':['Ordering','Runs','N1','N2','Z','Normal lower-tail p','Native normal two-tail p','Z with continuity correction','Corrected normal lower-tail p','Native corrected normal two-tail p','Exact lower-tail p','Exact upper-tail p','Exact two-tail p'],'rows':rows}
    notes=['Runs inference reproduces the native normal two-tail calculation min(1, 2Φ(Z)); it consequently reports 1 for positive Z. Continuity correction adds 0.5/SD. Exact two-tail probability sums outcomes at least as far from the expected runs as observed.']
    if tie_sets:notes.append(f'{tie_sets} cross-sample tied blocks contain {tie_values} observations. Minimum/maximum labels retain deterministic orderings; exact tails use unconditional label permutations, not a distribution conditioned on the tied values.')
    return table,notes


def regression_vectors(fit):
    x = np.asarray(fit.model.wexog, dtype=float)
    residual = np.asarray(fit.resid, dtype=float)
    white_residual = np.asarray(fit.wresid, dtype=float)
    hat = np.clip(np.sum(x * np.linalg.pinv(x).T, axis=1), 0, 1)
    remaining = 1 - hat
    # A leverage-one observation has no identifiable deleted fit. Do not turn
    # that undefined quantity into a huge, apparently valid diagnostic.
    remaining = np.where(remaining > 1e-12, remaining, np.nan)
    mse = float(fit.mse_resid)
    rmse = math.sqrt(mse)
    standard = white_residual / rmse if rmse > 0 else np.full(len(hat), np.nan)
    student = standard / np.sqrt(remaining)
    deleted_var = ((fit.ssr - white_residual**2 / remaining) / (fit.df_resid - 1)
                   if fit.df_resid > 1 else np.full(len(hat), np.nan))
    deleted = white_residual / np.sqrt(np.where(deleted_var > 0, deleted_var, np.nan) * remaining)
    press_residual = residual / remaining
    p = x.shape[1]
    cook = student**2 * hat / (p * remaining)
    dffits = deleted * np.sqrt(hat / remaining)
    return dict(hat=hat, standard=standard, student=student, deleted=deleted,
                press_residual=press_residual, press=float(np.sum((white_residual / remaining)**2)),
                cook=cook, dffits=dffits)


def regression_tables(fit, names, opt, result, b):
    vectors = regression_vectors(fit)
    n = int(fit.nobs)
    total = float(fit.centered_tss if fit.model.k_constant else fit.uncentered_tss)
    summary = next(t for t in result['tables'] if t['title'] == 'Model summary')
    for row in summary['rows']:
        if row[0] == 'Adjusted R²': row[1] = max(0., row[1])
    summary['rows'].extend([['Multiple R', math.sqrt(max(0., fit.rsquared))],
        ['Mean square error', fit.mse_resid], ['RMSE', math.sqrt(fit.mse_resid)],
        ['PRESS', vectors['press']], ['PRESS RMSE', math.sqrt(vectors['press'] / n)],
        ['Predicted R²', 1 - vectors['press'] / total if total > 0 else None]])
    result['tables'].append(b._table('Regression ANOVA',
        ['Source', 'Sum of squares', 'df', 'Mean square', 'F', 'p-value'], [
        ['Regression', fit.ess, fit.df_model, fit.mse_model, fit.fvalue, fit.f_pvalue],
        ['Residual', fit.ssr, fit.df_resid, fit.mse_resid, None, None],
        ['Total', total, n - int(fit.model.k_constant), None, None, None]]))
    coefficients = next(t for t in result['tables'] if t['title'] == 'Coefficients')
    coefficients['columns'] += ['VIF', 'Tolerance', 'H0 at alpha']
    x = np.asarray(fit.model.exog, dtype=float)
    weights = np.asarray(getattr(fit.model, 'weights', np.ones(n)), dtype=float)
    if weights.ndim == 0: weights = np.full(n, weights)
    intercept = [i for i in range(x.shape[1]) if np.ptp(x[:, i]) == 0]
    alpha = 1 - b._conf(opt)
    for j, row in enumerate(coefficients['rows']):
        vif = tol = None
        if j not in intercept:
            others = np.delete(x, j, axis=1)
            target = x[:, j]
            root = np.sqrt(weights)
            fitted = others @ np.linalg.lstsq(others * root[:, None], target * root, rcond=None)[0]
            rss = np.sum(weights * (target - fitted)**2)
            tss = np.sum(weights * (target - np.average(target, weights=weights))**2) if intercept else np.sum(weights * target**2)
            if tss > 0:
                tol = min(1., max(0., rss / tss))
                vif = 1 / tol if tol > 0 else math.inf
        row.extend([vif, tol, 'Reject' if row[4] < alpha else 'Do not reject'])
    if b.basic_options.boolean(opt, 'glm.showcorrs'):
        partial = []
        for name, value, pvalue in zip(names, fit.tvalues, fit.pvalues):
            if name != 'Intercept':
                partial.append([name, float(value) / math.sqrt(float(value)**2 + fit.df_resid),
                                fit.df_resid, pvalue])
        result['tables'].append(b._table('Partial correlations with response',
            ['Predictor', 'Partial correlation', 'df', 'p-value'], partial))
        active=[i for i in range(x.shape[1]) if i not in intercept]
        if active:
            variables=['Response']+[names[i] for i in active]
            values=np.column_stack([fit.model.endog,x[:,active]])
            covariance=np.cov(values,rowvar=False,aweights=weights)
            if np.linalg.matrix_rank(covariance)==len(variables):
                precision=np.linalg.inv(covariance)
                correlations=-precision/np.sqrt(np.outer(np.diag(precision),np.diag(precision)))
                np.fill_diagonal(correlations,1.)
                result['tables'].append(b._table('Partial correlation matrix',['Variable']+variables,
                    [[name]+list(correlations[i]) for i,name in enumerate(variables)]))
            else:result['warnings'].append('Partial correlation matrix is undefined for a singular response/predictor covariance matrix.')
    if np.isnan(vectors['press_residual']).any():
        result['warnings'].append('Deleted-observation diagnostics are undefined for leverage-one observations.')
    result['notes'].append('Adjusted R² is floored at zero. PRESS uses deleted-observation prediction residuals; PRESS RMSE uses N in the denominator.')
    if not np.all(weights == 1):
        result['notes'].append('WLS sums of squares, PRESS, standardization and leverage use the supplied variance weights. Raw fitted values and prediction residuals remain in response units.')
    return result


def normality(frame, opt, b):
    rows, critical, summaries = [], [], []
    for c in b._names(frame, opt):
        x = b._vector(frame, c, 3)
        n = len(x)
        if np.ptp(x) == 0: raise ValueError('Normality tests require nonconstant values: ' + c)
        s = stats.shapiro(x)
        rows.append([c, 'Shapiro–Wilk', n, s.statistic, s.pvalue])
        if n >= 8:
            skew = stats.skewtest(x); kurt = stats.kurtosistest(x)
            rows.extend([[c, 'D’Agostino skewness Z', n, skew.statistic, skew.pvalue],
                         [c, 'D’Agostino kurtosis Z', n, kurt.statistic, kurt.pvalue],
                         [c, 'D’Agostino K²', n, skew.statistic**2 + kurt.statistic**2,
                          stats.chi2.sf(skew.statistic**2 + kurt.statistic**2, 2)]])
        elif n >= 5:
            kurt = stats.kurtosistest(x)
            rows.append([c, 'D’Agostino kurtosis Z', n, kurt.statistic, kurt.pvalue])
        if n >= 3:
            d, p, raw = native_lilliefors(x)
            rows.append([c, 'Lilliefors normal', n, d, p])
            if n>100:rows.append([c,'KS unscaled empirical distance',n,raw,None])
            stephens=raw*(math.sqrt(n)-.01+.85/math.sqrt(n))
            bounded=float(np.interp(stephens,[.775,.819,.895,.995,1.035],[.15,.10,.05,.025,.01]))
            rows.append([c,'KS/Stephens (bounded reference)',n,stephens,bounded])
        s = stats.anderson(x, dist='norm')
        _, p_ad = normal_ad(x)
        rows.append([c, 'Anderson–Darling', n, s.statistic, p_ad])
        critical.extend([[c, a, cv] for a, cv in zip(s.significance_level, s.critical_values)])
        summaries.append([c, n, np.std(x, ddof=1), np.mean(x), np.median(x),
            stats.skew(x, bias=True), stats.kurtosis(x, fisher=False, bias=True),
            stats.skew(x, bias=False), stats.kurtosis(x, fisher=True, bias=False)])
    return b._result('1011', [
        b._table('Normality tests', ['Variable', 'Test', 'N', 'Statistic', 'p-value'], rows),
        b._table('Anderson–Darling critical values', ['Variable', 'Significance (%)', 'Critical value'], critical),
        b._table('Normality descriptive statistics', ['Variable', 'N', 'SD', 'Mean', 'Median',
            'Skewness', 'Kurtosis', "Skewness (Fisher's)", "Kurtosis (Fisher's)"], summaries)],
        notes=['Missing values omitted separately. Lilliefors reproduces native 0x4be590: Dallal–Wilkinson exponential approximation and piecewise Stephens polynomial when that p exceeds .1. For N > 100 the native displayed D is scaled by (N/100)^.49; the unscaled empirical distance is additionally identified. The separate KS/Stephens reference linearly interpolates published critical values and is bounded at .01 and .15 (endpoint values represent bounds, not exact p-values). Skewness/omnibus require N ≥ 8; kurtosis requires N ≥ 5 and its asymptotic calibration is less reliable below 20.'])


def variance_test(frame, opt, b):
    a, c = b._name(frame, opt, 'x'), b._name(frame, opt, 'y')
    clean = b._complete(frame, [a, c])
    x, y = clean[a].to_numpy(), clean[c].to_numpy()
    vx, vy = np.var(x, ddof=1), np.var(y, ddof=1)
    if vx <= 0 or vy <= 0: raise ValueError('Both samples need nonzero variance for an F variance-ratio test.')
    ratio = b._num(opt, 'help.f.ratio' if 'help.f.ratio' in opt else 'ratio', 1, minimum=np.finfo(float).tiny)
    f = vx / vy / ratio
    df1, df2 = len(x)-1, len(y)-1
    dist = stats.f(df1, df2); alpha = 1 - b._conf(opt)
    table = b._table('Variance ratio', ['N1', 'N2', 'Variance1', 'Variance2', 'F', 'df1', 'df2', 'p-value', 'Ratio CI lower', 'Ratio CI upper'],
        [[len(x), len(y), vx, vy, f, df1, df2, b._pvalue(f, dist, b._alt(opt)),
          (vx/vy)/dist.ppf(1-alpha/2), (vx/vy)/dist.ppf(alpha/2)]])
    ordered = (x, y) if vx >= vy else (y, x)
    larger = np.var(ordered[0], ddof=1) / np.var(ordered[1], ddof=1)
    tail_rows = [[a + ' / ' + c, f, df1, df2, dist.cdf(f), dist.sf(f),
                  b._pvalue(f, dist, 'two-sided'), dist.ppf(1-alpha), dist.ppf(1-alpha/2)]]
    ld = stats.f(len(ordered[0])-1, len(ordered[1])-1)
    tail_rows.append(['Larger / smaller variance (null ratio 1)', larger, len(ordered[0])-1,
        len(ordered[1])-1, ld.cdf(larger), ld.sf(larger), min(1., 2*ld.sf(larger)), ld.ppf(1-alpha), ld.ppf(1-alpha/2)])
    return b._result('1008', [table,
        b._table('F-test tails and critical values', ['Comparison', 'F', 'df1', 'df2', 'Lower-tail p', 'Upper-tail p', 'Two-tailed p', 'Upper critical F (one tail)', 'Upper critical F (two tails)'], tail_rows),
        b._table('Sample statistics', ['Variable', 'N', 'Mean', 'Variance', 'SD', 'SE'],
            [[name, len(v), np.mean(v), np.var(v, ddof=1), np.std(v, ddof=1), stats.sem(v)] for name, v in [(a, x), (c, y)]])],
        notes=['Samples must be independent and normally distributed. Missing values are removed listwise.', f'Hypothesized first/second variance ratio: {ratio:g}.'])


def mean_report(aid, frame, opt, result, b):
    table = result['tables'][0]
    tails = []
    if aid in ('1003', '1004'):
        table['columns'] += ['Difference']
        for row in table['rows']: row.append(row[2] - row[3])
        for row in table['rows']:
            dist = stats.norm if aid == '1004' else stats.t(row[6])
            tails.append([row[0], row[5], dist.cdf(row[5]), dist.sf(row[5]), b._pvalue(row[5], dist, 'two-sided'),
                          dist.ppf(b._conf(opt)), dist.ppf((1+b._conf(opt))/2)])
        cols = [row[0] for row in table['rows']]
        result['tables'].append(b._table('Sample statistics', ['Variable', 'N', 'Variance', 'SD', 'Population variance'],
            [[c, len(v), np.var(v, ddof=1), np.std(v, ddof=1), opt.get('variance') if aid == '1004' else None]
             for c in cols for v in [b._vector(frame, c)]]))
    else:
        row = table['rows'][0]
        dist = stats.norm if aid == '1007' else stats.t(row[9])
        tails.append([row[0], row[8], dist.cdf(row[8]), dist.sf(row[8]), b._pvalue(row[8], dist, 'two-sided'),
                      dist.ppf(b._conf(opt)), dist.ppf((1+b._conf(opt))/2)])
        if aid == '10052':
            sample = [('Sample1', int(opt['n1']), float(opt['sd1'])), ('Sample2', int(opt['n2']), float(opt['sd2']))]
        else:
            if aid == '10053': values = b.basic_options.group_selection(b._groups(frame,opt,1,1),opt)
            else:
                cols = [b._name(frame,opt,'x'), b._name(frame,opt,'y')]
                clean = b._complete(frame, cols) if opt.get('test_type') == 'paired' else frame
                values = [(c, b._vector(clean,c)) for c in cols]
            sample = [(c, len(v), np.std(v,ddof=1)) for c,v in values]
        stats_rows = [[c,n,sd*sd,sd,sd/math.sqrt(n)] for c,n,sd in sample]
        result['tables'].append(b._table('Sample statistics', ['Variable','N','Variance','SD','SE'],stats_rows))
        if aid != '1007' and opt.get('test_type','pooled') == 'pooled':
            pooled = sum((n-1)*sd*sd for _,n,sd in sample) / (sum(n for _,n,_ in sample)-2)
            result['tables'].append(b._table('Pooled variance', ['Metric','Value'], [['Pooled variance',pooled]]))
    result['tables'].append(b._table('Test tails and critical values', ['Comparison','Statistic','Lower-tail p','Upper-tail p','Two-tailed p','Upper critical (one tail)','Upper critical (two tails)'], tails))
    return result


def summarized_z(opt,b):
    n=b._num(opt,'help.z.n',minimum=2,integer=True)
    mean=b._num(opt,'help.z.sample_mean');mu=b._num(opt,'mean',0)
    variance=b._num(opt,'variance',minimum=np.finfo(float).tiny)
    se=math.sqrt(variance/n);z=(mean-mu)/se;confidence=b._conf(opt)
    margin=stats.norm.ppf((1+confidence)/2)*se
    return b._result('1004',[
        b._table('Mean tests',['Variable','N','Mean','Hypothesized mean','SE','Statistic','df','p-value','Mean CI lower','Mean CI upper','Difference'],
            [['Summarized sample',n,mean,mu,se,z,None,b._pvalue(z,stats.norm,b._alt(opt)),mean-margin,mean+margin,mean-mu]]),
        b._table('Population variance',['Metric','Value'],[['Known population variance',variance]]),
        b._table('Test tails and critical values',['Comparison','Statistic','Lower-tail p','Upper-tail p','Two-tailed p','Upper critical (one tail)','Upper critical (two tails)'],
            [['Summarized sample',z,stats.norm.cdf(z),stats.norm.sf(z),b._pvalue(z,stats.norm,'two-sided'),stats.norm.ppf(confidence),stats.norm.ppf((1+confidence)/2)]])],
        notes=['Summarized-data mode uses aggregate inputs; no raw observations are inferred. The population variance is supplied, not estimated.'])


def repeated_box(x,columns,b):
    """Native 1108 compound-symmetry report, not a multi-group Box M test."""
    n,k=x.shape;sample=np.cov(x,rowvar=False,ddof=1)
    offdiag=float(np.triu(sample,1).sum())/(2*(k*k-1))
    assumed=np.full((k,k),offdiag);np.fill_diagonal(assumed,np.trace(sample)/k)
    sign_s,log_s=np.linalg.slogdet(sample);sign_h,log_h=np.linalg.slogdet(assumed)
    rows=[['Sample covariance determinant',float(np.linalg.det(sample))],
          ['Assumed covariance determinant',float(np.linalg.det(assumed))]]
    valid=sign_s>0 and sign_h>0 and np.linalg.matrix_rank(sample)==k
    if valid:
        m=(n*k-1)*(log_h-log_s)
        correction=k*(k+1)**2*(2*k-3)/(6*(k*k+k-4)*(k-1)*(n-1))
        chi=(1-correction)*m;df=(k*k+k-4)//2
        p=1. if chi<=0 else 0. if chi<=.01 or chi>=1000 else 1-stats.chi2.cdf(chi,df)
        rows.extend([['M',m],['Correction factor',correction],['Chi-square',chi],['df',df],['p-value',p]])
    else:
        rows.extend([['M',None],['Chi-square',None],['df',(k*k+k-4)//2],['p-value',None]])
    tables=[b._table('Box’s M Test For Homogeneity',['Metric','Value'],rows),
            b._table('Sample variance-covariance matrix',['Variable']+columns,[[c]+list(sample[i]) for i,c in enumerate(columns)]),
            b._table('Assumed population variance-covariance matrix',['Variable']+columns,[[c]+list(assumed[i]) for i,c in enumerate(columns)])]
    note='Compatibility behavior: the native 1108 Box report uses off-diagonal covariance sum / [2(k²−1)] and multiplies the log determinant ratio by Nk−1. These differ from a conventional compound-symmetry likelihood test; the source-specific construction is reproduced. Native positive chi-square ≤ .01 displays p=0.'
    warning=None if valid else 'Box homogeneity test is unavailable because a covariance matrix is singular or has nonpositive determinant.'
    return tables,note,warning
