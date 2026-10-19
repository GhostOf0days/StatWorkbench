"""Subgroup and plotting controls for statistical process-control charts."""
import math
from functools import lru_cache
import numpy as np
import pandas as pd
from scipy import special, stats, integrate
from . import advanced as a
from .advanced_charts import choice


@lru_cache(maxsize=64)
def range_constants(n):
    known={2:(1.128,.8525),3:(1.693,.8884),4:(2.059,.8798),5:(2.326,.8641),6:(2.534,.8480),7:(2.704,.8332),8:(2.847,.8198),9:(2.970,.8078),10:(3.078,.7971)}
    if n in known:return known[n]
    # Integrate the normal order-statistic density for E(range) and E(range²).
    if n<2 or n>1000:raise ValueError('Subgroups must contain 2–1000 measurements.')
    maximum=integrate.quad(lambda z:z*n*stats.norm.pdf(z)*stats.norm.cdf(z)**(n-1),-9,9,epsabs=1e-9)[0]
    def outer(lo):
        philo=stats.norm.cdf(lo)
        inner=integrate.quad(lambda hi:(hi-lo)**2*stats.norm.pdf(hi)*max(0,stats.norm.cdf(hi)-philo)**(n-2),lo,9,epsabs=1e-8)[0]
        return n*(n-1)*stats.norm.pdf(lo)*inner
    second=integrate.quad(outer,-9,9,epsabs=1e-7)[0];mean=2*maximum
    return mean,math.sqrt(max(0,second-mean*mean))


def subgroups(data,o):
    names=a._names(data,o.get('columns'));f=a._numeric_frame(a._frame(data)[names])
    layout=choice(o,'sta.cc.datalayout',0 if o.get('sta.cc.xbar.GROUPS') else 3,4)
    if layout==0:
        group=a._names(data,o.get('sta.cc.xbar.GROUPS'))[0];g=a._frame(data)[group]
        out=[f.loc[g==level].to_numpy().ravel() for level in pd.unique(g) if pd.notna(level)]
    elif layout==1:
        if len(names)!=1:raise ValueError('Fixed-size subgroup layout requires one measurement column.')
        size=a._num(o,'sta.cc.xbar.d2.subgrsize',2,2,1000,True);v=f.to_numpy().ravel();v=v[np.isfinite(v)]
        if len(v)%size:raise ValueError('Number of observations must be divisible by the fixed subgroup size.')
        out=list(v.reshape(-1,size))
    elif layout==2:out=[f[name].to_numpy() for name in names]
    else:out=list(f.to_numpy())
    out=[z[np.isfinite(z)] for z in out]
    if len(out)<2 or any(len(z)<2 for z in out):raise ValueError('At least two subgroups with two finite observations each are required.')
    return out


def size_values(data,o,counts,mask):
    raw=o.get('sta.cc.subgr_size',o.get('size_column'))
    if isinstance(raw,str) and raw in data['columns']:
        v=a._numeric_frame(a._frame(data)[[raw]]).to_numpy()[:,0][mask]
    else:
        value=a._num({'value':raw},'value',None,1e-12);v=np.repeat(value,len(counts))
    if not np.isfinite(v).all() or np.any(v<=0):raise ValueError('Subgroup sizes must be positive and complete.')
    return v


def run(i,data,o,r):
    k=a._num(o,'sta.cc.ao.nosigmas',o.get('sigmas',3),1e-12,20)
    if i in ('4102','4103'):
        estimator=choice(o,'sta.cc.stddevest',0,2 if i=='4102' else 1);groups=subgroups(data,o);sizes=np.asarray([len(z) for z in groups]);means=np.asarray([z.mean() for z in groups]);center=np.average(means,weights=sizes)
        limits=sizes if choice(o,'sta.cc.uneqgroup.title',0,2)==0 else np.repeat(sizes.mean(),len(sizes))
        if i=='4102':
            v=np.asarray([np.ptp(z) for z in groups]);constants=np.asarray([range_constants(len(z)) for z in groups]);sigma=v.sum()/constants[:,0].sum()
            if estimator==1:
                d2,d3=constants.T;sigma=np.sum(d2*v/d3**2)/np.sum(d2**2/d3**2)
                r['notes'].append('Minimum-variance linear unbiased sigma combines independent subgroup ranges using weights proportional to d₂/d₃²; the default remains Rbar.')
            if np.ptp(limits)==0 and np.ptp(sizes)!=0:
                # Smooth expected range constants at the selected average size.
                low=int(math.floor(limits[0]));high=int(math.ceil(limits[0]));fraction=limits[0]-low
                c=np.asarray(range_constants(low))*(1-fraction)+np.asarray(range_constants(high))*fraction;constants=np.tile(c,(len(groups),1))
            spread_center=sigma*constants[:,0];spread_sd=sigma*constants[:,1];label='Range'
        else:
            v=np.asarray([z.std(ddof=1) for z in groups]);c=np.sqrt(2/(sizes-1))*np.exp(special.gammaln(sizes/2)-special.gammaln((sizes-1)/2));sigma=v.sum()/c.sum()
            c=np.sqrt(2/(limits-1))*np.exp(special.gammaln(limits/2)-special.gammaln((limits-1)/2));spread_center=sigma*c;spread_sd=sigma*np.sqrt(1-c*c);label='Standard deviation'
        a._control(r,'Subgroup means',means,center,center-k*sigma/np.sqrt(limits),center+k*sigma/np.sqrt(limits))
        a._control(r,label,v,spread_center,np.maximum(0,spread_center-k*spread_sd),spread_center+k*spread_sd)
        r['tables'].append(a._table('Sigma estimate',['Sigma','Subgroups','Total N'],[[sigma,len(groups),int(sizes.sum())]]));return
    if i in ('4105','4107'):
        values,mask=a._numbers(data,o.get('count_column'),minimum=2);counts=values[:,0];sizes=size_values(data,o,counts,mask)
        if np.any(counts<0) or np.any(counts!=np.floor(counts)):raise ValueError('Counts must be nonnegative integers.')
        if i=='4105':
            if np.any(counts>sizes) or np.any(sizes!=np.floor(sizes)):raise ValueError('Defectives cannot exceed integer subgroup sizes.')
            target=o.get('sta.cc.p.prop.target.opt')
            p=counts.sum()/sizes.sum() if target in (None,'') else a._num(o,'sta.cc.p.prop.target.opt',0,0,1)
            se=np.sqrt(p*(1-p)/sizes);plot=choice(o,'sta.charts.plot',2,3)
            if plot in (0,2):a._control(r,'P chart',counts/sizes,p,np.maximum(0,p-k*se),np.minimum(1,p+k*se))
            if plot in (1,2):a._control(r,'NP chart',counts,p*sizes,np.maximum(0,(p-k*se)*sizes),np.minimum(sizes,(p+k*se)*sizes))
            mode=choice(o,'sta.showstatsfor',0,3)
            if mode==2:r['tables']=[]
            elif mode==1:
                for table in r['tables']:table['rows']=[row for row in table['rows'] if row[-1]]
        else:
            u=counts.sum()/sizes.sum();se=np.sqrt(u/sizes);a._control(r,'U chart',counts/sizes,u,np.maximum(0,u-k*se),u+k*se)
        return
    if i=='4108':
        choice(o,'sta.cc.stddevest',0,1);y=a._padded_series(data,o.get('column'),minimum=2)
        span=a._num(o,'help.mr_span',2,2,min(50,len(y)),True)
        ranges=np.ptp(np.lib.stride_tricks.sliding_window_view(y,span),axis=1);avg=ranges.mean()
        d2,d3=(1.1283791671,.8525033) if span==2 else range_constants(span)
        sigma=avg/d2
        rawtarget=o.get('help.individuals_target','');center=y.mean() if rawtarget in (None,'') else a._num(o,'help.individuals_target',0)
        a._control(r,'Individuals',y,center,center-k*sigma,center+k*sigma)
        # A moving range belongs to the final observation in its window.
        # Preserve the leading unavailable rows, as the native chart does.
        padding=np.full(span-1,np.nan)
        a._control(r,'Moving range',np.r_[padding,ranges],np.r_[padding,np.repeat(avg,len(ranges))],np.r_[padding,np.repeat(max(0,avg-k*d3*sigma),len(ranges))],np.r_[padding,np.repeat(avg+k*d3*sigma,len(ranges))])
        r['tables'].append(a._table('Sigma estimate',['Sigma','Moving range span','Process mean'],[[sigma,span,center]]))
        r['notes'].append('Individuals/moving-range charts use average moving range with span 2 as the sigma estimator. Other spans and a fixed process mean are not currently supported.')
        return
    values,mask=a._numbers(data,o.get('column'),minimum=3);y=values[:,0]
    if o.get('GROUPS'):
        group=a._names(data,o['GROUPS'])[0]
        raw=a._numeric_frame(a._frame(data)[[group]]).loc[mask,group].to_numpy()
        if not np.isfinite(raw).all():raise ValueError('CUSUM group codes must be complete numeric values.')
        g=np.trunc(raw).astype(int);levels=np.arange(g.min(),g.max()+1)
        if len(levels)>10000:raise ValueError('Too many CUSUM groups.')
        samples=[y[g==level] for level in levels]
        if any(len(z)==0 for z in samples) or len({len(z) for z in samples})!=1:raise ValueError('Native CUSUM requires contiguous integer group codes and equal subgroup sizes.')
    else:
        samples=[np.asarray([v]) for v in y];levels=np.arange(1,len(y)+1)
    means=np.asarray([z.mean() for z in samples]);size=len(samples[0]);sigma=y.std(ddof=1)
    if sigma<=0:raise ValueError('CUSUM requires positive variability.')
    target=y.mean() if o.get('sta.cc.target.auto',True) else a._num(o,'sta.cc.target',0)
    H=a._num(o,'H',o.get('h',4),1e-12,1e6);K=a._num(o,'K',o.get('k',.5),1e-12,1e6)
    cumulative=np.cumsum(means-target);center=a._num(o,'sta.cc.subgr_center',0,0,len(means),True);center=(center or len(means))-1
    index=np.arange(len(means));scale=sigma/np.sqrt(size)
    lower=cumulative[center]-2*H*scale+index*K*scale
    upper=cumulative[center]+2*H*scale-index*K*scale
    r['tables'].append(a._table('CUSUM subgroups',['Group','Size','Mean','SD','Cumulative sum'],zip(levels,[size]*len(means),means,[z.std(ddof=1) if len(z)>1 else None for z in samples],cumulative)))
    se=sigma/np.sqrt(len(y));low=max(0,y.mean()-k*se);high=y.mean()+k*se
    r['tables'].append(a._table('CUSUM summary',['Grand mean','Global SD','Standard error','Target','Lower limit','Upper limit'],[[y.mean(),sigma,se,target,low,high]]))
    ss=[a._series('Cumulative deviations',levels,cumulative),a._series('Mean deviation',levels,np.repeat(np.mean(means-target),len(means))),a._series('Lower V-mask',levels,lower),a._series('Upper V-mask',levels,upper)]
    r['charts'].append(a._chart('CUSUM V-mask',ss,'line','Group','Cumulative deviation'))
    r['notes'].append('Native CUSUM uses raw cumulative subgroup-mean deviations and global sample SD. Its V-mask starts at selected cumulative sum ± 2H × SD/√subgroup-size, with slope ±K × SD/√subgroup-size from the first group.')
