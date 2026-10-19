"""Model coding and proximity recurrences."""
import heapq
import math
import numpy as np
from scipy.spatial.distance import pdist, squareform
from patsy.contrasts import ContrastMatrix, Treatment, Helmert


class NativeDummy:
    """Dummy contrasts use the last category as the reference."""
    def code_with_intercept(self,levels):return Treatment(reference=-1).code_with_intercept(levels)
    def code_without_intercept(self,levels):return Treatment(reference=-1).code_without_intercept(levels)


class NativeOrthogonal:
    """Build integer orthogonal contrasts with a negative Helmert basis."""
    def code_without_intercept(self,levels):
        contrast=Helmert().code_without_intercept(levels)
        return ContrastMatrix(-contrast.matrix,contrast.column_suffixes)
    def code_with_intercept(self,levels):
        contrast=self.code_without_intercept(levels)
        return ContrastMatrix(np.column_stack([np.ones(len(levels)),contrast.matrix]),['[mean]']+contrast.column_suffixes)


def rotate_orthomax(loadings, gamma):
    """Pairwise orthogonal sweeps without Kaiser normalization."""
    values=np.array(loadings,dtype=float,copy=True)
    p,k=values.shape
    transform=np.eye(k)
    if not np.isfinite(gamma) or gamma<0:
        raise ValueError('Orthomax gamma must be finite and nonnegative.')
    def objective():
        squares=values**2
        return float(np.sum(squares**2)-gamma/p*np.sum(np.sum(squares,axis=0)**2))
    old=objective();small_steps=0;tol=1e-9
    for _ in range(1000):
        changed=False
        for i in range(k-1):
            for j in range(i+1,k):
                u=values[:,i]**2-values[:,j]**2
                v=2*values[:,i]*values[:,j]
                a=p*np.sum(u*u-v*v)+gamma*(v.sum()**2-u.sum()**2)
                b=2*(p*np.sum(u*v)-gamma*u.sum()*v.sum())
                if abs(b)<=tol*abs(a):continue
                angle=math.atan2(b,a)/4
                c,s=math.cos(angle),math.sin(angle)
                for matrix in (values,transform):
                    left=matrix[:,i].copy();right=matrix[:,j].copy()
                    matrix[:,i]=c*left+s*right;matrix[:,j]=c*right-s*left
                changed=True
        current=objective()
        improvement=(current-old)/current if current>0 else 0
        small_steps=small_steps+1 if improvement<=tol else 0
        old=current
        if not changed or small_steps>=2:break
    signs=np.where(values.sum(axis=0)>0,1.,-1.)
    values*=signs;transform*=signs
    order=np.argsort(-np.sum(values**2,axis=0),kind='stable')
    return values[:,order],transform[:,order]


def native_proximity(x,metric,power=2,root=2):
    """Return the native proximity matrix and whether larger is nearer."""
    similarity=metric in ('cosine','angular')
    if similarity:
        norm=np.linalg.norm(x,axis=1)
        denominator=norm[:,None]*norm[None,:]
        valid=(norm[:,None]**2>np.finfo(float).eps)&(norm[None,:]**2>np.finfo(float).eps)
        matrix=np.divide(x@x.T,denominator,out=np.zeros_like(denominator),where=valid)
        if metric=='angular':
            with np.errstate(divide='ignore',invalid='ignore'):matrix=1-1/(np.pi*matrix)
        np.fill_diagonal(matrix,1.)
    else:
        if metric=='generalized':distance=pdist(x,metric='minkowski',p=power)**(power/root)
        else:distance=pdist(x,metric=metric,**({'p':power} if metric=='minkowski' else {}))
        matrix=squareform(distance)
    if not np.isfinite(matrix).all():
        raise ValueError('The selected proximity is nonfinite; native angular cosine is undefined for an orthogonal or zero-length pair.')
    return matrix,similarity


def native_linkage(matrix,method,beta=-.25,similarity=False):
    """Lance–Williams recurrences on the selected proximity, without squaring."""
    n=len(matrix);active=set(range(n));size={i:1 for i in active}
    distances={(i,j):float(matrix[i,j]) for i in range(n) for j in range(i+1,n)}
    direction=-1 if similarity else 1
    heap=[(direction*d,i,j) for (i,j),d in distances.items()];heapq.heapify(heap)
    rows=[]
    def get(i,j):return distances[min(i,j),max(i,j)]
    for step in range(n-1):
        while True:
            _,left,right=heapq.heappop(heap)
            if left in active and right in active:break
        merged=get(left,right);nl,nr=size[left],size[right];node=n+step
        active.remove(left);active.remove(right)
        for other in sorted(active):
            dl,dr=get(left,other),get(right,other);no=size[other]
            if method=='single':new=max(dl,dr) if similarity else min(dl,dr)
            elif method=='complete':new=min(dl,dr) if similarity else max(dl,dr)
            elif method=='average':new=(nl*dl+nr*dr)/(nl+nr)
            elif method=='weighted':new=(dl+dr)/2
            elif method=='flexible':new=(1-beta)*(dl+dr)/2+beta*merged
            elif method=='centroid':new=(nl*dl+nr*dr)/(nl+nr)-nl*nr*merged/(nl+nr)**2
            elif method=='median':new=(dl+dr)/2-merged/4
            elif method=='ward':new=((nl+no)*dl+(nr+no)*dr-no*merged)/(nl+nr+no)
            else:raise ValueError('Unknown linkage method.')
            distances[other,node]=new;heapq.heappush(heap,(direction*new,other,node))
        rows.append([left,right,merged,nl+nr]);size[node]=nl+nr;active.add(node)
    return np.asarray(rows,dtype=float)


def cut_membership(linkage,counts):
    """Cut by merge count, including nonmonotonic native similarities."""
    n=len(linkage)+1;active={i:[i] for i in range(n)};saved={}
    def snapshot():
        result=np.zeros(n,dtype=int)
        for group,members in enumerate(sorted(active.values(),key=min),1):result[members]=group
        saved[len(active)]=result
    snapshot()
    for step,row in enumerate(linkage):
        active[n+step]=active.pop(int(row[0]))+active.pop(int(row[1]));snapshot()
    return np.column_stack([saved[k] for k in counts])


def dendrogram_series(linkage,labels,similarity=False):
    n=len(labels);children={n+i:(int(row[0]),int(row[1])) for i,row in enumerate(linkage)}
    order=[];stack=[2*n-2]
    while stack:
        node=stack.pop()
        if node<n:order.append(node)
        else:stack.extend(reversed(children[node]))
    position={leaf:5+10*i for i,leaf in enumerate(order)}
    height={leaf:1. if similarity else 0. for leaf in order};series=[]
    for i,row in enumerate(linkage):
        left,right=children[n+i];h=float(row[2]);a,b=position[left],position[right]
        series.append(dict(name=f'Node {i+1}',x=[a,a,b,b],y=[height[left],h,h,height[right]]))
        position[n+i]=(a+b)/2;height[n+i]=h
    return series,{str(position[leaf]):labels[leaf] for leaf in order}
