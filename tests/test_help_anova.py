"""Reference report values for ANOVA workflows."""
import itertools
import unittest
import numpy as np
from scipy import stats
from backend.analyses.basic import analyze, catalog
from tests.test_basic import dataset, table


class HelpAnovaTests(unittest.TestCase):
    def test_native_fixed_default_and_explicit_ols_extension(self):
        for entry in catalog():
            if entry['id'] in ('1104','1105'):
                field=next(f for f in entry['fields'] if f['key']=='ss_type')
                self.assertEqual(field['default'],'native')

    def two_way(self,interaction):
        rows=[[a+1,b+1,10+10*a+15*b+interaction*a*b+e] for a,b,e in itertools.product(range(3),range(3),[-1,0,1])]
        return analyze('1104',dataset(['A','B','Y'],rows),{'response':'Y','factor_1':'A','factor_2':'B'})

    def test_two_way_strong_and_zero_interactions_still_print_simple_comparisons(self):
        for interaction in (0,12):
            result=self.two_way(interaction)
            reports=[t for t in result['tables'] if ' within ' in t['title']]
            self.assertEqual(len(reports),6)
            row=next(r for r in reports[0]['rows'] if r[0]=='Scheffe')
            np.testing.assert_allclose([row[3],row[7],row[8]],[-15,-17.130047293794263,-12.869952706205739])
        rows=table(self.two_way(12),'ANOVA')['rows']
        self.assertAlmostEqual(dict(table(self.two_way(0),'ANOVA totals')['rows'])['Omega squared for combined effect'],.9953995569943772)
        np.testing.assert_allclose([r[8] for r in rows],[4356,6561,432,1])
        np.testing.assert_allclose([r[9] for r in rows[:3]],[3.5545571456617866,3.5545571456617866,2.9277441728071842])
        np.testing.assert_allclose([r[10] for r in rows[:3]],[.36936516687163395,.5563801365506128,.07310970696747382])

    def test_three_way_live_slice_overwrite_relabel_and_range_zero(self):
        rows=[[a+1,b+1,c+1,100+2*a+3*b+4*c+5*a*b+6*a*c+7*b*c+a*b*c+e] for a,b,c,e in itertools.product(range(3),range(3),range(3),[-1,0,1])]
        result=analyze('1105',dataset(['A','B','C','Y'],rows),{'response':'Y','factor_1':'A','factor_2':'B','factor_3':'C'})
        reports=[t for t in result['tables'] if ' within ' in t['title']]
        self.assertEqual(len(reports),12)
        expected=[-17,-24,-31,-14,-21,-28,-13,-22,-31,-13,-22,-31]
        for i,report in enumerate(reports):
            row=next(r for r in report['rows'] if r[0]=='Scheffe')
            self.assertAlmostEqual(row[3],expected[i]);self.assertAlmostEqual(row[7],expected[i]-2.037577731943758)
            hsd=next(r for r in report['rows'] if r[0]=='Tukey HSD')
            if 6<=i<=8:self.assertEqual(hsd[5:7],[0.,1.]);self.assertFalse(hsd[9])
            else:
                self.assertAlmostEqual(hsd[5],abs(expected[i])*np.sqrt(3))
                self.assertAlmostEqual(hsd[6],2.0753575710408256e-5,delta=1e-8)

    def unequal_three_way(self,dimensions,ab=True):
        # Centered replicates make each cell's N=3 and the ANOVA error MS=1.
        # Expected comparisons below follow the documented report conventions,
        # not another call to the implementation's post-hoc helper.
        rows=[[a+1,b+1,c+1,100+2*a+3*b+4*c+6*a*c+7*b*c+(5*a*b+a*b*c if ab else 0)+e]
              for a,b,c,e in itertools.product(*(range(n) for n in dimensions),[-1,0,1])]
        return analyze('1105',dataset(['A','B','C','Y'],rows),
            {'response':'Y','factor_1':'A','factor_2':'B','factor_3':'C'})

    def test_three_by_two_by_three_retains_third_scratch_slot(self):
        result=self.unequal_three_way((3,2,3))
        reports=[t for t in result['tables'] if ' within ' in t['title']]
        self.assertEqual(len(reports),11)
        # A-within-B last wrote the third slot as Y(A=3,B=2,C=3)=167.
        # Later B-within-C and A-within-C write only the first two slots.
        expected=[[-13,-63,-50],[-22,-47,-25],[-31,-31,0]]
        for level,differences in enumerate(expected,1):
            report=table(result,f'A within C={level} — Additional post-hoc comparisons')
            hsd=[r for r in report['rows'] if r[0]=='Tukey HSD']
            self.assertEqual([r[1:3] for r in hsd],[['1','2'],['1','3'],['2','3']])
            np.testing.assert_allclose([r[3] for r in hsd],differences)
            np.testing.assert_allclose([r[4] for r in hsd],1/np.sqrt(3))
            np.testing.assert_allclose([r[5] for r in hsd],np.abs(differences)*np.sqrt(3))
            # The shifted minimum scans slot 2, which is retained and nonempty.
            b_report=table(result,f'B within C={level} — Additional post-hoc comparisons')
            b_hsd=next(r for r in b_report['rows'] if r[0]=='Tukey HSD')
            self.assertAlmostEqual(b_hsd[5],abs(differences[0])*np.sqrt(3))
        self.assertEqual(hsd[-1][5:7],[0.,1.])

    def test_two_by_three_by_three_reuses_conditioning_index_but_zero_tail(self):
        result=self.unequal_three_way((2,3,3))
        reports=[t for t in result['tables'] if ' within ' in t['title']]
        self.assertEqual(len(reports),11)
        # In A-within-B=3 the conditioning-index count uses slot 2, retained
        # from B-within-A. It must not become zero when only A slots are written.
        last_ab=table(result,'A within B=3 — Additional post-hoc comparisons')
        hsd=next(r for r in last_ab['rows'] if r[0]=='Tukey HSD')
        self.assertAlmostEqual(hsd[3],-28);self.assertAlmostEqual(hsd[5],28*np.sqrt(3))
        for level,difference in enumerate([-8,-16,-24],1):
            b_report=table(result,f'B within C={level} — Additional post-hoc comparisons')
            hsd=[r for r in b_report['rows'] if r[0]=='Tukey HSD']
            np.testing.assert_allclose([r[3] for r in hsd],[difference,2*difference,difference])
            self.assertTrue(all(np.isinf(r[4]) and r[5:7]==[0.,1.] and not r[9] for r in hsd))
            # A-within-C consumes only two of the three B-written values.
            a_report=table(result,f'A within C={level} — Additional post-hoc comparisons')
            a_hsd=[r for r in a_report['rows'] if r[0]=='Tukey HSD']
            self.assertEqual(len(a_hsd),1)
            self.assertEqual(a_hsd[0][1:4],['1','2',difference])
            self.assertAlmostEqual(a_hsd[0][5],abs(difference)*np.sqrt(3))

    def test_nonsignificant_ab_leaves_zero_tail_and_omits_empty_pairs(self):
        result=self.unequal_three_way((3,2,3),ab=False)
        anova=table(result,'ANOVA')['rows']
        self.assertEqual(next(row[4] for row in anova if row[0]=='C(f0, Sum):C(f1, Sum)'),1.)
        reports=[t for t in result['tables'] if ' within ' in t['title']]
        self.assertEqual(len(reports),6)
        self.assertFalse(any('within A=' in t['title'] or 'within B=' in t['title'] for t in reports))
        for level,difference in enumerate([-3,-10,-17],1):
            report=table(result,f'A within C={level} — Additional post-hoc comparisons')
            self.assertEqual(len(report['rows']),6)
            self.assertTrue(all(r[1:3]==['1','2'] for r in report['rows']))
            # Empty A=3 is skipped as a pair, but remains in family size K=3.
            bonf=next(r for r in report['rows'] if r[0]=='Bonferroni')
            expected=min(1.,3*2*stats.t.sf(abs(difference)/np.sqrt(2/3),54-3))
            self.assertAlmostEqual(bonf[6],expected,places=13)
            for row in report['rows']:
                if row[0] in ('Tukey HSD','Tukey B','Newman–Keuls'):
                    self.assertTrue(np.isinf(row[4]));self.assertEqual(row[5:7],[0.,1.]);self.assertFalse(row[9])

    def test_posthoc_mean_sort_keeps_empty_slot_in_rank_span(self):
        from backend.analyses import basic
        from backend.analyses.basic_model_options import posthoc
        from backend.analyses.native_posthoc import range_survival
        # Native swapping produces labels 3,2(empty),4,1. The empty slot
        # contributes to the 3-vs-4 rank span even though its pairs are omitted.
        groups=[('1',np.array([2.,3,4])),('2',np.array([])),
                ('3',np.array([0.,1,2])),('4',np.array([1.,2,3]))]
        report=posthoc(groups,3,24,.95,basic,balanced=True,effective_n=3,total_n=28)[0]
        self.assertTrue(all('2' not in row[1:3] for row in report['rows']))
        nk=next(row for row in report['rows'] if row[:3]==['Newman–Keuls','3','4'])
        self.assertEqual(nk[5],1.)
        self.assertAlmostEqual(nk[6],range_survival(1.,3,24),places=13)

    def test_typed_factor_label_collisions_are_rejected_clearly(self):
        rows=[[a,b,c,3*ai+2*b+c+e] for ai,a in enumerate([1,'1',2]) for b,c,e in itertools.product(range(3),range(2),[-1,1])]
        with self.assertRaisesRegex(ValueError,'same text label'):
            analyze('1105',dataset(['A','B','C','Y'],rows),{'response':'Y','factor_1':'A','factor_2':'B','factor_3':'C'})

