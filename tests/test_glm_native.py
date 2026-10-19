"""Independent fixtures for GLM design and model comparisons."""
import unittest
import numpy as np
from scipy import stats
from backend.analyses.basic import analyze
from tests.test_basic import dataset, table


class NativeGLMTests(unittest.TestCase):
    def setUp(self):
        self.a=np.repeat([1,2],12)
        self.b=np.tile(np.repeat([1,2,3],4),2)
        self.x=np.tile([-1.8,-.2,1.1,2.7],6)+np.repeat([0,1,2,1,3,2],4)
        self.noise=np.array([.2,-.3,.4,-.1,-.4,.5,-.1,.3]*3)
        self.y=3+2*(self.a==1)-.7*(self.b==1)+1.4*(self.b==2)+.8*np.trunc(self.x)+self.noise
        self.y2=-2+.3*self.y+np.sin(np.arange(24))
        self.data=dataset(['a','b','x','y','y2'],zip(self.a,self.b,self.x,self.y,self.y2))
        self.options={'responses':['y'],'factors':['a'],'random_factors':['b'],'predictors':['x'],'sta.reg.show_iter':True}

    def test_coefficients_and_se_are_least_squares_including_random_contrasts(self):
        result=analyze('1109',self.data,self.options)
        x=np.column_stack([np.ones(24),self.a==1,self.b==1,self.b==2,np.trunc(self.x)])
        beta=np.linalg.solve(x.T@x,x.T@self.y)
        residual=self.y-x@beta;mse=residual@residual/19
        se=np.sqrt(np.diag(np.linalg.inv(x.T@x))*mse)
        rows=table(result,'Coefficients')['rows']
        np.testing.assert_allclose([r[1] for r in rows],beta,atol=1e-12)
        np.testing.assert_allclose([r[2] for r in rows],se,atol=1e-12)
        np.testing.assert_allclose([r[4] for r in rows],2*stats.t.sf(abs(beta/se),19),rtol=1e-10)
        self.assertTrue(any('truncates numeric covariates' in w for w in result['warnings']))
        self.assertEqual(table(result,'Model variables')['rows'][1][2],'Random factor')

    def test_sequential_and_partial_sums_of_squares_and_step_denominators(self):
        result=analyze('1109',self.data,self.options)
        x=np.column_stack([np.ones(24),self.a==1,self.b==1,self.b==2,np.trunc(self.x)])
        def sse(cols):
            z=x[:,cols];res=self.y-z@np.linalg.lstsq(z,self.y,rcond=None)[0]
            return res@res
        full=sse(range(5));previous=sse([0]);selected=[0]
        sequential=table(result,'ANOVA')['rows'];partial=table(result,'Partial effects (full model minus term)')['rows'];steps=table(result,'Term steps — y')['rows']
        for i,columns in enumerate([[1],[2,3],[4]]):
            selected+=columns;current=sse(selected);effect=previous-current;df=len(columns)
            self.assertAlmostEqual(sequential[i][1],effect,places=11)
            self.assertAlmostEqual(sequential[i][3],effect/df/(full/19),places=9)
            self.assertAlmostEqual(steps[2*i][7],effect/df/(current/(24-len(selected))),places=9)
            self.assertAlmostEqual(partial[i][1],sse([j for j in range(5) if j not in columns])-full,places=11)
            previous=current
        self.assertAlmostEqual(sum(r[1] for r in sequential),np.sum((self.y-self.y.mean())**2),places=10)

    def test_random_factor_interactions_and_multivariate_model_are_available(self):
        result=analyze('1109',self.data,{**self.options,'responses':['y','y2'],'interactions':True})
        coefficients=table(result,'y — Coefficients')['rows']
        self.assertEqual(sum(':' in r[0] for r in coefficients),2)
        self.assertEqual(len(table(result,'Multivariate tests — Model')['rows']),4)
        fixed=analyze('1109',self.data,{**self.options,'responses':['y','y2'],'factors':['a','b'],'random_factors':[],'interactions':True})
        np.testing.assert_allclose([r[1:] for r in table(result,'Multivariate tests — Model')['rows']],[r[1:] for r in table(fixed,'Multivariate tests — Model')['rows']])

    def test_correlation_control_includes_random_design_columns_and_steps_toggle(self):
        off=analyze('1109',self.data,{**self.options,'sta.reg.show_iter':False})
        self.assertFalse(any('Term steps' in t['title'] or 'Correlations' in t['title'] for t in off['tables']))
        on=analyze('1109',self.data,{**self.options,'glm.showcorrs':True})
        corr=table(on,'Correlations of responses and model columns')
        self.assertEqual(len(corr['rows']),5)
        self.assertTrue(any('f1' in str(row[0]) for row in corr['rows']))

    def test_numeric_factor_order_and_fractional_truncation(self):
        d=dataset(['g','y'],[[g,mean+e] for g,mean in [(8.9,2),(9.2,4),(10.1,8)] for e in [-1,0,1]])
        result=analyze('1109',d,{'responses':['y'],'random_factors':['g']})
        np.testing.assert_allclose([r[1] for r in table(result,'Coefficients')['rows']],[8,-6,-4],atol=1e-12)
        with self.assertRaisesRegex(ValueError,'consecutive'):
            analyze('1109',dataset(['g','y'],[[1,1],[1,2],[3,3],[3,5]]),{'responses':['y'],'random_factors':['g']})


if __name__=='__main__':unittest.main()
