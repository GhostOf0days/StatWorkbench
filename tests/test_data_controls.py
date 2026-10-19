import math
import unittest

import numpy as np
from scipy import stats

from backend.analyses import advanced
from backend.analyses.data_controls import conditional_mask


class DataControlsTests(unittest.TestCase):
    def run_analysis(self, aid, columns, rows, options):
        return advanced.analyze(aid, {'name': 'Synthetic', 'columns': columns, 'rows': rows}, options)

    def test_stack_index_and_unstack_four_orders(self):
        r = self.run_analysis('3001', ['X', 'Y'], [[1, 10], [2, None]], {'columns': ['X', 'Y'], 'sta.data.stackcols.numgroups': True})
        self.assertEqual(r['dataset']['rows'][:3], [[1, 1], [1, 2], [2, 10]])
        self.assertTrue(math.isnan(r['dataset']['rows'][3][1]))
        for mode, names in [('0', ['1', '2', '3']), ('1', ['3', '2', '1']), ('2', ['3', '1', '2']), ('3', ['2', '1', '3'])]:
            with self.subTest(order=mode):
                r = self.run_analysis('3002', ['X', 'G'], [[11, 2], [12, 1], [13, 2], [14, 3], [15, 1], [16, 2]], {'column': 'X', 'group': 'G', 'data.sort': mode})
                self.assertEqual(r['dataset']['columns'], names)

    def test_all_conditional_predicates_including_endpoint_complements(self):
        x = np.array([1, 2, 2, 4, 5, np.nan])
        expected = {
            0: [1, 2], 1: [0, 3, 4], 2: [0], 3: [0, 1, 2], 4: [3, 4], 5: [1, 2, 3, 4],
            6: [1, 2, 3], 7: [], 8: [0, 4], 9: [0, 1, 2, 3, 4],
            10: [0], 11: [4], 12: [0, 1, 2], 13: [3, 4],
            14: [3, 4], 15: [0, 1, 2], 16: [1, 2, 3, 4], 17: [0, 1, 2, 3],
        }
        for mode in range(18):
            with self.subTest(mode=mode):
                self.assertEqual(np.flatnonzero(conditional_mask(x, mode, 2, 4)).tolist(), expected[mode])
        for mode, expected_indices in [(18, [0]), (19, [0, 1, 2]), (20, [3, 4]), (21, [1, 2, 3, 4])]:
            with self.subTest(mode=mode):
                self.assertEqual(np.flatnonzero(conditional_mask(x, mode, .25, 0)).tolist(), expected_indices)
        with self.assertRaisesRegex(ValueError, 'fraction'):
            conditional_mask(x, 18, 50, 0)

    def test_conditional_sample_retains_original_alignment(self):
        r = self.run_analysis('3303', ['Value', 'Condition'], [['a', 3], ['b', 1], ['c', None], ['d', 2]], {'columns': ['Value'], 'condition_column': 'Condition', 'sta.data.samp.cond.cond': '10', 'A': 3})
        self.assertEqual(r['dataset']['rows'], [['b'], ['d']])

    def test_boxcox_shift_geometric_scaling_and_optional_qq(self):
        o = {'columns': ['X'], 'data.boxcox.lambda.estimate.ui': False, 'data.boxcox.lambda.ui': 0,
             'data.boxcox.values.addconst': True, 'data.boxcox.shift.const.ui': 1,
             'data.boxcox.values.addconstmin': True, 'data.boxcox.gm.ui': True, 'data.boxcox.qq.ui': True}
        r = self.run_analysis('3005', ['X'], [[-2], [0], [6], [None]], o)
        values = np.array([1., 3., 9.]); expected = np.exp(np.log(values).mean()) * np.log(values)
        np.testing.assert_allclose([row[0] for row in r['dataset']['rows'][:3]], expected)
        self.assertEqual(len(r['dataset']['rows']), 3)
        self.assertEqual(len(r['charts']), 2)
        self.assertEqual(r['tables'][0]['rows'][0][3], 3)
        removed = self.run_analysis('3005', ['X'], [[-2], [0], [6]], {**o, 'data.boxcox.values.addconst': False})
        self.assertNotIn('dataset', removed)
        self.assertEqual(removed['tables'][0]['rows'][0][5], 0)
        self.assertTrue(removed['warnings'])

    def test_boxcox_manual_and_mle_lambda_change_output(self):
        values = [1., 2., 4., 8., 32.]
        r = self.run_analysis('3005', ['X'], [[v] for v in values], {'columns': ['X'], 'data.boxcox.lambda.estimate.ui': True})
        y, lam = stats.boxcox(values)
        np.testing.assert_allclose(np.asarray(r['dataset']['rows']).ravel(), y, atol=1e-7)
        self.assertAlmostEqual(r['tables'][0]['rows'][0][2], lam, places=6)
        r = self.run_analysis('3005', ['X'], [[v] for v in values], {'columns': ['X'], 'data.boxcox.lambda.estimate.ui': False, 'data.boxcox.lambda.ui': 1})
        np.testing.assert_allclose(np.asarray(r['dataset']['rows']).ravel(), np.array(values)-1)

    def test_casecontrol_matches_live_original_fixtures(self):
        o = {'odds_ratio': 2, 'exposure': 20, 'power': 80, 'ratio': 1}
        r = self.run_analysis('1704', ['Unused'], [], o)
        self.assertEqual(r['tables'][0]['rows'][0][:2], [172, 172])
        matched = self.run_analysis('1704', ['Unused'], [], {**o, 'sta.pass.matched_design': True})
        self.assertEqual(matched['tables'][0]['rows'][0][1:], [69, 171, 342])
        self.assertAlmostEqual(matched['tables'][0]['rows'][0][0], .4)
        one = self.run_analysis('1704', ['Unused'], [], {**o, 'sta.onesided': True})
        self.assertLess(one['tables'][0]['rows'][0][0], 172)

    def test_observe_events_preserves_observed_native_truncation_with_warning(self):
        for probability in [.05, .95]:
            r = self.run_analysis('1703', ['Unused'], [], {'prevalence': 5, 'events': 1, 'PROB': probability})
            self.assertEqual(r['tables'][0]['rows'][0][0], 1)
            self.assertEqual(r['tables'][0]['rows'][0][3], 0)
            self.assertTrue(r['warnings'])
        legacy = self.run_analysis('1703', ['Unused'], [], {'prevalence': 5, 'events': 1, 'probability': .95})
        self.assertEqual(legacy['tables'][0]['rows'][0][0], 59)
        with self.assertRaisesRegex(ValueError, 'After truncating the probability'):
            self.run_analysis('1703', ['Unused'], [], {'prevalence': 5, 'events': 3, 'PROB': .95})


if __name__ == '__main__':
    unittest.main()
