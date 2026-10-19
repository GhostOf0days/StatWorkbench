"""Factorial ANOVA arithmetic using orthogonal projections and residualized partial
regressions to compute marginal sums of squares for complete-case data.
"""
from __future__ import annotations
import itertools
import math
import numpy as np


def marginal_components(frame, response, factors):
    """Native marginal-total decomposition, including unequal cell counts.

Centering the response and evaluating within-cell residuals directly avoids
catastrophic cancellation while preserving the sums of squares.
"""
    values=frame[response].to_numpy(dtype=float)
    if len(values)<3:raise ValueError('At least three complete observations are required.')
    levels=[frame[f].nunique() for f in factors]
    if min(levels)<2:raise ValueError('Each factor needs at least two levels.')
    centered=values-values.mean()
    data=frame[factors].copy();key='__anova_response__'
    while key in data:key+='_' 
    data[key]=centered
    total=float(centered@centered);components={}
    tolerance=64*np.finfo(float).eps*max(total,1)
    for size in range(1,len(factors)+1):
        for members in itertools.combinations(range(len(factors)),size):
            members=frozenset(members)
            group=data.groupby([factors[i] for i in sorted(members)],observed=True)[key]
            means=group.mean();counts=group.size()
            ss=float(np.dot(means*means,counts))-sum(value[0] for subset,value in components.items() if subset<members)
            if ss < -tolerance:
                raise ValueError('The ANOVA marginal decomposition produced negative sums of squares (ANOVA_NEGSS); use a different model for these unbalanced data.')
            components[members]=(max(0.,ss),math.prod(levels[i]-1 for i in members))
    groups=data.groupby(factors,observed=True)[key]
    errors=centered-groups.transform('mean').to_numpy()
    residual=(float(errors@errors),len(values)-math.prod(levels))
    return components,residual


def denominator_terms(members,random_factors,n_factors):
    """Return signed MS terms and the native denominator-df convention.

None identifies residual error. A composite all-random test uses the
highest interaction df; a fixed main effect with two random factors uses
the signed sum of interaction dfs. Neither uses Satterthwaite df.
"""
    members=frozenset(members);random_factors=frozenset(random_factors)
    if not random_factors or len(members)==n_factors:return [(1,None)],'single'
    outside=random_factors-members
    if not outside:return [(1,None)],'single'
    terms=[]
    for size in range(1,len(outside)+1):
        terms.extend((1 if size%2 else -1,members|frozenset(extra)) for extra in itertools.combinations(sorted(outside),size))
    mode='highest' if len(random_factors)==n_factors and len(terms)>1 else 'signed' if len(terms)>1 else 'single'
    return terms,mode


def denominator(components,residual,members,random_factors,n_factors):
    terms,mode=denominator_terms(members,random_factors,n_factors)
    values=[(sign,residual if term is None else components[term]) for sign,term in terms]
    ms=sum(sign*ss/df if df>0 else math.nan for sign,(ss,df) in values)
    if mode=='highest':df=components[frozenset(range(n_factors))][1]
    elif mode=='signed':df=sum(sign*value[1] for sign,value in values)
    else:df=values[0][1][1]
    return ms,df,terms
