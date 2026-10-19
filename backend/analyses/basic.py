"""Core statistical analyses for the StatWorkbench catalog."""
from __future__ import annotations

import itertools
import math
import warnings
import numpy as np
import pandas as pd
from scipy import stats, linalg
from scipy.cluster import hierarchy
from scipy.spatial.distance import pdist
import statsmodels.api as sm
import statsmodels.formula.api as smf
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.diagnostic import lilliefors
from statsmodels.stats.contingency_tables import cochrans_q
from sklearn.cluster import KMeans
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from . import doe, basic_options, basic_model_options, basic_help_reports
from .basic_native_models import NativeDummy, NativeOrthogonal


from .basic_catalog import _DOE_IDS, _META, catalog


_QUANTILES = ['inverted_cdf', 'averaged_inverted_cdf', 'closest_observation', 'interpolated_inverted_cdf', 'hazen', 'weibull', 'linear', 'median_unbiased', 'normal_unbiased']


def _frame(data):
    cols = data.get('columns', [])
    if not isinstance(cols, list) or not cols or any(not isinstance(c, str) or not c for c in cols) or len(set(cols)) != len(cols):
        raise ValueError('Dataset needs unique, nonempty column names.')
    rows = data.get('rows', [])
    if any(not isinstance(r, list) or len(r) != len(cols) for r in rows):
        raise ValueError('Every row must match the column count.')
    return pd.DataFrame(rows, columns=cols).replace(r'^\s*$', np.nan, regex=True)


def _names(frame, opt, key='columns', minimum=1):
    names = opt.get(key, [])
    if isinstance(names, str):
        names = [names]
    if not isinstance(names, list) or len(names) < minimum or len(set(names)) != len(names):
        raise ValueError(f'Select at least {minimum} distinct column(s) for {key}.')
    if any(c not in frame.columns for c in names):
        raise ValueError(f'Unknown column in {key}.')
    return names


def _name(frame, opt, key='column'):
    return _names(frame, {key: opt.get(key, [])}, key)[0]


def _numeric(frame, names):
    out = frame[names].copy()
    for c in names:
        values = pd.to_numeric(out[c], errors='coerce')
        bad = out[c].notna() & values.isna()
        if bad.any():
            raise ValueError(f'Column "{c}" has nonnumeric values; choose numeric variables.')
        if np.isinf(values.astype(float)).any():
            raise ValueError(f'Column "{c}" contains infinity.')
        out[c] = values.astype(float)
    return out


def _complete(frame, names, minimum=2):
    out = _numeric(frame, names).dropna()
    if len(out) < minimum:
        raise ValueError(f'At least {minimum} complete observations are required.')
    return out


def _vector(frame, name, minimum=2):
    return _complete(frame, [name], minimum)[name].to_numpy()


def _num(opt, key, default=None, minimum=None, maximum=None, integer=False):
    val = opt.get(key, default)
    if isinstance(val, bool):
        raise ValueError(f'{key} must be a number, not a boolean.')
    try:
        val = float(val)
    except (ValueError, TypeError):
        raise ValueError(f'{key} must be a number.') from None
    if not np.isfinite(val) or (minimum is not None and val < minimum) or (maximum is not None and val > maximum):
        raise ValueError(f'{key} is outside its allowed range.')
    if integer:
        if val != int(val):
            raise ValueError(f'{key} must be an integer.')
        return int(val)
    return val


def _conf(opt):
    return _num(opt, 'confidence', .95, .001, .999999)


def _alt(opt):
    alt = opt.get('alternative', 'two-sided')
    if alt not in ('less', 'greater', 'two-sided'):
        raise ValueError('Alternative must be less, greater or two-sided.')
    return alt


def _pvalue(stat, dist, alternative):
    if alternative == 'less':
        return float(dist.cdf(stat))
    if alternative == 'greater':
        return float(dist.sf(stat))
    return float(min(1., 2 * min(dist.cdf(stat), dist.sf(stat))))


def _table(title, columns, rows):
    return dict(title=title, columns=columns, rows=rows)


def _df_table(title, frame, index='Term'):
    return _table(title, [index] + list(frame.columns), [[str(k)] + list(row) for k, row in frame.iterrows()])


def _result(id, tables=(), charts=(), notes=(), warnings_=(), dataset=None):
    result = dict(analysis=id, title=_META[id]['name'], tables=list(tables), charts=list(charts),
                  notes=list(notes), warnings=list(warnings_))
    if dataset is not None:
        result['dataset'] = dataset
    return result


def _groups(frame, opt, minimum=2, minimum_groups=2):
    val, group = _name(frame, opt), _name(frame, opt, 'group')
    if val == group:
        raise ValueError('Value and group must be distinct columns.')
    values = _numeric(frame, [val])
    keep = values[val].notna() & frame[group].notna()
    groups = [(str(label), part[val].to_numpy()) for label, part in values.loc[keep].groupby(frame.loc[keep, group], sort=False)]
    if len({label for label, _ in groups}) != len(groups):
        raise ValueError('Group labels collide when represented as text; use distinct labels.')
    if len(groups) < minimum_groups or any(len(x) < minimum for _, x in groups):
        raise ValueError(f'At least {minimum_groups} group(s) with {minimum} observations each are required.')
    return groups


def _hist(x, bins, closed):
    if bins == 1 or bins == 2:
        raise ValueError('Use at least 3 bins or 0 for automatic bins.')
    if bins > 10000:
        raise ValueError('At most 10000 bins are allowed.')
    edges = np.histogram_bin_edges(x, bins=max(3,int(np.ceil(1+np.log2(len(x))))) if not bins else bins)
    indices = np.searchsorted(edges, x, side='right' if closed == 'left' else 'left') - 1
    indices = np.clip(indices, 0, len(edges) - 2)
    counts = np.bincount(indices, minlength=len(edges)-1)
    return counts, edges


def _anova_table(fit, typ=2):
    if fit.df_resid <= 0 or np.linalg.matrix_rank(fit.model.exog) < fit.model.exog.shape[1]:
        raise ValueError('ANOVA design must be estimable with positive residual degrees of freedom.')
    return _df_table('ANOVA', anova_lm(fit, typ=typ))


def _fit_summary(id, fit, names, index, response, opt, extra=()):
    ci = np.asarray(fit.conf_int(alpha=1-_conf(opt)))
    rows = [[name, float(np.asarray(fit.params)[i]), float(np.asarray(fit.bse)[i]), float(np.asarray(fit.tvalues)[i]), float(np.asarray(fit.pvalues)[i]), float(ci[i, 0]), float(ci[i, 1])] for i, name in enumerate(names)]
    summary = [['N', fit.nobs], ['R²', fit.rsquared], ['Adjusted R²', fit.rsquared_adj], ['Residual df', fit.df_resid], ['Residual standard error', np.sqrt(fit.mse_resid)], ['F', fit.fvalue], ['F p-value', fit.f_pvalue], ['AIC', fit.aic], ['BIC', fit.bic]]
    diag = [[int(i)+1, y, pred, res] for i, y, pred, res in zip(index, response, fit.fittedvalues, fit.resid)]
    result = _result(id, [_table('Model summary', ['Metric', 'Value'], summary), _table('Coefficients', ['Term', 'Estimate', 'SE', 't', 'p-value', 'CI lower', 'CI upper'], rows), _table('Fitted values and residuals', ['Source row', 'Observed', 'Fitted', 'Residual'], diag)] + list(extra),
       [dict(type='scatter', title='Residuals vs fitted', xLabel='Fitted', yLabel='Residual', series=[dict(name='Residuals', x=list(fit.fittedvalues), y=list(fit.resid))])],
       ['Complete-case deletion for all model variables. Confidence intervals are two-sided.'])
    if id in ('1301','1302','1303','1304','1305','1307','1310'):
        result=basic_help_reports.regression_tables(fit,names,opt,result,__import__(__name__,fromlist=['']))
    return basic_model_options.regression_report(id,fit,names,index,response,opt,result,__import__(__name__,fromlist=['']))


def analyze(analysis_id, data, options=None):
    aid = str(analysis_id)
    if aid not in _META:
        raise ValueError('Unknown analysis ID: ' + aid)
    opt = basic_model_options.normalize(aid,options or {})
    if aid in _DOE_IDS:
        return doe.analyze(aid, data, opt)
    if _META[aid]['coverage'] == 'unsupported':
        raise ValueError(_META[aid]['limitations'][0])
    scalar_table=aid=='1401' and all(f'sta.nps.2x2.param.{i}' in opt for i in range(4))
    summary_z=aid=='1004' and opt.get('help.z.input_mode')=='summary'
    frame = _frame(data) if aid != '10052' and not scalar_table and not summary_z else pd.DataFrame()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        if aid in ('1012','1013','1015'):
            result=basic_options.frequencies(aid,frame,opt,__import__(__name__,fromlist=['']))
        elif aid in ('1014','1401','1411'):
            result=basic_options.contingency(aid,frame,opt,__import__(__name__,fromlist=['']))
        elif aid=='1310':
            result=basic_model_options.curves(frame,opt,__import__(__name__,fromlist=['']))
        elif aid in ('1104','1105'):
            result=basic_model_options.factorial(aid,frame,opt,__import__(__name__,fromlist=['']))
        elif aid=='1109':
            result=basic_model_options.glm(frame,opt,__import__(__name__,fromlist=['']))
        else:
            result = _dispatch(aid, frame, opt)
            result=basic_options.enhance(aid,frame,opt,result,__import__(__name__,fromlist=['']))
            result=basic_model_options.model_extras(aid,frame,opt,result,__import__(__name__,fromlist=['']))
            if aid in ('1102','1103'):
                result=basic_model_options.one_way(aid,frame,opt,result,__import__(__name__,fromlist=['']))
    result['warnings'].extend(dict.fromkeys(str(w.message) for w in caught))
    return result


# Logical statistic order and the live native six-column wide report. None marks
# a spacer; all numerical definitions have explicit finite-sample domains.
_DESC_LEFT = ['Count', 'Mean', 'Mean LCL', 'Mean UCL', 'Variance', 'Standard Deviation',
    'Mean Standard Error', 'Coefficient of Variation', None, 'Minimum', 'Maximum',
    'Range', None, 'Median', 'Median Error', 'Percentile 25% (Q1)', 'Percentile 75% (Q3)',
    'IQR', 'MAD (Median Absolute Deviation)', 'Coefficient of Dispersion (COD)']
_DESC_LEFT.insert(4,'Trimmed Mean (5%)')
_DESC_RIGHT = ['Mean Deviation', 'Second Moment', 'Third Moment', 'Fourth Moment', None,
    'Sum', 'Sum Standard Error', 'Total Sum Squares', 'Adjusted Sum Squares', None,
    'Geometric Mean', 'Harmonic Mean', 'Mode', None, 'Skewness', 'Skewness Standard Error',
    'Kurtosis', 'Kurtosis Standard Error', "Skewness (Fisher's)", "Kurtosis (Fisher's)"]
_DESC_WIDE = [
    ['Count',None,None], ['Mean','Mean Standard Error',None], ['Mean LCL','Mean UCL',None],
    ['Trimmed Mean (5%)','Geometric Mean','Harmonic Mean'], ['Median','Median Error','Mode'],
    [None,None,None], ['Standard Deviation','Variance','Coefficient of Variation'],
    ['Range','Minimum','Maximum'], ['IQR','Percentile 25% (Q1)','Percentile 75% (Q3)'],
    ['Mean Deviation','MAD (Median Absolute Deviation)','Coefficient of Dispersion (COD)'],
    [None,None,None], ['Sum','Sum Standard Error',None], ['Total Sum Squares','Adjusted Sum Squares',None],
    ['Second Moment','Third Moment','Fourth Moment'], [None,None,None],
    ["Skewness (Fisher's)",'Skewness','Skewness Standard Error'],
    ["Kurtosis (Fisher's)",'Kurtosis','Kurtosis Standard Error'],
]


def _desc_flag(opt, key):
    value = opt.get(key, False)
    if isinstance(value, bool):
        return value
    if value in ('true', 'false'):
        return value == 'true'
    raise ValueError(f'{key} must be true or false.')


def _descriptive(aid, frame, opt):
    groups = _groups(frame, opt, 1, 1) if aid == '1002' else [(c, _vector(frame, c, 1)) for c in _names(frame, opt)]
    # Preserve the old numerical API alias while making source keys authoritative.
    q = _num(opt, 'sta.percentile.def', 6, 0, 8, True) + 1 if 'sta.percentile.def' in opt else _num(opt, 'quantile', 7, 1, 9, True)
    report = _num(opt, 'sta.bst.ds.report', 2, 0, 2, True)
    order = _num(opt, 'vars.ui.sortby', 0, 0, 4, True)
    histogram = _desc_flag(opt, 'sta.bst.ds.ao.0')
    overlay = _desc_flag(opt, 'sta.bst.ds.ao.1')
    qq = _desc_flag(opt, 'sta.chart.qq')
    bins = _num(opt, 'sta.bst.ds.ao.2', 0, 0, 10000, True)
    if bins in (1, 2):
        raise ValueError('Number of intervals must be 0 (automatic) or at least 3.')
    if order in (1, 2):
        groups = sorted(groups, key=lambda item:item[0].casefold(), reverse=order==2)
    elif order in (3, 4):
        groups = sorted(groups, key=lambda item:float(np.mean(item[1])), reverse=order==4)
    conf = _conf(opt)
    summaries, charts, notes, warning_list, conventional_mad = [], [], [], [], []
    for label, x in groups:
        n, mean = len(x), float(np.mean(x))
        deviation = x - mean
        moments = [float(np.mean(deviation**k)) for k in (2, 3, 4)]
        sd = float(np.std(x, ddof=1)) if n > 1 else None
        se = sd / np.sqrt(n) if sd is not None else None
        margin = float(stats.t.ppf((1+conf)/2, n-1)*se) if n > 1 else None
        q1, median, q3 = [float(v) for v in np.quantile(x, [.25, .5, .75], method=_QUANTILES[q-1])]
        values, counts = np.unique(x, return_counts=True)
        modes = values[counts==max(counts)]
        reciprocal_sum = float(np.sum(1/x)) if np.all(x != 0) else None
        geometric = float(np.exp(np.mean(np.log(x)))) if np.all(x > 0) else (0. if np.all(x >= 0) else None)
        harmonic = n/reciprocal_sum if reciprocal_sum not in (None, 0.) else None
        # Native compatibility: the deviation buffer is not sorted again before
        # type-7 interpolation at p=.5; preserve this observable report quirk.
        absolute_deviation = np.abs(x-median)
        native_mad = float((absolute_deviation[(n-1)//2]+absolute_deviation[n//2])/2)
        conventional_mad.append(dict(variable=label, value=float(np.median(np.abs(x-np.median(x))))))
        ordered=np.sort(x);trim=.05*n
        retained=np.maximum(0,np.minimum(np.arange(1,n+1),n-trim)-np.maximum(np.arange(n),trim))
        summary = {
            'Count':n, 'Mean':mean, 'Mean LCL':mean-margin if margin is not None else None,
            'Mean UCL':mean+margin if margin is not None else None, 'Variance':sd**2 if sd is not None else None,
            'Trimmed Mean (5%)':float(np.sum(ordered*retained)/np.sum(retained)) if n>=3 else None,
            'Standard Deviation':sd, 'Mean Standard Error':se,
            'Coefficient of Variation':sd/mean if sd is not None and mean != 0 else None,
            'Minimum':float(np.min(x)), 'Maximum':float(np.max(x)), 'Range':float(np.ptp(x)),
            'Median':median,
            'Median Error':np.sqrt(np.pi/2)*sd/n if sd is not None else None,
            'Percentile 25% (Q1)':q1, 'Percentile 75% (Q3)':q3, 'IQR':q3-q1,
            'MAD (Median Absolute Deviation)':native_mad,
            'Coefficient of Dispersion (COD)':float(np.mean(absolute_deviation))/abs(median) if median != 0 else None,
            'Mean Deviation':float(np.mean(np.abs(deviation))),
            'Second Moment':moments[0], 'Third Moment':moments[1], 'Fourth Moment':moments[2],
            'Sum':float(np.sum(x)), 'Sum Standard Error':sd*np.sqrt(n) if sd is not None else None,
            'Total Sum Squares':float(np.sum(x*x)), 'Adjusted Sum Squares':float(np.sum(deviation**2)),
            'Geometric Mean':geometric, 'Harmonic Mean':harmonic,
            'Mode':float(modes[0]) if len(modes)==1 else None,
            'Skewness':moments[1]/moments[0]**1.5 if moments[0]>0 else None,
            'Skewness Standard Error':np.sqrt(6*(n-1)/((n+1)*(n+3))) if n>=2 else None,
            'Kurtosis':moments[2]/moments[0]**2 if moments[0]>0 else None,
            'Kurtosis Standard Error':np.sqrt(24*n*(n-2)*(n-3)/((n+3)*(n+5)))/(n-1) if n>=4 else None,
            "Skewness (Fisher's)":float(stats.skew(x, bias=False)) if n>2 and moments[0]>0 else None,
            "Kurtosis (Fisher's)":float(stats.kurtosis(x, fisher=True, bias=False)) if n>3 and moments[0]>0 else None,
        }
        summaries.append((label, summary))
        if histogram and sd is not None and sd>=1e-7:
            from .native_histogram import descriptive_histogram
            counts, edges = descriptive_histogram(x, bins)
            centers=(edges[:-1]+edges[1:])/2
            series=[dict(name=label,type='histogram',x=list(centers),y=list(counts),color='#386D9E',barWidth=95,opacity=1)]
            if overlay:
                if sd is not None and sd>0:
                    curve_x=np.linspace(edges[0],edges[-1],31)
                    curve_y=stats.norm.pdf(curve_x,loc=mean,scale=sd)*n*(edges[1]-edges[0])
                    series.append(dict(name='Expected Normal',type='spline',x=list(curve_x),y=list(curve_y),color='#9F386D',width=2.25,splineTension=.7,markers={'visible':False}))
                else:
                    warning_list.append(f'{label}: normal overlay omitted because a positive sample standard deviation is required.')
            peak=max(float(max(s['y'])) for s in series)
            chart=dict(type='histogram',title=f'Histogram for "{label}"',variable=label,
                xLabel='',yLabel='No. of obs.',binEdges=list(edges),series=series,legend=False,
                xTicks=[dict(value=float(center),label=(f'{edges[j]:g} To {edges[j+1]:g}' if j<len(centers)-1 else f'{edges[j]:g} and over')) for j,center in enumerate(centers)],
                yMin=0.,yMax=float(math.ceil(peak*1.1)))
            from .native_chart_axes import nice_range
            chart['yMajorUnit']=nice_range(chart['yMin'],chart['yMax'],fixed=True)[2]
            if overlay:chart.update(xMin=float(edges[0]),xMax=float(edges[-1]))
            charts.append(chart)
        elif histogram:
            warning_list.append(f'{label}: the native descriptive histogram is omitted when sample SD is below 1e-7 or undefined.')
        if qq:
            if n>=2 and sd is not None and sd>0:
                from .advanced_charts import qq as normal_qq
                scratch=_result(aid)
                normal_qq(scratch,label,x,'4011',{'sta.qq.detrended.show':False})
                chart=scratch['charts'][0];chart.update(title=f'Normal Q-Q Plot - {label}',variable=label,xLabel='',yLabel='Expected Value',legend=False)
                chart['series'][0].update(name='Q-Q',color='#386D9E',markers={'visible':True,'style':'nofill','radius':4},width=2.25)
                for reference in chart['series'][1:]:reference.update(name='Reference line',color='#000000',width=2.25,markers={'visible':False})
                from .native_chart_axes import descriptive_qq_axes
                chart.update(descriptive_qq_axes(chart['series'][0]['x'],chart['series'][0]['y']))
                # Draw the reference below the hollow markers without changing
                # the numerical series order used by result consumers.
                chart['series'][0]['layer']=1
                charts.append(chart)
            else:
                warning_list.append(f'{label}: Q-Q plot omitted because at least two nonconstant observations are required.')
    all_metrics=[m for m in _DESC_LEFT+_DESC_RIGHT if m is not None]
    if report==1:
        tables=[_table('Descriptive Statistics',['Statistic']+[label for label,_ in summaries],
            [[metric]+[summary[metric] for _,summary in summaries] for metric in all_metrics])]
        tables[0]['layout']={'kind':'combined','freezeFirstColumn':True}
    else:
        tables=[]
        for label,summary in summaries:
            if report==0:
                tab=_table(label,['Statistic','Value'],[[metric,summary[metric]] for metric in all_metrics])
            else:
                native_labels={'Count':'N','MAD (Median Absolute Deviation)':'Median Absolute Deviation',
                    'Coefficient of Dispersion (COD)':'Coefficient of Dispersion',"Skewness (Fisher's)":"Fisher's Skewness G1",
                    "Kurtosis (Fisher's)":"Fisher's Kurtosis G2",'Mean LCL':f'Mean LCL {100*conf:g}%','Mean UCL':f'Mean UCL {100*conf:g}%'}
                tab=_table(label,['Statistic','Value','Statistic (continued)','Value (continued)','Statistic (continued 2)','Value (continued 2)'],[
                    list(itertools.chain.from_iterable((native_labels.get(metric,metric) if metric else '',summary[metric] if metric else None) for metric in row))
                    for row in _DESC_WIDE])
                fmt=lambda value:f'{value:.5f}'.rstrip('0').rstrip('.')
                tab['displayTitle']=f'{label} ({fmt(summary["Mean"])}±{fmt(summary["Standard Deviation"])})' if summary['Standard Deviation'] is not None else label
            tab['layout']={'kind':'separate_two_columns' if report==0 else 'separate_wide','variable':label}
            if report==2:tab['layout']['hideColumnHeaders']=True
            tables.append(tab)
    notes.extend([
        f'Missing values excluded separately. Sample variance uses N−1; percentiles use Hyndman–Fan type {q}; mean CI is {100*conf:g}% Student t.',
        'Blank cells denote undefined statistics. A nonunique mode is blank. Geometric mean requires nonnegative observations; harmonic mean requires nonzero observations and a nonzero reciprocal sum.',
        'Skewness and kurtosis use population central moments; Fisher values use finite-sample bias corrections and excess kurtosis. Median Error is sqrt(pi/2) × sample SD / N. Skewness and kurtosis standard errors require N≥2 and N≥4, respectively.',
    ])
    if histogram:
        notes.append('Descriptive histogram bins use ceil(1 + log2(N)) followed by a 1/2/5 width policy; the final bin includes the upper tail. The normal overlay has 31 points and is a fitted density scaled by N × bin width.')
    if qq:
        notes.append('Q-Q plots use average tied ranks, Blom positions, fitted-normal quantiles using sample mean/SD, and an identity reference line between fitted 1% and 99% quantiles.')
    warning_list.append('The MAD report column interpolates the middle absolute deviations in source order without sorting. This value is order-sensitive and differs from the conventional median absolute deviation, which is also reported in the notes and conventionalMAD metadata.')
    notes.append('Conventional median absolute deviation (sorted absolute deviations): '+ '; '.join(f'{item["variable"]} = {item["value"]:.15g}' for item in conventional_mad)+'.')
    result=_result(aid,tables,charts,notes,warning_list)
    result['layout']={'report':report,'variableOrder':[label for label,_ in summaries]}
    result['unavailableStatistics']=[]
    result['conventionalMAD']=conventional_mad
    return result


def _dispatch(aid, frame, opt):
    if aid in ('1001', '1002'):
        return _descriptive(aid, frame, opt)
    if aid in ('1003', '1004', '1005', '1007', '10052', '10053'):
        if aid=='1004' and opt.get('help.z.input_mode')=='summary':
            return basic_help_reports.summarized_z(opt,__import__(__name__,fromlist=['']))
        return basic_help_reports.mean_report(aid,frame,opt,_mean_tests(aid, frame, opt),__import__(__name__,fromlist=['']))
    if aid == '1008':
        return basic_help_reports.variance_test(frame,opt,__import__(__name__,fromlist=['']))
    if aid in ('1009', '1010', '1016', '1404', '1405'):
        return _correlations(aid, frame, opt)
    if aid == '1011':
        return basic_help_reports.normality(frame,opt,__import__(__name__,fromlist=['']))
    if aid in ('1012','1013','1015'):
        return basic_options.frequencies(aid,frame,opt,__import__(__name__,fromlist=['']))
    if aid in ('1014','1401','1411'):
        return basic_options.contingency(aid,frame,opt,__import__(__name__,fromlist=['']))
    if aid in ('1102', '1103'):
        groups = _groups(frame, opt) if aid == '1103' else [(c, _vector(frame, c)) for c in _names(frame, opt, minimum=2)]
        allv = np.concatenate([x for _, x in groups])
        grand = np.mean(allv)
        ssb = sum(len(x)*(np.mean(x)-grand)**2 for _, x in groups)
        sse = sum(np.sum((x-np.mean(x))**2) for _, x in groups)
        dfb, dfe = len(groups)-1, len(allv)-len(groups)
        if sse <= 0:
            raise ValueError('Within-group variance must be positive.')
        f = ssb/dfb/(sse/dfe)
        tables = [_table('ANOVA', ['Source', 'Sum of squares', 'df', 'Mean square', 'F', 'p-value'],
            [['Between groups', ssb, dfb, ssb/dfb, f, stats.f.sf(f, dfb, dfe)], ['Residual', sse, dfe, sse/dfe, None, None], ['Total', ssb+sse, dfb+dfe, None, None, None]]),
            _table('Group summaries', ['Group', 'N', 'Mean', 'SD'], [[g, len(x), np.mean(x), np.std(x, ddof=1)] for g, x in groups])]
        return _result(aid, tables, notes=['Independent groups; equal-variance normal-errors model. Missing values removed within groups.'])
    if aid in ('1104', '1105', '1109'):
        return _factor_model(aid, frame, opt)
    if aid in ('1106', '1107', '1108'):
        return _repeated(aid, frame, opt)
    if aid in ('1110', '1120', '1121', '1130', '1132'):
        return _multivariate(aid, frame, opt)
    if aid == '1320':
        from .advanced import residual_diagnostics
        return residual_diagnostics({'columns': list(frame.columns), 'rows': frame.values.tolist()}, opt)
    if aid in ('1301', '1302', '1303', '1304', '1305', '1306', '1307', '1310'):
        return _regression(aid, frame, opt)
    if aid.startswith('14'):
        return _nonparametric(aid, frame, opt)
    raise ValueError('No implementation for ' + aid)


def _mean_tests(aid, frame, opt):
    confidence, alternative = _conf(opt), _alt(opt)
    diff0 = _num(opt, 'difference', 0)
    rows = []
    if aid in ('1003', '1004'):
        mu = _num(opt, 'mean', 0)
        cols = _names(frame, opt) if aid == '1003' else [_name(frame, opt)]
        constants=[mu]*len(cols)
        if aid=='1003' and opt.get('TTEST_OS_CONST') not in (None,''):
            supplied=opt['TTEST_OS_CONST']
            if isinstance(supplied,str) and supplied in frame:
                values=_vector(frame,supplied,1)
                if len(np.unique(values))==1:constants=[float(values[0])]*len(cols)
                elif len(values)==len(cols):constants=list(values)
                else:raise ValueError('The hypothesized-value range must contain one value per selected variable.')
            else:constants=[_num({'constant':supplied},'constant')]*len(cols)
        for c,mu in zip(cols,constants):
            x = _vector(frame, c)
            var = _num(opt, 'variance', minimum=0) if aid == '1004' else np.var(x, ddof=1)
            if var <= 0:
                raise ValueError('Variance must be positive for inference.')
            se = math.sqrt(var/len(x))
            dist = stats.norm if aid == '1004' else stats.t(len(x)-1)
            z = (np.mean(x)-mu)/se
            margin = dist.ppf((1+confidence)/2)*se
            rows.append([c, len(x), np.mean(x), mu, se, z, None if aid == '1004' else len(x)-1, _pvalue(z, dist, alternative), np.mean(x)-margin, np.mean(x)+margin])
        return _result(aid, [_table('Mean tests', ['Variable', 'N', 'Mean', 'Hypothesized mean', 'SE', 'Statistic', 'df', 'p-value', 'Mean CI lower', 'Mean CI upper'], rows)], notes=['Missing values removed per column. Confidence intervals are two-sided, regardless of test alternative.'])
    ttype = opt.get('test_type', 'pooled')
    if ttype not in ('pooled', 'welch', 'paired') or (aid != '1005' and ttype == 'paired'):
        raise ValueError('Choose a supported t-test type.')
    if aid == '10052':
        n1, n2 = [_num(opt, k, minimum=2, integer=True) for k in ('n1', 'n2')]
        m1, m2 = [_num(opt, k) for k in ('mean1', 'mean2')]
        s1, s2 = [_num(opt, k, minimum=0) for k in ('sd1', 'sd2')]
        label = 'Sample1 − Sample2'
    else:
        if aid == '10053':
            groups = basic_options.group_selection(_groups(frame, opt,1,1),opt)
            if len(groups) != 2:
                raise ValueError('Exactly two groups are required.')
            (a,x), (b,y) = groups
        else:
            a, b = _name(frame, opt, 'x'), _name(frame, opt, 'y')
            if a == b:
                raise ValueError('Select two different variables.')
            if ttype == 'paired' and aid == '1005':
                vals = _complete(frame, [a, b])
                x, y = vals[a].to_numpy(), vals[b].to_numpy()
            else:
                x, y = _vector(frame, a), _vector(frame, b)
        n1, n2, m1, m2, s1, s2 = len(x), len(y), np.mean(x), np.mean(y), np.std(x, ddof=1), np.std(y, ddof=1)
        label = f'{a} − {b}'
    effect = m1-m2
    if aid == '1007':
        v1 = _num(opt, 'variance_x', minimum=0)
        v2 = _num(opt, 'variance_y', minimum=0)
        se, df, dist = math.sqrt(v1/n1+v2/n2), None, stats.norm
    elif ttype == 'paired':
        se, df = stats.sem(x-y), n1-1
        dist = stats.t(df)
    elif ttype == 'pooled':
        df = n1+n2-2
        se = math.sqrt(((n1-1)*s1*s1+(n2-1)*s2*s2)/df*(1/n1+1/n2))
        dist = stats.t(df)
    else:
        v1, v2 = s1*s1/n1, s2*s2/n2
        se = math.sqrt(v1+v2)
        if se <= 0:
            raise ValueError('Both samples have zero variance; a t-test is undefined.')
        df = (v1+v2)**2/(v1*v1/(n1-1)+v2*v2/(n2-1))
        dist = stats.t(df)
    if se <= 0:
        raise ValueError('The standard error is zero; this test is undefined.')
    stat = (effect-diff0)/se
    margin = dist.ppf((1+confidence)/2)*se
    return _result(aid, [_table('Difference of means', ['Comparison', 'N1', 'N2', 'Mean1', 'Mean2', 'Difference', 'Hypothesized difference', 'SE', 'Statistic', 'df', 'p-value', 'CI lower', 'CI upper'],
        [[label,n1,n2,m1,m2,effect,diff0,se,stat,df,_pvalue(stat,dist,alternative),effect-margin,effect+margin]])], notes=[('Paired complete-case deletion.' if ttype == 'paired' else 'Missing values removed independently within samples.'), 'Confidence interval is two-sided and applies to the unshifted population mean difference.'])


def _correlations(aid, frame, opt):
    cols = _names(frame, opt, minimum=2)
    if aid == '1010':
        numeric = _numeric(frame, cols)
        if opt.get('missing','pairwise')=='casewise':numeric=numeric.dropna()
        cov = numeric.cov(min_periods=2)
        return _result(aid, [_df_table('Sample covariance', cov, 'Variable')], notes=[opt.get('missing','pairwise').title()+' deletion; N−1 denominator. Undefined covariance appears blank.'])
    controls = _names(frame, opt, 'controls') if aid == '1016' else []
    if set(cols) & set(controls):
        raise ValueError('Control covariates must differ from the variables being correlated.')
    alt = 'two-sided' if aid in ('1009','1016') and 'sta.tail.h' in opt else _alt(opt)
    rows = []
    base = _numeric(frame, cols+controls)
    if opt.get('missing', 'pairwise') == 'casewise':
        base = base.dropna()
    rank_details=[]
    for a, b in itertools.combinations(cols, 2):
        clean = base[[a, b]+controls].dropna()
        n = len(clean)
        if n < (1 if aid=='1405' else len(controls)+3):
            raise ValueError(f'Too few complete observations for {a} and {b}.')
        x, y = clean[a].to_numpy(), clean[b].to_numpy()
        if aid!='1405' and (np.ptp(x) == 0 or np.ptp(y) == 0):
            raise ValueError(f'Correlation is undefined for a constant variable: {a}, {b}.')
        if aid == '1016':
            cov = sm.add_constant(clean[controls].to_numpy(), has_constant='add')
            rank = np.linalg.matrix_rank(cov)
            if rank != cov.shape[1]:
                raise ValueError('Control covariates are constant or linearly dependent.')
            x = x-cov@np.linalg.lstsq(cov, x, rcond=None)[0]
            y = y-cov@np.linalg.lstsq(cov, y, rcond=None)[0]
            if np.linalg.norm(x) < 1e-12 or np.linalg.norm(y) < 1e-12:
                raise ValueError('A variable is perfectly explained by the controls; partial correlation is undefined.')
            r = np.clip(np.corrcoef(x,y)[0,1], -1., 1.)
            df = n-len(controls)-2
            t = r*math.sqrt(df/max(1e-300, 1-r*r))
            rows.append([a,b,'Partial Pearson',n,r,_pvalue(t,stats.t(df),alt)])
        elif aid == '1009':
            s = stats.pearsonr(x, y, alternative=alt)
            rows.append([a,b,'Pearson',n,s.statistic,s.pvalue])
        elif aid == '1404':
            s = stats.spearmanr(x,y,alternative=alt)
            t = stats.kendalltau(x,y,alternative=alt)
            concordant = discordant = 0
            if n > 20000:
                raise ValueError('Gamma pair counting is limited to 20000 observations.')
            for i in range(n-1):
                prod = np.sign(x[i+1:]-x[i])*np.sign(y[i+1:]-y[i])
                concordant += int(np.sum(prod > 0))
                discordant += int(np.sum(prod < 0))
            gamma = (concordant-discordant)/(concordant+discordant) if concordant+discordant else np.nan
            pearson=stats.pearsonr(x,y,alternative=alt)
            rows.extend([[a,b,'Spearman',n,s.statistic,s.pvalue],[a,b,'Kendall tau-b',n,t.statistic,t.pvalue],[a,b,'Goodman–Kruskal gamma',n,gamma,None],[a,b,'Pearson',n,pearson.statistic,pearson.pvalue]])
            rho=float(s.statistic);spearman_t=rho*math.sqrt((n-2)/max(np.finfo(float).tiny,1-rho*rho))
            # The help explicitly prints this no-tie normal transform; retain
            # the tie-corrected Kendall inference in the main result table.
            kendall_z=float(t.statistic)/math.sqrt(2*(2*n+5)/(9*n*(n-1)))
            rank_details.append([a,b,concordant,discordant,n*(n-1)//2-concordant-discordant,spearman_t,n-2,kendall_z,_pvalue(kendall_z,stats.norm,alt)])
        else:
            matches = np.sign(x-np.mean(x)) == np.sign(y-np.mean(y))
            rows.append([a,b,'Fechner',n,2*float(np.mean(matches))-1,None])
    result=_result(aid, [_table('Correlations', ['Variable1', 'Variable2', 'Method', 'N', 'Coefficient', 'p-value'], rows)], notes=['Pairwise complete-case deletion unless casewise explicitly selected. Gamma/Fechner are descriptive coefficients without a p-value.'])
    if rank_details:
        result['tables'].append(_table('Rank-correlation diagnostics',['Variable1','Variable2','Concordant pairs','Inversions (discordant pairs)','Pairs tied in either variable','Spearman t','Spearman df','Kendall Z (help formula)','Kendall normal p (help formula)'],rank_details))
        result['notes'].append('Kendall Z uses the transform printed in the help; the main Kendall p-value retains tie correction and exact inference where available. The normal approximation is intended for N > 10.')
    return result


def _factor_model(aid, frame, opt):
    response = _name(frame, opt, 'response')
    factors = _names(frame, opt, 'factors') if aid != '1109' else _names(frame, opt, 'factors', 0)
    predictors = _names(frame, opt, 'predictors', 0) if aid == '1109' else []
    counts = {'1104':2, '1105':3}
    if aid in counts and len(factors) != counts[aid]:
        raise ValueError(f'This design requires exactly {counts[aid]} factors.')
    if not factors and not predictors:
        raise ValueError('Select at least one fixed factor or numeric covariate.')
    names = [response]+factors+predictors
    if len(set(names)) != len(names):
        raise ValueError('Response, factors and covariates must be distinct columns.')
    clean = _numeric(frame, [response]+predictors)
    for f in factors:
        clean[f] = frame[f]
    clean = clean.dropna()
    if len(clean) < 3:
        raise ValueError('At least three complete observations are required.')
    for f in factors:
        if clean[f].nunique() < 2:
            raise ValueError(f'Factor {f} needs at least two levels.')
    d = pd.DataFrame({'y':clean[response]})
    for i, f in enumerate(factors):
        d[f'f{i}'] = clean[f].astype(str)
    for i, x in enumerate(predictors):
        d[f'x{i}'] = clean[x]
    coding = opt.get('coding', 'Treatment') if aid == '1109' else 'Sum'
    if coding not in ('Treatment', 'Sum', 'Helmert','NativeDummy','NativeOrthogonal'):
        raise ValueError('Unsupported factor contrast coding.')
    terms = [f'C(f{i}, {coding})' for i in range(len(factors))]
    interactions = bool(opt.get('interactions', aid in ('1104','1105')))
    expr = (' * ' if interactions else ' + ').join(terms)
    expr = ' + '.join(([expr] if expr else [])+[f'x{i}' for i in range(len(predictors))])
    fit = smf.ols('y ~ ' + expr, data=d).fit()
    typ = _num(opt, 'ss_type', 2, 2, 3, True)
    table = _anova_table(fit, typ)
    mapping = [(f'f{i}', f) for i,f in enumerate(factors)] + [(f'x{i}', x) for i,x in enumerate(predictors)]
    if aid == '1109':
        result = _fit_summary(aid, fit, list(fit.params.index), clean.index, clean[response], opt, [table])
    else:
        result = _result(aid, [table])
    result['tables'].append(_table('Model variables', ['Model code','Dataset column'], mapping))
    result['notes'].extend([f'Type {typ} sums of squares; fixed factors only. Complete-case deletion.', 'Model formula: ' + expr])
    return result


def _repeated(aid, frame, opt):
    cols = _names(frame,opt,minimum=2)
    factors = [] if aid == '1108' else ([_name(frame,opt,'group')] if aid == '1106' else _names(frame,opt,'factors',2))
    if aid == '1107' and len(factors) != 2:
        raise ValueError('Mixed ANOVA with two treatments needs exactly two between-subject factors.')
    if set(cols)&set(factors):
        raise ValueError('Repeated measurements and factor columns must differ.')
    clean = _numeric(frame,cols)
    for f in factors:
        clean[f]=frame[f]
    clean = clean.dropna()
    n,k = len(clean),len(cols)
    if n < 3:
        raise ValueError('Repeated-measures inference needs at least three complete subjects.')
    x = clean[cols].to_numpy()
    if not factors:
        means = x.mean(axis=0)
        ss = n*np.sum((means-x.mean())**2)
        residuals = x-x.mean(axis=1,keepdims=True)-means+x.mean()
        sse = np.sum(residuals**2)
        df1,df2 = k-1,(n-1)*(k-1)
        if sse <= np.finfo(float).eps:
            raise ValueError('Within-subject residual variance is zero; repeated-measures inference is undefined.')
        f = ss/df1/(sse/df2)
        p = stats.f.sf(f,df1,df2)
        centered = np.eye(k)-np.ones((k,k))/k
        s = centered @ np.cov(x,rowvar=False,ddof=1) @ centered
        epsilon = float(np.trace(s)**2/((k-1)*np.trace(s@s)))
        epsilon = np.clip(epsilon,1/(k-1),1)
        subjects_ss=k*np.sum((x.mean(axis=1)-x.mean())**2)
        result=_result(aid, [_table('Repeated measures ANOVA', ['Effect','SS','df1','df2','F','p-value','Mean square'],
            [['Within factor',ss,df1,df2,f,p,ss/df1],['Greenhouse–Geisser corrected',ss,df1*epsilon,df2*epsilon,f,stats.f.sf(f,df1*epsilon,df2*epsilon),ss/(df1*epsilon)]]),
            _table('ANOVA decomposition',['Source','SS','df','Mean square','F','p-value'],[
                ['Subjects',subjects_ss,n-1,subjects_ss/(n-1),None,None],
                ['Treatments',ss,df1,ss/df1,f,p],['Error',sse,df2,sse/df2,None,None],
                ['Total',subjects_ss+ss+sse,n*k-1,None,None,None]]),
            basic_options.descriptive_table(clean,cols,__import__(__name__,fromlist=['']),'Treatment descriptive statistics'),
            _table('Diagnostics',['Metric','Value'],[['Subjects',n],['Repeated levels',k],['Residual SS',sse],['Greenhouse–Geisser epsilon',epsilon]])], notes=['One subject per original row; incomplete subjects removed. The corrected test rescales degrees of freedom, not F.'])
        tables,note,warning=basic_help_reports.repeated_box(x,cols,__import__(__name__,fromlist=['']))
        result['tables'].extend(tables);result['notes'].append(note)
        if warning:result['warnings'].append(warning)
        return result
    d=pd.DataFrame(index=clean.index)
    for i,c in enumerate(factors):
        d[f'f{i}']=clean[c].astype(str)
    if any(d[c].nunique()<2 for c in d.columns):
        raise ValueError('Each between-subject factor needs at least two levels.')
    sizes=d.groupby(list(d.columns),observed=True).size()
    cells=math.prod(d[c].nunique() for c in d.columns)
    if len(sizes)!=cells or sizes.nunique()!=1 or sizes.min()<2:
        raise ValueError('Mixed ANOVA requires a fully crossed design with equal cell sizes and at least two subjects per cell.')
    expr=' * '.join(f'C(f{i}, Sum)' for i in range(len(factors)))
    d['z']=x.mean(axis=1)
    fit=smf.ols('z ~ '+expr,data=d).fit()
    a=anova_lm(fit,typ=2)
    rows=[]
    error_ss=float(a.loc['Residual','sum_sq'])*k
    error_df=float(a.loc['Residual','df'])
    if error_ss <= 0:
        raise ValueError('Between-subject residual variance is zero.')
    for term,row in a.drop('Residual').iterrows():
        ss=float(row['sum_sq'])*k
        df=float(row['df'])
        f=(ss/df)/(error_ss/error_df)
        rows.append([term,ss,df,error_df,f,stats.f.sf(f,df,error_df)])
    rows.append(['Subjects within between-subject cells',error_ss,error_df,None,None,None])
    scores=x@linalg.helmert(k,full=False).T
    within_ss=n*np.sum(scores.mean(axis=0)**2)
    interaction_ss={term:0. for term in a.index if term!='Residual'}
    residual_ss=0.
    for j in range(k-1):
        d['z']=scores[:,j]
        test=anova_lm(smf.ols('z ~ '+expr,data=d).fit(),typ=2)
        residual_ss+=test.loc['Residual','sum_sq']
        for term in interaction_ss:
            interaction_ss[term]+=test.loc[term,'sum_sq']
    residual_df=(n-cells)*(k-1)
    if residual_ss <= 0:
        raise ValueError('Within-subject residual variance is zero.')
    def within_row(term,ss,df):
        f=(ss/df)/(residual_ss/residual_df)
        return [term,ss,df,residual_df,f,stats.f.sf(f,df,residual_df)]
    rows.append(within_row('Within factor',within_ss,k-1))
    for term,ss in interaction_ss.items():
        rows.append(within_row(term+' × Within',ss,float(a.loc[term,'df'])*(k-1)))
    rows.append(['Within residual',residual_ss,residual_df,None,None,None])
    for row in rows:row.append(row[1]/row[2])
    rows.append(['Total',float(np.sum((x-x.mean())**2)),n*k-1,None,None,None,None])
    desc=[]
    for labels,part in clean.groupby(factors,sort=False,observed=True):
        labels=list(labels) if isinstance(labels,tuple) else [labels]
        for col in cols:desc.append(labels+[col,len(part),part[col].mean(),part[col].std(ddof=1)])
    return _result(aid,[_table('Balanced mixed ANOVA',['Effect','SS','df1','Denominator df','F','p-value','Mean square'],rows),
        _table('Treatment descriptive statistics',factors+['Repeated level','N','Mean','SD'],desc),
        _table('Factor mapping',['Code','Dataset column'],[[f'f{i}',c] for i,c in enumerate(factors)])],
        notes=['Complete-subject deletion; balanced fixed-factor between-subject design. Within tests assume sphericity. Each row represents one independent subject.'])


def _orthomax(loadings,gamma):
    from .basic_native_models import rotate_orthomax
    return rotate_orthomax(loadings,gamma)


def _multivariate(aid,frame,opt):
    cols=_names(frame,opt,minimum=1 if aid=='1132' else 2)
    data=_numeric(frame,cols)
    if aid=='1110':
        group=_name(frame,opt,'group')
        if group in cols:
            raise ValueError('The group label cannot also be a predictor.')
        data=data.loc[frame[group].notna()]
    data=data.dropna()
    if len(data)<3:
        raise ValueError('At least three complete rows are required.')
    x=data[cols].to_numpy()
    if (np.std(x,axis=0,ddof=1)==0).any():
        raise ValueError('Remove constant variables before multivariate analysis.')
    if aid=='1130':return basic_model_options.kmeans(frame,data,cols,x,opt,__import__(__name__,fromlist=['']))
    if aid=='1132':return basic_model_options.hierarchical(frame,data,cols,x,opt,__import__(__name__,fromlist=['']))
    if aid in ('1120','1121'):
        centered=x-x.mean(axis=0)
        matrix=opt.get('matrix','correlation')
        if matrix not in ('correlation','covariance'):
            raise ValueError('PCA matrix must be correlation or covariance.')
        z=centered/np.std(x,axis=0,ddof=1) if matrix=='correlation' else centered
        eig,vec=np.linalg.eigh(np.cov(z,rowvar=False,ddof=1))
        eig,vec=eig[::-1].clip(min=0),vec[:,::-1]
        # Deterministic component sign; PCA signs carry no substantive meaning.
        for j in range(vec.shape[1]):
            if vec[np.argmax(np.abs(vec[:,j])),j]<0:
                vec[:,j]*=-1
        prefix=str(opt.get('sta.mv.pca.pcprefix','PC'))
        if not prefix.strip() or len(prefix)>80:raise ValueError('Component prefix must contain 1–80 characters.')
        labels=[f'{prefix}{i+1}' for i in range(len(cols))]
        tables=[_table('Eigenvalues',['Component','Eigenvalue','Variance fraction','Cumulative fraction'],[[labels[i],e,e/eig.sum(),eig[:i+1].sum()/eig.sum()] for i,e in enumerate(eig)])]
        charts=[dict(type='line',title='Scree plot',xLabel='Component',yLabel='Eigenvalue',series=[dict(name='Eigenvalue',x=list(range(1,len(eig)+1)),y=list(eig))])]
        if aid=='1120':
            load=vec*np.sqrt(eig)
            scores=z@vec
            tables.extend([_table('Component coefficients',['Variable']+labels,[[c]+list(v) for c,v in zip(cols,vec)]),
              _table('Loadings',['Variable']+labels,[[c]+list(v) for c,v in zip(cols,load)]),
              _table('Scores',['Source row']+labels,[[int(i)+1]+list(v) for i,v in zip(data.index,scores)])])
        else:
            threshold=_num(opt,'threshold',1,0)
            if opt.get('retention','eigenvalue')=='count':
                nf=_num(opt,'threshold',1,1,len(cols),True)
            else:
                nf=int(np.sum(eig>threshold))
            if nf<1:
                raise ValueError('No factors meet the retention threshold; lower X or request an exact count.')
            load=vec[:,:nf]*np.sqrt(eig[:nf])
            rotation=opt.get('rotation','none')
            if rotation not in ('none','varimax','quartimax','biquartimax','equamax','orthomax'):
                raise ValueError('Unsupported factor rotation.')
            gamma={'varimax':1.,'quartimax':0.,'biquartimax':.5,'equamax':len(cols)/2,'none':0.}.get(rotation,_num(opt,'gamma',0,0))
            if matrix=='covariance':load=load/np.std(x,axis=0,ddof=1)[:,None]
            rotated=load if rotation=='none' else _orthomax(load,gamma)[0]
            headers=['Variable']+[f'Factor{i+1}' for i in range(nf)]
            tables.extend([_table('Initial component-factor loadings',headers,[[c]+list(v) for c,v in zip(cols,load)]),
              _table('Rotated loadings',headers,[[c]+list(v) for c,v in zip(cols,rotated)]),
              _table('Communalities',['Variable','Communality'],[[c,float(np.sum(row*row))] for c,row in zip(cols,rotated)])])
        result=_result(aid,tables,charts,['Complete-case deletion. Components are ordered by descending eigenvalue; component signs are arbitrary. Principal-component extraction is not common-factor maximum likelihood.'])
        return basic_model_options.spectral_report(aid,cols,eig,load,load if aid=='1120' else rotated,opt,result,__import__(__name__,fromlist=['']))
    if aid=='1110':
        y=frame.loc[data.index,group].astype(str).to_numpy()
        classes,counts=np.unique(y,return_counts=True)
        if len(classes)<2 or np.min(counts)<2 or len(x)<=len(classes):
            raise ValueError('LDA requires at least two groups and at least two observations per group.')
        priors=np.ones(len(classes))/len(classes) if opt.get('priors','empirical')=='equal' else None
        lda=LinearDiscriminantAnalysis(priors=priors,solver='svd').fit(x,y)
        pred=lda.predict(x)
        tables=[_table('Class means',['Class']+cols,[[g]+list(row) for g,row in zip(lda.classes_,lda.means_)]),
                _table('Classification coefficients',['Class']+cols+['Intercept'],[[g]+list(row)+[b] for g,row,b in zip(lda.classes_[1:] if len(classes)==2 else lda.classes_,lda.coef_,lda.intercept_)]),
                _table('Training classification',['Source row','Actual','Predicted'],[[int(i)+1,a,p] for i,a,p in zip(data.index,y,pred)]),
                _table('Accuracy',['Evaluation','Accuracy'],[['Training (optimistic)',float(np.mean(y==pred))]])]
        if opt.get('cross_validate',False):
            if len(y)>2000:
                raise ValueError('Leave-one-out validation is limited to 2000 observations.')
            cv=cross_val_predict(LinearDiscriminantAnalysis(priors=priors),x,y,cv=LeaveOneOut())
            tables[-1]['rows'].append(['Leave-one-out',float(np.mean(y==cv))])
        result=_result(aid,tables,notes=['Complete-case deletion; training accuracy does not estimate generalization performance.'])
        return basic_model_options.lda_report(frame,data,cols,x,y,lda,opt,result,__import__(__name__,fromlist=['']))


def _regression(aid,frame,opt):
    response=_name(frame,opt,'response')
    predictors=[_name(frame,opt,'predictor')] if aid in ('1303','1310') else _names(frame,opt,'predictors')
    if response in predictors:
        raise ValueError('The response cannot also be a predictor.')
    names=[response]+predictors
    if aid=='1302':
        weight_name=_name(frame,opt,'weights')
        if weight_name in names:
            raise ValueError('Weights must be in a separate column.')
        names.append(weight_name)
    categorical=_names(frame,opt,'help.logit.categorical',0) if aid=='1306' else []
    if set(categorical)-set(predictors):raise ValueError('Categorical predictors must also be selected among the independent variables.')
    if categorical:
        clean=_numeric(frame,[c for c in names if c not in categorical])
        clean[categorical]=frame[categorical];clean=clean.dropna()
        if len(clean)<3:raise ValueError('At least three complete observations are required.')
    else:clean=_complete(frame,names,3)
    y=clean[response].to_numpy()
    encoding=[];design_columns=[];labels=[]
    for col in predictors:
        if col in categorical:
            values=clean[col].astype(str);levels=sorted(values.unique())
            if not 2<=len(levels)<=100:raise ValueError('Categorical predictors require 2–100 observed levels.')
            encoding.append([col,levels[-1],', '.join(levels[:-1])])
            for level in levels[:-1]:design_columns.append((values==level).to_numpy(dtype=float));labels.append(col+'['+level+']')
        else:design_columns.append(clean[col].to_numpy(dtype=float));labels.append(col)
    x=np.column_stack(design_columns)
    intercept=bool(opt.get('intercept',True))
    if aid=='1303':
        degree=_num(opt,'degree',2,1,10,True)
        x=np.column_stack([x[:,0]**i for i in range(1,degree+1)])
        labels=[f'{predictors[0]}^{i}' for i in range(1,degree+1)]
    original_y=y.copy()
    transformed=False
    if aid=='1310':
        model=opt.get('model','linear')
        if model not in ('linear','quadratic','cubic','inverse','logarithmic','power','exponential','growth','compound','sigmoid','logistic'):
            raise ValueError('Unsupported curve model.')
        v=x[:,0]
        if model in ('quadratic','cubic'):
            degree=2 if model=='quadratic' else 3
            x=np.column_stack([v**i for i in range(1,degree+1)])
            labels=[f'{predictors[0]}^{i}' for i in range(1,degree+1)]
        if model in ('inverse','sigmoid'):
            if np.any(v==0):
                raise ValueError('Inverse/S-curve models require nonzero predictor values.')
            x=(1/v)[:,None]
            labels=['1/'+predictors[0]]
        if model in ('logarithmic','power'):
            if np.any(v<=0):
                raise ValueError('Logarithmic/power models require positive predictor values.')
            x=np.log(v)[:,None]
            labels=['log('+predictors[0]+')']
        if model in ('power','exponential','growth','compound','sigmoid'):
            if np.any(y<=0):
                raise ValueError('This transformed curve model requires a positive response.')
            y=np.log(y)
            transformed=True
        if model=='logistic':
            upper=_num(opt,'sta.reg.model.logistic.ub',100,minimum=np.finfo(float).tiny)
            if np.any(y<=0) or np.any(y>=upper):raise ValueError('Bounded logistic curve requires 0 < response < upper bound.')
            y=np.log(1/y-1/upper);transformed=True
    design=sm.add_constant(x,has_constant='add') if intercept else x
    labels=(['Intercept'] if intercept else [])+labels
    if len(y)<=design.shape[1] or np.linalg.matrix_rank(design)<design.shape[1]:
        raise ValueError('Regression requires more complete rows than coefficients and a full-rank design; remove constant or collinear predictors.')
    if aid=='1306':
        if set(np.unique(y))!={0.,1.}:
            raise ValueError('Binary logistic regression requires both 0 and 1 responses.')
        from statsmodels.tools.sm_exceptions import PerfectSeparationWarning, PerfectSeparationError
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',PerfectSeparationWarning)
                logit=sm.Logit(y,design);iterations=[]
                def record(parameters):iterations.append([len(iterations)+1,float(logit.loglike(parameters))]+list(parameters))
                fit=logit.fit(disp=False,maxiter=_num(opt,'sta.reg.max_iter',20,1,10000,True),callback=record)
        except (PerfectSeparationWarning,PerfectSeparationError,np.linalg.LinAlgError) as exc:
            raise ValueError('Logistic model is separated or singular; coefficients cannot be reliably estimated.') from exc
        if not fit.mle_retvals.get('converged',False) or not np.isfinite(fit.bse).all():
            raise ValueError('Logistic model did not converge; inspect separation and predictor scaling.')
        ci=np.asarray(fit.conf_int(alpha=1-_conf(opt)))
        rows=[[label,b,se,z,p,np.exp(b),np.exp(lo),np.exp(hi)] for label,b,se,z,p,(lo,hi) in zip(labels,fit.params,fit.bse,fit.tvalues,fit.pvalues,ci)]
        probability=fit.predict()
        result=_result(aid,[_table('Logit coefficients',['Term','Log-odds estimate','SE','z','p-value','Odds ratio','OR CI lower','OR CI upper'],rows),
           _table('Model summary',['Metric','Value'],[['N',len(y)],['Log likelihood',fit.llf],['McFadden pseudo-R²',fit.prsquared],['AIC',fit.aic],['Likelihood-ratio p-value',fit.llr_pvalue]]),
           _table('Fitted probabilities',['Source row','Observed','P(Y=1)'],[[int(i)+1,a,p] for i,a,p in zip(clean.index,y,probability)])],notes=['Complete-case deletion. Reference outcome is 0; modeled outcome is 1. Wald intervals assume a regular finite maximum-likelihood estimate.'])
        if basic_options.boolean(opt,'sta.reg.show_iter',True):result['tables'].append(_table('Logistic iterations',['Iteration','Log likelihood']+labels,iterations))
        if encoding:
            result['tables'].append(_table('Categorical predictor coding',['Predictor','Reference category','Indicator categories'],encoding))
            result['notes'].append('Categorical predictors use treatment indicators with the last sorted category as the reference.')
        return result
    extras=[]
    if aid in ('1304','1305','1307'):
        intercept=True
        def subset(indices):
            selected=x[:,indices] if indices else np.empty((len(y),0))
            return sm.OLS(y,sm.add_constant(selected,has_constant='add')).fit()
        history=[];step_summaries=[];step_models=[]
        if aid=='1307':
            criterion=opt.get('criterion','bic')
            if criterion not in ('bic','aic','adj_r2'):
                raise ValueError('Selection criterion must be BIC, AIC or adjusted R².')
            from .best_subsets import best_subsets
            winners,subset_search=best_subsets(x,y)
            candidates=[]
            for combo in winners:
                trial=subset(list(combo))
                score=-trial.rsquared_adj if criterion=='adj_r2' else getattr(trial,criterion)
                candidates.append((score,combo,trial))
            score,indices,fit=min(candidates,key=lambda row:row[0])
            best_by_size=[]
            previous_r2=0.
            for size in range(len(predictors)+1):
                _,combo,trial=min((row for row in candidates if len(row[1])==size),key=lambda row:row[0])
                best_by_size.append([size,', '.join(predictors[i] for i in combo) or '(intercept only)',max(0.,trial.rsquared_adj),trial.aic,trial.bic,trial.rsquared,trial.rsquared-previous_r2])
                previous_r2=trial.rsquared
                if size:step_models.append((f'Best subset with {size} predictors',list(combo),trial))
            extras.append(_table('Best model for each size',['Predictors','Variables','Adjusted R²','AIC','BIC','R²','R² increment'],best_by_size))
        else:
            alpha=_num(opt,'alpha',.05 if aid=='1304' else .10,.000001,.999999)
            indices=[] if aid=='1304' else list(range(len(predictors)))
            if basic_options.boolean(opt,'sta.reg.show_steps'):step_models.append(('Initial model',list(indices),subset(indices)))
            while True:
                if aid=='1304':
                    candidates=[]
                    for i in range(len(predictors)):
                        if i not in indices:
                            trial=subset(indices+[i])
                            candidates.append((float(trial.pvalues[-1]),i))
                    if not candidates:
                        break
                    p,i=min(candidates)
                    if not np.isfinite(p) or p>=alpha:
                        break
                    indices.append(i)
                    history.append([len(history)+1,'Add',predictors[i],p])
                else:
                    if not indices:
                        break
                    trial=subset(indices)
                    pv=np.asarray(trial.pvalues)[1:]
                    j=int(np.argmax(pv))
                    p=float(pv[j])
                    if not np.isfinite(p) or p<=alpha:
                        break
                    i=indices.pop(j)
                    history.append([len(history)+1,'Remove',predictors[i],p])
                current=subset(indices);step_summaries.append([len(history),', '.join(predictors[i] for i in indices),current.rsquared,current.rsquared_adj,current.aic,current.bic,current.f_pvalue])
                if basic_options.boolean(opt,'sta.reg.show_steps'):step_models.append((f'Step {len(history)}',list(indices),current))
            fit=subset(indices)
            extras.append(_table('Selection steps',['Step','Action','Variable','Partial p-value'],history))
            if basic_options.boolean(opt,'sta.reg.show_steps'):extras.append(_table('Model summary for each step',['Step','Predictors','R²','Adjusted R²','AIC','BIC','F p-value'],step_summaries))
        for title,selected,trial in step_models:
            report=_fit_summary(aid,trial,['Intercept']+[predictors[i] for i in selected],clean.index,y,opt)
            for tab in report['tables']:
                if tab['title']=='Fitted values and residuals':continue
                tab['title']=title+' — '+tab['title'];extras.append(tab)
        labels=['Intercept']+[predictors[i] for i in indices]
    elif aid=='1302':
        weights=clean[weight_name].to_numpy()
        if np.any(weights<=0):
            raise ValueError('WLS inverse-variance weights must be strictly positive.')
        weights=weights**_num(opt,'sta.reg.wpower',1)
        if not np.isfinite(weights).all() or np.any(weights<=0):raise ValueError('Raised weights must remain positive and finite.')
        fit=sm.WLS(y,design,weights=weights).fit()
    else:
        fit=sm.OLS(y,design).fit()
    result=_fit_summary(aid,fit,labels,clean.index,y,opt,extras)
    if aid=='1307':
        result['subsetSearch']=subset_search
        result['notes'].append('The exact subset search completed for every predictor count. Only winning models are retained; branch bounds do not substitute approximate models. Worst-case search time grows exponentially.')
    if aid=='1302':result['notes'].append(f'Weight transformation: {weight_name} ^ {_num(opt,"sta.reg.wpower",1):g}; weights are proportional to inverse observation variance.')
    if aid in ('1304','1305','1307'):
        result['warnings'].append('Model selection uses the same observations as inference. Reported p-values and intervals do not account for selection.')
    if aid=='1310':
        fitted=1/(1/upper+np.exp(fit.fittedvalues)) if model=='logistic' else np.exp(fit.fittedvalues) if transformed else fit.fittedvalues
        result['tables'].append(_table('Predictions on original response scale',['Source row','Observed','Predicted'],[[int(i)+1,a,p] for i,a,p in zip(clean.index,original_y,fitted)]))
        order=np.argsort(clean[predictors[0]].to_numpy())
        result['charts'].append(dict(type='scatter',title='Curve fit',xLabel=predictors[0],yLabel=response,series=[dict(name='Observed',x=list(clean[predictors[0]]),y=list(original_y)),dict(name='Fitted',type='line',x=list(clean[predictors[0]].to_numpy()[order]),y=list(np.asarray(fitted)[order]))]))
        if model=='logistic':
            result['notes'].append('Bounded logistic fit regresses log(1/Y − 1/upper) on X; predictions invert this transform. Coefficients and inference are on this transformed scale.')
        elif transformed:
            result['notes'].append('Coefficients, R², residuals and inference above are on log(response) scale. Original-scale predictions exponentiate fitted log values without bias correction.')
    return result


def _nonparametric(aid,frame,opt):
    if aid=='1403':
        cols=_names(frame,opt)
        numeric=_numeric(frame,cols).dropna()
        ties=opt.get('ties','average')
        if ties not in ('average','max','min','ordinal'):
            raise ValueError('Unsupported tie ranking method.')
        tables=[]
        derived=frame.copy()
        for col in cols:
            x=numeric[col].dropna()
            if len(x)<2:
                raise ValueError(f'At least two complete numeric observations are required in {col}.')
            ranks=stats.rankdata(x,method=ties)
            descending=len(x)+1-ranks if ties=='ordinal' else stats.rankdata(-x,method=ties)
            percentiles=(ranks-1)/(len(x)-1)
            report=_table(col,['Source row','Value','Rank','Percentile rank','Descending rank'],[[int(i)+1,v,r,p,rd] for i,v,r,p,rd in zip(x.index,x,ranks,percentiles,descending)])
            report['columnFormats']={'3':'0.00%'}
            tables.append(report)
            for suffix,values in [('Rank',ranks),('Percentile',percentiles),('Descending rank',descending)]:
                label=f'{col} {suffix}'
                while label in derived.columns:
                    label+=' (new)'
                derived[label]=np.nan
                derived.loc[x.index,label]=values
        return _result(aid,tables,notes=['Listwise deletion across selected variables. Excluded rows retain blank derived cells at their original positions. Percentile fraction = (assigned rank − 1)/(complete-case N − 1); the report formats this fraction as a percentage.'],
            dataset=dict(name='Ranked data',columns=list(derived.columns),rows=derived.where(pd.notna(derived),None).values.tolist()))
    if aid in ('1406','14063'):
        if aid=='14063':
            groups=basic_options.group_selection(_groups(frame,opt,1,1),opt)
            if len(groups)!=2:
                raise ValueError('Exactly two independent groups are required.')
            (a,x),(b,y)=groups
        else:
            a,b=_name(frame,opt,'x'),_name(frame,opt,'y')
            x,y=_vector(frame,a),_vector(frame,b)
        u_min,mw_tables=basic_help_reports.mann_whitney_report(x,y,[a,b])
        rows=[['Mann–Whitney U',u_min,None]]
        notes=['Independent missing-value deletion. The Mann–Whitney report shows normal and Student-t approximations, both with and without continuity correction. One-tailed probabilities use the smaller tail. No automatic exact/asymptotic selection rule is applied to this report. When uncorrected Z is zero, continuity-corrected cells are blank.']
        allv=np.concatenate([x,y])
        has_ties=len(np.unique(allv))!=len(allv)
        extension_method='exact' if min(len(x),len(y))<=8 and not has_ties else 'asymptotic'
        u=stats.mannwhitneyu(x,y,alternative=_alt(opt),method=extension_method)
        extension=_table('Additional Mann–Whitney inference (StatWorkbench extension)',
            ['Method','Alternative for first sample','First-sample U','p-value'],
            [[extension_method,_alt(opt),u.statistic,u.pvalue]])
        notes.append('This analysis uses exact inference when either sample has at most eight observations and there are no ties; otherwise it uses a tie- and continuity-corrected normal approximation. Directional alternatives apply only to this procedure.')
        ks=stats.ks_2samp(x,y,alternative='two-sided',method='auto')
        rows.append(['Kolmogorov–Smirnov D',ks.statistic,ks.pvalue])
        runs_report,runs_notes=basic_help_reports.runs_report(x,y)
        notes.extend(runs_notes)
        q,critical=basic_help_reports.rosenbaum(x,y,_conf(opt))
        notes.append('Rosenbaum reproduces native tail counting and tabulated critical values. A critical value is available only for both sample sizes 11–26 and confidence .95 or .99; no continuous p-value is fabricated.')
        return _result(aid,[_table(f'{a} versus {b}',['Test','Statistic','p-value'],rows),*mw_tables,runs_report,
            _table('Rosenbaum Q criterion',['N1','N2','Q','Critical value','Confidence'],[[len(x),len(y),q,critical,_conf(opt)]]),extension],notes=notes)
    if aid in ('1407','14072'):
        groups=_groups(frame,opt) if aid=='14072' else [(c,_vector(frame,c)) for c in _names(frame,opt,minimum=2)]
        arrays=[x for _,x in groups]
        if np.ptp(np.concatenate(arrays))==0:
            raise ValueError('All observations are identical; rank tests are undefined.')
        kw=stats.kruskal(*arrays)
        rows=[['Kruskal–Wallis',kw.statistic,len(groups)-1,kw.pvalue]]
        notes=['Independent missing-value deletion; Kruskal–Wallis applies tie correction. Mood median test assigns ties to the below-median group.']
        try:
            median=stats.median_test(*arrays,ties='below',correction=True)
            rows.append(['Mood median',median.statistic,len(groups)-1,median.pvalue])
        except ValueError:
            notes.append('Mood median test omitted: at least one expected cell is zero after median splitting.')
        return _result(aid,[_table('Independent-samples tests',['Test','Statistic','df','p-value'],rows)],notes=notes)
    if aid=='1408':
        a,b=_name(frame,opt,'x'),_name(frame,opt,'y')
        if a==b:
            raise ValueError('Select two distinct paired variables.')
        clean=_complete(frame,[a,b])
        dif=clean[a].to_numpy()-clean[b].to_numpy()
        nonzero=dif[dif!=0]
        pos=int(np.sum(nonzero>0))
        rows=[]
        if len(nonzero):
            w=stats.wilcoxon(dif,alternative=_alt(opt),zero_method='wilcox',method='auto')
            rows.append(['Wilcoxon signed rank',w.statistic,w.pvalue])
            sign=stats.binomtest(pos,len(nonzero),.5,alternative=_alt(opt))
            rows.append(['Exact sign test (positive differences)',pos,sign.pvalue])
            ranks=stats.rankdata(np.abs(nonzero));plus=float(ranks[nonzero>0].sum());minus=float(ranks[nonzero<0].sum())
            _,tie_counts=np.unique(np.abs(nonzero),return_counts=True)
            n=len(nonzero);variance=(n*(n+1)*(2*n+1)-np.sum(tie_counts**3-tie_counts)/2)/24
            z=(min(plus,minus)-n*(n+1)/4)/math.sqrt(variance)
            rows.append(['Wilcoxon Z (tie corrected, no continuity correction)',z,2*stats.norm.sf(abs(z))])
        else:
            rows.append(['Exact sign test (no nonzero differences)',0,1.])
        return _result(aid,[_table('Paired tests',['Test','Statistic','p-value'],rows)],notes=[f'Complete-pair deletion. {len(dif)-len(nonzero)} zero differences excluded; comparisons use {a} − {b}.', 'Wilcoxon is omitted if all differences are zero.'])
    if aid in ('1409','14092','1410'):
        if aid=='14092':
            val,grp=_name(frame,opt),_name(frame,opt,'group')
            sub=_name(frame,opt,'subject') if opt.get('subject') else None
            if val==grp or (sub is not None and len(set([val,grp,sub]))!=3):
                raise ValueError('Value, group and subject must be different columns.')
            clean=_numeric(frame,[val])
            clean[grp]=frame[grp]
            clean=clean.dropna(subset=[grp])
            clean=clean.loc[clean[grp].map(lambda value:not isinstance(value,str) or value not in ('','<null>'))]
            if sub is None:
                # Native mode 1 removes missing raw rows before grouping. A
                # later missing value therefore shifts its group's ordinal
                # pairing, rather than deleting a whole aligned subject.
                clean=clean.dropna(subset=[val])
                sub='__ordinal_subject__'
                while sub in frame:sub+='_' 
                clean[sub]=clean.groupby(grp,sort=False).cumcount()
            else:
                clean[sub]=frame[sub]
                clean=clean.dropna(subset=[sub])
            if clean.duplicated([grp,sub]).any():
                raise ValueError('Each subject/group pair must have exactly one observation.')
            pivot=clean.pivot(index=sub,columns=grp,values=val)
            x=pivot.dropna().to_numpy()
        else:
            minimum=3 if aid=='1410' else 2
            cols=_names(frame,opt,minimum=minimum)
            x=_complete(frame,cols,minimum).to_numpy()
        n,k=x.shape
        minimum=3 if aid=='1410' else 2
        if n<minimum or k<minimum:
            raise ValueError(f'At least {minimum} complete subjects and {minimum} related groups are required.')
        if aid=='1410':
            if not np.isin(x,[0,1]).all():
                raise ValueError('Cochran Q requires binary 0/1 observations.')
            if np.all(np.ptp(x,axis=1)==0):
                raise ValueError('Cochran Q is undefined when every subject has identical responses across treatments.')
            test=cochrans_q(x)
            proportions=_table('Proportions statistics',['Variable','Sum','Proportion: 0','Proportion: 1'],[[c,float(x[:,j].sum()),float(np.mean(x[:,j]==0)),float(np.mean(x[:,j]==1))] for j,c in enumerate(cols)])
            proportions['columnFormats']={'2':'0.00%','3':'0.00%'}
            return _result(aid,[_table('Cochran Q',['Subjects','Treatments','Q','df','p-value','Critical chi-square'],[[n,k,test.statistic,k-1,test.pvalue,stats.chi2.ppf(_conf(opt),k-1)]]),proportions],notes=['Complete-subject deletion. Chi-square asymptotic inference.'])
        if np.all(np.ptp(x,axis=1)==0):
            raise ValueError('Friedman test is undefined when every subject has all tied measurements.')
        # SciPy requires at least three groups; the inspected native routine
        # also accepts two. Compute the rank-sum definition for both cases.
        ranks=stats.rankdata(x,axis=1)
        tie_sum=sum(sum(count**3-count for count in np.unique(row,return_counts=True)[1]) for row in x)
        rank_ss=float(np.sum((ranks.sum(axis=0)-n*(k+1)/2)**2))
        denominator=(n*n*k*(k*k-1)-n*tie_sum)/12
        w=rank_ss/denominator
        statistic=n*(k-1)*w
        result=_result(aid,[_table('Friedman and concordance',['Subjects','Treatments','Chi-square','df','p-value','Kendall W'],[[n,k,statistic,k-1,stats.chi2.sf(statistic,k-1),w]])],notes=['Complete-subject deletion and within-subject tie correction. Chi-square approximation can be poor for small samples.'])
        if aid=='14092' and not opt.get('subject'):
            result['notes']=['Rows with missing values or groups are excluded before pairing observations by order within each group. Values beyond the shortest group are excluded. Within-subject ties are corrected; the chi-square approximation can be poor for small samples.']
        return result
    raise ValueError('Unknown nonparametric test: '+aid)
