"""Reference values for deterministic post-hoc regression fixtures."""
import unittest
from backend.analyses.basic import analyze
from tests.test_basic import dataset, table


class NativePosthocTests(unittest.TestCase):
    def test_native_equal_size_families_and_decision_rules(self):
        data=dataset(['A','B','C'],[[1,3,7],[2,4,8],[4,6,10],[5,9,12]])
        result=analyze('1102',data,{'columns':['A','B','C'],'sta.anova.showcontrasts':True})
        rows=table(result,'Additional post-hoc comparisons')['rows']
        expected={
            'Fisher LSD':([.14515005663667124,.0023915514728329867,.038338980597223404],[False,True,False]),
            'Bonferroni':([.45388906209207125,.010527904185357206,.12945047479417537],[False,True,False]),
            'Scheffe':([.337231596983783,.011306636732846154,.11575005880037825],[False,True,False]),
            'Tukey HSD':([.3072421961969336,.00888873732374329,.09891075768889235],[False,True,False]),
            'Tukey B':([.22933070278972317,.00888873732374329,.07105663037362087],[False,True,False]),
            'Newman–Keuls':([.15141920938251274,.00888873732374329,.043202503058349384],[False,True,True]),
        }
        for method,(probabilities,significance) in expected.items():
            actual=[r for r in rows if r[0]==method]
            self.assertEqual(len(actual),3)
            for row,p,significant in zip(actual,probabilities,significance):
                # Finite quadrature; normal-tail arithmetic differs at roundoff scale.
                tolerance=1e-8 if method in ('Tukey HSD','Tukey B','Newman–Keuls') else 1e-12
                self.assertAlmostEqual(row[6],p,delta=tolerance)
                self.assertEqual(row[9],significant)
        self.assertFalse(any(t['title'].startswith('Tukey HSD (95%') for t in result['tables']))

    def test_later_smaller_group_routes_only_to_kramer(self):
        data=dataset(['A','B','C'],[[7,1,3],[8,2,4],[10,4,6],[12,None,9],[13,None,None]])
        result=analyze('1102',data,{'columns':['A','B','C'],'sta.anova.showcontrasts':True})
        methods={r[0] for r in table(result,'Additional post-hoc comparisons')['rows']}
        self.assertEqual(methods,{'Fisher LSD','Bonferroni','Scheffe','Tukey–Kramer'})
        rows=[r for r in table(result,'Additional post-hoc comparisons')['rows'] if r[0]=='Tukey–Kramer']
        for row,q,p in zip(rows,[6.196382919923736,3.95947210557654,2.4472311072242245],[.004550375952530938,.049328372706917256,.24662625558385698]):
            self.assertAlmostEqual(row[5],q,places=12)
            self.assertAlmostEqual(row[6],p,delta=1e-8)

    def test_native_first_minimum_group_retains_hsd_with_unequal_counts(self):
        data=dataset(['A','B','C'],[[1,3,7],[2,4,8],[4,6,10],[None,9,12],[None,None,13]])
        result=analyze('1102',data,{'columns':['A','B','C'],'sta.anova.showcontrasts':True})
        rows=table(result,'Additional post-hoc comparisons')['rows']
        hsd=[r for r in rows if r[0]=='Tukey HSD']
        for row,q,p in zip(hsd,[2.289175087372122,5.542213369427244,3.253038282055121],[.28723941797852715,.008906837004148849,.1070773831470454]):
            self.assertAlmostEqual(row[5],q,places=12)
            self.assertAlmostEqual(row[6],p,delta=1e-8)

    def test_native_group_sort_precedes_first_minimum_rule(self):
        data=dataset(['C','A','B'],[[7,1,3],[8,2,4],[10,4,6],[12,None,9],[13,None,None]])
        result=analyze('1102',data,{'columns':['C','A','B'],'sta.anova.showcontrasts':True})
        rows=table(result,'Additional post-hoc comparisons')['rows']
        self.assertEqual([r[0] for r in table(result,'Group summaries')['rows']],['A','B','C'])
        self.assertTrue(any(r[0]=='Tukey HSD' for r in rows))
        self.assertAlmostEqual(next(r[6] for r in rows if r[:3]==['Tukey B','A','B']),.2136676681369173,delta=1e-8)

    def test_native_range_families_follow_mean_order(self):
        data=dataset(['A','B','C'],[[7,1,3],[8,2,4],[10,4,6],[12,5,9]])
        result=analyze('1102',data,{'columns':['A','B','C'],'sta.anova.showcontrasts':True})
        rows=table(result,'Additional post-hoc comparisons')['rows']
        for method in ('Tukey B','Newman–Keuls'):
            family=[row for row in rows if row[0]==method]
            self.assertEqual([row[1:3] for row in family],[['B','C'],['B','A'],['C','A']])
            self.assertTrue(all(row[3]<0 for row in family))
        self.assertEqual([r[1:3] for r in rows if r[0]=='Scheffe'],[['A','B'],['A','C'],['B','C']])


if __name__=='__main__':unittest.main()
