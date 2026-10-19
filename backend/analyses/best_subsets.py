"""Exact best residual-sum-of-squares model for every predictor count.

The search streams subsets, retains one incumbent per size, and prunes only
with a lower bound from the unrestricted remaining superset. Greedy fits seed
incumbents; they never substitute for the completed exact search. Worst-case
cost is exponential. No partial result is returned on interruption.
"""
from __future__ import annotations
import numpy as np


def best_subsets(x, y):
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float)
    if x.ndim!=2 or y.ndim!=1 or len(x)!=len(y):
        raise ValueError('Best subsets requires aligned numeric predictors and response.')
    n,p=x.shape
    if p<1 or n<=p+1 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Best subsets requires finite data and more rows than coefficients.')
    centered=x-x.mean(axis=0);response=y-y.mean()
    scale=np.linalg.norm(centered,axis=0)
    if np.any(scale==0) or np.linalg.matrix_rank(centered)<p:
        raise ValueError('Best subsets requires a full-rank design; remove constant or collinear predictors.')
    # QR compression preserves every subset's residual norm while making the
    # enumeration independent of the original row count. Scaling columns does
    # not change their spans and improves the projection's conditioning.
    compressed=np.linalg.qr(np.column_stack([centered/scale,response]),mode='r')
    a,b=compressed[:,:p],compressed[:,p]
    m=len(b);eps=np.finfo(float).eps
    best_rss=np.full(p+1,np.inf);winners=[None]*(p+1)
    best_rss[0]=float(b@b);winners[0]=()

    def record(indices,residual):
        combo=tuple(sorted(indices));size=len(combo);rss=float(residual@residual)
        old=best_rss[size]
        # Deterministic lexicographic treatment of numerical ties. This is
        # relative to the residual norm, not the much larger response norm.
        tolerance=8*eps*max(rss,old if np.isfinite(old) else 0.,np.finfo(float).tiny)
        if rss<old-tolerance or (abs(rss-old)<=tolerance and combo<winners[size]):
            best_rss[size]=rss;winners[size]=combo

    # A single forward sequence supplies feasible incumbents of every size.
    # These are only upper bounds; all other subsets remain eligible below.
    available=list(range(p));selected=[];basis=np.empty((m,0));residual=b.copy()
    while available:
        vectors=a[:,available].copy()
        for _ in range(2):
            if basis.shape[1]:vectors-=basis@(basis.T@vectors)
        norms=np.linalg.norm(vectors,axis=0)
        if np.any(norms==0):raise ValueError('Predictor projections are numerically singular.')
        gains=np.square(vectors.T@residual)/np.square(norms)
        pick=int(np.argmax(gains));unit=vectors[:,pick]/norms[pick]
        selected.append(available.pop(pick));basis=np.column_stack([basis,unit])
        residual=residual-unit*(unit@residual);record(selected,residual)

    # Iterative DFS avoids the Python recursion limit. One shared basis and
    # one residual per depth keep search workspace O(p²), not O(2**p).
    q=np.empty((m,p));residuals=np.empty((m,p+1));residuals[:,0]=b
    chosen=np.empty(p,dtype=int);next_column=np.zeros(p+1,dtype=int)
    depth=0;visited=0;pruned=0;bound_checks=0
    while depth>=0:
        j=int(next_column[depth])
        if j>=p:
            depth-=1;continue
        next_column[depth]=j+1
        v=a[:,j].copy()
        for _ in range(2):
            if depth:v-=q[:,:depth]@(q[:,:depth].T@v)
        length=np.linalg.norm(v)
        if length==0:raise ValueError('Predictor projections are numerically singular.')
        unit=v/length;q[:,depth]=unit;chosen[depth]=j
        residuals[:,depth+1]=residuals[:,depth]-unit*(unit@residuals[:,depth])
        size=depth+1;visited+=1
        record(chosen[:size],residuals[:,size])
        remaining=p-j-1
        if not remaining:continue
        # A descendant can fit no better than selected + ALL remaining
        # columns. Subtract a conservative rounding allowance from that lower
        # bound; ill-conditioned bounds merely prune less, never more.
        if remaining>=3:
            allowed=list(chosen[:size])+list(range(j+1,p));design=a[:,allowed]
            beta,_,rank,_=np.linalg.lstsq(design,b,rcond=None);bound_checks+=1
            if rank==len(allowed):
                error=b-design@beta;rss=float(error@error)
                envelope=np.linalg.norm(b)+np.linalg.norm(design)*np.linalg.norm(beta)
                roundoff=128*eps*m*envelope*envelope
                lower=max(0.,rss-roundoff)
                if np.all(best_rss[size+1:size+remaining+1]<lower):
                    pruned+=1;continue
        depth+=1;next_column[depth]=j+1
    return winners,{'complete':True,'strategy':'Exact streamed QR search with superset residual bounds',
        'predictors':p,'visited_subsets':visited,'pruned_branches':pruned,
        'bound_checks':bound_checks,'retained_models':p+1}
