"""Event-code mappings and survival-analysis report controls."""
import math
from itertools import combinations
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from . import advanced as a
from .advanced_charts import choice


def _code(value):
    if value is None or (isinstance(value,float) and np.isnan(value)):return ''
    text=str(value).strip()
    try:
        number=float(text)
        if math.isfinite(number):return number
    except ValueError:pass
    return text


def _same_code(first,second):
    if isinstance(first,float) and isinstance(second,float):return abs(first-second)<1e-12
    return first==second


def recode(i,data,o,r):
    if i=='1610':keys=('sta.surv.roc.code.positive.ui','sta.surv.roc.code.negative.ui')
    elif i=='1611':keys=('sta.surv.roc.code.positive','sta.surv.roc.code.negative')
    else:keys=('sta.surv.code.fail','sta.surv.code.censor')
    positive,negative=[_code(o.get(k,v)) for k,v in zip(keys,('1','0'))]
    if _same_code(positive,negative):raise ValueError('Positive/failure and negative/censor codes must be distinct.')
    unknown=choice(o,'sta.surv.roc.code.unknown',2,3)
    status=a._names(data,o.get('status'))[0];index=data['columns'].index(status);rows=[];count=0
    for source in data['rows']:
        row=list(source);code=_code(row[index])
        if _same_code(code,positive):row[index]=1
        elif _same_code(code,negative):row[index]=0
        else:row[index]=[1,0,None][unknown] if code!='' else None;count+=1
        rows.append(row)
    if count:r['notes'].append(f'{count} unrecognized/missing status code(s): nonempty codes mapped to '+['event/positive; blanks omitted.','censored/negative; blanks omitted.','missing.'][unknown])
    return {**data,'rows':rows}


def ci_binomial(success,total,alpha):
    return (0 if success==0 else stats.beta.ppf(alpha/2,success,total-success+1),1 if success==total else stats.beta.isf(alpha/2,success+1,total-success))


def roc(i,data,o,r):
    rule=choice(o,'sta.surv.roc.threshold.cond',0 if o.get('direction','higher')=='higher' else 2,4)
    o={**o,'direction':'higher' if rule<2 else 'lower'}
    a._survival_base(i,data,o,r)
    if i=='1611':
        if choice(o,'sta.surv.roc.compare.opt',1,2)==0:
            first=a._names(data,o['columns'],2)[0]
            r['tables'][-1]['rows']=[row for row in r['tables'][-1]['rows'] if row[0]==first]
        return
    r['tables']=[t for t in r['tables'] if t['title']!='ROC coordinates']
    if not o.get('sta.surv.roc.report.ss.opt',True):return
    values,_=a._numbers(data,[o.get('score'),o.get('status')],minimum=4);scores,status=values.T;status=status==1
    thresholds=np.r_[-np.inf,np.unique(scores),np.inf]
    columns=['Threshold','Sensitivity','Specificity','Positive predictive value','Negative predictive value','Youden index']
    with_ci=o.get('sta.surv.roc.report.ci',True);fractions=o.get('sta.surv.roc.report.tfpn',True)
    if with_ci:columns+=['Sensitivity lower','Sensitivity upper','Specificity lower','Specificity upper']
    if fractions:columns+=['TP','TN','FP','FN']
    rows=[];alpha=a._num(o,'alpha',.05,1e-9,.99999)
    for threshold in thresholds:
        prediction=[scores>threshold,scores>=threshold,scores<=threshold,scores<threshold][rule]
        tp=int(np.sum(prediction&status));tn=int(np.sum(~prediction&~status));fp=int(np.sum(prediction&~status));fn=int(np.sum(~prediction&status))
        sensitivity=tp/(tp+fn);specificity=tn/(tn+fp)
        row=[threshold,sensitivity,specificity,tp/(tp+fp) if tp+fp else None,tn/(tn+fn) if tn+fn else None,sensitivity+specificity-1]
        if with_ci:row+=list(ci_binomial(tp,tp+fn,alpha))+list(ci_binomial(tn,tn+fp,alpha))
        if fractions:row += [tp,tn,fp,fn]
        rows.append(row)
    r['tables'].append(a._table('ROC coordinates',columns,rows))
    r['notes'].append('Threshold performance confidence limits use exact Clopper-Pearson binomial intervals.')


def curves(i,data,o,r):
    if i=='1620':return life(data,o,r)
    a._survival_base(i,data,o,r);r['charts']=[]
    showci=o.get('sta.charts.showci',False)
    for table in r['tables']:
        rows=table['rows'];group=table['title'].split(': ',1)[-1]
        times=np.r_[0,[x[0] for x in rows]]
        if i=='1621':
            s=np.r_[1,[x[4] for x in rows]];low=np.r_[1,[x[5] for x in rows]];high=np.r_[1,[x[6] for x in rows]]
            logsurvival=np.full(len(s),np.nan);np.log(s,out=logsurvival,where=s>0)
            hazard=np.r_[0,np.cumsum([2*row[2]/(2*row[1]-row[2]) if row[1]>row[2] else np.nan for row in rows])]
        else:
            hazard=np.r_[0,[x[4] for x in rows]];se=np.r_[0,[x[5] for x in rows]];s=np.exp(-hazard)
            z=stats.norm.isf(a._num(o,'alpha',.05,1e-9,.999)/2);lowerh=np.full(len(hazard),np.nan);upperh=lowerh.copy()
            for j,row in enumerate(rows,1):
                if row[2]>0:lowerh[j],upperh[j]=hazard[j]-z*se[j],hazard[j]+z*se[j]
                else:lowerh[j],upperh[j]=lowerh[j-1],upperh[j-1]
            low=np.full(len(hazard),np.nan);high=low.copy();variance=0.
            for j,row in enumerate(rows,1):
                variance+=row[2]/(row[1]**2*np.exp(-row[2]/row[1]))
                if row[2]>0:low[j],high[j]=max(0.,s[j]-z*s[j]*np.sqrt(variance)),min(1.,s[j]+z*s[j]*np.sqrt(variance))
                else:low[j],high[j]=low[j-1],high[j-1]
            table['columns']+=['Hazard lower','Hazard upper']
            for j,row in enumerate(rows,1):row.extend([lowerh[j],upperh[j]])
        if o.get('sta.surv.lt.report.plot.sdf',True):
            ss=[a._series(group,times,s)]
            if showci:ss += [a._series('Lower confidence',times,low),a._series('Upper confidence',times,high)]
            r['charts'].append(a._chart(f'Survival: {group}',ss,'step','Time','Survival probability'))
        if i=='1621':
            if o.get('sta.surv.lt.report.plot.sdf1m',True):r['charts'].append(a._chart(f'Failure: {group}',[a._series(group,times,1-s)],'step','Time','1 − survival'))
            if o.get('sta.surv.lt.report.plot.sdflog',True):r['charts'].append(a._chart(f'Log survival: {group}',[a._series(group,times,logsurvival)],'step','Time','Log survival'))
        if o.get('sta.surv.lt.report.plot.hazard.cumulative',True):
            ss=[a._series(group,times,hazard)]
            if showci and i=='1622':ss += [a._series('Lower confidence',times,lowerh),a._series('Upper confidence',times,upperh)]
            r['charts'].append(a._chart(f'Cumulative hazard: {group}',ss,'step','Time','Cumulative hazard'))
    if i=='1621' and o.get('group'):
        compare_survival(data,o,r)


def compare_survival(data,o,r):
    """Weighted logrank scores with the exact tied-death risk-set covariance."""
    values,mask=a._numbers(data,[o.get('time'),o.get('status')],minimum=3)
    labels=a._frame(data).loc[mask,a._names(data,o['group'])[0]].to_numpy()
    present=pd.notna(labels);time,status=values[present].T;labels=labels[present]
    levels=pd.unique(labels);k=len(levels)
    if k<2:return
    score=np.zeros((3,k));covariance=np.zeros((3,k,k))
    for event_time in np.unique(time[status==1]):
        risk=np.array([np.sum((labels==level)&(time>=event_time)) for level in levels],float)
        events=np.array([np.sum((labels==level)&(time==event_time)&(status==1)) for level in levels],float)
        n=risk.sum();deaths=events.sum()
        if n<=1:continue
        proportions=risk/n;difference=events-deaths*proportions
        cov=deaths*(n-deaths)/(n-1)*(np.diag(proportions)-np.outer(proportions,proportions))
        for j,weight in enumerate([1.,n,np.sqrt(n)]):
            score[j]+=weight*difference;covariance[j]+=weight**2*cov
    rows=[]
    for j,name in enumerate(['Logrank','Gehan–Breslow–Wilcoxon','Tarone–Ware']):
        df=int(np.linalg.matrix_rank(covariance[j]));stat=score[j]@np.linalg.pinv(covariance[j],hermitian=True)@score[j] if df else None
        rows.append([name,k,df,stat,stats.chi2.sf(stat,df) if df else None])
        if df<k-1:r['warnings'].append(f'{name}: covariance rank {df} is below the nominal {k-1}; only estimable group contrasts are tested.')
    r['tables'].append(a._table('Survival distribution comparisons',['Test','Groups','df','Chi-square','p'],rows))
    r['notes'].append('Group comparisons weight each event-time score by 1 (Logrank), pooled at-risk count (Gehan–Breslow–Wilcoxon), or its square root (Tarone–Ware). Covariance includes the finite-population correction for tied deaths; censoring at an event time remains at risk for that event.')


def life(data,o,r):
    v,mask=a._numbers(data,[o.get('time'),o.get('status')],minimum=3);a._missing(r,mask);time,status=v.T
    if (time<0).any():raise ValueError('Survival times must be nonnegative.')
    groups=a._frame(data).loc[mask,a._names(data,o['group'])[0]].to_numpy() if o.get('group') else np.repeat('All',len(time))
    maxtime=a._num(o,'sta.surv.lt.maxtime.ui',float(np.max(time)),1e-12) if o.get('sta.surv.lt.maxtime.ui') not in (None,'') else float(np.max(time))
    width=a._num(o,'sta.surv.lt.timeintw',o.get('width',1),1) if o.get('sta.surv.lt.timeintw') not in (None,'') else a._num(o,'width',1,1)
    # Native core consumes full half-open bins and checks its upper-limit stop
    # after advancing one more bin. Preserve that observed boundary behavior.
    intervals=min(int(np.floor(time.max()/width))+1,int(np.floor(maxtime/width))+2)
    if intervals>10000:raise ValueError('More than 10000 intervals; increase interval width.')
    summaries=[]
    for group in pd.unique(groups):
        if pd.isna(group):continue
        use=groups==group;t=time[use];d=status[use];rows=[];survival=1.;xs=[0.];ss=[1.];dens=[];haz=[];greenwood=0.;median=None
        for j in range(intervals):
            lo=j*width;hi=(j+1)*width;ininterval=(t>=lo)&(t<hi)
            risk=int(np.sum(t>=lo))
            if risk==0:break
            deaths=int(np.sum(ininterval&(d==1)));censored=int(np.sum(ininterval&(d==0)))
            effective=risk-censored/2;q=deaths/effective if effective else 0;p=1-q;previous=survival;survival*=p
            density=previous*q/width;hazard=q/(width*(1-q/2))
            density_se=density*np.sqrt(greenwood+p/(effective*q)) if q and effective else 0.
            greenwood+=q/(effective*p) if effective and p else (np.inf if q else 0.)
            survival_se=survival*np.sqrt(greenwood) if np.isfinite(greenwood) else np.nan
            hazard_se=np.sqrt(max(0,hazard**2/(effective*q)*(1-width**2*hazard**2/4))) if q and effective else 0.
            if median is None and previous>=.5 and survival<.5:median=lo+width*(previous-.5)/(previous-survival)
            rows.append([lo,hi,risk,deaths,censored,effective,q,survival,density,hazard,survival_se,density_se,hazard_se]);xs.append(hi);ss.append(survival);dens.append(density);haz.append(hazard)
        r['tables'].append(a._table(f'Life table: {group}',['From','To','At risk','Events','Censored','Effective risk','Failure probability','Survival','Density','Hazard','Survival std. error','Density std. error','Hazard std. error'],rows))
        summaries.append([str(group),int(np.sum(d==1)),int(np.sum(d==0)),len(t),median])
        ss=np.asarray(ss);log=np.full(len(ss),np.nan);np.log(ss,out=log,where=ss>0)
        kind='step' if o.get('sta.surv.lt.plotstaircase',True) else 'line'
        for suffix,label,values,xvals,chartkind in [('sdf','Survival',ss,xs,kind),('sdf1m','1 − survival',1-ss,xs,kind),('sdflog','Log survival',log,xs,kind),('density','Probability density',dens,xs[:-1],'scatter'),('hazard','Hazard rate',haz,xs[:-1],'scatter')]:
            if o.get('sta.surv.lt.report.plot.'+suffix,True):r['charts'].append(a._chart(f'{label}: {group}',[a._series(group,xvals,values)],chartkind,'Time',label))
    if not r['tables']:raise ValueError('No observations remain after excluding missing group labels.')
    r['tables'].append(a._table('Survival summary',['Group','Failed','Censored','Total','Median survival time'],summaries))
    if o.get('sta.surv.lt.maxtime.ui') not in (None,''):r['notes'].append('Native compatibility: life-table bins remain full width and may extend beyond the selected upper limit.')


def run(i,data,o,r):
    if i in ('1309','1620','1621','1622','1610','1611'):
        data=recode(i,data,o,r)
        if i in ('1610','1611'):return roc(i,data,o,r)
        if i=='1309':return a._survival_base(i,data,o,r)
        return curves(i,data,o,r)
    if i=='1601':return probit(data,o,r)
    if i=='1630':
        if o.get('ba.groups.subject'):return repeated_agreement(data,o,r)
        choice(o,'sta.chart.ploty',0,1)
        a._survival_base(i,data,o,r)
        values,mask=a._numbers(data,[o.get('first'),o.get('second')],minimum=3)
        if o.get('sta.surv.ba.tablediffaverage.opt',False):r['tables'].append(a._table('Averages and differences',['Row','Average','Difference'],zip(np.flatnonzero(mask)+1,values.mean(axis=1),values[:,0]-values[:,1])))
        return
    return a._survival_base(i,data,o,r)


def probit(data,o,r):
    from statsmodels.tools.sm_exceptions import PerfectSeparationWarning,PerfectSeparationError
    import warnings
    model=choice(o,'sta.surv.probit.algo',0,3);correction=[.25,.49][choice(o,'sta.surv.prob_perc_cor',0,2)]
    sets=[('Series 1',[o.get('dose'),o.get('events'),o.get('total')])]
    extra=[o.get(k) for k in ('PROBIT_S_0.N','PROBIT_S_1.N','PROBIT_S_3.N')]
    if any(extra):
        if not all(extra):raise ValueError('The additional dose series needs Dose, Count and Sample Size variables together.')
        sets.append(('Series 2',extra))
    weights_table=np.asarray([10,12,14,16,18,20,23,26,29,32,35,37,39,41,43,45,46,47,48,49,50,49,48,47,46,45,43,41,39,37,35,32,29,26,23,20,18,16,14,12])/10
    potency={}
    for label,names in sets:
        v,mask=a._numbers(data,names,minimum=3);a._missing(r,mask);dose,events,total=v.T
        if o.get('sta.surv.probit.opt.intC',True):events,total=np.rint(events),np.rint(total)
        if (dose<0).any() or (total<1).any() or (events<0).any() or (events>total).any():raise ValueError('Dose must be nonnegative; sizes ≥1 and counts between zero and size.')
        if np.ptp(dose)==0:raise ValueError('Probit regression requires varying doses.')
        for mode in ([0,1] if model==2 else [model]):
            if mode==0 and (dose<=0).any():raise ValueError('Log-dose MLE requires strictly positive doses.')
            x=np.log10(dose) if mode==0 else dose
            cor=correction if mode==0 else .25
            p=events/total;p=np.where(events==0,cor/total,np.where(events==total,1-cor/total,p));probits=5+stats.norm.ppf(p)
            design=sm.add_constant(x,has_constant='add');initial=sm.OLS(probits-5,design).fit().params
            if mode==0:
                try:
                    with warnings.catch_warnings():
                        # Exact probabilities in grouped binomial data may be
                        # fitted perfectly without separating individual cases.
                        warnings.simplefilter('ignore' if ((events>0)&(events<total)).all() else 'error',PerfectSeparationWarning)
                        fit=sm.GLM(np.column_stack([events,total-events]),design,family=sm.families.Binomial(link=sm.families.links.Probit())).fit(start_params=initial,maxiter=60,tol=1e-8)
                except (PerfectSeparationWarning,PerfectSeparationError,np.linalg.LinAlgError) as exc:raise ValueError('Probit fit is separated or singular; finite coefficients cannot be reliably estimated.') from exc
                if not fit.converged or not np.isfinite(fit.params).all() or max(abs(fit.params))>1e6:raise ValueError('Probit fit did not converge to finite estimates.')
                coef=fit.params.copy();coef[0]+=5;name='MLE log10(Dose)';se=fit.bse;stat=fit.tvalues;pv=fit.pvalues
            else:
                weights=np.ones(len(p));valid=(probits>=3)&(probits<6.9)
                weights[valid]=np.interp(probits[valid],np.arange(30,70)/10,weights_table)
                fit=sm.WLS(probits,design,weights=weights).fit();coef=fit.params;se=fit.bse;stat=fit.tvalues;pv=fit.pvalues;name='Weighted LS Dose'
            eds=(np.asarray([4.,5.,6.])-coef[0])/coef[1]
            if mode==0:eds=10**eds
            potency.setdefault(mode,[]).append(eds)
            r['tables'].append(a._table(f'{label}: {name} coefficients',['Term','Estimate','Std. error','Statistic','p'],zip(['Intercept','Log10 dose' if mode==0 else 'Dose'],coef,se,stat,pv)))
            r['tables'].append(a._table(f'{label}: {name} adjusted responses',['Dose','Count','Sample size','Adjusted probability','Probit'],zip(dose,events,total,p,probits)))
            from .advanced_probit_reports import append
            append(r,f'{label}: {name}',mode,dose,x,events,total,p,probits,coef,None if mode==0 else weights)
            curveprob=np.r_[.01,np.arange(.05,1,.05),.99]
            linear=5+stats.norm.ppf(curveprob)
            xs=(linear-coef[0])/coef[1] if abs(coef[1])>1e-15 else np.linspace(x.min(),x.max(),len(linear))
            plotprobit=o.get('sta.surv.probit.opt0',False)
            ss=[a._series('Observed',x,probits if plotprobit else 100*p),{**a._series('Fitted',xs,linear if plotprobit else 100*curveprob),'type':'line'}]
            r['charts'].append(a._chart(f'{label}: {name}',ss,'scatter','Log10 dose' if mode==0 else 'Dose','Probit (5 + normal score)' if plotprobit else 'Response percent'))
    for mode,sets_ed in potency.items():
        if len(sets_ed)==2:
            factors=[.5*(ed[2]/ed[1]+ed[1]/ed[0]) if ed[0]!=0 and ed[1]!=0 else np.nan for ed in sets_ed]
            denominator=sets_ed[1][1]*factors[1]
            relative=sets_ed[0][1]*factors[0]/denominator if denominator!=0 else None
            r['tables'].append(a._table(('MLE' if mode==0 else 'LS')+' coefficient of cumulation',['Series 1 factor','Series 2 factor','Coefficient of cumulation'],[[*factors,relative]]))
    r['notes'].append('Probit scale is 5 + Φ⁻¹(p); logarithmic dose uses base 10. Endpoint correction initializes MLE; least squares uses 0.25/N and a fixed Finney weight grid.')


def repeated_agreement(data,o,r):
    v,mask=a._numbers(data,[o.get('first'),o.get('second')],minimum=4)
    subject=a._names(data,o['ba.groups.subject'])[0];g=a._frame(data).loc[mask,subject].to_numpy();valid=pd.notna(g);v=v[valid];g=g[valid]
    groups=[v[g==level] for level in pd.unique(g)];n=len(v);k=len(groups)
    if k<2 or any(len(z)<2 for z in groups):raise ValueError('Repeated-subject agreement requires at least two subjects with two pairs each.')
    differences=[z[:,0]-z[:,1] for z in groups];means=np.asarray([z.mean() for z in differences]);bias=means.mean();between=means.var(ddof=1)
    within=sum(np.sum((z-z.mean())**2) for z in differences)/(n-k);adjustment=1-np.mean([1/len(z) for z in differences]);variance=between+adjustment*within
    critical=stats.norm.isf(a._num(o,'alpha',.05,1e-9,.999)/2);sd=np.sqrt(variance);lower=bias-critical*sd;upper=bias+critical*sd
    r['tables']=[a._table('Repeated-subject agreement',['Subjects','N','Bias','Within variance','Subject-mean variance','Total variance','Lower agreement limit','Upper agreement limit'],[[k,n,bias,within,between,variance,lower,upper]])]
    average=v.mean(axis=1);difference=v[:,0]-v[:,1];ends=[average.min(),average.max()]
    ss=[a._series(level,average[g==level],difference[g==level]) for level in pd.unique(g)]
    ss += [{**a._series(label,ends,[value,value]),'type':'line'} for label,value in [('Bias',bias),('Lower agreement',lower),('Upper agreement',upper)]]
    r['charts']=[a._chart('Repeated-subject Bland-Altman',ss,'scatter','Pair mean','Method 1 − Method 2')]
    if o.get('sta.surv.ba.tablediffaverage.opt',False):r['tables'].append(a._table('Averages and differences',['Subject','Average','Difference'],zip(g,average,difference)))
    r['notes'].append('Bias is the unweighted mean of subject mean differences. Total variance = variance(subject means) + [1 − mean(1/nᵢ)] × pooled within-subject variance.')
