"""Independent numeric fixtures for restricted factorial F tests."""
import itertools
import unittest
import numpy as np
from scipy import stats
from backend.analyses.basic import analyze
from tests.test_basic import dataset,table


class NativeFactorialTests(unittest.TestCase):
    def two_way(self,types,extra=None):
        means=[[1,3,4],[5,6,12]]
        rows=[[a,b,means[a][b]+e] for a,b,e in itertools.product(range(2),range(3),[-1,0,1])]
        return analyze('1104',dataset(['A','B','Y'],rows),{'response':'Y','factor_1':'A','factor_2':'B','factor_type_1':str(types[0]),'factor_type_2':str(types[1]),'sta.anova.showcontrasts':False,**(extra or {})})

    def three_way(self,types):
        rows=[[a,b,c,100+2*a+3*b+4*c+5*a*b+6*a*c+7*b*c+a*b*c+e] for a,b,c,e in itertools.product([-1,1],[-1,0,1],[-1,1],[-1,1])]
        return analyze('1105',dataset(['A','B','C','Y'],rows),{'response':'Y','factor_1':'A','factor_2':'B','factor_3':'C',**{f'factor_type_{i+1}':str(t) for i,t in enumerate(types)},'sta.anova.showcontrasts':False})

    def test_two_way_all_type_combinations_and_live_mixed_fixture(self):
        # Hand-computed SS: A=112.5(df1),B=79(df2),AB=21(df2),E=12(df12).
        for kinds,denominators,dfs in [((0,0),[1,1,1],[12,12,12]),((1,0),[1,10.5,1],[12,2,12]),((0,1),[10.5,1,1],[2,12,12]),((1,1),[10.5,10.5,1],[2,2,12])]:
            with self.subTest(types=kinds):
                rows=table(self.two_way(kinds),'ANOVA')['rows'][:3]
                np.testing.assert_allclose([r[1] for r in rows],[112.5,79,21],atol=1e-10)
                np.testing.assert_allclose([r[5] for r in rows],denominators,atol=1e-10)
                np.testing.assert_allclose([r[6] for r in rows],dfs)
                np.testing.assert_allclose([r[3] for r in rows],np.array([112.5,39.5,10.5])/denominators,atol=1e-10)
        rows=table(self.two_way((1,0)),'ANOVA')['rows']
        self.assertAlmostEqual(rows[0][4],1.8885783270583545e-7,places=13)
        self.assertAlmostEqual(rows[1][4],.21,places=13)
        self.assertEqual(rows[2][4],0)
        self.assertTrue(any('unwritten' in note for note in self.two_way((1,0))['notes']))

    def test_three_way_all_random_uses_native_highest_interaction_df(self):
        rows=table(self.three_way((1,1,1)),'ANOVA')['rows'][:7]
        # Orthogonal polynomial coefficients give these exact mean squares.
        means=np.array([96,72,384,200,864,392,8.])
        den=np.array([1056,584,1248,8,8,8,2.]);df=np.array([2,2,2,2,2,2,12])
        np.testing.assert_allclose([r[1]/r[2] for r in rows],means,atol=1e-9)
        np.testing.assert_allclose([r[5] for r in rows],den,atol=1e-9)
        np.testing.assert_allclose([r[6] for r in rows],df)
        np.testing.assert_allclose([r[4] for r in rows],stats.f.sf(means/den,[1,2,1,2,1,2,2],df))

    def test_three_way_single_random_restricted_error_strata(self):
        cases={
            (1,0,0):([2,200,864,2,2,8,2],[12,2,1,12,12,2,12]),
            (0,1,0):([200,2,392,2,8,2,2],[2,12,2,12,2,12,12]),
            (0,0,1):([864,392,2,8,2,2,2],[1,2,12,2,12,12,12]),
        }
        for types,(den,df) in cases.items():
            with self.subTest(types=types):
                rows=table(self.three_way(types),'ANOVA')['rows'][:7]
                np.testing.assert_allclose([r[5] for r in rows],den,atol=1e-9)
                np.testing.assert_allclose([r[6] for r in rows],df)

    def test_three_way_two_random_native_composite_df_and_pending_permutations(self):
        result=self.three_way((0,1,1));rows=table(result,'ANOVA')['rows'][:7]
        np.testing.assert_allclose([r[5] for r in rows],[1056,392,392,8,8,2,2],atol=1e-9)
        np.testing.assert_allclose([r[6] for r in rows],[1,2,2,2,2,12,12])

    def test_live_three_way_rfr_report_slots_are_preserved(self):
        result=self.three_way((1,0,1));rows=table(result,'ANOVA')['rows'][:7]
        np.testing.assert_allclose([r[3] for r in rows],[.08333333333333333,.1643835616438356,.4444444444444444,25,432,49,4])
        np.testing.assert_allclose([r[4] for r in rows],[.8675121437695433,.7999999999999998,.6256659163780025,.038461538461538436,8.895972847255962e-11,.020000000000000018,.04665600000000003],atol=2e-15)
        self.assertTrue(any('probability slots' in note for note in result['notes']))

    def test_live_three_way_rrf_report_slots_are_preserved(self):
        result=self.three_way((1,1,0));rows=table(result,'ANOVA')['rows'][:7]
        np.testing.assert_allclose([r[3] for r in rows],[.48,.36,.3076923076923077,196,25,108,4])
        np.testing.assert_allclose([r[4] for r in rows],[.6348516283298891,.7352941176470589,.6142777338450196,2.125584597223451e-8,.005076142131979711,.037749551350623745,.04665600000000003],atol=2e-15)
        self.assertTrue(any('Random/Random/Fixed' in note for note in result['notes']))

    def test_no_interactions_switch_defaults_to_false(self):
        from backend.analyses.basic import catalog
        item=next(e for e in catalog() if e['id']=='1104');fields={f['key']:f for f in item['fields']}
        self.assertNotIn('interactions',fields);self.assertFalse(fields['sta.anova.ao_nointer']['default'])
        full=self.two_way((1,0),{'sta.anova.ao_nointer':False});reduced=self.two_way((1,0),{'sta.anova.ao_nointer':True})
        self.assertEqual(len(table(full,'ANOVA')['rows']),4);self.assertEqual(len(table(reduced,'ANOVA')['rows']),3)
        self.assertAlmostEqual(table(reduced,'ANOVA')['rows'][0][5],10.5)

    def test_descriptive_normal_qq_uses_fitted_scale_and_average_ties(self):
        values=np.array([2,2,4,8,11.]);result=analyze('1001',dataset(['x'],[[v] for v in values]),{'columns':['x'],'sta.chart.qq':True})
        chart=result['charts'][0];quantiles=chart['series'][0]
        p=(np.array([1.5,1.5,3,4,5])-.375)/5.25
        expected=stats.norm.ppf(p,loc=values.mean(),scale=values.std(ddof=1))
        np.testing.assert_allclose(quantiles['x'],values);np.testing.assert_allclose(quantiles['y'],expected)
        np.testing.assert_allclose(chart['series'][1]['x'],chart['series'][1]['y'])

    def test_unequal_random_cells_use_marginal_totals_without_balance_rejection(self):
        # Independently evaluated rational marginal-total SS.
        rows=[[0,0,0],[0,0,2],[0,1,3],[0,1,4],[0,1,5],[1,0,6],[1,0,7],[1,0,9],[1,0,10],[1,1,2],[1,1,4]]
        y=np.array([r[2] for r in rows]);cf=y.sum()**2/len(y)
        sa=(14**2/5+38**2/6)-cf;sb=(34**2/6+18**2/5)-cf
        cells=2**2/2+12**2/3+32**2/4+6**2/2
        sab=cells-cf-sa-sb;se=np.dot(y,y)-cells
        r=analyze('1104',dataset(['A','B','Y'],rows),{'response':'Y','factor_1':'A','factor_2':'B','factor_type_1':'1','factor_type_2':'0','sta.anova.showcontrasts':False})
        out=table(r,'ANOVA')['rows'];np.testing.assert_allclose([z[1] for z in out],[sa,sb,sab,se],atol=1e-10)
        self.assertAlmostEqual(out[0][5],se/7);self.assertAlmostEqual(out[1][5],sab)

    def test_no_interactions_uses_interaction_error_not_pooled_replication_error(self):
        rows=table(self.two_way((1,0),{'interactions':False}),'ANOVA')['rows']
        self.assertEqual(len(rows),3);np.testing.assert_allclose(rows[2][1:3],[21,2])
        np.testing.assert_allclose([r[5] for r in rows[:2]],[10.5,10.5])

    def test_factor_posthoc_gate_and_within_error_scale(self):
        result=self.two_way((1,0),{'sta.anova.showcontrasts':True})
        self.assertFalse(any('post-hoc' in t['title'] for t in result['tables']))
        means=[[0,20,40],[5,25,50]]
        rows=[[a,b,means[a][b]+e] for a,b,e in itertools.product(range(2),range(3),[-1,0,1])]
        r=analyze('1104',dataset(['A','B','Y'],rows),{'response':'Y','factor_1':'A','factor_2':'B','factor_type_1':'1','factor_type_2':'0'})
        comparisons=table(r,'B — Additional post-hoc comparisons')['rows']
        lsd=next(row for row in comparisons if row[0]=='Fisher LSD')
        self.assertAlmostEqual(lsd[4],np.sqrt(1/3))
        self.assertFalse(any(t['title'].startswith('A — Additional') for t in r['tables']))

    def test_negative_marginal_ss_is_rejected_and_large_offsets_are_stable(self):
        # Strong unbalanced main effects can make the interaction SS negative.
        rows=[[0,0,0],[0,0,0],[0,1,1],[1,0,1],[1,1,2],[1,1,2]]
        options={'response':'Y','factor_1':'A','factor_2':'B','factor_type_1':'1','sta.anova.showcontrasts':False}
        with self.assertRaisesRegex(ValueError,'negative sums'):analyze('1104',dataset(['A','B','Y'],rows),options)
        rows=[[a,b,10**12+2*a+3*b+a*b+e] for a,b,e in itertools.product([-1,1],[-1,1],[-1,1])]
        out=table(analyze('1104',dataset(['A','B','Y'],rows),options),'ANOVA')['rows']
        np.testing.assert_allclose([r[1] for r in out],[32,72,8,8])


if __name__=='__main__':unittest.main()
