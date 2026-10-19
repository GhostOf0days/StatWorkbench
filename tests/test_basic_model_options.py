import unittest
import numpy as np
from backend.analyses.basic import analyze,catalog
from tests.test_basic import dataset,table

class ModelControlTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(313);self.x=np.arange(1,21,dtype=float);self.y=3+2*self.x+rng.normal(size=20);self.d=dataset(['x','y','w','z'],zip(self.x,self.y,1+self.x/20,rng.normal(size=20)))
    def test_ols_report_toggles_and_residual_types(self):
        opt={'response':'y','predictors':['x'],'sta.reg.ao.residuals':False,'sta.reg.lin.ao.res.ht-tests':False,'sta.reg.lin.ao.norm-qq-hist':False,'sta.reg.lin.ao.1':False,'sta.reg.lin.ao.0':False,'sta.reg.lin.ao.resorder':True,'sta.reg.plot.resid.type':'2','sta.reg.coldiag':True}
        r=analyze('1301',self.d,opt);self.assertFalse(any(t['title']=='Fitted values and residuals' for t in r['tables']));self.assertEqual(len(r['charts']),1);self.assertEqual(r['charts'][0]['yLabel'],'Studentized residual');self.assertEqual(len(table(r,'Collinearity diagnostics')['rows']),2)
        r=analyze('1301',self.d,{**opt,'sta.reg.ao.residuals':True,'sta.reg.stdres.emulateexcel':True})
        rows=table(r,'Fitted values and residuals')['rows'];res=np.array([r[3] for r in rows]);np.testing.assert_allclose([r[4] for r in rows],res/np.sqrt(np.sum(res**2)/19))
    def test_wls_weight_exponent_zero_equals_ols(self):
        opt={'response':'y','predictors':['x'],'weights':'w','sta.reg.wpower':0}
        weighted=analyze('1302',self.d,opt);ordinary=analyze('1301',self.d,opt)
        np.testing.assert_allclose([r[1] for r in table(weighted,'Coefficients')['rows']],[r[1] for r in table(ordinary,'Coefficients')['rows']],rtol=1e-12)
        self.assertEqual(weighted['charts'],[])
    def test_curve_checkboxes_simultaneous_and_logistic_inverse(self):
        r=analyze('1310',self.d,{'response':'y','predictor':'x','sta.reg.model.lin':True,'sta.reg.model.quad':True,'sta.reg.modelsum':'0','sta.reg.lin.ao.plotfit':'2'})
        self.assertEqual(len(r['tables']),1);self.assertEqual(len(r['tables'][0]['rows']),2);self.assertEqual(len(r['charts'][0]['series']),3)
        y=1/(.01+np.exp(2-.3*self.x));d=dataset(['x','y'],zip(self.x,y))
        r=analyze('1310',d,{'response':'y','predictor':'x','sta.reg.model.lin':False,'sta.reg.model.logistic':True,'sta.reg.model.logistic.ub':100})
        np.testing.assert_allclose([row[2] for row in table(r,'Predictions on original response scale')['rows']],y,rtol=1e-12)
    def test_oneway_report_controls_and_pooled_intervals(self):
        d=dataset(['a','b','c'],[[1,4,8],[2,6,10],[3,8,12],[4,10,14]])
        opt={'columns':['a','b','c'],'sta.anova.showcontrasts':False,'sta.show.DS':False,'anova.plot.meanci_intervals.ui':False}
        r=analyze('1102',d,opt);self.assertEqual(len(r['tables']),1);self.assertEqual(r['charts'],[])
        r=analyze('1102',d,{**opt,'sta.show.DS':True,'means.ci.vartype.ui':'1','anova.plot.meanci_intervals.ui':True})
        rows=table(r,'Group summaries')['rows'];self.assertAlmostEqual(rows[0][5]-rows[0][2],rows[2][5]-rows[2][2]);self.assertEqual(len(r['charts']),1)
    def test_balanced_random_factor_uses_interaction_denominator(self):
        means=np.array([[1,3,4],[5,6,12]],float);rows=[[a,b,means[a,b]+e] for a in range(2) for b in range(3) for e in (-1,0,1)]
        r=analyze('1104',dataset(['a','b','y'],rows),{'response':'y','factor_1':'a','factor_2':'b','factor_type_1':'0','factor_type_2':'1','sta.anova.showcontrasts':False})
        t=table(r,'ANOVA');interaction=3*np.sum((means-means.mean(axis=1,keepdims=True)-means.mean(axis=0,keepdims=True)+means.mean())**2)/2
        self.assertAlmostEqual(t['rows'][0][5],interaction);self.assertAlmostEqual(t['rows'][1][5],1);self.assertAlmostEqual(t['rows'][2][5],1)
    def test_pca_prefix_and_plot_controls(self):
        r=analyze('1120',self.d,{'columns':['x','y','z'],'sta.mv.pca.pcprefix':'Axis','sta.mv.scree':False,'sta.mv.varexplained.plot':False,'sta.mv.pca.compload.plot':False})
        self.assertEqual(r['charts'],[]);self.assertEqual(table(r,'Scores')['columns'][1],'Axis1')
    def test_factor_rotation_select_and_plot_choices(self):
        r=analyze('1121',self.d,{'columns':['x','y','z'],'retention':'count','threshold':2,'sta.fa.rot.type':'4','sta.mv.scree':False,'sta.mv.varexplained.plot':False,'sta.mv.pca.compload.plot':'2'})
        self.assertEqual([c['title'] for c in r['charts']],['Rotated loadings'])
        initial=np.asarray([r[1:] for r in table(r,'Initial component-factor loadings')['rows']]);rotated=np.asarray([r[1:] for r in table(r,'Rotated loadings')['rows']]);np.testing.assert_allclose(np.sum(initial**2,axis=1),np.sum(rotated**2,axis=1))
    def test_kmeans_uses_supplied_centers_and_real_iteration_trace(self):
        d=dataset(['x','y','ix','iy','label'],[[0,0,0,0,'a'],[1,0,10,10,'b'],[0,1,None,None,'c'],[10,10,None,None,'d'],[11,10,None,None,'e'],[10,11,None,None,'f']])
        r=analyze('1130',d,{'columns':['x','y'],'clusters':2,'initial_centers':['ix','iy'],'sta.in.caselabels':'label'})
        self.assertEqual(table(r,'Initial cluster centers')['rows'][1],[2,10,10]);np.testing.assert_allclose(table(r,'Cluster centers (analysis scale)')['rows'][0][1:],[1/3,1/3]);self.assertEqual(table(r,'Membership')['rows'][0][0],'a');self.assertTrue(table(r,'Change in cluster centers')['rows'])
    def test_flexible_generalized_linkage_range_and_dendrogram(self):
        d=dataset(['x','y','label'],[[0,1,'a'],[1,2,'b'],[4,6,'c'],[10,9,'d']])
        r=analyze('1132',d,{'columns':['x','y'],'cluster.linkage':'2','cluster.linkage.flex.beta':0,'mv.distancemeasure':'5','mv.distance.generalized.opt.power':2,'mv.distance.generalized.opt.root':2,'mv.noc.opt.singleorrange':'2-3','cluster.proximity':True,'sta.in.caselabels':'label'})
        self.assertAlmostEqual(table(r,'Proximity matrix')['rows'][0][2],np.sqrt(2));self.assertEqual(table(r,'Membership')['columns'],['Object','2 clusters','3 clusters']);self.assertEqual(r['charts'][0]['title'],'Dendrogram')

    def test_native_similarity_formulas_and_merge_direction(self):
        from backend.analyses.basic_native_models import native_proximity,native_linkage,cut_membership
        x=np.array([[1,0],[1,1],[-1,2]],float)
        cosine,similarity=native_proximity(x,'cosine')
        self.assertTrue(similarity);self.assertAlmostEqual(cosine[0,1],1/np.sqrt(2));self.assertEqual(cosine[0,0],1)
        z=native_linkage(cosine,'single',similarity=True)
        np.testing.assert_array_equal(z[0,:2],[0,1]);self.assertAlmostEqual(z[0,2],cosine[0,1])
        angular,_=native_proximity(x,'angular');self.assertAlmostEqual(angular[0,2],1+np.sqrt(5)/np.pi)
        z=native_linkage(angular,'average',similarity=True)
        np.testing.assert_array_equal(z[0,:2],[0,2]);np.testing.assert_array_equal(cut_membership(z,[2])[:,0],[1,2,1])
        zero,_=native_proximity(np.array([[0,0],[1,2.]]),'cosine');self.assertEqual(zero[0,1],0)
        with self.assertRaises(ValueError):native_proximity(np.eye(2),'angular')

    def test_native_linkage_uses_proximity_scale_and_flexible_endpoints(self):
        from backend.analyses.basic_native_models import native_linkage
        matrix=np.array([[0,2,8],[2,0,6],[8,6,0]],float)
        self.assertAlmostEqual(native_linkage(matrix,'centroid')[1,2],6.5)
        self.assertAlmostEqual(native_linkage(matrix,'median')[1,2],6.5)
        self.assertAlmostEqual(native_linkage(matrix,'ward')[1,2],26/3)
        self.assertAlmostEqual(native_linkage(matrix,'flexible',1)[1,2],2)
        d=dataset(['x','y'],[[1,2],[2,4],[4,8]])
        for key,value in [('mv.distance.generalized.opt.power',11),('mv.distance.generalized.opt.root',2.5)]:
            with self.assertRaises(ValueError):analyze('1132',d,{'columns':['x','y'],'mv.distancemeasure':'5',key:value})
        with self.assertRaises(ValueError):analyze('1132',d,{'columns':['x','y'],'cluster.linkage':'2','cluster.linkage.flex.beta':-1})

    def test_native_orthomax_matches_two_factor_global_objective(self):
        from backend.analyses.basic_native_models import rotate_orthomax
        load=np.array([[.8,.1],[.6,.3],[.1,.7],[.2,.9]])
        for gamma in (0,.5,1,2,3.25):
            rotated,transform=rotate_orthomax(load,gamma)
            np.testing.assert_allclose(rotated,load@transform,atol=1e-12)
            np.testing.assert_allclose(transform.T@transform,np.eye(2),atol=1e-12)
            objective=lambda a:np.sum(a**4)-gamma/4*np.sum(np.sum(a*a,axis=0)**2)
            grid=np.linspace(-np.pi/2,np.pi/2,10001)
            maximum=max(objective(load@np.array([[np.cos(t),-np.sin(t)],[np.sin(t),np.cos(t)]])) for t in grid)
            self.assertGreaterEqual(objective(rotated)+1e-10,maximum)
            self.assertTrue(np.all(rotated.sum(axis=0)>=0))
        with self.assertRaises(ValueError):rotate_orthomax(load,-.1)

    def test_equamax_uses_variable_count_and_covariance_loadings_are_rescaled(self):
        from backend.analyses.basic_native_models import rotate_orthomax
        options={'columns':['x','y','z'],'retention':'count','threshold':2,'sta.fa.rot.type':'1'}
        result=analyze('1121',self.d,options)
        initial=np.asarray([r[1:] for r in table(result,'Initial component-factor loadings')['rows']])
        actual=np.asarray([r[1:] for r in table(result,'Rotated loadings')['rows']])
        np.testing.assert_allclose(actual,rotate_orthomax(initial,1.5)[0])
        cov=analyze('1121',self.d,{**options,'matrix':'covariance','threshold':3,'sta.fa.rot.type':'0'})
        full=np.asarray([r[1:] for r in table(cov,'Initial component-factor loadings')['rows']])
        np.testing.assert_allclose(np.sum(full**2,axis=1),np.ones(3),atol=1e-12)
    def test_multivariate_glm_and_term_step_report(self):
        rng=np.random.default_rng(17);x=np.arange(30);d=dataset(['x','y1','y2'],zip(x,2*x+rng.normal(size=30),-.5*x+rng.normal(size=30)))
        r=analyze('1109',d,{'responses':['y1','y2'],'predictors':['x'],'glm.showcorrs':True,'sta.reg.show_iter':True})
        self.assertTrue(any(t['title'].startswith('Multivariate tests') for t in r['tables']));self.assertEqual([row[0] for row in table(r,'Term steps — y1')['rows']],['Added','Removed'])

    def test_native_glm_contrast_bases_and_fitted_coefficients(self):
        from backend.analyses.basic_native_models import NativeDummy,NativeOrthogonal
        np.testing.assert_array_equal(NativeDummy().code_without_intercept(['a','b','c']).matrix,[[1,0],[0,1],[0,0]])
        np.testing.assert_array_equal(NativeOrthogonal().code_without_intercept(['a','b','c']).matrix,[[1,1],[-1,1],[0,-2]])
        d=dataset(['group','y'],[[g,mean+error] for g,mean in [('a',2),('b',4),('c',8)] for error in [-1,0,1]])
        for code,expected in [('0',[8,-6,-4]),('1',[14/3,-8/3,-2/3]),('2',[14/3,-1,-5/3])]:
            result=analyze('1109',d,{'responses':['y'],'factors':['group'],'glm.coding':code})
            np.testing.assert_allclose([r[1] for r in table(result,'Coefficients')['rows']],expected,atol=1e-12)
    def test_logistic_iteration_limit_and_trace(self):
        d=dataset(['x','y'],[[0,0],[0,1],[1,0],[1,1],[2,0],[2,1],[3,1],[3,1]])
        r=analyze('1306',d,{'response':'y','predictors':['x'],'sta.reg.max_iter':30,'sta.reg.show_iter':True});self.assertTrue(table(r,'Logistic iterations')['rows'])
        off=analyze('1306',d,{'response':'y','predictors':['x'],'sta.reg.show_iter':False});self.assertFalse(any(t['title']=='Logistic iterations' for t in off['tables']))
        with self.assertRaises(ValueError):analyze('1306',d,{'response':'y','predictors':['x'],'sta.reg.max_iter':1})

    def test_random_factor_glm_uses_same_native_regression_as_fixed(self):
        rng=np.random.default_rng(25);g=np.repeat(np.arange(8),8);x=rng.normal(size=64);effects=rng.normal(size=8);y=2+x+effects[g]+rng.normal(scale=.3,size=64)
        d=dataset(['x','g','y'],zip(x,g,y));r=analyze('1109',d,{'responses':['y'],'predictors':['x'],'random_factors':['g'],'sta.reg.show_iter':True})
        fixed=analyze('1109',d,{'responses':['y'],'predictors':['x'],'factors':['g'],'sta.reg.show_iter':True})
        np.testing.assert_allclose([row[1:] for row in table(r,'Coefficients')['rows']],[row[1:] for row in table(fixed,'Coefficients')['rows']])
        trace=table(r,'Term steps — y')['rows'];self.assertEqual(len(trace),4);self.assertGreater(trace[2][2],trace[0][2])
        self.assertFalse(any('Variance components' in t['title'] for t in r['tables']))

    def test_lda_report_controls_suppress_actual_outputs(self):
        rng=np.random.default_rng(12);rows=[[*(rng.normal(size=2)+group*3),str(group)] for group in range(3) for _ in range(8)]
        d=dataset(['x','y','g'],rows);options={'columns':['x','y'],'group':'g','sta.DS':False,'mv.var_covar.mxs':False,'sta.class.casewiseopt':False,'sta.mv.scree-varexplained':False,'mv.biplot.ui.opt':False}
        r=analyze('1110',d,options);self.assertEqual(r['charts'],[]);self.assertFalse(any('Covariance' in t['title'] or 'classification'==t['title'].lower() or t['title']=='Training classification' for t in r['tables']))
        r=analyze('1110',d,{**options,'sta.class.casewiseopt':True,'sta.class.missclass.opt':True,'mv.biplot.ui.opt':True});self.assertEqual(r['charts'][0]['title'],'Canonical plot');self.assertTrue(all(row[1]!=row[2] for row in table(r,'Training classification')['rows']))

if __name__=='__main__':unittest.main()
