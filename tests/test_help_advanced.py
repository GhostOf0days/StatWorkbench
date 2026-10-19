"""Documented reports verified with independent equations and identities."""
import unittest
import numpy as np
from scipy import stats,optimize,linalg
from backend.analyses.advanced import analyze,catalog
from backend.common import sanitize_json


def data(columns,rows):return {'columns':columns,'rows':np.asarray(rows,dtype=object).tolist(),'name':'Help fixture'}
def table(result,title):return next(t for t in result['tables'] if title in t['title'])


class HelpAdvancedTests(unittest.TestCase):
    def test_cox_likelihood_wald_and_survival_at_mean(self):
        times=np.arange(1.,11);status=np.array([1,1,0,1,1,0,1,0,1,1]);x=np.array([2.,4,1,3,2,5,3,1,4,0])
        def likelihood(beta):
            return sum(beta*x[j]-np.log(np.exp(beta*x[j:]).sum()) for j in range(len(x)) if status[j])
        beta=optimize.minimize_scalar(lambda b:-likelihood(b),bounds=(-2,2),method='bounded').x
        r=analyze('1309',data(['t','d','x'],np.column_stack([times,status,x])),{'time':'t','status':'d','predictors':['x']})
        coef=table(r,'Hazard ratios')['rows'][0];self.assertAlmostEqual(coef[1],beta,places=5)
        expected_information=0.
        for j in np.flatnonzero(status):
            weights=np.exp(coef[1]*x[j:]);weights/=weights.sum();mean=np.dot(weights,x[j:]);expected_information+=np.dot(weights,(x[j:]-mean)**2)
        self.assertAlmostEqual(coef[2],1/np.sqrt(expected_information),places=10)
        self.assertAlmostEqual(coef[7],coef[1]**2*expected_information,places=10)
        fit=table(r,'Model fit')['rows'][0]
        self.assertAlmostEqual(fit[0],-2*likelihood(0));self.assertAlmostEqual(fit[2],2*(likelihood(coef[1])-likelihood(0)))
        risk=np.exp(coef[1]*(x-x.mean()));increments=[status[j]/risk[j:].sum() for j in range(len(x))]
        np.testing.assert_allclose(np.array(table(r,'Baseline')['rows'])[:,3],np.exp(-np.cumsum(increments)))
        shifted=analyze('1309',data(['t','d','x'],np.column_stack([times,status,x+100])),{'time':'t','status':'d','predictors':['x']})
        np.testing.assert_allclose(table(shifted,'Baseline')['rows'],table(r,'Baseline')['rows'],atol=1e-10)

    def test_acf_large_lags_toeplitz_solution_and_summary(self):
        y=np.array([1.,2,4,3,7,6,8,5]);r=analyze('1501',data(['x'],y[:,None]),{'column':'x','lags':7,'sta.time.acf.ao.6':True})
        rows=np.asarray(r['tables'][0]['rows']);z=y-y.mean();corr=np.array([np.dot(z[k:],z[:len(z)-k])/np.dot(z,z) for k in range(8)])
        for k in range(1,8):self.assertAlmostEqual(rows[k,2],linalg.solve_toeplitz(corr[:k],corr[1:k+1])[-1],places=12)
        np.testing.assert_allclose(rows[1:,3],np.sqrt((8-np.arange(1,8))/80))
        np.testing.assert_allclose(table(r,'Series summary')['rows'][0],[8,4.5,5.25,1/np.sqrt(8)])
        np.testing.assert_allclose(rows[1:4,4],[.2191943533304343,.05286152126342059,-.35034457495699894],rtol=1e-12)
        np.testing.assert_allclose(rows[1:4,5],[.5908317595573247,.46920009581941685,.0900521863882544],rtol=1e-12)
        np.testing.assert_allclose(r['charts'][0]['series'][1]['y'],2*rows[1:,3])
        np.testing.assert_allclose(r['charts'][1]['series'][1]['y'],1/np.sqrt(8))

    def test_kaplan_meier_three_group_comparisons_hand_risk_sets(self):
        d=data(['t','d','g'],[[1,1,'a'],[2,0,'a'],[4,1,'a'],[2,1,'b'],[3,1,'b'],[5,0,'b']])
        r=analyze('1621',d,{'time':'t','status':'d','group':'g'})
        rows=table(r,'Survival distribution comparisons')['rows']
        score=np.array([.5,-.4,-1/3,.5]);variance=np.array([.25,.24,2/9,.25]);risk=np.array([6.,5,3,2])
        for row,weights in zip(rows,[np.ones(4),risk,np.sqrt(risk)]):
            expected=np.dot(weights,score)**2/np.dot(weights**2,variance)
            self.assertEqual(row[2],1);self.assertAlmostEqual(row[3],expected);self.assertAlmostEqual(row[4],stats.chi2.sf(expected,1))
        self.assertAlmostEqual(rows[1][3],1/18)
        # Relabeling groups does not change a multivariate contrast test.
        d['rows'] += [[1.5,1,'c'],[3.5,0,'c'],[6,1,'c']]
        r=analyze('1621',d,{'time':'t','status':'d','group':'g'})
        d['rows']=list(reversed(d['rows']))
        other=analyze('1621',d,{'time':'t','status':'d','group':'g'})
        np.testing.assert_allclose([row[3] for row in table(r,'Survival distribution comparisons')['rows']],[row[3] for row in table(other,'Survival distribution comparisons')['rows']])
        for row in d['rows']:row[1]=0
        empty=analyze('1621',d,{'time':'t','status':'d','group':'g'})
        self.assertTrue(all(row[3] is None for row in table(empty,'Survival distribution comparisons')['rows']))

    def test_multiple_differences_keep_alignment_and_catalog_isolation(self):
        d=data(['x','y'],[[1,2],[2,6],[4,12],[8,20],[16,None]])
        r=analyze('1521',d,{'column':['x','y'],'order':2,'lag':1})
        rows=np.asarray(r['dataset']['rows'],float)
        np.testing.assert_allclose(rows[2:,0],[1,2,4]);np.testing.assert_allclose(rows[2:4,1],[2,2]);self.assertTrue(np.isnan(rows[4,1]))
        entries={e['id']:e for e in catalog()}
        self.assertEqual(entries['1521']['fields'][0]['type'],'columns')
        self.assertEqual(entries['1501']['fields'][0]['type'],'column')

    def test_smoothing_accuracy_and_zero_mape(self):
        y=np.array([0.,2,4,3,8]);r=analyze('1522',data(['x'],y[:,None]),{'column':'x','initial':'first','smoothing':.5})
        predictions=np.array([0,0,1,2.5,2.75]);resid=y-predictions
        np.testing.assert_allclose(table(r,'Accuracy measures')['rows'][0],[5,np.abs(resid[1:]/y[1:]).mean()*100,np.abs(resid).mean(),np.mean(resid**2),4])

    def test_seasonal_smoothing_matches_explicit_additive_recursion(self):
        y=np.array([8.,12,9,13,10,14,11,15]);alpha,beta,gamma=.3,.2,.1;m=2
        r=analyze('1540',data(['x'],y[:,None]),{'column':'x','help.seasonal':'additive','help.seasonal_period':2,'help.seasonal_gamma':gamma,'smoothing':alpha,'beta':beta,'ts.report.forecast':True,'ts.report.forecast.n':2})
        level=10.;trend=.5;seasons=[-2.,2.];pred=[]
        for j,value in enumerate(y):
            season=seasons[j%m];pred.append(level+trend+season);newlevel=alpha*(value-season)+(1-alpha)*(level+trend)
            newtrend=beta*(newlevel-level)+(1-beta)*trend
            seasons[j%m]=gamma*(value-level-trend)+(1-gamma)*season
            level,trend=newlevel,newtrend
        np.testing.assert_allclose(np.asarray(table(r,'Fitted')['rows'])[:,2],pred)
        np.testing.assert_allclose(np.asarray(table(r,'Forecast')['rows'])[:,1],[level+(j+1)*trend+seasons[j] for j in range(2)])
        for seasonal in ('additive','multiplicative'):
            for trend in ('0','1','2'):
                with self.subTest(seasonal=seasonal,trend=trend):
                    out=analyze('1540',data(['x'],y[:,None]),{'column':'x','help.seasonal':seasonal,'help.seasonal_period':2,'sta.time.dp.expsm':trend})
                    self.assertTrue(np.isfinite(np.array(out['tables'][0]['rows'],float)).all())

    def test_interrupted_series_adds_four_correlograms(self):
        r=analyze('1503',data(['before','after'],[[1,4],[2,7],[4,6],[3,9],[6,8]]),{'before':'before','after':'after'})
        self.assertEqual(len(r['charts']),5)
        differences=np.array([1.,2,-1,3]);z=differences-differences.mean()
        expected=np.dot(z[1:],z[:-1])/np.dot(z,z)
        self.assertAlmostEqual(table(r,'Before: first differences')['rows'][1][1],expected)

    def test_random_sample_columns_independent_and_reproducible(self):
        d=data(['x','y'],[[j,10*j] for j in range(20)])
        r=analyze('3301',d,{'columns':['x','y'],'count':12,'seed':987})
        rows=np.asarray(r['dataset']['rows']);self.assertFalse(np.array_equal(rows[:,1],10*rows[:,0]))
        self.assertEqual(len(set(rows[:,0])),12);self.assertEqual(len(set(rows[:,1])),12)
        self.assertEqual(r['dataset'],analyze('3301',d,{'columns':['x','y'],'count':12,'seed':987})['dataset'])
        short=analyze('3301',data(['x','y'],[[1,4],[2,None],[3,None]]),{'columns':['x','y'],'count':4,'replace':True})
        self.assertEqual([row[1] for row in short['dataset']['rows']],[4]*4)

    def test_matrix_transpose_is_numeric_and_multiplication_uses_padding(self):
        original=np.array([[1,2],[3,4],[5,6]])
        r=analyze('3200',data(['a','b'],original),{'columns':['a','b']})
        np.testing.assert_array_equal(r['dataset']['rows'],original.T)
        back=analyze('3200',r['dataset'],{'columns':r['dataset']['columns']})
        np.testing.assert_array_equal(back['dataset']['rows'],original)
        product=analyze('3201',data(['a','b','r1','r2'],[[1,2,2,0],[3,4,0,3],[5,6,None,None]]),{'left':['a','b'],'right':['r1','r2']})
        np.testing.assert_array_equal(product['dataset']['rows'],original@np.diag([2,3]))

    def test_all_documented_standardization_formulas(self):
        x=np.array([2.,4,9]);d=data(['x','y'],np.column_stack([x,2*x+5]))
        formulas={'zscore':lambda z:(z-z.mean())/z.std(ddof=1),'center':lambda z:z-z.mean(),'scale':lambda z:z/z.std(ddof=1),'affine':lambda z:(z-1)/3,'range':lambda z:1+2*(z-z.min())/np.ptp(z)}
        for method,expected in formulas.items():
            result=analyze('3003',d,{'columns':['x','y'],'method':method,'a':1,'b':3})
            np.testing.assert_allclose(result['dataset']['rows'],np.column_stack([expected(x),expected(2*x+5)]))

    def test_probit_fieller_endpoints_satisfy_inverse_confidence_equation(self):
        x=np.linspace(.1,1.4,8);dose=10.**x;totals=np.repeat(1000.,8);events=totals*stats.norm.cdf(-1+2*x)
        r=analyze('1601',data(['dose','events','n'],np.column_stack([dose,events,totals])),{'dose':'dose','events':'events','total':'n','sta.surv.probit.opt.intC':False})
        coefficients=table(r,'coefficients')['rows'];a,b=[row[1] for row in coefficients]
        self.assertAlmostEqual(a,4,places=7);self.assertAlmostEqual(b,2,places=7)
        prob=stats.norm.cdf(a+b*x-5);weights=totals*stats.norm.pdf(a+b*x-5)**2/(prob*(1-prob));X=np.column_stack([np.ones(8),x]);cov=np.linalg.inv(X.T@(weights[:,None]*X))
        rows=table(r,'effective dose')['rows'];self.assertEqual(len(rows),17)
        for p,estimate,z,logdose,logse,se,lower,upper in rows:
            self.assertAlmostEqual(estimate,10**((z-a)/b),places=8)
            for bound in (lower,upper):
                v=np.array([1,np.log10(bound)]);self.assertAlmostEqual((a+b*v[1]-z)**2,1.96**2*(v@cov@v),places=9)
            self.assertAlmostEqual(se,(10**(logdose+logse)-10**(logdose-logse))/2,places=10)
        self.assertAlmostEqual(table(r,'goodness of fit')['rows'][0][0],0,places=10)
        np.testing.assert_allclose(r['charts'][0]['series'][0]['x'],x)
        self.assertEqual(r['charts'][0]['xLabel'],'Log10 dose')

    def test_range_mvlue_and_general_moving_range_span(self):
        d=data(['x','g'],[[1,'a'],[5,'a'],[2,'b'],[4,'b'],[10,'b']])
        r=analyze('4102',d,{'columns':['x'],'sta.cc.xbar.GROUPS':'g','sta.cc.stddevest':'1'})
        d2=np.array([1.128,1.693]);d3=np.array([.8525,.8884]);ranges=np.array([4,8])
        expected=np.sum(d2*ranges/d3**2)/np.sum(d2**2/d3**2)
        self.assertAlmostEqual(table(r,'Sigma estimate')['rows'][0][0],expected)
        values=[1,4,2,8,5];r=analyze('4108',data(['x'],np.array(values)[:,None]),{'column':'x','help.mr_span':3,'help.individuals_target':7})
        np.testing.assert_allclose(np.array(table(r,'Moving range')['rows'])[:,1],[np.nan,np.nan,3,6,6],equal_nan=True)
        self.assertAlmostEqual(table(r,'Sigma estimate')['rows'][0][0],5/1.693)
        self.assertEqual(table(r,'Individuals')['rows'][0][2],7)

    def test_native_imr_precise_constants_alignment_and_two_observations(self):
        r=analyze('4108',data(['x'],[[1],[4]]),{'column':'x'})
        sigma=3/1.1283791671
        self.assertAlmostEqual(table(r,'Sigma estimate')['rows'][0][0],sigma,places=12)
        moving=table(r,'Moving range')['rows']
        self.assertTrue(np.isnan(moving[0][1]))
        self.assertEqual(moving[1][0],2)
        self.assertAlmostEqual(moving[1][4],3+3*.8525033*sigma,places=12)
        with self.assertRaises(ValueError):analyze('4108',data(['x'],[[1],[4]]),{'column':'x','sta.cc.stddevest':'1'})

    def test_box_mean_outlier_classes_and_c_chart_missing_lower_limit(self):
        r=analyze('4001',data(['x'],np.array([1,2,3,4,5,6,12,30])[:,None]),{'columns':['x']})
        box=r['charts'][0]['series'][0]['box'];self.assertEqual(box['mean'],63/8);self.assertEqual(box['extremeOutliers'],[30]);self.assertTrue(set(box['mildOutliers']).issubset(set(box['outliers'])))
        r=sanitize_json(analyze('4106',data(['x'],[[0],[1],[2]]),{'count_column':'x'}));self.assertIsNone(r['tables'][0]['rows'][0][3])


if __name__=='__main__':unittest.main()
