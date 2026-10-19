"""Chart calculations and distribution reference curves."""
import math
import numpy as np
import pandas as pd
from scipy import stats
from . import advanced as a


def choice(o,key,default,count):
    return int(a._choice(o,key,str(default),[str(j) for j in range(count)]))


def qq(r,name,x,i,o):
    y=np.sort(x)
    if np.ptp(y)==0:raise ValueError('Q-Q fitting requires nonconstant data.')
    method=choice(o,'sta.qq.proportion.method',0,4)
    tie=choice(o,'sta.rankperc.tie',0,4)
    ranks=stats.rankdata(y,method=['average','max','min','ordinal'][tie])
    # Blom, Hazen (rankit), Tukey, and Weibull (Van der Waerden).
    offset=[.375,.5,1/3,0][method]
    p=(ranks-offset)/(len(y)+1-2*offset)
    estimate=o.get('sta.distr.params.estimate.opt',True)
    if i=='4011':
        loc=y.mean() if estimate else a._num(o,'DS_AVERAGE',0)
        scale=y.std(ddof=1) if estimate else a._num(o,'DS_STDDEV',1,1e-15)
        dist=stats.norm(loc=loc,scale=scale)
    elif i=='4012':
        if (y<0).any() or (y>1).any():raise ValueError('Beta data must lie in [0,1].')
        if estimate:
            mu=y.mean(); v=y.var(ddof=1); concentration=mu*(1-mu)/v-1
            if concentration<=0:raise ValueError('Beta moment estimates require variance below mean × (1−mean).')
            aa,bb=mu*concentration,(1-mu)*concentration
        else:aa,bb=a._num(o,'sta.beta.alpha',o.get('shape',1),1e-15),a._num(o,'sta.beta.beta',o.get('shape2',1),1e-15)
        dist=stats.beta(aa,bb)
        r['notes'].append('Beta parameters are estimated by moments when automatic estimation is enabled.')
    elif i in ('4013','4016'):
        df=a._num(o,'DF',o.get('shape',1),1e-15)
        dist=(stats.chi2 if i=='4013' else stats.t)(df)
    elif i=='4017':
        low=y.min() if estimate else a._num(o,'DS_MIN',0)
        high=y.max() if estimate else a._num(o,'DS_MAX',1)
        if high==low:raise ValueError('Uniform endpoints must differ.')
        low,high=min(low,high),max(low,high)
        dist=stats.uniform(loc=low,scale=high-low)
    else:
        if (y<=0).any():raise ValueError('This distribution requires positive data.')
        family={'4014':stats.gamma,'4015':stats.lognorm,'4018':stats.weibull_min}[i]
        if estimate:
            if i=='4014':
                mu=y.mean();variance=y.var(ddof=1);dist=stats.gamma(mu*mu/variance,scale=mu/variance)
                r['warnings'].append('This implementation uses mean/variance for the gamma scale; the conventional moment scale is variance/mean.')
            elif i=='4015':dist=stats.lognorm(np.log(y).std(ddof=1),scale=np.exp(np.log(y).mean()))
            else:
                slope,intercept=np.polyfit(np.log(y),np.log(-np.log1p(-p)),1)
                if slope<=0:raise ValueError('Weibull probability-plot slope must be positive.')
                dist=stats.weibull_min(slope,scale=np.exp(-intercept/slope))
        else:
            shapekey='sta.distr.shape' if i=='4015' else 'sta.gamma.shapek'
            scalekey={'4014':'sta.gamma.scaletheta','4015':'sta.distr.scale','4018':'sta.weibull.scalelambda'}[i]
            first=a._num(o,shapekey,1,1e-15);second=a._num(o,scalekey,1,1e-15)
            if i=='4015':dist=stats.lognorm(second,scale=np.exp(first))
            elif i=='4018':
                dist=stats.weibull_min(first,scale=second)
            else:dist=family(first,scale=second)
    theo=dist.ppf(p)
    if not np.isfinite(theo).all():raise ValueError('Specified Q-Q parameters yield nonfinite quantiles.')
    axy=bool(o.get('sta.qq.swapaxes',False))
    # The original label explicitly places empirical quantiles on Y when checked.
    xs,ys=(theo,y) if axy else (y,theo)
    labels=('Theoretical quantile','Observed quantile') if axy else ('Observed quantile','Theoretical quantile')
    series=[a._series('Quantiles',xs,ys)]
    if o.get('sta.qq.plot.showline',True):
        endpoints=dist.ppf([.01,.99]).tolist()
        series.append({**a._series('Reference',endpoints,endpoints),'type':'line'})
    r['tables'].append(a._table(name,['Probability','Theoretical quantile','Observed quantile'],zip(p,theo,y)))
    r['charts'].append(a._chart(f'{r["title"]}: {name}',series,'scatter',*labels))
    if o.get('sta.qq.detrended.show',True):
        difference=(y-theo)/np.sqrt(2)
        ss=[a._series('Deviation',xs,difference)]
        if o.get('sta.qq.plot.showline',True):ss.append({**a._series('Zero',[xs.min(),xs.max()],[0,0]),'type':'line'})
        r['charts'].append(a._chart(f'Detrended: {name}',ss,'scatter',labels[0],'Signed perpendicular deviation'))


def run(i,data,o,r):
    if i=='4002':
        v,mask=a._numbers(data,[o.get('x'),o.get('y')],minimum=2);a._missing(r,mask)
        groups=a._frame(data).loc[mask,a._names(data,o['group'])[0]].to_numpy() if o.get('group') else np.repeat('Points',len(v))
        mode=choice(o,'charts.scatter.group.plots',0,2)
        ellipse=choice(o,'charts.ellipses.add',0,4)
        try:intervals=[float(x) for x in str(o.get('ellipse.values.ui','95')).replace(';',',').split(',')]
        except ValueError:raise ValueError('Ellipse intervals must be comma-separated percentages.') from None
        if not intervals or any(not 0<x<100 for x in intervals):raise ValueError('Ellipse confidence percentages must lie strictly between 0 and 100.')
        reverse=choice(o,'sta.plotxy.reverseaxes',0,4)
        charts=[];combined=[]
        for g in pd.unique(groups):
            if pd.isna(g):continue
            z=v[groups==g];ss=[a._series(g,z[:,0],z[:,1])]
            if ellipse:
                if len(z)<=2 or np.linalg.matrix_rank(z-z.mean(axis=0))<2:raise ValueError('Ellipses require at least three noncollinear observations per group.')
                values,vectors=np.linalg.eigh(np.cov(z,rowvar=False,ddof=1));angles=np.linspace(0,2*np.pi,129)
                circle=np.stack([np.cos(angles),np.sin(angles)])
                for level in intervals:
                    # Hotelling region of the mean and bivariate prediction region.
                    for kind in (['Prediction','Confidence'] if ellipse==3 else [['Prediction'],['Confidence']][ellipse-1]):
                        n=len(z);factor=2*(n-1)/(n-2)*stats.f.ppf(level/100,2,n-2)
                        factor*= (n+1)/n if kind=='Prediction' else 1/n
                        pts=z.mean(axis=0)[:,None]+vectors@np.diag(np.sqrt(values*factor))@circle
                        ss.append({**a._series(f'{g}: {level:g}% {kind}',pts[0],pts[1]),'type':'line'})
            if mode==0:charts.append(a._chart(f'Scatter plot: {g}',ss,'scatter',o['x'],o['y']))
            else:combined.extend(ss)
        if mode==1:charts=[a._chart('Scatter plot',combined,'scatter',o['x'],o['y'])]
        for chart in charts:chart.update(reverseX=reverse in (1,3),reverseY=reverse in (2,3))
        r['charts'].extend(charts);return
    for name in a._names(data,o.get('columns')):
        v,mask=a._numbers(data,name,minimum=2);a._missing(r,mask);x=v[:,0]
        if i.startswith('401'):qq(r,name,x,i,o)
        elif i=='4003':
            unit=a._num(o,'unit',1,1e-12);scaled=np.trunc(x/unit).astype(np.int64);rows={}
            for v in np.sort(scaled):
                stem=('−' if v<0 else '')+str(abs(int(v))//10)
                rows.setdefault(stem,[]).append(str(abs(int(v))%10))
            pairs=list(rows.items())
            if o.get('sta.chart.stemleaf.opt.reverseorder',False):pairs.reverse()
            separator=' ' if o.get('sta.chart.stemleaf.opt.addspaces',True) else ''
            r['tables'].append(a._table(name,['Stem','Leaves'],[(k,separator.join(vals)) for k,vals in pairs]))
            r['notes'].append(f'Leaf unit = {unit:g}.')
        else:
            groups=a._frame(data).loc[mask,a._names(data,o['group'])[0]].to_numpy() if o.get('group') else np.repeat(name,len(x))
            definition=choice(o,'sta.percentile.def',6,9)
            qmethod=['inverted_cdf','averaged_inverted_cdf','closest_observation','interpolated_inverted_cdf','hazen','weibull','linear','median_unbiased','normal_unbiased'][definition]
            whisker=choice(o,'sta.chart.box.whisker.def',0,4)
            percent=a._num(o,'sta.chart.box.whisker.percentile',2,1,25,True)
            ss=[];rows=[]
            for g in pd.unique(groups):
                if pd.isna(g):continue
                v=x[groups==g];q1,med,q3=np.quantile(v,[.25,.5,.75],method=qmethod)
                if whisker==0:
                    inside=v[(v>=q1-1.5*(q3-q1))&(v<=q3+1.5*(q3-q1))];low,high=inside.min(),inside.max()
                elif whisker==1:low,high=v.min(),v.max()
                elif whisker==2:
                    if len(v)<2:raise ValueError('Mean ± SD whiskers require two observations per group.')
                    low,high=v.mean()-v.std(ddof=1),v.mean()+v.std(ddof=1)
                else:low,high=np.quantile(v,[percent/100,1-percent/100],method=qmethod)
                outliers=v[(v<low)|(v>high)]
                far=outliers[(outliers<q1-3*(q3-q1))|(outliers>q3+3*(q3-q1))] if whisker==0 else np.array([])
                mild=outliers[~np.isin(outliers,far)]
                box={'q1':q1,'median':med,'mean':v.mean(),'q3':q3,'low':low,'high':high,'outliers':outliers.tolist(),'mildOutliers':mild.tolist(),'extremeOutliers':far.tolist()}
                ss.append({**a._series(g,np.arange(len(v)),v),'box':box})
                rows.append([str(g),len(v),q1,med,q3,low,high])
            r['tables'].append(a._table(name,['Group','N','Q1','Median','Q3','Lower whisker','Upper whisker'],rows))
            chart=a._chart(name,ss,'box','Group',name);chart['legend']=bool(o.get('sta.chart.legend',True));r['charts'].append(chart)
