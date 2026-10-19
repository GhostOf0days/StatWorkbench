import unittest
import numpy as np
from backend.analyses.basic import analyze,catalog
from tests.test_basic import dataset,table


class NegativeModelControlTests(unittest.TestCase):
    def test_native_nointercept_checkbox_controls_ols_and_wls_model(self):
        x=np.array([1.,2.,3.,5.,8.]);y=np.array([6.,7.,11.,14.,21.]);w=np.array([1.,3.,2.,4.,1.])
        d=dataset(['x','y','w'],zip(x,y,w))
        base={'response':'y','predictors':['x'],'weights':'w','sta.reg.lin.ao.res.ht-tests':False,'sta.reg.lin.ao.norm-qq-hist':False}
        for aid,weights in [('1301',np.ones(5)),('1302',w)]:
            with self.subTest(aid=aid):
                origin=analyze(aid,d,{**base,'sta.reg.nointercept':True})
                rows=table(origin,'Coefficients')['rows'];self.assertEqual(len(rows),1)
                self.assertAlmostEqual(rows[0][1],np.sum(weights*x*y)/np.sum(weights*x*x),places=12)
                intercept=analyze(aid,d,{**base,'sta.reg.nointercept':False})
                rows=table(intercept,'Coefficients')['rows'];self.assertEqual(rows[0][0],'Intercept')
                design=np.column_stack([np.ones(5),x]);expected=np.linalg.solve(design.T@(weights[:,None]*design),design.T@(weights*y))
                np.testing.assert_allclose([r[1] for r in rows],expected,atol=1e-12)
                legacy=analyze(aid,d,{**base,'intercept':False})
                np.testing.assert_allclose([r[1] for r in table(origin,'Coefficients')['rows']],[r[1] for r in table(legacy,'Coefficients')['rows']])
                authoritative=analyze(aid,d,{**base,'intercept':True,'sta.reg.nointercept':True})
                self.assertEqual(len(table(authoritative,'Coefficients')['rows']),1)

    def test_native_catalog_has_negative_default_and_no_opposing_alias(self):
        entries={c['id']:c for c in catalog()}
        for aid in ('1301','1302','1310'):
            fields={f['key']:f for f in entries[aid]['fields']}
            self.assertFalse(fields['sta.reg.nointercept']['default'])
            self.assertNotIn('intercept',fields)


if __name__=='__main__':unittest.main()
