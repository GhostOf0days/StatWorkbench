"""Model controls and analysis implementations."""
from __future__ import annotations
import copy,itertools,math
import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster import hierarchy
from scipy.spatial.distance import pdist,squareform
from .basic_model_fields import FIELDS
from .basic_options import boolean,index,descriptive_table
from .basic_native_models import native_proximity,native_linkage,cut_membership,dendrogram_series,NativeDummy,NativeOrthogonal
from .native_posthoc import range_survival,ordered_groups


def extend_catalog(entries):
    for entry in entries:
        aid=entry['id']
        if aid not in FIELDS:continue
        existing={f['key'] for f in entry['fields']}
        entry['fields'].extend(copy.deepcopy(f) for f in FIELDS[aid] if f['key'] not in existing)
        remove={'1102':{'tukey'},'1103':{'tukey'},'1104':{'factors'},'1105':{'factors'},'1107':{'factors'},'1109':{'response','coding'},'1121':{'rotation'},'1132':{'linkage','metric','power','clusters'},'1310':{'model'}}.get(aid,set())
        entry['fields']=[f for f in entry['fields'] if f['key'] not in remove]
        if aid=='1104':
            entry['fields']=[f for f in entry['fields'] if f['key']!='interactions']
            entry['fields'].append(dict(key='sta.anova.ao_nointer',label='No Interactions / Randomized Block Design',type='boolean',default=False,required=False))
        if aid in ('1301','1302'):
            entry['fields']=[f for f in entry['fields'] if f['key']!='intercept']
            entry['fields'].append(dict(key='sta.reg.nointercept',label='No intercept model',type='boolean',default=False,required=False))
        for f in entry['fields']:
            if f['key'] in ('factor_1','factor_2','factor_3','factor_a','factor_b','responses'):f['required']=True
        if aid in ('1301','1302','1303','1304','1305','1306','1307','1310','1110','1120','1130','1132'):
            entry['limitations']=['Implementation choices and supported options are stated in analysis results.']
        if aid in ('1104','1105'):
            entry['description']='Factorial ANOVA with fixed/random factor choices, restricted mixed-model F tests and explicit report conventions.'
            entry['limitations']=['Native marginal sums of squares are the default for fixed and random factors. Negative marginal SS are rejected as in the native routine. Fixed-only Type II/III sums of squares remain explicit extensions.']
            for field in entry['fields']:
                if field['key']=='ss_type':field['default']='native';field['options'].insert(0,{'value':'native','label':'Native marginal sums of squares'})
        if aid=='1104':entry['limitations'].append('Compatibility behavior: native mixed/random models display interaction p=0 because their report reads an unwritten probability slot; this confirmed quirk is preserved and explained in results.')
        if aid=='1105':entry['limitations'].append('Confirmed native F/probability slot permutations in Random/Fixed/Random and Random/Random/Fixed models are preserved with explanatory result notes.')
        if aid=='1109':entry['limitations']=['GLM uses contrast-coded OLS and a joint multivariate model for fixed and random factor inputs. Numeric covariates are truncated toward zero; numeric factors require contiguous integer codes. Dummy coding uses the last reference category and orthogonal coding uses the negative Helmert integer basis. Text factor labels are also supported.']
        if aid=='1130':entry['description']='Supplied initial centers or seeded k-means++ followed by a recorded Lloyd sequence; selectable initial, iteration, summary and membership reports.'
        if aid=='1132':entry['description']='Agglomerative and flexible-beta linkage, supported distance controls, cluster-count ranges, proximity tables and dendrogram.'
        if aid=='1121':entry['limitations']=['Principal-component extraction. Native pairwise orthomax without Kaiser normalization, equamax gamma=number of variables/2; covariance loadings are rescaled by input SD. Eigenvector signs and floating-point roundoff can differ.']
        if aid=='1132':
            entry['limitations']=['Limited to 1000 objects. Native angular-cosine reciprocal formula is preserved; it is undefined at zero cosine. Native proximity-scale linkage recurrences are used; ties can differ.']
            for f in entry['fields']:
                if f['key'] in ('mv.distance.generalized.opt.power','mv.distance.generalized.opt.root'):f.update(min=1,max=10,integer=True)
        if aid=='1310':entry['description']='Multiple curve-model fits, bounded logistic transformation, intercept control and individual/combined comparison plots.'


def normalize(aid,opt):
    opt=dict(opt)
    if aid in ('1104','1105'):
        keys=[f'factor_{i}' for i in range(1,3 if aid=='1104' else 4)]
        if any(opt.get(k) for k in keys):
            if not all(opt.get(k) for k in keys):raise ValueError('Select every factor input.')
            opt['factors']=[opt[k] for k in keys]
        if aid=='1104' and 'sta.anova.ao_nointer' in opt:opt['interactions']=not boolean(opt,'sta.anova.ao_nointer')
    if aid=='1107' and (opt.get('factor_a') or opt.get('factor_b')):opt['factors']=[opt.get('factor_a'),opt.get('factor_b')]
    if aid in ('1102','1103') and 'sta.anova.showcontrasts' in opt:opt['tukey']=boolean(opt,'sta.anova.showcontrasts',True)
    if aid in ('1301','1302','1310') and 'sta.reg.nointercept' in opt:opt['intercept']=not boolean(opt,'sta.reg.nointercept')
    if aid=='1121':
        if 'sta.fa.rot.type' in opt:opt['rotation']=['none','equamax','quartimax','biquartimax','varimax','orthomax'][index(opt,'sta.fa.rot.type',0,5)]
        index(opt,'sta.method',0,0)
    if aid=='1132':
        if 'cluster.linkage' in opt:opt['linkage']=['single','complete','flexible','average','weighted','centroid','median','ward'][index(opt,'cluster.linkage',3,7)]
        if 'mv.distancemeasure' in opt:opt['metric']=['euclidean','sqeuclidean','chebyshev','cityblock','minkowski','generalized','cosine','angular'][index(opt,'mv.distancemeasure',1,7)]
        if 'mv.distance.generalized.opt.power' in opt:opt['power']=opt['mv.distance.generalized.opt.power']
    return opt


def regression_report(aid,fit,names,indexes,response,opt,result,b):
    if aid not in ('1301','1302','1303'):return result
    residual=np.asarray(fit.resid);fitted=np.asarray(fit.fittedvalues);x=np.asarray(fit.model.exog);n=len(residual)
    rmse=np.sqrt(fit.mse_resid)
    diagnostics=b.basic_help_reports.regression_vectors(fit)
    hat=diagnostics['hat']
    standard=residual/np.sqrt(np.sum(residual**2)/(n-1)) if boolean(opt,'sta.reg.stdres.emulateexcel') else diagnostics['standard']
    student=diagnostics['student'];deleted=diagnostics['deleted']
    kind=index(opt,'sta.reg.plot.resid.type',0,3) if aid=='1301' else 0
    plotted=[residual,standard,student,deleted][kind];resid_label=['Residual','Standardized residual','Studentized residual','Deleted t residual'][kind]
    for tab in result['tables']:
        if tab['title']=='Fitted values and residuals':
            tab['columns']+=['Standardized residual','Studentized residual','Deleted t residual','Leverage','PRESS residual','Cook distance','DFFITS']
            for row,s,t,d,h,pr,cd,dfit in zip(tab['rows'],standard,student,deleted,hat,diagnostics['press_residual'],diagnostics['cook'],diagnostics['dffits']):row.extend([s,t,d,h,pr,cd,dfit])
    if aid=='1301':
        if not boolean(opt,'sta.reg.ao.residuals',True):result['tables']=[t for t in result['tables'] if t['title']!='Fitted values and residuals']
    result['charts']=[]
    def scatter(title,xlabel,values,y=plotted):return dict(type='scatter',title=title,xLabel=xlabel,yLabel=resid_label,series=[dict(name=resid_label,x=list(values),y=list(y))])
    if boolean(opt,'sta.reg.lin.ao.0',aid=='1301'):result['charts'].append(scatter('Residuals vs fitted','Fitted',fitted))
    if boolean(opt,'sta.reg.lin.ao.resorder'):result['charts'].append(scatter('Residuals vs order','Source row',np.asarray(indexes)+1))
    if aid=='1301' and boolean(opt,'sta.reg.lin.ao.indep'):
        for i,name in enumerate(names):
            if name!='Intercept':result['charts'].append(scatter('Residuals vs '+name,name,x[:,i]))
    if aid=='1301':
        predictor_indices=[i for i,name in enumerate(names) if name!='Intercept']
        if boolean(opt,'sta.reg.lin.ao.1',True) and len(predictor_indices)==1:
            values=x[:,predictor_indices[0]];order=np.argsort(values)
            result['charts'].append(dict(type='scatter',title='Line fit',xLabel=names[predictor_indices[0]],yLabel='Response',series=[dict(name='Observed',x=list(values),y=list(response)),dict(name='Fitted',type='line',x=list(values[order]),y=list(fitted[order]))]))
        if boolean(opt,'sta.reg.lin.ao.res.ht-tests',True):
            from .advanced import residual_diagnostics
            if predictor_indices:
                columns=['Residual']+[names[i] for i in predictor_indices]
                data={'columns':columns,'rows':np.column_stack([residual,x[:,predictor_indices]]).tolist()}
                try:
                    diagnostics=residual_diagnostics(data,{'residuals':'Residual','predictors':columns[1:]})
                    result['tables'].extend(diagnostics['tables']);result['warnings'].extend(diagnostics['warnings'])
                except ValueError as exc:result['warnings'].append('Heteroscedasticity diagnostics unavailable: '+str(exc))
        if boolean(opt,'sta.reg.lin.ao.norm-qq-hist',True) and np.ptp(residual)>0:
            tests=[]
            if n>=3:
                test=stats.shapiro(residual);tests.append(['Shapiro–Wilk',test.statistic,test.pvalue])
            if n>=8:
                test=stats.normaltest(residual);tests.append(['D’Agostino K²',test.statistic,test.pvalue])
            result['tables'].append(b._table('Residual normality tests',['Test','Statistic','p-value'],tests))
            desc=b._descriptive('1001',pd.DataFrame({'Residual':residual}),{'columns':['Residual'],'sta.bst.ds.ao.0':True,'sta.chart.qq':True})
            result['charts'].extend(desc['charts'])
        if boolean(opt,'sta.reg.coldiag'):
            z=x/np.linalg.norm(x,axis=0);eigen,vectors=np.linalg.eigh(z.T@z);order=np.argsort(eigen)[::-1];eigen=eigen[order];vectors=vectors[:,order]
            indices=np.sqrt(eigen.max()/eigen);variance=vectors**2/eigen;proportions=variance/variance.sum(axis=1,keepdims=True)
            result['tables'].append(b._table('Collinearity diagnostics',['Dimension','Eigenvalue','Condition index']+names,[[i+1,eigen[i],indices[i]]+list(proportions[:,i]) for i in range(len(eigen))]))
    return result


def model_extras(aid,frame,opt,result,b):
    if aid in ('1304','1305','1307','1109'):
        columns=b._names(frame,opt,'predictors',0)
        response=opt.get('response')
        if response:columns=[response]+columns
        if boolean(opt,'sta.show.DS',aid!='1109') and columns:result['tables'].append(descriptive_table(frame,columns,b))
        if boolean(opt,'glm.showcorrs') and len(columns)>=2:result['tables'].extend(b._correlations('1009',frame,{'columns':columns})['tables'])
    if aid=='1303' and boolean(opt,'sta.reg.ao.plot.linefit',True):
        response,predictor=b._name(frame,opt,'response'),b._name(frame,opt,'predictor');clean=b._complete(frame,[response,predictor]);table=next(t for t in result['tables'] if t['title']=='Fitted values and residuals');fitted=np.array([r[2] for r in table['rows']]);x=clean[predictor].to_numpy();order=np.argsort(x)
        result['charts'].append(dict(type='scatter',title='Polynomial line fit',xLabel=predictor,yLabel=response,series=[dict(name='Observed',x=list(x),y=list(clean[response])),dict(name='Fitted',type='line',x=list(x[order]),y=list(fitted[order]))]))
    return result


CURVE_MODELS={'inv':'inverse','ln':'logarithmic','lin':'linear','quad':'quadratic','cub':'cubic','pow':'power','com':'compound','scurve':'sigmoid','logistic':'logistic','grow':'growth','exp':'exponential'}

def curves(frame,opt,b):
    has_model_options=any('sta.reg.model.'+k in opt for k in CURVE_MODELS)
    models=[v for k,v in CURVE_MODELS.items() if boolean(opt,'sta.reg.model.'+k,k=='lin')] if has_model_options or 'model' not in opt else [opt['model']]
    if not models:raise ValueError('Select at least one curve model.')
    result=b._result('1310');combined=[];summary=[];plot=index(opt,'sta.reg.lin.ao.plotfit',2,2);detail=index(opt,'sta.reg.modelsum',1,1)
    for model in models:
        r=b._regression('1310',frame,{**opt,'model':model})
        values=dict(next(t for t in r['tables'] if t['title']=='Model summary')['rows'])
        summary.append([model,values['N'],values['R²'],values['Adjusted R²'],values['Residual standard error'],values['F'],values['F p-value']])
        if detail:
            for tab in r['tables']:
                if len(models)>1:tab['title']=model+' — '+tab['title']
                result['tables'].append(tab)
        if plot:
            c=next(c for c in r['charts'] if c['title']=='Curve fit')
            if plot==1:c['title']=model+' fit';result['charts'].append(c)
            else:
                if not combined:combined.append(c['series'][0])
                fitted=c['series'][1];fitted['name']=model;combined.append(fitted)
        result['warnings'].extend(r['warnings']);result['notes'].extend(r['notes'])
    result['tables'].insert(0,b._table('Curve model comparison',['Model','N','R² (fit scale)','Adjusted R² (fit scale)','Residual SE (fit scale)','F','p-value'],summary))
    if plot==2:result['charts'].append(dict(type='scatter',title='Curve fits',xLabel=opt['predictor'],yLabel=opt['response'],series=combined))
    result['notes'].append('Fit-scale R² values from differently transformed responses are not directly comparable; transformed models report their actual regression scale.')
    return result


def one_way(aid,frame,opt,result,b):
    groups=b._groups(frame,opt) if aid=='1103' else [(c,b._vector(frame,c)) for c in b._names(frame,opt,minimum=2)]
    groups=ordered_groups(groups)
    df=sum(len(x) for _,x in groups)-len(groups);mse=sum(np.sum((x-np.mean(x))**2) for _,x in groups)/df
    pooled=index(opt,'means.ci.vartype.ui',0,1)==1;conf=b._conf(opt);means=[]
    for name,x in groups:
        sd=np.std(x,ddof=1);se=math.sqrt(mse/len(x)) if pooled else sd/math.sqrt(len(x));critical=stats.t.ppf((1+conf)/2,df if pooled else len(x)-1);mean=np.mean(x)
        means.append([name,len(x),mean,sd,mean-critical*se,mean+critical*se])
    result['tables']=[t for t in result['tables'] if t['title']!='Group summaries' and not t['title'].startswith('Tukey HSD')]
    if boolean(opt,'sta.show.DS',True):result['tables'].append(b._table('Group summaries',['Group','N','Mean','SD','Mean CI lower','Mean CI upper'],means))
    if boolean(opt,'anova.plot.meanci_intervals.ui',True):
        series=[dict(name='Mean',x=list(range(1,len(means)+1)),y=[r[2] for r in means])]
        series.extend(dict(name=r[0],type='line',x=[i+1,i+1],y=r[4:6]) for i,r in enumerate(means))
        result['charts'].append(dict(type='scatter',title='Means and confidence intervals',xLabel='Group',yLabel='Mean',xTickLabels={str(i+1):r[0] for i,r in enumerate(means)},series=series))
    if boolean(opt,'sta.anova.showcontrasts',opt.get('tukey',True)):
        result['tables'].extend(posthoc(groups,mse,df,conf,b))
        control=str(opt.get('sta.anova.mc.dunnettcontrolgroup','')).strip() or groups[0][0]
        if control:
            mapping=dict(groups)
            if control not in mapping:raise ValueError('Dunnett control group is not present.')
            names=[g for g,_ in groups if g!=control];test=stats.dunnett(*[mapping[g] for g in names],control=mapping[control],rng=np.random.default_rng(0));ci=test.confidence_interval(confidence_level=conf)
            result['tables'].append(b._table('Dunnett comparisons',['Treatment','Control','Statistic','Adjusted p-value','CI lower','CI upper'],[[g,control,s,p,lo,hi] for g,s,p,lo,hi in zip(names,test.statistic,test.pvalue,ci.low,ci.high)]))
    return result


def posthoc(groups,mse,df,confidence,b,balanced=None,effective_n=None,total_n=None):
    """Native family routing, finite range integration and decision rules."""
    groups=ordered_groups(groups)
    k=len(groups);alpha=1-confidence;comparisons=k*(k-1)/2;rows=[]
    # The native selection sort leaves a zero-count (NaN mean) slot in place.
    # Keep those slots in the family size/rank span, but omit empty pairs.
    ordered=list(groups)
    for i in range(k-1):
        for j in range(i+1,k):
            if len(ordered[i][1]) and len(ordered[j][1]) and np.mean(ordered[j][1])<np.mean(ordered[i][1]):ordered[i],ordered[j]=ordered[j],ordered[i]
    rank={g:i for i,(g,x) in enumerate(ordered)}
    if balanced is None:balanced=len(groups[0][1])==min(len(x) for _,x in groups)
    if effective_n is None:effective_n=min(len(x) for _,x in groups)
    if total_n is None:total_n=sum(len(x) for _,x in groups)
    pair_df=total_n-k
    for (a,x),(c,y) in itertools.combinations(groups,2):
        if not len(x) or not len(y):continue
        diff=np.mean(x)-np.mean(y);se=math.sqrt(mse*(1/len(x)+1/len(y)))
        t=abs(diff)/se if se else (math.inf if diff else math.nan)
        span=abs(rank[a]-rank[c])+1
        for method,p,critical,threshold in [
            ('Fisher LSD',2*stats.t.sf(t,pair_df+2),None,alpha/2),
            ('Bonferroni',min(1,comparisons*2*stats.t.sf(t,pair_df)),stats.t.ppf(1-alpha/(2*comparisons),pair_df),alpha),
            ('Scheffe',stats.f.sf(t*t/(k-1),k-1,pair_df),math.sqrt((k-1)*stats.f.ppf(1-alpha,k-1,pair_df)),alpha)]:
            rows.append([method,a,c,diff,se,t,p,None if critical is None else diff-critical*se,None if critical is None else diff+critical*se,bool(p<=threshold)])
        qse=(math.sqrt(mse/effective_n) if effective_n else math.inf) if balanced else se/math.sqrt(2)
        q=abs(diff)/qse if qse else (math.inf if diff else math.nan)
        full_p=range_survival(q,k,df)
        rows.append(['Tukey HSD' if balanced else 'Tukey–Kramer',a,c,diff,qse,q,full_p,None,None,bool(full_p<=alpha)])
        if balanced:
            span_p=range_survival(q,span,df)
            # Average the lower- and upper-tail probabilities, not the critical values.
            p=(full_p+span_p)/2
            left,right,ordered_diff=(a,c,diff) if rank[a]<rank[c] else (c,a,-diff)
            rows.append(['Tukey B',left,right,ordered_diff,qse,q,p,None,None,bool(p<=alpha)])
            rows.append(['Newman–Keuls',left,right,ordered_diff,qse,q,span_p,None,None,bool(span_p<alpha)])
    for method in ('Tukey B','Newman–Keuls'):
        positions=[i for i,row in enumerate(rows) if row[0]==method]
        ordered_rows=sorted((rows[i] for i in positions),key=lambda row:(rank[row[1]],rank[row[2]]))
        for i,row in zip(positions,ordered_rows):rows[i]=row
    return [b._table('Additional post-hoc comparisons',['Method','Group1','Group2','Difference (1−2)','SE','Statistic (t or q)','p-value','CI lower','CI upper','Significant'],rows)]


def spectral_report(aid,cols,eigen,loadings,rotated,opt,result,b):
    if not boolean(opt,'sta.mv.scree',True):result['charts']=[c for c in result['charts'] if c['title']!='Scree plot']
    if boolean(opt,'sta.mv.varexplained.plot',True):
        result['charts'].append(dict(type='line',title='Variance explained',xLabel='Component',yLabel='Fraction of variance',series=[dict(name='Individual',x=list(range(1,len(eigen)+1)),y=list(eigen/eigen.sum())),dict(name='Cumulative',x=list(range(1,len(eigen)+1)),y=list(np.cumsum(eigen)/eigen.sum()))]))
    mode=(1 if boolean(opt,'sta.mv.pca.compload.plot',True) else 0) if aid=='1120' else index(opt,'sta.mv.pca.compload.plot',3,3)
    for title,values,enabled in [('Initial loadings',loadings,mode in (1,3)),('Rotated loadings',rotated,aid=='1121' and mode in (2,3))]:
        if not enabled:continue
        if values.shape[1]>1:
            result['charts'].append(dict(type='scatter',title=title,xLabel='Component 1',yLabel='Component 2',series=[dict(name=c,x=[float(v[0])],y=[float(v[1])]) for c,v in zip(cols,values)]))
        else:result['charts'].append(dict(type='bar',title=title,xLabel='Variable',yLabel='Loading',series=[dict(name='Component 1',x=cols,y=list(values[:,0]))]))
    return result


def lda_report(frame,data,cols,x,y,lda,opt,result,b):
    if not boolean(opt,'sta.class.casewiseopt',True):result['tables']=[t for t in result['tables'] if t['title']!='Training classification']
    elif boolean(opt,'sta.class.missclass.opt'):
        for t in result['tables']:
            if t['title']=='Training classification':t['rows']=[r for r in t['rows'] if r[1]!=r[2]]
    within=np.zeros((x.shape[1],x.shape[1]));between=np.zeros_like(within);mean=x.mean(axis=0)
    for group in lda.classes_:
        part=x[y==group];centered=part-part.mean(axis=0);within+=centered.T@centered;delta=part.mean(axis=0)-mean;between+=len(part)*np.outer(delta,delta)
        if boolean(opt,'sta.DS',True):result['tables'].append(descriptive_table(pd.DataFrame(part,columns=cols),cols,b,'Descriptive statistics — '+str(group)))
        if boolean(opt,'mv.var_covar.mxs',True):result['tables'].append(b._table('Covariance — '+str(group),['Variable']+cols,[[c]+list(row) for c,row in zip(cols,np.cov(part,rowvar=False,ddof=1))]))
    if boolean(opt,'mv.var_covar.mxs',True):result['tables'].append(b._table('Pooled within-group covariance',['Variable']+cols,[[c]+list(row) for c,row in zip(cols,within/(len(x)-len(lda.classes_)))]))
    if boolean(opt,'sta.mv.scree-varexplained',True):
        roots=np.sort(np.linalg.eigvals(np.linalg.pinv(within)@between).real)[::-1][:min(x.shape[1],len(lda.classes_)-1)].clip(min=0);fraction=roots/roots.sum() if roots.sum() else roots
        result['charts'].extend([dict(type='line',title='Canonical roots',xLabel='Canonical variable',yLabel='Root',series=[dict(name='Root',x=list(range(1,len(roots)+1)),y=list(roots))]),dict(type='line',title='Canonical variance explained',xLabel='Canonical variable',yLabel='Fraction',series=[dict(name='Individual',x=list(range(1,len(roots)+1)),y=list(fraction)),dict(name='Cumulative',x=list(range(1,len(roots)+1)),y=list(np.cumsum(fraction)))])])
    if boolean(opt,'mv.biplot.ui.opt',True):
        scores=lda.transform(x)
        if scores.shape[1]>=2:result['charts'].append(dict(type='scatter',title='Canonical plot',xLabel='Canonical variable 1',yLabel='Canonical variable 2',series=[dict(name=str(group),x=list(scores[y==group,0]),y=list(scores[y==group,1])) for group in lda.classes_]))
        else:result['notes'].append('Canonical two-variable plot omitted because only one canonical variable is estimable.')
    return result


def kmeans(frame,data,cols,x,opt,b):
    from sklearn.cluster import KMeans,kmeans_plusplus
    k=b._num(opt,'clusters',2,1,min(len(x),1000),True);limit=b._num(opt,'max_iter',10,1,1000,True)
    if len(np.unique(x,axis=0))<k:raise ValueError('More clusters requested than distinct observations.')
    mean,sd=x.mean(axis=0),x.std(axis=0,ddof=1)
    scaled=boolean(opt,'standardize')
    if scaled:x=(x-mean)/sd
    initial=opt.get('initial_centers',[])
    if initial:
        values=b._numeric(frame,b._names(frame,opt,'initial_centers')).dropna(how='all')
        if values.isna().any().any() or values.shape!=(k,len(cols)):raise ValueError('Initial centers must contain K complete rows and one column per input variable.')
        centers=values.to_numpy();centers=(centers-mean)/sd if scaled else centers
    else:centers,_=kmeans_plusplus(x,n_clusters=k,random_state=b._num(opt,'seed',0,0,2**32-1,True))
    start=centers.copy();changes=[];converged=False
    for step in range(1,limit+1):
        fit=KMeans(n_clusters=k,init=centers,n_init=1,max_iter=1,tol=0,algorithm='lloyd').fit(x)
        delta=fit.cluster_centers_-centers
        changes.extend([[step,i+1,float(np.linalg.norm(row))]+list(row) for i,row in enumerate(delta)])
        centers=fit.cluster_centers_.copy()
        if np.max(np.abs(delta))<=1e-10:converged=True;break
    distances=np.linalg.norm(x-centers[fit.labels_],axis=1);tables=[]
    if boolean(opt,'sta.DS'):tables.append(descriptive_table(data,cols,b))
    if boolean(opt,'mv.km.initcenters',True):tables.append(b._table('Initial cluster centers',['Cluster']+cols,[[i+1]+list(row) for i,row in enumerate(start)]))
    if boolean(opt,'mv.mk.iterations_change',True):tables.append(b._table('Change in cluster centers',['Iteration','Cluster','Euclidean change']+cols,changes))
    if boolean(opt,'mv.km.summary',True):
        tables.extend([b._table('Cluster centers (analysis scale)',['Cluster']+cols,[[i+1]+list(row) for i,row in enumerate(centers)]),b._table('Cluster summary',['Cluster','N','Within-cluster SS','Mean distance'],[[i+1,int(np.sum(fit.labels_==i)),float(np.sum(distances[fit.labels_==i]**2)),float(np.mean(distances[fit.labels_==i])) if np.any(fit.labels_==i) else None] for i in range(k)]),b._table('Fit summary',['Metric','Value'],[['Within-cluster sum of squares',float(np.sum(distances**2))],['Iterations',step]])])
    labels=[str(i+1) for i in data.index]
    if opt.get('sta.in.caselabels'):
        label=b._name(frame,opt,'sta.in.caselabels');labels=[str(v) if pd.notna(v) else '' for v in frame.loc[data.index,label]]
    if boolean(opt,'mv.km.membership_distance',True):tables.append(b._table('Membership',['Case','Cluster','Distance to center'],[[label,int(group)+1,float(d)] for label,group,d in zip(labels,fit.labels_,distances)]))
    return b._result('1130',tables,notes=['Supplied centers are used directly; otherwise seeded k-means++ initializes one Lloyd sequence. Iteration changes are measured from the actual fitted centers.'],warnings_=[] if converged else ['Iteration limit reached before centers became stationary.'])


def hierarchical(frame,data,cols,x,opt,b):
    if opt.get('cluster_axis','rows')=='columns':x=x.T;labels=cols
    else:
        labels=[str(i+1) for i in data.index]
        if opt.get('sta.in.caselabels'):labels=[str(v) if pd.notna(v) else '' for v in frame.loc[data.index,b._name(frame,opt,'sta.in.caselabels')]]
    n=len(x)
    if not 2<=n<=1000:raise ValueError('Hierarchical clustering requires 2 to 1000 objects.')
    method=opt.get('linkage','average');metric=opt.get('metric','sqeuclidean')
    power=b._num(opt,'power',2,1,10,True) if metric in ('minkowski','generalized') else 2
    root=b._num(opt,'mv.distance.generalized.opt.root',2,1,10,True) if metric=='generalized' else 2
    proximity,similarity=native_proximity(x,metric,power,root)
    beta=b._num(opt,'cluster.linkage.flex.beta',-.25,-1,1) if method=='flexible' else -.25
    if method=='flexible' and beta<=-1:raise ValueError('Flexible beta must be greater than -1 and at most 1.')
    z=native_linkage(proximity,method,beta,similarity)
    raw=str(opt.get('mv.noc.opt.singleorrange',opt.get('clusters','2'))).strip();parts=raw.split('-')
    try:
        counts=[int(raw)] if len(parts)==1 else list(range(int(parts[0]),int(parts[1])+1)) if len(parts)==2 else []
    except ValueError:counts=[]
    if not counts or min(counts)<1 or max(counts)>n:raise ValueError('Cluster count must be an integer or ascending range within the number of objects.')
    tables=[];charts=[]
    proximity_label='Similarity' if similarity else 'Distance'
    if boolean(opt,'cluster.node.stats',True):tables.append(b._table('Linkage',['Node','Left child','Right child',proximity_label,'Objects'],[[n+i,int(row[0]),int(row[1]),row[2],int(row[3])] for i,row in enumerate(z)]))
    if boolean(opt,'cluster.membership',True):
        groups=cut_membership(z,counts);tables.append(b._table('Membership',['Object']+[f'{k} clusters' for k in counts],[[label]+[int(g) for g in row] for label,row in zip(labels,groups)]))
    if boolean(opt,'cluster.proximity'):
        if n>1000:raise ValueError('A displayed proximity matrix is limited to 1000 objects.')
        tables.append(b._table('Proximity matrix',['Object']+labels,[[label]+list(row) for label,row in zip(labels,proximity)]))
    if boolean(opt,'cluster.dendrogram',True):
        series,ticks=dendrogram_series(z,labels,similarity);charts.append(dict(type='line',title='Dendrogram',xLabel='Object',yLabel='Linkage '+proximity_label.lower(),xTickLabels=ticks,series=series))
    notes=['Proximity and Lance–Williams recurrences update centroid, median and Ward linkages without squaring or square-rooting distances. Generalized distance is (sum(abs(delta)^power))^(1/root). Similarities merge the greatest proximity first. Tie ordering can differ.']
    if metric=='angular':notes.append('Compatibility behavior: native angular cosine is 1−1/(π·cosine), not the usual arccosine angular distance; this unusual formula is preserved.')
    return b._result('1132',tables,charts,notes=notes)


def flexible_linkage(distance,beta):
    import heapq
    n=len(distance);active=set(range(n));sizes={i:1 for i in active};d={(i,j):float(distance[i,j]) for i in range(n) for j in range(i+1,n)};heap=[(value,*key) for key,value in d.items()];heapq.heapify(heap);rows=[]
    for step in range(n-1):
        while True:
            value,a,c=heapq.heappop(heap)
            if a in active and c in active:break
        new=n+step;rows.append([a,c,value,sizes[a]+sizes[c]]);others=active-{a,c}
        for v in others:
            av=d[tuple(sorted((a,v)))];cv=d[tuple(sorted((c,v)))];combined=(1-beta)/2*(av+cv)+beta*value
            if combined<0:raise ValueError('Flexible linkage beta creates a negative distance.')
            d[(v,new)]=combined;heapq.heappush(heap,(combined,v,new))
        active=others|{new};sizes[new]=sizes[a]+sizes[c]
    return np.asarray(rows,dtype=float)


def factorial(aid,frame,opt,b):
    from .basic_native_anova import marginal_components,denominator as native_denominator
    factors=b._names(frame,opt,'factors');types=[index(opt,f'factor_type_{i+1}',0,1) for i in range(len(factors))]
    if len(factors)!=(2 if aid=='1104' else 3):raise ValueError('Select every factor input.')
    response=b._name(frame,opt,'response')
    if len(set([response]+factors))!=len(factors)+1:raise ValueError('Response and factors must be distinct columns.')
    clean=b._numeric(frame,[response]);clean[factors]=frame[factors];clean=clean.dropna();interactions=boolean(opt,'interactions',True)
    for factor in factors:
        values=clean[factor].unique()
        if len({str(value) for value in values})!=len(values):
            raise ValueError('Factor '+factor+' contains distinct values with the same text label; use unambiguous categorical labels.')
    random_factors={i for i,value in enumerate(types) if value}
    native=any(types) or (aid=='1104' and not interactions) or opt.get('ss_type','native')=='native'
    term_label=lambda members:':'.join(f'C(f{i}, Sum)' for i in sorted(members))
    if native:
        components,error=marginal_components(clean,response,factors)
        if aid=='1104' and not interactions:
            error=components[frozenset(range(2))]
            components={members:values for members,values in components.items() if len(members)==1}
        elif not interactions:
            # The three-factor additive model is an independent API extension.
            additive=b._factor_model(aid,frame,{**opt,'ss_type':opt.get('ss_type') if opt.get('ss_type') in ('2','3',2,3) else 2})
            components={frozenset([i]):(additive['tables'][0]['rows'][i][1],additive['tables'][0]['rows'][i][2]) for i in range(len(factors))}
            error=tuple(next(row for row in additive['tables'][0]['rows'] if row[0]=='Residual')[1:3])
        if error[1]<=0:raise ValueError('ANOVA needs positive error degrees of freedom; two-way unreplicated data require No Interactions / Randomized Block Design.')
        rows=[[term_label(members),ss,df,None,None] for members,(ss,df) in components.items()]
        rows.append(['Residual',*error,None,None])
        tab=b._table('ANOVA',['Source','Sum of squares','df','F','p-value'],rows)
        result=b._result(aid,[tab,b._table('Model variables',['Model code','Dataset column'],[(f'f{i}',name) for i,name in enumerate(factors)])])
        result['notes'].append('Marginal-total sums of squares and restricted mixed/random F-test denominators are used. Complete-case deletion; unequal cell counts are permitted when the decomposition has nonnegative sums of squares.')
        if aid=='1104' and not interactions:result['notes'].append('No Interactions / Randomized Block Design uses the A×B component as error, without pooling within-cell replication error; factor-type choices do not alter this branch.')
        if aid=='1105' and len(random_factors)==3:result['notes'].append('Compatibility convention: composite main-effect tests use A×B×C degrees of freedom, not Satterthwaite degrees of freedom.')
    else:
        result=b._factor_model(aid,frame,opt);tab=result['tables'][0]
    terms={};residual=next(r for r in tab['rows'] if r[0]=='Residual');mse=residual[1]/residual[2];dfe=residual[2]
    import re
    for row in tab['rows']:
        members=frozenset(int(i) for i in re.findall(r'C\(f(\d+),',row[0]))
        if members:terms[members]=row
    denominator={}
    tab['columns']+=['Denominator MS','Denominator df','Denominator terms']
    for row in tab['rows']:
        members=frozenset(int(i) for i in re.findall(r'C\(f(\d+),',row[0]))
        if not members:row.extend([None,None,None]);continue
        if native and interactions:
            den,den_df,combination=native_denominator(components,error,members,random_factors,len(factors))
            label=' '.join(('+' if sign>0 else '−')+' '+('Residual' if term is None else term_label(term)) for sign,term in combination).lstrip('+ ')
        else:den,den_df,label=mse,dfe,'Residual'
        denominator[members]=(den,den_df)
        row[3]=(row[1]/row[2])/den if den>0 else None;row[4]=stats.f.sf(row[3],row[2],den_df) if den>0 and den_df>0 else None;row.extend([den,den_df,label])
        if den<=0 or den_df<=0:result['warnings'].append(row[0]+': denominator mean square or degrees of freedom is nonpositive; its p-value is unavailable.')
    if aid=='1104' and random_factors and interactions:
        interaction=terms[frozenset([0,1])];conventional=interaction[4];interaction[4]=0.
        detail=f' The conventional F-test probability is {conventional:.12g}.' if conventional is not None else ''
        result['notes'].append('Compatibility behavior: the native mixed/random ANOVA interaction report displays p=0 from an unwritten report slot; this displayed value is preserved.'+detail)
    if aid=='1105' and random_factors=={0,2} and interactions:
        a,bb,c=(terms[frozenset([i])] for i in range(3));ac=terms[frozenset([0,2])]
        composite=bb[5];composite_df=bb[6]
        # Native R/F/R slots exchange main-effect numerators and use the other
        # row's F statistic for each of the first two probability slots.
        a[3]=(bb[1]/bb[2])/(ac[1]/ac[2]) if ac[1]>0 else None
        bb[3]=(a[1]/a[2])/composite if composite>0 else None
        a[5:8]=[ac[1]/ac[2],ac[2],ac[0]]
        bb[5:8]=[composite,composite_df,'C(f0, Sum):C(f1, Sum) + C(f1, Sum):C(f2, Sum) − C(f0, Sum):C(f1, Sum):C(f2, Sum)']
        a[4]=stats.f.sf(bb[3],bb[2],ac[2]) if bb[3] is not None else None
        bb[4]=stats.f.sf(a[3],a[2],composite_df) if a[3] is not None and composite_df>0 else None
        result['notes'].append('Compatibility behavior: the confirmed native Random/Fixed/Random report exchanges A/B F numerators and uses the other main-effect F statistic in the A/B probability slots. These displayed values are reproduced; the row p-values therefore do not describe the displayed F statistic under the row degrees of freedom.')
    if aid=='1105' and random_factors=={0,1} and interactions:
        a,bb,c=(terms[frozenset([i])] for i in range(3))
        ab,ac,bc=(terms[frozenset(pair)] for pair in [(0,1),(0,2),(1,2)])
        abc=terms[frozenset(range(3))];msabc=abc[1]/abc[2]
        ab[3]=(bc[1]/bc[2])/mse if mse>0 else None
        ac[3]=(ab[1]/ab[2])/msabc if msabc>0 else None
        bc[3]=(ac[1]/ac[2])/msabc if msabc>0 else None
        sf=lambda value,df1,df2:stats.f.sf(value,df1,df2) if value is not None and df2>0 else None
        a[4]=sf(c[3],c[2],ab[2]);c[4]=sf(a[3],a[2],c[6])
        ab[4]=sf(bc[3],bc[2],dfe);ac[4]=sf(ab[3],ab[2],abc[2]);bc[4]=sf(ac[3],ac[2],abc[2])
        result['notes'].append('Compatibility behavior: the confirmed native Random/Random/Fixed report permutes interaction F numerators and uses different report F slots for A, C and interaction probabilities. These displayed values are reproduced; the row p-values therefore do not describe the displayed F statistic under the row degrees of freedom.')
    if boolean(opt,'sta.show.DS',True):
        grouped=clean.groupby(factors,sort=False,observed=True)[response]
        result['tables'].append(b._table('Cell descriptive statistics',factors+['N','Mean','SD','Variance'],[(list(label) if isinstance(label,tuple) else [label])+[len(x),x.mean(),x.std(ddof=1),x.var(ddof=1)] for label,x in grouped]))
        result['tables'].append(b._table('Factor descriptive statistics',['Factor','Level','N','Mean','Variance','SD'],[[factor,label,len(x),x.mean(),x.var(ddof=1),x.std(ddof=1)] for factor in factors for label,x in clean.groupby(factor,sort=False,observed=True)[response]]))
    total_ss=float(np.sum((clean[response]-clean[response].mean())**2))
    tab['columns']+=['Mean square','F critical','Omega squared']
    omega=[]
    for row in tab['rows']:
        members=frozenset(int(i) for i in re.findall(r'C\(f(\d+),',row[0]))
        ms=row[1]/row[2] if row[2]>0 else None
        critical=stats.f.ppf(b._conf(opt),row[2],row[6]) if members and row[6] and row[6]>0 else None
        effect=max(0.,(row[1]-row[2]*mse)/(total_ss+mse)) if members and total_ss+mse>0 else None
        if effect is not None:omega.append((row[1]-row[2]*mse)/(total_ss+mse))
        row.extend([ms,critical,effect])
    result['tables'].append(b._table('ANOVA totals',['Metric','Value'],[['Total SS',total_ss],['Total df',len(clean)-1],['Total mean square',total_ss/(len(clean)-1)],['Omega squared for combined effect',max(0.,sum(omega))]]))
    if boolean(opt,'sta.anova.showcontrasts',True):
        cell_sizes=clean.groupby(factors,observed=True).size();balanced=len(cell_sizes)==math.prod(clean[f].nunique() for f in factors) and cell_sizes.nunique()==1
        for i,factor in enumerate(factors):
            groups=[(str(label),x.to_numpy()) for label,x in clean.groupby(factor,sort=False,observed=True)[response]];den,df=mse,dfe
            p=terms[frozenset([i])][4]
            if len(groups)>2 and p is not None and p<1-b._conf(opt) and den>0 and df>0:
                for table in posthoc(groups,den,df,b._conf(opt),b,balanced=balanced,effective_n=min(len(x) for _,x in groups),total_n=len(clean)):table['title']=factor+' — '+table['title'];result['tables'].append(table)
        if aid=='1104' and interactions and not random_factors and mse>0:
            # Both strong- and zero-interaction native fixtures enter this
            # branch: the caller's gate is a zero-initialized probability slot.
            for fixed,compared in [(factors[0],factors[1]),(factors[1],factors[0])]:
                if clean[compared].nunique()<2:continue
                for level,part in clean.groupby(fixed,sort=True,observed=True):
                    groups=[(str(label),x.to_numpy()) for label,x in part.groupby(compared,sort=True,observed=True)[response]]
                    for report in posthoc(groups,mse,dfe,b._conf(opt),b,balanced=balanced,effective_n=min(len(x) for _,x in groups),total_n=len(clean)):
                        report['title']=f'{compared} within {fixed}={level} — '+report['title'];result['tables'].append(report)
            result['notes'].append('Native two-way fixed-factor simple comparisons are printed even when the A×B interaction is not significant, as verified against zero-interaction and strong-interaction reference reports.')
        if aid=='1105' and interactions and mse>0:
            levels=[ordered_groups([(str(label),np.array([0.])) for label in clean[factor].unique()]) for factor in factors]
            # Sorting must be shared with the native post-hoc label convention.
            lookup=[{str(value):value for value in clean[factor].unique()} for factor in factors]
            levels=[[lookup[i][label] for label,_ in group] for i,group in enumerate(levels)]
            # Three native scratch vectors are zero-initialized to A+B+C
            # slots, then reused without clearing between these sections.
            scratch=[np.array([],dtype=float) for _ in range(sum(map(len,levels)))]
            sections=[(0,1,2,(0,1),'minimum'),(1,0,2,(0,1),'conditioning_index'),(2,1,0,(1,2),'zero_tail'),(2,1,0,(0,2),'relabel_a')]
            for conditioned,compared,omitted,gate,kind in sections:
                probability=terms[frozenset(gate)][4]
                if probability is None or probability>=1-b._conf(opt):continue
                for level_index,level in enumerate(levels[conditioned]):
                    part=clean[(clean[factors[conditioned]]==level)&(clean[factors[omitted]]==levels[omitted][-1])]
                    for j,value in enumerate(levels[compared]):scratch[j]=part.loc[part[factors[compared]]==value,response].to_numpy()
                    label=factors[compared]
                    labels=levels[0] if kind=='relabel_a' else levels[compared]
                    groups=[(str(value),scratch[j]) for j,value in enumerate(labels)]
                    if kind=='relabel_a':label=factors[0]
                    effective=min(len(values) for _,values in groups)
                    if kind=='conditioning_index':effective=len(scratch[level_index])
                    if kind=='zero_tail':effective=min(len(scratch[j]) for j in range(1,len(levels[1])+1))
                    for report in posthoc(groups,mse,dfe,b._conf(opt),b,balanced=balanced,effective_n=effective,total_n=len(clean)):
                        report['title']=f'{label} within {factors[conditioned]}={level} — '+report['title']
                        result['tables'].append(report)
            result['notes'].append('Three-way simple comparisons use the last sorted level for omitted factors. The A-within-C section uses B values at the last A level. Unequal dimensions retain earlier values, and zero effective counts give range statistic 0 and p=1. These report conventions differ from conventional simple-effect tests; pairs with zero observations are omitted.')
    return result


def glm(frame,opt,b):
    import statsmodels.api as sm
    from patsy import dmatrices
    from statsmodels.multivariate.manova import MANOVA
    responses=opt.get('responses') or ([opt['response']] if opt.get('response') else [])
    if isinstance(responses,str):responses=[responses]
    responses=b._names(frame,{'responses':responses},'responses');fixed=b._names(frame,opt,'factors',0);random=b._names(frame,opt,'random_factors',0);predictors=b._names(frame,opt,'predictors',0)
    if len(set(responses+fixed+random+predictors))!=len(responses+fixed+random+predictors):raise ValueError('Response, fixed/random factors and covariates must be distinct.')
    if not fixed and not random and not predictors:raise ValueError('Select a fixed factor, random factor, or covariate.')
    result=b._result('1109');factors=fixed+random
    clean=b._numeric(frame,responses+predictors);clean[factors]=frame[factors];clean=clean.dropna()
    if len(clean)<3:raise ValueError('At least three complete observations are required.')
    coding=['NativeDummy','Sum','NativeOrthogonal'][index(opt,'glm.coding',0,2)] if 'glm.coding' in opt else opt.get('coding','NativeDummy')
    if coding not in ('Treatment','Sum','Helmert','NativeDummy','NativeOrthogonal'):raise ValueError('Unknown GLM contrast coding.')
    d=pd.DataFrame(index=clean.index)
    for i,c in enumerate(responses):d[f'y{i}']=clean[c]
    for i,c in enumerate(factors):
        numeric=pd.to_numeric(clean[c],errors='coerce')
        if numeric.notna().all():
            values=np.trunc(numeric.to_numpy(dtype=float))
            if not np.isfinite(values).all():raise ValueError('GLM factor codes must be finite.')
            levels=sorted(np.unique(values))
            if len(levels)>1 and levels[-1]-levels[0]!=len(levels)-1:raise ValueError('Native GLM factor codes must be consecutive integers; omitted levels make the design singular.')
            if np.any(values!=numeric):result['warnings'].append('Native GLM truncates fractional factor codes toward zero: '+c)
        else:values=clean[c].astype(str);levels=sorted(values.unique())
        if len(levels)<2:raise ValueError('Factor '+c+' needs at least two levels.')
        d[f'f{i}']=pd.Categorical(values,categories=levels)
    for i,c in enumerate(predictors):
        d[f'x{i}']=np.trunc(clean[c])
        if np.any(d[f'x{i}']!=clean[c]):result['warnings'].append('Native GLM truncates numeric covariates toward zero before fitting: '+c)
    terms=[f'C(f{i}, {coding})' for i in range(len(factors))];expr=(' * ' if boolean(opt,'interactions') else ' + ').join(terms)
    expr=' + '.join(([expr] if expr else [])+[f'x{i}' for i in range(len(predictors))]) or '1'
    for i,response in enumerate(responses):
        response_matrix,design=dmatrices(f'y{i} ~ '+expr,data=d,return_type='dataframe')
        fit=sm.OLS(response_matrix,design).fit()
        x=np.asarray(fit.model.exog);y=d[f'y{i}'].to_numpy();names=list(fit.params.index)
        if fit.df_resid<=0 or np.linalg.matrix_rank(x)!=x.shape[1]:raise ValueError('GLM design must be estimable with positive residual degrees of freedom.')
        slices=[(name,list(range(sl.start,sl.stop))) for name,sl in design.design_info.term_name_slices.items() if name!='Intercept']
        selected=[0];previous=sm.OLS(y,x[:,selected]).fit();sequential=[];partial=[];steps=[]
        for name,columns in slices:
            selected+=columns;current=sm.OLS(y,x[:,selected]).fit();df=len(columns)
            ss=max(0.,float(previous.ssr-current.ssr));f=(ss/df)/fit.mse_resid
            sequential.append([name,ss,df,f,stats.f.sf(f,df,fit.df_resid)])
            step_f=(ss/df)/current.mse_resid
            steps.append(['Added',name,current.rsquared,current.df_resid,current.ssr,ss,df,step_f,stats.f.sf(step_f,df,current.df_resid)])
            retained=[j for j in range(x.shape[1]) if j not in columns];reduced=sm.OLS(y,x[:,retained]).fit()
            ss_partial=max(0.,float(reduced.ssr-fit.ssr));partial_f=(ss_partial/df)/fit.mse_resid
            partial.append([name,ss_partial,df,partial_f,stats.f.sf(partial_f,df,fit.df_resid)])
            steps.append(['Removed',name,reduced.rsquared,reduced.df_resid,reduced.ssr,ss_partial,df,partial_f,stats.f.sf(partial_f,df,fit.df_resid)])
            previous=current
        sequential.append(['Residual',fit.ssr,fit.df_resid,None,None])
        columns=['Source','Sum of squares','df','F','p-value']
        part=b._fit_summary('1109',fit,names,clean.index,y,opt,[b._table('ANOVA',columns,sequential),b._table('Partial effects (full model minus term)',columns,partial)])
        for tab in part['tables']:
            if len(responses)>1:tab['title']=response+' — '+tab['title']
            result['tables'].append(tab)
        result['charts'].extend(part['charts'])
        if boolean(opt,'sta.reg.show_iter'):result['tables'].append(b._table('Term steps — '+response,['Action','Term','R²','Residual df','Residual SS','Effect SS','Effect df','F','p-value'],steps))
    result['tables'].append(b._table('Model variables',['Model code','Dataset column','Input role'],[(f'f{i}',c,'Fixed factor' if i<len(fixed) else 'Random factor') for i,c in enumerate(factors)]+[(f'x{i}',c,'Numeric covariate') for i,c in enumerate(predictors)]))
    if len(responses)>1:
        model=MANOVA.from_formula(' + '.join(f'y{i}' for i in range(len(responses)))+' ~ '+expr,data=d)
        test=model.mv_test()
        for term,entry in test.results.items():result['tables'].append(b._df_table('Multivariate tests — '+term,entry['stat'],'Test'))
        joint=model.mv_test([('Model',np.eye(x.shape[1])[1:])])
        result['tables'].append(b._df_table('Multivariate tests — Model',joint.results['Model']['stat'],'Test'))
    if boolean(opt,'glm.showcorrs'):
        values=np.column_stack([d[[f'y{i}' for i in range(len(responses))]],x[:,1:]])
        labels=responses+names[1:]
        result['tables'].append(b._df_table('Correlations of responses and model columns',pd.DataFrame(values,columns=labels).corr(),'Variable'))
    result['notes'].append('Complete-case regression using the same contrast columns for native fixed and random factor inputs. Random labels do not select a variance-component or REML estimator. Dummy coding references the last category; effect coding uses +1/last−1; orthogonal coding uses negative Helmert contrasts. ANOVA reports sequential sums of squares with full-model residual error; partial tests remove each term from the full model. Term-step added tests use that step’s residual error. Multiple responses share the design and have joint multivariate tests. Native numeric factor codes and covariates are truncated toward zero before fitting.')
    return result
