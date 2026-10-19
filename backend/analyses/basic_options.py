"""Report, frequency, and table option definitions."""
from __future__ import annotations
import copy
import math
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.inter_rater import cohens_kappa
from statsmodels.stats.contingency_tables import mcnemar
from .basic_option_fields import FIELDS


def extend_catalog(entries):
    for entry in entries:
        aid=entry['id']
        if aid not in FIELDS:continue
        existing={f['key'] for f in entry['fields']}
        entry['fields'].extend(copy.deepcopy(f) for f in FIELDS[aid] if f['key'] not in existing)
        if aid in ('1009','1016'):
            entry['fields']=[f for f in entry['fields'] if f['key']!='alternative']
        if aid=='1003':
            entry['fields']=[f for f in entry['fields'] if f['key']!='mean']
            next(f for f in entry['fields'] if f['key']=='TTEST_OS_CONST')['required']=True
        if aid=='1401':
            entry['fields']=[f for f in entry['fields'] if f['key']!='columns']
            entry['description']='A/B/C/D 2×2 table analysis with rounding, table, exact-test, association and accuracy options.'
        if aid in ('10053','14063'):entry['limitations']=['Blank group codes select the first two observed groups; explicit codes select and order two groups.']
        if aid in ('1012','1013','1014','1015','1401','1411'):
            entry['limitations']=['Fractional-frequency handling is explicit.']
        if aid=='1011':entry['limitations'].append('Automatic histogram bin boundaries are approximate. Q-Q charts use average ranks, Blom plotting positions, and fitted-normal quantiles.')


def boolean(opt,key,default=False):
    value=opt.get(key,default)
    if isinstance(value,bool):return value
    if value in ('true','false'):return value=='true'
    raise ValueError(key+' must be true or false.')


def index(opt,key,default,upper):
    value=opt.get(key,str(default))
    if isinstance(value,bool):raise ValueError(key+' must be an option index.')
    try:n=float(value)
    except (ValueError,TypeError):raise ValueError(key+' must be an option index.') from None
    if not np.isfinite(n) or n!=int(n) or not 0<=n<=upper:raise ValueError(key+' is outside its allowed choices.')
    return int(n)


def group_selection(groups,opt):
    first,second=[str(opt.get(key,'')).strip() for key in ('GROUP.1','GROUP.2')]
    if not first and not second:
        if len(groups)<2:raise ValueError('At least two groups are required.')
        selected=groups[:2]
        if any(len(x)<2 for _,x in selected):raise ValueError('Each selected group needs at least two observations.')
        return selected
    if not first or not second or first==second:raise ValueError('Specify two distinct group codes, or leave both blank.')
    lookup=dict(groups)
    def resolve(code):
        if code in lookup:return code
        try:matches=[g for g in lookup if float(g)==float(code)]
        except ValueError:matches=[]
        if len(matches)!=1:raise ValueError('A selected group code is absent or ambiguous in the data.')
        return matches[0]
    first,second=resolve(first),resolve(second)
    if first==second:raise ValueError('Specify two distinct group codes.')
    if len(lookup[first])<2 or len(lookup[second])<2:raise ValueError('Each selected group needs at least two observations.')
    return [(first,lookup[first]),(second,lookup[second])]


def _optional_column(frame,opt,key):
    value=opt.get(key)
    if value in (None,''):return None
    if not isinstance(value,str) or value not in frame:raise ValueError('Choose a valid column for '+key+'.')
    return value


def _layers(frame,opt):
    layer=_optional_column(frame,opt,'sta.bst.freq.layervar')
    if layer is None:return [('',frame)]
    return [(f'{layer}={label}',part) for label,part in frame.loc[frame[layer].notna()].groupby(layer,sort=False)]


def _weighted(frame,opt,columns,b):
    weight=_optional_column(frame,opt,'sta.bst.freq.freqvar')
    keep=frame[columns].notna().all(axis=1)
    if weight:
        w=b._numeric(frame,[weight])[weight]
        keep &= w.notna()
    else:w=pd.Series(1.,index=frame.index)
    values=w.loc[keep].to_numpy(float)
    if (values<0).any():raise ValueError('Frequencies must be nonnegative.')
    return frame.loc[keep,columns],values


def _ordered_indices(labels,totals,mode):
    if mode==0:return np.arange(len(labels))
    if mode in (1,2):return np.argsort(totals if mode==1 else -totals,kind='stable')
    return np.asarray(sorted(range(len(labels)),key=lambda i:str(labels[i]).casefold(),reverse=mode==4))


def frequencies(aid,frame,opt,b):
    tables,charts=[],[]
    for layer,part in _layers(frame,opt):
        for col in b._names(frame,opt):
            selected,weights=_weighted(part,opt,[col],b)
            if not len(selected) or weights.sum()<=0:raise ValueError('No positive total frequency for '+col+'.')
            title=col+(' — '+layer if layer else '')
            percent_style=boolean(opt,'output.percenstyleforpercentages',True)
            scale=1 if percent_style else 100
            if aid=='1012':
                counts=pd.Series(weights,index=selected[col].astype(str)).groupby(level=0,sort=False).sum()
                try:category_order=sorted(counts.index,key=float)
                except ValueError:category_order=sorted(counts.index,key=lambda s:s.casefold())
                cumulative=counts.loc[category_order].cumsum()
                order=opt.get('order','asc');order={'count_asc':1,'count_desc':2,'asc':3,'desc':4}.get(order)
                if order is None:raise ValueError('Unknown category order.')
                if order in (3,4):counts=counts.loc[category_order if order==3 else category_order[::-1]]
                else:counts=counts.iloc[_ordered_indices(counts.index,counts.to_numpy(),order)]
                p=counts/counts.sum()*scale
                tab=b._table(title,['Category','Count','Cumulative count','Percent','Cumulative percent'],[[label,float(n),float(cumulative[label]),float(p[label]),float(cumulative[label]/counts.sum()*scale)] for label,n in counts.items()])
                if percent_style:tab['columnFormats']={'3':'0.00%','4':'0.00%'}
                tables.append(tab)
                bar=index(opt,'tables.plot.bar',1,2)
                if bar:charts.append(dict(type='bar',title=title,xLabel='Category',yLabel='Count' if bar==1 else 'Percent',series=[dict(name=col,x=list(counts.index),y=list(counts if bar==1 else counts/counts.sum()*100))]))
                continue
            numeric=b._numeric(selected,[col])[col].to_numpy()
            bins=b._num(opt,'bins',0,0,10000,True)
            if bins in (1,2):raise ValueError('Number of intervals must be zero or at least three.')
            closed=opt.get('closed','left')
            if closed not in ('left','right'):raise ValueError('Bin intervals must be left- or right-closed.')
            custom=_optional_column(frame,opt,'sta.bst.freq.bins_var') if aid=='1015' else None
            start_text=str(opt.get('sta.bst.freq.minval2','')).strip();width_text=str(opt.get('sta.bst.freq.width2','')).strip()
            if custom:
                edges=b._vector(frame,custom,2)
                if np.any(np.diff(edges)<=0):raise ValueError('Bin boundaries must be strictly increasing.')
                below=np.any(numeric<edges[0]) or (closed=='right' and np.any(numeric==edges[0]))
                above=np.any(numeric>edges[-1]) or (closed=='left' and np.any(numeric==edges[-1]))
                boundaries=np.concatenate(([-np.inf] if below else [],edges,[np.inf] if above else []))
            elif start_text or width_text:
                if not start_text or not width_text:raise ValueError('Specify both start value and interval width.')
                start=b._num({'v':start_text},'v');width=b._num({'v':width_text},'v',minimum=np.finfo(float).tiny)
                count=bins or max(3,int(np.ceil((numeric.max()-start)/width)))
                if count>10000:raise ValueError('At most 10000 bins are supported.')
                edges=start+np.arange(count+1)*width
                below=np.any(numeric<edges[0]) or (closed=='right' and np.any(numeric==edges[0]))
                above=np.any(numeric>edges[-1]) or (closed=='left' and np.any(numeric==edges[-1]))
                boundaries=np.concatenate(([-np.inf] if below else [],edges,[np.inf] if above else []))
            else:
                from .native_histogram import frequency_edges
                edges=frequency_edges(numeric,bins,closed,histogram=aid=='1015')
                boundaries=edges
            location=np.searchsorted(boundaries,numeric,side='right' if closed=='left' else 'left')-1
            location=np.clip(location,0,len(boundaries)-2)
            counts=np.bincount(location,weights=weights,minlength=len(boundaries)-1)
            cumulative=np.cumsum(counts);total=counts.sum()
            ids=np.arange(len(counts))
            if boolean(opt,'sta.bst.ds.hist.bins0',True):ids=ids[counts[ids]!=0]
            if aid=='1015' and boolean(opt,'sta.bst.pareto'):ids=ids[np.argsort(-counts[ids],kind='stable')]
            labels=[];rows=[]
            for i in ids:
                low,high=boundaries[i:i+2]
                label=f'Up to {high:g}' if np.isneginf(low) else f'More than {low:g}' if np.isposinf(high) else f'{low:g}–{high:g}'
                labels.append(label);rows.append([None if np.isneginf(low) else float(low),None if np.isposinf(high) else float(high),float(counts[i]),float(cumulative[i]),float(counts[i]/total*scale),float(cumulative[i]/total*scale)])
            tab=b._table(title,['Lower boundary','Upper boundary','Count','Cumulative count','Percent','Cumulative percent'],rows)
            if percent_style:tab['columnFormats']={'4':'0.00%','5':'0.00%'}
            tables.append(tab)
            if aid=='1015' or boolean(opt,'sta.bst.ds.ao.0'):
                charts.append(dict(type='bar',title=title,xLabel='Interval',yLabel='Count',series=[dict(name=col,x=labels,y=list(counts[ids]))]))
    return b._result(aid,tables,charts,notes=['Complete rows for each input, frequency and break variable; frequencies are summed without expanding rows. Percent-style cells contain fractions. Automatic interval counts use floor(1 + log2(valid row count)), followed by a 1/2/5 width rule with normalized thresholds 1.4, 2.8 and 7. An endpoint equal to the open outer boundary causes a 1% range expansion and recomputation. Cumulative frequencies retain ascending-value meaning when output is reordered.'])


def _round_half_away(x):return np.floor(np.asarray(x)+.5)


def contingency(aid,frame,opt,b):
    result=b._result(aid)
    for layer,part in _layers(frame,opt) if aid=='1014' else [('',frame)]:
        mode=index(opt,'tables.freq.nonint.2x2' if aid=='1401' else 'tables.freq.nonint',0,4 if aid=='1014' else 2)
        if aid=='1014':
            row,col=b._name(frame,opt,'row'),b._name(frame,opt)
            if row==col:raise ValueError('Select two different categorical columns.')
            clean,w=_weighted(part,opt,[row,col],b)
            if mode<2:w=np.trunc(w) if mode==0 else _round_half_away(w)
            labels_r=list(pd.unique(clean[row].astype(str)));labels_c=list(pd.unique(clean[col].astype(str)))
            mat=pd.DataFrame(0.,index=labels_r,columns=labels_c)
            for (r,c),n in zip(clean.astype(str).itertuples(index=False,name=None),w):mat.loc[r,c]+=n
            if mode in (2,3):mat[:]=np.trunc(mat) if mode==2 else _round_half_away(mat)
        elif aid=='1401' and all(f'sta.nps.2x2.param.{i}' in opt for i in range(4)):
            values=[b._num(opt,f'sta.nps.2x2.param.{i}',minimum=0) for i in range(4)]
            mat=pd.DataFrame(np.asarray(values).reshape(2,2),index=['Positive','Negative'],columns=['Positive','Negative'])
        else:
            mat=b._numeric(part,b._names(part,opt,minimum=2))
            labels=_optional_column(part,opt,'tables.rowlabels') if aid=='1411' else None
            if labels:
                if part[labels].isna().any():raise ValueError('Row labels cannot be missing.')
                mat.index=part[labels].astype(str)
        original=mat.to_numpy(float)
        if not np.isfinite(original).all() or (original<0).any():raise ValueError('Frequencies must be finite and nonnegative before rounding or truncation.')
        if aid!='1014' and mode<2:mat[:]=np.trunc(mat) if mode==0 else _round_half_away(mat)
        x=mat.to_numpy(float)
        if x.ndim!=2 or min(x.shape)<2 or not np.isfinite(x).all() or (x<0).any():raise ValueError('Tables require at least 2 rows/columns of finite nonnegative counts.')
        if aid=='1401' and x.shape!=(2,2):raise ValueError('A 2×2 table is required.')
        if (x.sum(axis=0)==0).any() or (x.sum(axis=1)==0).any():raise ValueError('Every row and column must have a positive total after frequency conversion.')
        rorder=index(opt,'tables.order.row',3 if aid=='1014' else 0,4 if aid=='1014' else 2)
        corder=index(opt,'tables.order.column',3 if aid=='1014' else 0,4 if aid=='1014' else 2)
        mat=mat.iloc[_ordered_indices(mat.index,x.sum(axis=1),rorder),_ordered_indices(mat.columns,x.sum(axis=0),corder)];x=mat.to_numpy(float)
        part_result=_table_report(aid,mat,x,opt,b)
        for tab in part_result['tables']:
            if layer:tab['title']+=' — '+layer
        for chart in part_result['charts']:
            if layer:chart['title']+=' — '+layer
        for key in ('tables','charts','notes','warnings'):result[key].extend(part_result[key])
    return result


def _table_report(aid,mat,x,opt,b):
    total=x.sum();expected=np.outer(x.sum(axis=1),x.sum(axis=0))/total
    plain=float(np.sum((x-expected)**2/expected));df=(len(x)-1)*(x.shape[1]-1)
    tables=[];charts=[];notes=[];warn=[]
    pct=boolean(opt,'tables.ui.2x2.percentage' if aid=='1401' else 'tables.ui.tables.percentage',True)
    exp=boolean(opt,'tables.ui.2x2.expected' if aid=='1401' else 'sta.chi.exp_freq',True)
    crosstab=aid in ('1014','1411')
    residuals=boolean(opt,'tables.ui.tables.residuals')
    mode=index(opt,'sta.chi.table_combined',2 if aid=='1401' else 1,3)
    combined=mode in (1,3)
    # The inspected 2x2 crosstab renderer has no individual-table branch.
    individual=mode in (2,3) and not (crosstab and x.shape==(2,2))
    if crosstab and x.shape==(2,2) and mode in (2,3):
        notes.append('Individual count, expected-frequency, and percentage tables are unavailable for 2×2 crosstabs. Use Combined tables to display them.')
    bar=index(opt,'tables.plot.bar',1,3)
    if crosstab and not (mode or residuals or boolean(opt,'sta.nps.chi.tests',True)
            or boolean(opt,'tables.measures',True) or boolean(opt,'tables.ui.kappaopt',True)
            or bar or boolean(opt,'tables.plot.interaction',True)):
        raise ValueError('Select at least one table, statistic, or plot; the report would be empty.')
    metrics=[('Observed counts',x)]
    if exp:metrics.append(('Expected counts',expected))
    if pct:metrics.extend([('Row percent',x/x.sum(axis=1)[:,None]),('Column percent',x/x.sum(axis=0)[None,:]),('Total percent',x/total)])
    if residuals and not crosstab:metrics.extend([('Residuals',x-expected),('Standardized residuals',(x-expected)/np.sqrt(expected)),('Chi-square contributions',(x-expected)**2/expected)])
    style=boolean(opt,'output.percenstyleforpercentages',True)
    row_labels=[str(label) for label in mat.index]
    column_labels=[str(c) for c in mat.columns]
    if crosstab:
        # Native tables include margins before computing percentage denominators.
        # Summing displayed column percentages would give incorrect row margins.
        augmented=np.vstack([np.column_stack([x,x.sum(axis=1)]),np.r_[x.sum(axis=0),total]])
        expanded_expected=np.vstack([np.column_stack([expected,x.sum(axis=1)]),np.r_[x.sum(axis=0),total]])
        metrics=[('Observed counts',augmented)]
        if exp:metrics.append(('Expected counts',expanded_expected))
        if pct:metrics.extend([('Row percent',augmented/augmented[:,-1,None]),('Column percent',augmented/augmented[-1,None,:]),('Total percent',augmented/total)])
        row_labels.append('Column totals');column_labels.append('Row totals')
    if combined:
        rows=[]
        percent_rows=[]
        if crosstab:
            labels={'Expected counts':'Expected','Row percent':'% within row','Column percent':'% within column','Total percent':'% of total'}
            for i,label in enumerate(row_labels):
                for title,values in metrics:
                    if 'percent' in title:percent_rows.append(len(rows))
                    rows.append([label if title=='Observed counts' else labels[title]]+list(values[i]*(100 if 'percent' in title and not style else 1)))
            tab=b._table('Combined crosstab',['Row']+column_labels,rows)
        else:
            for title,values in metrics:
                for label,row in zip(row_labels,values):
                    if 'percent' in title:percent_rows.append(len(rows))
                    rows.append([label,title]+list(row*(100 if 'percent' in title and not style else 1)))
            tab=b._table('Combined crosstab',['Row','Measure']+column_labels,rows)
        if style:tab['rowFormats']={str(i):'0.00%' for i in percent_rows}
        tables.append(tab)
    if individual:
        for title,values in metrics:
            if crosstab and x.shape!=(2,2) and mode==3 and not (exp or pct) and title=='Observed counts':continue
            tab=b._table(title,['Row']+column_labels,[[label]+list(row*(100 if 'percent' in title and not style else 1)) for label,row in zip(row_labels,values)])
            if style and 'percent' in title:tab['columnFormats']={str(i):'0.00%' for i in range(1,len(tab['columns']))}
            tables.append(tab)
    if (combined or individual) and not crosstab:
        tables.append(b._table('Crosstab marginal totals',['Row']+[str(c) for c in mat.columns]+['Total'],
            [[str(label)]+list(row)+[float(row.sum())] for label,row in zip(mat.index,x)]+
            [['Total']+list(x.sum(axis=0))+[float(total)]]))
    if crosstab and residuals:
        raw=x-expected
        standardized=np.divide(raw,np.sqrt(expected),out=np.full_like(x,np.nan),where=expected>1e-12)
        row_complement=1-x.sum(axis=1)[:,None]/total
        column_complement=1-x.sum(axis=0)[None,:]/total
        valid=(expected>1e-12)&(row_complement>1e-12)&(column_complement>1e-12)
        adjusted=np.divide(standardized,np.sqrt(row_complement*column_complement),out=np.full_like(x,np.nan),where=valid)
        for title,values in [('Residuals',raw),('Standardized residuals',standardized),('Adjusted residuals',adjusted),('Chi-square contributions',raw**2/expected)]:
            rows=[[str(label)]+list(row) for label,row in zip(mat.index,values)]
            columns=['Row']+[str(c) for c in mat.columns]
            if title=='Chi-square contributions':
                rows=[row+[float(values[i].sum())] for i,row in enumerate(rows)]
                rows.append(['Column totals']+list(values.sum(axis=0))+[float(values.sum())])
                columns.append('Row totals')
            tables.append(b._table(title,columns,rows))
    if aid=='1401' or boolean(opt,'sta.nps.chi.tests',True):
        if mode==0 and not crosstab:
            tables.extend([b._table(title,['Row']+[str(c) for c in mat.columns],
                [[str(label)]+list(row) for label,row in zip(mat.index,values)])
                for title,values in [('Observed counts',x)]+([('Expected counts',expected)] if exp else [])])
        if not crosstab and (not residuals or mode==0):
            tables.append(b._table('Chi-square contributions',['Row']+[str(c) for c in mat.columns],
                [[str(label)]+list(row) for label,row in zip(mat.index,(x-expected)**2/expected)]))
        chi=stats.chi2_contingency(x,correction=False)
        rows=[['Pearson chi-square',plain,df,chi.pvalue]]
        if x.shape==(2,2) and boolean(opt,'correction',True):
            v=stats.chi2_contingency(x,correction=True);rows.append(['Yates continuity correction',v.statistic,df,v.pvalue])
        v=stats.chi2_contingency(x,correction=False,lambda_='log-likelihood');rows.append(['Likelihood-ratio G²',v.statistic,df,v.pvalue])
        tables.append(b._table('Chi-square tests',['Test','Statistic','df','p-value'],rows))
    full=x.shape==(2,2) and (aid=='1401' or boolean(opt,'tables.ui.full2x2',True))
    if full:
        exact_counts=np.trunc(x).astype(np.int64)
        if boolean(opt,'T22_FISH',True):
            exact=stats.fisher_exact(exact_counts,alternative='two-sided')
            tables.append(b._table('Fisher exact (two-sided)',['Odds ratio','p-value'],[[exact.statistic,exact.pvalue]]))
        if boolean(opt,'sta.nps.mcnemar1',True):
            discordant=x[0,1]+x[1,0]
            stat=(abs(x[0,1]-x[1,0])-min(1,abs(x[0,1]-x[1,0])))**2/discordant if discordant else 0.
            exact=mcnemar(exact_counts,exact=True)
            tables.append(b._table('McNemar test',['Corrected chi-square','Asymptotic p-value','Exact p-value'],[[stat,stats.chi2.sf(stat,1),exact.pvalue]]))
        if np.any(x!=exact_counts):warn.append('Exact tests use truncated integer cell counts; other selected statistics use the requested frequency conversion.')
    if boolean(opt,'tables.measures',True):
        rows=[['N',total],['Cramér V',math.sqrt(plain/(total*min(x.shape[0]-1,x.shape[1]-1)))],['Contingency coefficient',math.sqrt(plain/(plain+total))]]
        if x.shape==(2,2):
            a,c1,c2,d=x.ravel();den=(a+c1)*(c2+d)*(a+c2)*(c1+d)
            rows.extend([['Phi',(a*d-c1*c2)/math.sqrt(den)],['Phi-square',plain/total],['Odds ratio',a*d/(c1*c2) if c1*c2 else None],['Risk ratio',(a/(a+c1))/(c2/(c2+d)) if c2 else None]])
        tables.append(b._table('Measures of association',['Statistic','Value'],rows))
    if x.shape[0]==x.shape[1] and boolean(opt,'sta.nps.kappa' if aid=='1401' else 'tables.ui.kappaopt',True):
        k=cohens_kappa(x)
        tables.append(b._table('Cohen kappa',['Kappa','SE','CI lower','CI upper','Two-sided p-value'],[[k.kappa,k.std_kappa,k.kappa_low,k.kappa_upp,k.pvalue_two_sided]]))
    if full and boolean(opt,'tables.measures.verification',True):
        a,fp,fn,d=x.ravel()
        div=lambda n,d:n/d if d else None
        sens=div(a,a+fn);spec=div(d,d+fp)
        rows=[['Sensitivity',sens],['Specificity',spec],['Positive predictive value',div(a,a+fp)],['Negative predictive value',div(d,d+fn)],['Accuracy',(a+d)/total],['Prevalence',(a+fn)/total],['Positive likelihood ratio',div(sens,1-spec)],['Negative likelihood ratio',div(1-sens,spec)]]
        tables.append(b._table('Measures of accuracy',['Statistic','Value'],rows))
        notes.append('Accuracy uses first row/column as positive: A=TP, B=FP, C=FN, D=TN.')
    if bar:
        values=x/x.sum(axis=1)[:,None]*100 if bar==3 else x
        charts.append(dict(type='bar',title='Crosstab counts' if bar!=3 else 'Crosstab percentages',xLabel='Row',yLabel='Count' if bar!=3 else 'Percent',stack='percent' if bar==3 else 'normal' if bar==2 else None,series=[dict(name=str(c),x=[str(v) for v in mat.index],y=list(values[:,i])) for i,c in enumerate(mat.columns)]))
    if boolean(opt,'tables.plot.interaction',True):charts.append(dict(type='line',title='Crosstab interaction',xLabel='Row',yLabel='Count',series=[dict(name=str(c),x=[str(v) for v in mat.index],y=list(x[:,i])) for i,c in enumerate(mat.columns)]))
    if (expected<5).any():warn.append('Some expected frequencies are below five; asymptotic tests may be inaccurate.')
    return b._result(aid,tables,charts,notes,warn)


def enhance(aid,frame,opt,result,b):
    if aid=='1005' and opt.get('test_type','pooled')=='paired' and boolean(opt,'ttest.paired.plot.ui'):
        a,c=b._name(frame,opt,'x'),b._name(frame,opt,'y');data=b._complete(frame,[a,c])
        result['charts'].append(dict(type='line',title='Paired profiles',xLabel='Measurement',yLabel='Value',series=[dict(name=f'Pair {i+1}',x=[a,c],y=list(row)) for i,row in data.iterrows()]))
    if aid=='1011':
        chart_opts={k:v for k,v in opt.items()};chart_opts['sta.bst.ds.report']='0'
        desc=b._descriptive('1001',frame,chart_opts)
        result['charts'].extend(desc['charts']);result['warnings'].extend(w for w in desc['warnings'] if 'MAD' not in w)
    if aid in ('1009','1016','1404'):
        table=result['tables'][0];rows=table['rows']
        if aid in ('1009','1016'):
            if index(opt,'sta.tail.h',1,1)==0:
                for row in rows:
                    if row[5] is not None:row[5]/=2
                result['notes'].append('One-tailed correlation p-values follow the observed coefficient direction (half the two-sided value).')
            if aid=='1009' and boolean(opt,'bst.corr.table.trse.ui'):
                table['columns']+=['SE of correlation','t-statistic']
                for row in rows:
                    se=math.sqrt(max(0,1-row[4]**2)/(row[3]-2));row.extend([se,row[4]/se if se else None])
            if not boolean(opt,'bst.corr.table.pval.ui',True):
                table['columns'].pop(5)
                for row in rows:row.pop(5)
            if aid=='1009':
                if boolean(opt,'bst.corr.ui.listrs',True):rows.sort(key=lambda r:abs(r[4]),reverse=True)
                table['layout']={'freezeFirstColumn':boolean(opt,'ui.freezecols')}
            if aid=='1016':
                if boolean(opt,'corr.partial.zeroorder'):
                    zero=b._correlations('1009',frame,opt);zero['tables'][0]['title']='Zero-order correlations';result['tables'].extend(zero['tables'])
                if boolean(opt,'sta.DS',True):
                    cols=b._names(frame,opt)+b._names(frame,opt,'controls');result['tables'].append(descriptive_table(frame,cols,b))
        scatter=index(opt,'sta.scatterplots',0,1)==1 if aid=='1009' else boolean(opt,'sta.scatterplots') if aid=='1404' else False
        if scatter:
            for a,c in __import__('itertools').combinations(b._names(frame,opt),2):
                clean=b._complete(frame,[a,c]);result['charts'].append(dict(type='scatter',title=f'{a} vs {c}',xLabel=a,yLabel=c,series=[dict(name=f'{a} / {c}',x=list(clean[a]),y=list(clean[c]))]))
    if aid in ('1009','1405'):
        columns=b._names(frame,opt);pairs=result['tables'][0]['rows']
        lookup={(r[0],r[1]):r[4] for r in pairs}
        matrix=b._table('Correlation matrix',['Variable']+columns,
            [[c]+[1. if c==d else lookup.get((c,d),lookup.get((d,c))) for d in columns] for c in columns])
        matrix['layout']={'freezeFirstColumn':boolean(opt,'ui.freezecols')}
        result['tables'].append(matrix)
        if aid=='1009':
            critical=[];alpha=1-b._conf(opt);two_sided=index(opt,'sta.tail.h',1,1)==1
            for row in pairs:
                n=row[3];tcrit=stats.t.ppf(1-alpha/(2 if two_sided else 1),n-2)
                rcrit=tcrit/math.sqrt(tcrit*tcrit+n-2)
                critical.append([row[0],row[1],n-2,rcrit,'Reject' if abs(row[4])>rcrit else 'Do not reject'])
            result['tables'].append(b._table('Correlation significance',['Variable1','Variable2','df','Critical |r|','H0 at alpha'],critical))
    if aid=='1403':
        order=index(opt,'sta.sort.output',0,2)
        if order:
            for tab in result['tables']:tab['rows'].sort(key=lambda r:r[2],reverse=order==2)
            if len(result['tables'])==1:
                indices=[r[0]-1 for r in result['tables'][0]['rows']];data=result['dataset'];indices.extend(i for i in range(len(data['rows'])) if i not in set(indices));data['rows']=[data['rows'][i] for i in indices]
            else:result['notes'].append('Each variable report is independently rank-sorted; the shared multi-variable dataset retains original alignment.')
    return result


def descriptive_table(frame,columns,b,title='Descriptive statistics'):
    rows=[]
    for c in columns:
        x=b._vector(frame,c,1);rows.append([c,len(x),np.mean(x),np.std(x,ddof=1) if len(x)>1 else None,np.min(x),np.max(x),np.var(x,ddof=1) if len(x)>1 else None])
    return b._table(title,['Variable','N','Mean','SD','Minimum','Maximum','Variance'],rows)
