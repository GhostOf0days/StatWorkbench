"""Time-series procedures and their analysis options."""
import math
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.tsa.holtwinters import Holt, SimpleExpSmoothing, ExponentialSmoothing
from statsmodels.tsa.stattools import acf, pacf, adfuller, kpss
from statsmodels.tsa.adfvalues import mackinnonp, mackinnoncrit
from . import advanced as a
from .advanced_charts import choice

ALIASES={
'1502':{'length':'sta.time.sma.length'},
'1521':{'lag':'sta.time.acf.ao.4','order':'sta.time.acf.ao.5'},
'1522':{'smoothing':'sta.time.expsm.ao.0','steps':'ts.report.forecast.n'},
'1540':{'smoothing':'sta.time.expsm.ao.0','beta':'ts.expsm.beta.full','phi':'ts.expsm.phi.full','steps':'ts.report.forecast.n'},
'1530':{'differences':'sta.ts.transform.diff.opt','lags':'p'}}


def residuals(r,y,fit,o):
    residual=np.asarray(y)-np.asarray(fit);valid=np.isfinite(residual);x=residual[valid]
    if not len(x):return
    if o.get('report.residuals.plothistogram',False):
        h,e=np.histogram(x,bins='auto');r['charts'].append(a._chart('Residual histogram',[a._series('Frequency',(e[1:]+e[:-1])/2,h)],'bar','Residual','Count'))
    if o.get('report.residuals.plotqq',False):
        y=np.sort(x);p=(np.arange(1,len(y)+1)-.375)/(len(y)+.25)
        r['charts'].append(a._chart('Normal Q-Q: residuals',[a._series('Residuals',stats.norm.ppf(p),y)],'scatter','Normal quantile','Residual'))
    if o.get('sta.reg.lin.ao.resorder',False):r['charts'].append(a._chart('Residuals vs. order',[a._series('Residual',np.flatnonzero(valid)+1,x)]))


def _series_result(r,y,out,columns=None):
    t=np.arange(1,len(y)+1)
    r['tables'].append(a._table('Series',columns or ['Observation','Original','Result'],zip(t,y,out)))
    r['dataset']=a._dataset(['Original','Result'],np.column_stack([y,out]),r['title'])


def _bandwidth(y,setting):return min(len(y)-2,int((4 if setting==0 else 12)*(len(y)/100)**.25))


def _durbin_levinson(correlation):
    """Biased ACF yields a positive-definite Toeplitz system through lag N−1."""
    result=np.ones(len(correlation));coeff=np.empty(0);variance=1.
    for lag in range(1,len(correlation)):
        reflection=(correlation[lag]-np.dot(coeff,correlation[1:lag][::-1]))/variance
        result[lag]=reflection
        coeff=np.r_[coeff-reflection*coeff[::-1],reflection]
        variance*=1-reflection**2
    return result


def _accuracy(y,fit):
    residual=np.asarray(y)-np.asarray(fit);valid=np.isfinite(residual);residual=residual[valid];actual=np.asarray(y)[valid]
    nonzero=actual!=0
    return [len(residual),np.mean(np.abs(residual[nonzero]/actual[nonzero]))*100 if nonzero.any() else np.nan,np.mean(np.abs(residual)),np.mean(residual**2),int(nonzero.sum())]


def unitroots(y,o,r):
    order=choice(o,'sta.ts.transform.diff.opt',0,3);y=np.diff(y,n=order);n=len(y)
    if n<8 or np.ptp(y)==0:raise ValueError('Unit-root tests require at least eight nonconstant observations after differencing.')
    rows=[];summaries=[]
    for test in ('adf','pp','kpss'):
        key={'adf':'sta.time.test.df-adf','pp':'sta.time.test.pp','kpss':'sta.time.test.kpss'}[test]
        if not o.get(key,True):continue
        termkey='sta.time.reg.include__'+('df_adf' if test=='adf' else test)
        term=choice(o,termkey,0 if test=='kpss' else 1,2 if test=='kpss' else 3)
        trend=['c','ct'][term] if test=='kpss' else ['n','c','ct'][term]
        if test=='adf':
            lag=0 if choice(o,'sta.time.adf.lag.selection',1,2)==0 else a._num(o,'p',1,0,n//2-3,True)
            result=adfuller(y,maxlag=lag,regression=trend,autolag=None,store=True,regresults=True)
            stat,pval,crit,store=result;fit=store.resols
        elif test=='kpss':
            longlag=choice(o,'sta.time.lag__kpss',0,2)
            lag=min(n-1,int(np.sqrt(n)*(10/14 if longlag else 3/13)))
            stat,pval,_,crit=kpss(y,regression=trend,nlags=lag)
            native_critical=[.347,.463,.574,.739,np.inf] if trend=='c' else [.119,.146,.176,.216,np.inf]
            pval=next(p for critical,p in zip(native_critical,[.1,.05,.025,.01,0]) if stat<critical)
            r['notes'].append('KPSS p-values are selected from the critical-table categories 0.10, 0.05, 0.025, 0.01, or 0; they are not interpolated tail probabilities.')
            design=np.ones((n,1)) if trend=='c' else np.column_stack([np.ones(n),np.arange(1,n+1)])
            fit=sm.OLS(y,design).fit()
        else:
            lag=_bandwidth(y[:-1],choice(o,'sta.time.lag__pp',0,2));X=y[:-1,None]
            if trend!='n':X=np.column_stack([X,np.ones(n-1)])
            if trend=='ct':X=np.column_stack([X,np.arange(1,n)])
            fit=sm.OLS(y[1:],X).fit();u=fit.resid;nn=len(u);g0=np.dot(u,u)/nn
            longvar=g0+2*sum((1-j/(lag+1))*np.dot(u[j:],u[:-j])/nn for j in range(1,lag+1))
            s2=fit.mse_resid;se=fit.bse[0]
            if min(longvar,s2,se)<=0:raise ValueError('Phillips-Perron requires positive residual and long-run variance.')
            stat=np.sqrt(g0/longvar)*(fit.params[0]-1)/se-(longvar-g0)*nn*se/(2*np.sqrt(longvar*s2))
            pval=mackinnonp(stat,regression=trend);crit=dict(zip(['1%','5%','10%'],mackinnoncrit(regression=trend,nobs=nn)))
        rows.append([test.upper(),stat,pval,lag,'Stationarity' if test=='kpss' else 'Unit root'])
        if o.get('sta.reg.modelsum.opt',False):
            summaries.extend([a._table(test.upper()+' model',['Term','Estimate','Std. error','t','p'],zip(fit.model.exog_names,fit.params,fit.bse,fit.tvalues,fit.pvalues)),a._table(test.upper()+' critical values',['Level','Critical value'],crit.items())])
    if not rows:raise ValueError('Select at least one unit-root/stationarity test.')
    r['tables']=[a._table('Stationarity tests',['Test','Statistic','p','Lags','Null hypothesis'],rows)]+summaries
    if o.get('sta.plot.series',True):r['charts'].append(a._chart('Tested series',[a._series('Series',np.arange(1,n+1),y)]))
    r['notes'].append('PP bandwidth uses floor(4 or 12 × ((N−1)/100)^0.25); KPSS uses floor(3√N/13 or 10√N/14). PP uses Bartlett/Newey-West long-run variance and MacKinnon tau probabilities.')


def run(i,data,o,r):
    o=dict(o)
    if i=='1521' and isinstance(o.get('column'),list):
        names=a._names(data,o['column'])
        if len(names)==1:o['column']=names[0]
        else:
            outputs={}
            for name in names:
                child={**r,'tables':[],'charts':[],'notes':[],'warnings':[]}
                run(i,data,{**o,'column':name},child)
                for tab in child['tables']:tab['title']=name+': '+tab['title']
                for chart in child['charts']:chart['title']=name+': '+chart['title']
                for key in ('tables','charts','notes','warnings'):r[key].extend(child[key])
                outputs[name]=pd.Series([row[1] for row in child['dataset']['rows']])
            frame=pd.DataFrame(outputs)
            r['dataset']=a._dataset(names,frame.to_numpy(),r['title'])
            return
    for old,new in ALIASES.get(i,{}).items():
        if old in o and new not in o:o[new]=str(o[old]) if old=='differences' else o[old]
    if i=='1502' and 'method' in o:o.setdefault('MOVING_AVERAGE',{'trailing':'0','centered':'1','weighted':'2'}[o['method']])
    if i=='1522' and 'initial' in o:o.setdefault('ts.expsm.inits0',{'mean':'1','first':'2'}[o['initial']])
    if i=='1540' and 'trend' in o:o.setdefault('sta.time.dp.expsm',{'linear':'0','exponential':'1','damped':'2'}[o['trend']])
    if i in ('1522','1540') and 'steps' in o:o.setdefault('ts.report.forecast',True)
    if i=='1530' and 'test' in o:
        o.setdefault('sta.time.test.df-adf',o['test'] in ('both','adf'));o.setdefault('sta.time.test.kpss',o['test'] in ('both','kpss'));o.setdefault('sta.time.test.pp',False)
    if i=='1530' and 'regression' in o:
        for suffix in ('df_adf','pp','kpss'):o.setdefault('sta.time.reg.include__'+suffix,str((0 if suffix=='kpss' else 1)+(o['regression']=='ct')))
    y=a._padded_series(data,o.get('column'));n=len(y);t=np.arange(1,n+1)
    if i=='1530':return unitroots(y,o,r)
    if i=='1501':
        if o.get('sta.time.acf.ao.2',False):y=y-y.mean()
        if o.get('sta.time.acf.ao.3',False):
            lag=a._num(o,'sta.time.acf.ao.4',1,1,n-1,True);order=a._num(o,'sta.time.acf.ao.5',1,1,10,True)
            for _ in range(order):y=y[lag:]-y[:-lag]
        n=len(y)
        if n<3 or np.ptp(y)==0:raise ValueError('Autocorrelation requires at least three nonconstant observations after differencing.')
        lags=a._num(o,'lags',min(10,n-1),1,n-1,True)
        av=acf(y,nlags=lags,fft=True);pv=_durbin_levinson(av)
        se=np.sqrt(((n-np.arange(1,lags+1))/(n+2) if o.get('sta.time.acf.ao.6',False) else 1+2*np.r_[0,np.cumsum(av[1:-1]**2)])/n)
        Q=n*(n+2)*np.cumsum(av[1:]**2/(n-np.arange(1,lags+1)))
        # The original calls a normal CDF here, not an inverse CDF. Live
        # eight-observation results confirm this narrow Fisher-z interval.
        width=stats.norm.cdf(a._num(o,'alpha',.05,1e-9,.999)/2)/np.sqrt(n-3) if n>3 else np.inf
        fisher=np.arctanh(np.clip(av[1:],-1+1e-15,1-1e-15));lower=np.tanh(fisher-width);upper=np.tanh(fisher+width)
        rows=[[0,av[0],pv[0],0,1,1,0,1]]+[[j,av[j],pv[j],se[j-1],lower[j-1],upper[j-1],Q[j-1],stats.chi2.sf(Q[j-1],j)] for j in range(1,lags+1)]
        r['tables'].append(a._table('Correlations',['Lag','ACF','PACF','ACF standard error','Lower','Upper','Ljung-Box Q','p'],rows))
        r['tables'].append(a._table('Series summary',['N','Overall mean','Variance','PACF standard error'],[[n,y.mean(),y.var(ddof=0),1/np.sqrt(n)]]))
        for key,label,v in [('sta.time.acf.ao.0','ACF',av),('sta.time.acf.ao.1','PACF',pv)]:
            if o.get(key,True):
                lag=np.arange(1,lags+1);band=2*se if label=='ACF' else np.repeat(1/np.sqrt(n),lags)
                series=[a._series(label,lag,v[1:])]+[{**a._series(name,lag,sign*band),'type':'line'} for name,sign in [('Upper reference',1),('Lower reference',-1)]]
                r['charts'].append(a._chart(label,series,'bar','Lag','Correlation'))
        r['warnings'].append('The reported ACF limits use Φ(alpha/2), the normal CDF, rather than the inverse normal quantile, so they are not conventional confidence intervals. Plot reference bands use ±2 ACF-SE and ±1 PACF-SE.')
        if o.get('sta.time.acf.ao.2',False) or o.get('sta.time.acf.ao.3',False):r['dataset']=a._dataset(['Prepared series'],y[:,None],r['title'])
    elif i=='1521':
        if o.get('sta.time.acf.ao.2',False):y=y-y.mean()
        lag=a._num(o,'sta.time.acf.ao.4',1,1,n-1,True);order=a._num(o,'sta.time.acf.ao.5',1,1,10,True)
        if lag*order>=n:raise ValueError('Lag × order must be smaller than the number of rows.')
        out=pd.Series(y)
        for _ in range(order):out=out.diff(lag)
        _series_result(r,y,out.to_numpy());r['charts'].append(a._chart(r['title'],[a._series('Original',t,y),a._series('Result',t,out)]))
    elif i=='1502':
        method=choice(o,'MOVING_AVERAGE',0,5);length=a._num(o,'sta.time.sma.length',3,2,n,True)
        if method in (3,4):
            coeff=[-3,-6,-5,3,21,46,67,74,67,46,21,3,-5,-6,-3] if method==3 else [-1,-3,-5,-5,-2,6,18,33,47,57,60,57,47,33,18,6,-2,-5,-5,-3,-1]
            length=len(coeff)
            weights=np.asarray(coeff)/sum(coeff);out=np.convolve(np.pad(y,length//2,mode='edge'),weights,'valid')
        elif method==2:
            if o.get('sta.time.wma.weightsvar'):weights=a._padded_series(data,o['sta.time.wma.weightsvar'],1)
            else:
                try:weights=np.asarray([float(v) for v in o.get('weights','1,2,3').split(',')])
                except (ValueError,AttributeError):raise ValueError('Choose a numeric weights variable.') from None
            length=len(weights)
            if length>n or not np.isfinite(weights).all() or weights.sum()==0:raise ValueError('Weights must be finite, have nonzero sum, and fit within the series.')
            out=pd.Series(y).rolling(length).apply(lambda z:np.dot(z,weights)/weights.sum(),raw=True).to_numpy()
        else:
            if method==1 and length%2==0:
                weights=np.r_[.5,np.ones(length-1),.5]/length;out=np.full(n,np.nan)
                if n>length:out[length//2:n-length//2]=np.convolve(y,weights,'valid')
            else:out=pd.Series(y).rolling(length,center=method==1).mean().to_numpy()
        _series_result(r,y,out)
        predicted=np.r_[np.nan,out[:-1]]
        r['tables'].append(a._table('Forecast errors',['Observation','Predicted','Residual'],zip(t,predicted,y-predicted)))
        if o.get('sta.time.ma.showexcelse',False) and method==0:
            denom=max(1,length-choice(o,'sta.time.ma.se_denom',0,3))
            err=np.nan_to_num(y-out,nan=0);se=np.sqrt(pd.Series(err*err).rolling(length).sum()/denom).to_numpy()
            se[:length+denom-2]=np.nan
            r['tables'].append(a._table('Excel ATP standard errors',['Observation','Standard error'],zip(t,se)))
        mode=choice(o,'sta.charts.plot',1,3)
        if mode==1:r['charts'].append(a._chart('Moving average and actual',[a._series('Actual',t,y),a._series('Moving average',t,out)]))
        elif mode==2:r['charts'].append(a._chart('Predicted vs. actual',[a._series('Observations',y,predicted)],'scatter','Actual','Predicted'))
        residuals(r,y,predicted,o)
    elif i in ('1522','1540'):
        alpha=a._num(o,'sta.time.expsm.ao.0',.1,0,1);steps=a._num(o,'ts.report.forecast.n',1,1,1000,True)
        if i=='1522':
            initial=choice(o,'ts.expsm.inits0',1,4)
            value=a._num(o,'ts.expsm.inits0.m',1)
            if initial==0:
                if value<1 or value>n or value!=int(value):raise ValueError('Initial mean M must be an integer within the series length.')
                level=y[:int(value)].mean()
            else:level=[None,y.mean(),y[0],value][initial]
            fit=SimpleExpSmoothing(y,initialization_method='known',initial_level=level).fit(smoothing_level=alpha,optimized=False)
        else:
            trend=choice(o,'sta.time.dp.expsm',0,3);beta=a._num(o,'ts.expsm.beta.full',.1,0,1);phi=a._num(o,'ts.expsm.phi.full',.1,1e-12,1)
            if trend==1 and (y<=0).any():raise ValueError('Exponential trend requires positive data.')
            custom=o.get('ts.expsm.init.custom',False)
            if custom:
                initial_level=a._num(o,'ts.expsm.inits0',1);initial_trend=a._num(o,'ts.expsm.initt0',1)
            else:
                initial_trend=y[1]/y[0] if trend==1 else (y[-1]-y[0])/(n-1)/(phi if trend==2 else 1)
                initial_level=y[0]/np.sqrt(initial_trend) if trend==1 else y[0]-.5*initial_trend
            args={'initialization_method':'known','initial_level':initial_level,'initial_trend':initial_trend}
            if custom and trend==1 and min(args['initial_level'],args['initial_trend'])<=0:raise ValueError('Exponential level and trend must be positive.')
            seasonal=a._choice(o,'help.seasonal','none',['none','additive','multiplicative'])
            if seasonal=='none':
                fit=Holt(y,exponential=trend==1,damped_trend=trend==2,**args).fit(smoothing_level=alpha,smoothing_trend=beta,damping_trend=phi if trend==2 else None,optimized=False)
            else:
                period=a._num(o,'help.seasonal_period',12,2,n//2,True);gamma=a._num(o,'help.seasonal_gamma',.1,0,1)
                if seasonal=='multiplicative' and (y<=0).any():raise ValueError('Multiplicative seasonality requires positive observations.')
                first,second=y[:period].mean(),y[period:2*period].mean()
                initial_seasons=y[:period]-first if seasonal=='additive' else y[:period]/first
                if not custom:
                    args['initial_level']=first
                    args['initial_trend']=(second/first)**(1/period) if trend==1 else (second-first)/period
                fit=ExponentialSmoothing(y,trend='mul' if trend==1 else 'add',damped_trend=trend==2,seasonal='add' if seasonal=='additive' else 'mul',seasonal_periods=period,initial_seasonal=initial_seasons,**args).fit(smoothing_level=alpha,smoothing_trend=beta,smoothing_seasonal=gamma,damping_trend=phi if trend==2 else None,optimized=False)
                r['notes'].append('Seasonal indices start from first-cycle deviations or ratios; the initial trend compares the first two cycle means.')
        r['tables'].append(a._table('Fitted observations',['Observation','Actual','One-step fit','Residual'],zip(t,y,fit.fittedvalues,fit.resid)))
        if (y==0).any():r['notes'].append('MAPE excludes observations equal to zero; MAD and MSD include all finite residuals.')
        ss=[a._series('Actual',t,y),a._series('One-step fit',t,fit.fittedvalues)]
        if o.get('ts.report.forecast',False):
            forecast=fit.forecast(steps);future=np.arange(n+1,n+steps+1)
            if i=='1540' and seasonal!='none':
                # Use the last UPDATED season states. The upstream prediction
                # extension overwrites its final seasonal state with an older
                # cycle value; fit.season retains the actual recurrence states.
                horizons=np.arange(1,steps+1)
                horizon=np.cumsum(phi**horizons) if trend==2 else horizons
                projected=fit.level[-1]*fit.trend[-1]**horizon if trend==1 else fit.level[-1]+horizon*fit.trend[-1]
                season=np.asarray(fit.season)[-period:][np.arange(steps)%period]
                forecast=projected*season if seasonal=='multiplicative' else projected+season
            width=np.full(steps,stats.norm.isf(a._num(o,'alpha',.05,1e-9,.999)/2)*1.25*np.mean(np.abs(fit.resid)))
            if i=='1540' and trend==0 and seasonal=='none':
                v=1-beta;factor=beta/(2-beta)**3;aa=1+4*v+5*v*v;bb=2*beta*(1+3*v);h=np.arange(1,steps+1)
                width*=np.sqrt((1+factor*(beta*h*h+aa+bb*h))/(1+factor*(beta+aa+bb)))
            if i=='1540' and seasonal!='none':
                width[:]=np.nan
                r['notes'].append('Seasonal forecast confidence limits are unavailable: the documented Holt–Winters entry does not specify a forecast-error model.')
            r['tables'].append(a._table('Forecast',['Observation','Forecast','Lower','Upper'],zip(future,forecast,forecast-width,forecast+width)));ss.append(a._series('Forecast',future,forecast))
        r['tables'].append(a._table('Accuracy measures',['N','MAPE (%)','MAD','MSD','Nonzero observations for MAPE'],[_accuracy(y,fit.fittedvalues)]))
        if o.get('ts.report.plot.actual_smoothed',True):r['charts'].append(a._chart(r['title'],ss))
        residuals(r,y,fit.fittedvalues,o)
    elif i=='1510':
        period=a._num(o,'period',12,2,n//4,True)
        model=choice(o,'sta.time.expsm.ao.1',0 if o.get('model','additive')=='additive' else 1,2)
        if model and (y<=0).any():raise ValueError('Multiplicative decomposition requires positive data.')
        centered=o.get('time.decompose.opt.centerma',False)
        if period%2==0 and centered:
            weights=np.r_[.5,np.ones(period-1),.5]/period;trend=np.full(n,np.nan);trend[period//2:n-period//2]=np.convolve(y,weights,'valid')
        else:trend=pd.Series(y).rolling(period,center=True).mean().to_numpy()
        detrended=y/trend if model else y-trend
        indices=np.asarray([np.nanmean(detrended[j::period]) for j in range(period)])
        indices=indices/indices.mean() if model else indices-indices.mean();season=np.resize(indices,n)
        adjusted=y/season if model else y-season
        irregular=y/(trend*season) if model else y-trend-season
        cycle=np.empty(n);cycle[2:-2]=np.convolve(adjusted,np.array([1,2,3,2,1])/9,'valid')
        cycle[1]=adjusted[:3].mean();cycle[-2]=adjusted[-3:].mean()
        cycle[0]=cycle[1]+.5*(cycle[1]-cycle[2]);cycle[-1]=cycle[-2]+.5*(cycle[-2]-cycle[-3])
        irregular=adjusted/cycle if model else adjusted-cycle
        multiplier=100 if model and o.get('time.opt.percentforratios',False) else 1
        r['tables'].append(a._table('Components',['Observation','Observed','Trend','Seasonal','Residual','Seasonally adjusted','Smoothed trend-cycle'],zip(t,y,trend,season*multiplier,irregular*multiplier,adjusted,cycle)))
        r['dataset']=a._dataset(['Observed','Trend','Seasonal','Residual','Seasonally adjusted','Smoothed trend-cycle'],np.column_stack([y,trend,season*multiplier,irregular*multiplier,adjusted,cycle]),r['title'])
        if o.get('time.decompose.opt.printsi',False):r['tables'].append(a._table('Seasonal indices',['Period','Index'],zip(range(1,period+1),indices*multiplier)))
        for key,label,val in [('time.opt.series.original','Original',y),('time.opt.trendma','Trend',trend),('time.sas','Seasonally adjusted',adjusted),('time.stc','Smoothed trend-cycle',cycle),('time.irregular.comp','Irregular',irregular*multiplier)]:
            if o.get(key,False):r['charts'].append(a._chart(label,[a._series(label,t,val)]))
        mode=choice(o,'time.opt.si',0,3)
        if mode:r['charts'].append(a._chart('Seasonal indices',[a._series('Seasonal',np.arange(1,period+1),indices*multiplier)],'line' if mode==1 else 'bar','Period','Index'))
