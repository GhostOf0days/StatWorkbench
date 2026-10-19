"""Independent integer fixtures with hand-computed orthogonal sums of squares."""
import copy
import itertools
import unittest
import numpy as np
from backend.analyses.doe import analyze, catalog


def data(columns, rows):
    return dict(columns=columns, rows=rows, name='Independent DOE fixture')


def anova(result):
    return {r[0]: r[1:] for r in result['tables'][0]['rows']}


def between_fixture(plan):
    rows = []
    if plan in ('1201', '1204'):
        for a,b,e in itertools.product(range(1,4),range(1,4),(-1,1)):
            c, d = (a+b-2)%3+1, (a+2*b-3)%3+1
            y = 40+2*(a-2)+3*(b-2)+4*(c-2)+e
            if plan == '1204':
                y += 5*(d-2)
            rows.append([y,a,b,c,d])
    elif plan == '1202':
        for a,b,d,e in itertools.product(range(1,4),range(1,4),range(1,3),(-1,1)):
            c = (a+b-2)%3+1
            y = 60+2*(a-2)+3*(b-2)+4*(c-2)+7*d+5*(a-2)*(2*d-3)+e
            rows.append([y,a,b,c,d])
    else:
        for a,b,c,e in itertools.product(range(1,4),range(1,4),range(1,4),(-1,1)):
            d = (a+b+c-3)%3+1
            y = 80+2*(a-2)+3*(b-2)+4*(c-2)+5*(d-2)+6*(a-2)*(b-2)+e
            rows.append([y,a,b,c,d])
    return data(['y','a','b','c','d'],rows), dict(response='y',a='a',b='b',c='c',d='d',cases_per_cell=2)


def repeated_fixture(plan):
    rows = []
    if plan != '1208':
        for g,a,sub in itertools.product(range(1,4),range(1,4),range(1,3)):
            b,c = (g+a-2)%3+1,(g+2*a-3)%3+1
            y = 40+2*(g-2)+3*(a-2)+4*(b-2)+6*(2*sub-3)+(2*sub-3)*(a-2)
            if plan == '1207':
                y += 5*(c-2)
            rows.append([y,a,b,c,sub,g])
    else:
        for c,row,a,sub in itertools.product(range(1,4),range(1,4),range(1,4),range(1,3)):
            g = (c-1)*3+row
            person = (g-1)*2+sub
            b = (row+a-2)%3+1
            y = (100+2*(c-2)+3*(row-2)+4*(a-2)+5*(b-2)+6*(c-2)*(a-2)
                 +7*(c-2)*(row-2)+6*(2*sub-3)+(2*sub-3)*(a-2))
            rows.append([y,a,b,c,person,g])
    return data(['y','a','b','c','sub','group'],rows), dict(response='y',a='a',b='b',c='c',subject='sub',group='group',cases_per_cell=2)


class DesignOfExperimentsTests(unittest.TestCase):
    def assert_ss(self, rows, expected):
        for name, (ss, df) in expected.items():
            self.assertAlmostEqual(rows[name][0], ss, places=8, msg=name)
            self.assertEqual(rows[name][1], df, name)

    def test_plan1_separate_pure_error_and_native_f(self):
        d,o = between_fixture('1201')
        r = anova(analyze('1201',d,o))
        self.assert_ss(r, {'Factor A':(48,2),'Factor B':(108,2),'Factor C':(192,2),'Residual':(0,2),'Within':(18,9),'Total':(366,17)})
        self.assertEqual(r['Factor A'][3],12)
        # Pooling residual into error would give 14.6667, not 12.
        # Closed-form F(2,9) survival probability, independent of SciPy's CDF.
        self.assertAlmostEqual(r['Factor A'][4], (9/(9+2*12))**4.5)

    def test_plan2_separate_block_interaction(self):
        d,o = between_fixture('1202')
        r = anova(analyze('1202',d,o))
        self.assert_ss(r, {'Factor A':(96,2),'Factor B':(216,2),'Factor C':(384,2),'Factor D':(441,1),'A × D':(600,2),'B × D':(0,2),'C × D':(0,2),'Residual':(0,4),'Within':(36,18)})
        self.assertEqual(r['A × D'][3],150)

    def test_plan3_block_removed_from_abc_confounding(self):
        d,o = between_fixture('1203')
        r = anova(analyze('1203',d,o))
        self.assert_ss(r, {'Factor A':(144,2),'Factor B':(324,2),'Factor C':(576,2),'Factor D':(900,2),'A × B':(864,4),'A × C':(0,4),'B × C':(0,4),'A × B × C (partial)':(0,6),'Within':(54,27)})
        self.assertEqual(r['Factor D'][3],225)

    def test_plan4_orthogonal_square_and_zero_residual_df(self):
        d,o = between_fixture('1204')
        r = anova(analyze('1204',d,o))
        self.assert_ss(r, {'Factor A':(48,2),'Factor B':(108,2),'Factor C':(192,2),'Factor D':(300,2),'Residual':(0,0),'Within':(18,9)})
        self.assertEqual(r['Residual'][2:], [None,None,None])

    def test_plans5_and6_subject_error_not_residual_error(self):
        for plan in ('1205','1206'):
            d,o = repeated_fixture(plan)
            r = anova(analyze(plan,d,o))
            group = 'Groups' if plan=='1205' else 'Factor C'
            self.assert_ss(r, {'Between subjects':(696,5),group:(48,2),'Subjects within groups':(648,3),'Within subjects':(312,12),'Factor A':(108,2),'Factor B':(192,2),'Error within':(12,6),'Total':(1008,17)})
            self.assertAlmostEqual(r[group][3],1/9)
            self.assertEqual(r['Factor A'][3],27)
            self.assertEqual(r['Factor B'][3],48)

    def test_plan7_orthogonal_repeated_square(self):
        d,o = repeated_fixture('1207')
        r = anova(analyze('1207',d,o))
        self.assert_ss(r, {'Groups':(48,2),'Subjects within groups':(648,3),'Factor A':(108,2),'Factor B':(192,2),'Factor C':(300,2),'Residual':(0,0),'Error within':(12,6)})
        self.assertEqual(r['Factor C'][3],75)

    def test_plan8_prime_terms_remove_rows_and_c_by_rows(self):
        d,o = repeated_fixture('1208')
        r = anova(analyze('1208',d,o))
        self.assert_ss(r, {'Between subjects':(3588,17),'Factor C':(144,2),'Rows':(324,2),'C × Rows':(1176,4),'Subjects within groups':(1944,9),'Within subjects':(2376,36),'Factor A':(576,2),'Factor B':(900,2),'A × C':(864,4),'B × C':(0,4),'A × B prime':(0,2),'A × B × C prime':(0,4),'Error within':(36,18),'Total':(5964,53)})
        self.assertAlmostEqual(r['Factor C'][3],1/3)
        self.assertEqual(r['A × C'][3],108)

    def test_row_permutation_invariance_and_ss_decomposition(self):
        rng = np.random.default_rng(42)
        for aid in [str(i) for i in range(1201,1209)]:
            d,o = between_fixture(aid) if int(aid)<=1204 else repeated_fixture(aid)
            d['rows'] = [[int(rng.integers(-20,40))]+row[1:] for row in d['rows']]
            before = anova(analyze(aid,d,o))
            rng.shuffle(d['rows'])
            after = anova(analyze(aid,d,o))
            for key in before:
                np.testing.assert_allclose(before[key],after[key],rtol=1e-12,atol=1e-10) if all(v is not None for v in before[key]) else self.assertEqual(before[key][1],after[key][1])
            components = [v for key,v in before.items() if key not in ('Between subjects','Within subjects','Total')]
            self.assertAlmostEqual(sum(v[0] for v in components),before['Total'][0],places=8)
            self.assertEqual(sum(v[1] for v in components),before['Total'][1])

    def test_missing_and_duplicate_cells_rejected(self):
        d,o = repeated_fixture('1205')
        d['rows'][0] = d['rows'][1].copy()
        with self.assertRaisesRegex(ValueError,'subject'):
            analyze('1205',d,o)
        d,o = between_fixture('1202')
        d['rows'].pop()
        with self.assertRaisesRegex(ValueError,'cell'):
            analyze('1202',d,o)

    def test_wrong_latin_square_and_nonorthogonality_rejected(self):
        d,o = between_fixture('1201')
        d['rows'][0][3] = 2 if d['rows'][0][3]==1 else 1
        with self.assertRaises(ValueError):
            analyze('1201',d,o)
        d,o = between_fixture('1204')
        for row in d['rows']:
            row[4] = row[3]
        with self.assertRaisesRegex(ValueError,'orthogonal'):
            analyze('1204',d,o)

    def test_native_response_integer_coercion_with_negative_values(self):
        d,o = between_fixture('1201')
        for i,row in enumerate(d['rows']):
            row[0] = (-1 if i%2 else 1)*(row[0]+.75)
        integer = copy.deepcopy(d)
        for row in integer['rows']:
            row[0] = int(row[0])
        result = analyze('1201',d,o)
        self.assertTrue(any('truncated toward zero' in w for w in result['warnings']))
        self.assertEqual(result['tables'],analyze('1201',integer,o)['tables'])

    def test_unreplicated_and_zero_error_do_not_fabricate_f(self):
        d,o = between_fixture('1201')
        d['rows'] = d['rows'][::2]
        o['cases_per_cell'] = 1
        result = analyze('1201',d,o)
        self.assertIsNone(anova(result)['Factor A'][3])
        self.assertTrue(result['warnings'])
        d,o = repeated_fixture('1207')
        for row in d['rows']:
            row[0] = 7
        r = analyze('1207',d,o)
        self.assertTrue(all(row[4] is None for row in r['tables'][0]['rows']))

    def test_plan8_unsupported_dimensions_and_reused_subject_ids(self):
        d,o = repeated_fixture('1208')
        for row in d['rows']:
            row[4] = (row[4]-1)%2+1
        with self.assertRaisesRegex(ValueError,'unique across groups'):
            analyze('1208',d,o)
        d,o = repeated_fixture('1208')
        d['rows'] = [row for row in d['rows'] if row[3]<=2]
        with self.assertRaisesRegex(ValueError,'unequal C levels'):
            analyze('1208',d,o)

    def test_invalid_codes_cases_and_missing_values(self):
        d,o = between_fixture('1201')
        for n in (True,0,-1,1.5,10001,float('inf')):
            with self.assertRaises(ValueError):
                analyze('1201',d,dict(o,cases_per_cell=n))
        bad = copy.deepcopy(d)
        bad['rows'][0][1] = 0
        with self.assertRaisesRegex(ValueError,'positive integers'):
            analyze('1201',bad,o)
        bad['rows'][0][1] = None
        with self.assertRaises(ValueError):
            analyze('1201',bad,o)

    def test_small_error_is_preserved_beside_large_treatment_effect(self):
        d,o = between_fixture('1201')
        for row in d['rows']:
            row[0] += 10000000*(row[2]-2)
        r = anova(analyze('1201',d,o))
        self.assertEqual(r['Within'][0],18)
        self.assertAlmostEqual(r['Factor A'][3],12)

    def test_catalog_eight_original_ids_and_roles(self):
        entries = catalog()
        self.assertEqual([e['id'] for e in entries],[str(i) for i in range(1201,1209)])
        p5 = next(e for e in entries if e['id']=='1205')
        self.assertEqual(next(f['label'] for f in p5['fields'] if f['key']=='subject'),'Factor C')
        self.assertTrue(all(e['coverage']!='unsupported' for e in entries))
