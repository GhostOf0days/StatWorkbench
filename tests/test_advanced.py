"""Numeric fixtures and validation for original advanced implementations."""
import math
import unittest
import numpy as np
from backend.analyses.advanced import analyze, catalog, residual_diagnostics
from backend.common import sanitize_json


def dataset(columns, rows):
    return {"columns": columns, "rows": rows, "name": "Fixture"}


class AdvancedNumericalTests(unittest.TestCase):
    def test_heteroscedasticity_uses_supplied_residuals_without_refitting(self):
        from backend.worker import dispatch
        x = np.arange(1.,11.)
        d = dataset(['e','x'],np.column_stack([x,x]).tolist())
        opts = dict(residuals='e',predictors=['x'],**{'reg.harvey':False,'reg.glejser':False,'reg.arch':False,'reg.white':False})
        result = dispatch('analyze',dict(analysis='1320',data=d,options=opts))
        row = result['tables'][0]['rows'][0]
        # Simple auxiliary regression R² from centered cross-products.
        y = x*x
        expected = len(x)*np.dot(x-x.mean(),y-y.mean())**2/(np.dot(x-x.mean(),x-x.mean())*np.dot(y-y.mean(),y-y.mean()))
        self.assertAlmostEqual(row[3],expected)
        self.assertGreater(row[3],9)
        # A preliminary regression of e on x would erase the supplied sequence.
        with self.assertRaises(ValueError):
            residual_diagnostics(d,dict(response='e',predictors=['x']))

    def test_heteroscedasticity_flags_white_modes_and_summaries(self):
        rng = np.random.default_rng(72)
        d = dataset(['e','x','z'],rng.normal(size=(30,3)).tolist())
        opts = dict(residuals='e',predictors=['x','z'])
        for mode,df in [('0',5),('1',4),('2',2)]:
            result = residual_diagnostics(d,dict(opts,**{'sta.time.reg.include':mode}))
            self.assertEqual(len(result['tables'][0]['rows']),5)
            self.assertEqual(result['tables'][0]['rows'][-1][2],df)
            self.assertEqual(len(result['tables']),1)
        opts.update({'reg.harvey':False,'reg.glejser':False,'reg.arch':False,'reg.white':False,'sta.reg.modelsum.opt':True})
        result = residual_diagnostics(d,opts)
        self.assertEqual(len(result['tables'][0]['rows']),1)
        self.assertEqual(len(result['tables']),3)
        self.assertEqual(result['tables'][2]['rows'][0][0],'Intercept')
        with self.assertRaisesRegex(ValueError,'at least one'):
            residual_diagnostics(d,dict(opts,**{'reg.bpg':False}))

    def test_heteroscedasticity_arch_preserves_lag_alignment(self):
        e = np.array([1.,2.,-1.,4.,3.,-2.,5.,1.,-3.,2.])
        d = dataset(['e','x'],np.column_stack([e,np.arange(len(e))]).tolist())
        opts = dict(residuals='e',predictors=['x'],**{'reg.bpg':False,'reg.harvey':False,'reg.glejser':False,'reg.white':False,'sta.time.lags_c':1})
        row = residual_diagnostics(d,opts)['tables'][0]['rows'][0]
        x,y = e[:-1]**2,e[1:]**2
        expected = len(y)*np.corrcoef(x,y)[0,1]**2
        self.assertEqual(row[1:3],[9,1])
        self.assertAlmostEqual(row[3],expected)
        d['rows'][4][0] = None
        with self.assertRaisesRegex(ValueError,'no internal gaps'):
            residual_diagnostics(d,opts)

    def test_heteroscedasticity_harvey_zero_is_explicitly_unavailable(self):
        d = dataset(['e','x'],[[0,1],[2,2],[-1,3],[3,4],[5,5],[2,6],[4,7],[1,8]])
        r = residual_diagnostics(d,dict(residuals='e',predictors=['x']))
        row = next(row for row in r['tables'][0]['rows'] if row[0]=='Harvey')
        self.assertEqual(row[3:],[None,None])
        self.assertTrue(any('zero residuals' in w for w in r['warnings']))
        self.assertIsNotNone(r['tables'][0]['rows'][0][3])

    def test_heteroscedasticity_trailing_padding_and_collinearity(self):
        d = dataset(['e','x'],[[i%3+1,i] for i in range(12)]+[[None,None],[None,None]])
        r = residual_diagnostics(d,dict(residuals='e',predictors=['x']))
        self.assertEqual(r['tables'][0]['rows'][0][1],12)
        self.assertTrue(any('Trimmed 2' in note for note in r['notes']))
        for row in d['rows'][:12]:
            row[1] = 1
        r = residual_diagnostics(d,dict(residuals='e',predictors=['x']))
        self.assertIsNone(r['tables'][0]['rows'][0][3])
        self.assertTrue(any('collinear' in w for w in r['warnings']))

    def test_kaplan_meier_censoring_and_ties(self):
        d = dataset(["time", "status"], [[1, 1], [2, 1], [2, 0], [3, 1]])
        r = analyze("1621", d, {"time": "time", "status": "status"})
        self.assertEqual(r["charts"][0]["type"], "step")
        rows = r["tables"][0]["rows"]
        np.testing.assert_allclose([row[4] for row in rows], [.75, .5, 0])
        self.assertEqual([row[1] for row in rows], [4, 3, 1])
        self.assertEqual([row[3] for row in rows], [0, 1, 0])

    def test_nelson_aalen(self):
        d = dataset(["time", "status"], [[1, 1], [2, 1], [2, 0], [3, 1]])
        r = analyze("1622", d, {"time": "time", "status": "status"})
        self.assertEqual(r["charts"][0]["type"], "step")
        np.testing.assert_allclose([row[4] for row in r["tables"][0]["rows"]], [.25, .25+1/3, 1.25+1/3])

    def test_survival_with_censoring_only(self):
        d = dataset(["time", "status"], [[1, 0], [2, 0], [3, 0]])
        o = {"time": "time", "status": "status"}
        km = analyze("1621", d, o)["tables"][0]["rows"]
        na = analyze("1622", d, o)["tables"][0]["rows"]
        self.assertEqual([x[4] for x in km], [1, 1, 1])
        self.assertEqual([x[4] for x in na], [0, 0, 0])

    def test_interrupted_series_gaps_rejected_and_padding_allowed(self):
        d = dataset(["before", "after"], [[1, 2], [None, 5], [2, 4], [4, None]])
        with self.assertRaisesRegex(ValueError, "internal gaps"):
            analyze("1503", d, {"before": "before", "after": "after"})
        d["rows"][1][0] = 3
        self.assertTrue(analyze("1503", d, {"before": "before", "after": "after"})["tables"])

    def test_probit_singular_and_separated_rejected(self):
        o = {"dose": "dose", "events": "events", "total": "total"}
        d = dataset(["dose", "events", "total"], [[1, 1, 10], [1, 2, 10], [1, 4, 10], [1, 8, 10]])
        with self.assertRaisesRegex(ValueError, "varying doses"):
            analyze("1601", d, o)
        d["rows"] = [[1, 0, 10], [2, 0, 10], [3, 10, 10], [4, 10, 10]]
        with self.assertRaisesRegex(ValueError, "separated"):
            analyze("1601", d, o)

    def test_constant_acf_and_numeric_typo_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonconstant"):
            analyze("1501", dataset(["x"], [[1], [1], [1], [1]]), {"column": "x", "lags": 1})
        d = dataset(["x", "y"], [[1, 2], [2, 3], ["typo", 4], [4, 5]])
        with self.assertRaisesRegex(ValueError, "nonnumeric"):
            analyze("1630", d, {"first": "x", "second": "y"})

    def test_roc_hand_computed_auc(self):
        d = dataset(["score", "outcome"], [[.1, 0], [.4, 0], [.35, 1], [.8, 1]])
        r = analyze("1610", d, {"score": "score", "status": "outcome"})
        self.assertEqual(r["tables"][0]["rows"][0][1], .75)
        # Three concordant positive-negative pairs out of four.

    def test_paired_identical_roc(self):
        d = dataset(["a", "b", "outcome"], [[.1, .1, 0], [.4, .4, 0], [.35, .35, 1], [.8, .8, 1]])
        r = analyze("1611", d, {"columns": ["a", "b"], "status": "outcome"})
        self.assertEqual(r["tables"][-1]["rows"][0][2:], [0, 0, 0, 1])

    def test_paired_degenerate_roc_does_not_claim_zero_pvalue(self):
        d = dataset(["a", "b", "outcome"], [[0, 3, 0], [1, 2, 0], [2, 1, 1], [3, 0, 1]])
        r = analyze("1611", d, {"columns": ["a", "b"], "status": "outcome"})
        row = r["tables"][-1]["rows"][0]
        self.assertEqual(row[2:4], [1, 0])
        self.assertEqual(row[4:], [None, None])
        self.assertEqual(r["tables"][0]["rows"][0][3:], [None, None])
        self.assertTrue(any("variance is zero" in w for w in r["warnings"]))

    def test_bland_altman_bias(self):
        d = dataset(["a", "b"], [[2, 1], [4, 3], [6, 5]])
        result = analyze("1630", d, {"first": "a", "second": "b"})
        row = result["tables"][0]["rows"][0]
        self.assertEqual(row, [3, 1, 0, 1, 1])
        self.assertTrue(all(s["type"] == "line" for s in result["charts"][0]["series"][1:]))

    def test_qq_reference_is_line(self):
        r = analyze("4011", dataset(["x"], [[1], [2], [3]]), {"columns": ["x"]})
        self.assertEqual(r["charts"][0]["series"][1]["type"], "line")

    def test_generated_output_budget_checked_before_allocation(self):
        columns = [f"X{i}" for i in range(100)]
        d = dataset(columns, [[1]*100])
        with self.assertRaisesRegex(ValueError, "cell limit"):
            analyze("3301", d, {"columns": columns, "replace": True, "count": 100000})

    def test_transform_typo_rejected(self):
        d = dataset(["x"], [[1], [2], ["oops"]])
        with self.assertRaisesRegex(ValueError, "nonnumeric"):
            analyze("3003", d, {"columns": ["x"]})

    def test_fft_inverse_roundtrip(self):
        d = dataset(["x"], [[1], [2], [3], [4]])
        r = analyze("1523", d, {"real": "x"})
        self.assertAlmostEqual(r["dataset"]["rows"][0][0], 10)
        back = analyze("1524", r["dataset"], {"real": "Real", "imaginary": "Imaginary"})
        np.testing.assert_allclose(np.array(back["dataset"]["rows"])[:, 0], [1, 2, 3, 4])

    def test_differences_preserve_alignment(self):
        d = dataset(["x"], [[1], [4], [9], [16], [25]])
        r = analyze("1521", d, {"column": "x", "order": 2})
        vals = [row[1] for row in r["dataset"]["rows"]]
        self.assertTrue(math.isnan(vals[0]) and math.isnan(vals[1]))
        np.testing.assert_allclose(vals[2:], [2, 2, 2])

    def test_weighted_moving_average_orientation(self):
        d = dataset(["x"], [[1], [2], [3], [4]])
        r = analyze("1502", d, {"column": "x", "length": 3, "method": "weighted", "weights": "1,2,3"})
        self.assertAlmostEqual(r["dataset"]["rows"][2][1], 14/6)

    def test_single_smoothing_known_initial(self):
        d = dataset(["x"], [[1], [3], [5]])
        r = analyze("1522", d, {"column": "x", "smoothing": .5, "initial": "first", "steps": 1})
        self.assertAlmostEqual(r["tables"][1]["rows"][0][1], 3.5)

    def test_standardization_sample_sd(self):
        d = dataset(["x"], [[1], [2], [3]])
        r = analyze("3003", d, {"columns": ["x"]})
        np.testing.assert_allclose(r["dataset"]["rows"], [[-1], [0], [1]])

    def test_boxcox_log_case(self):
        d = dataset(["x"], [[1], [math.e], [math.e**2]])
        r = analyze("3005", d, {"columns": ["x"], "estimate": False, "lambda": 0})
        np.testing.assert_allclose(r["dataset"]["rows"], [[0], [1], [2]])

    def test_matrix_inverse_and_determinant(self):
        d = dataset(["a", "b"], [[4, 7], [2, 6]])
        inv = analyze("3202", d, {"columns": ["a", "b"]})["dataset"]["rows"]
        np.testing.assert_allclose(inv, [[.6, -.7], [-.2, .4]])
        self.assertAlmostEqual(analyze("3203", d, {"columns": ["a", "b"]})["tables"][0]["rows"][0][0], 10)

    def test_random_reproducible(self):
        d = dataset(["x"], [])
        a = analyze("3102", d, {"count": 20, "seed": 123})["dataset"]
        b = analyze("3102", d, {"count": 20, "seed": 123})["dataset"]
        self.assertEqual(a, b)
        self.assertNotEqual(a, analyze("3102", d, {"count": 20, "seed": 124})["dataset"])
        report = analyze("3102", d, {"count": 20, "seed": 2**53-1})
        self.assertEqual(report["tables"][0]["columnFormats"], {"0": "0", "1": "0", "2": "0"})
        self.assertEqual(report["tables"][0]["rows"][0][3], "MT19937")
        self.assertFalse(any("PCG64" in note for note in report["notes"]))

    def test_exact_binomial_boundaries(self):
        d = dataset(["x"], [])
        zero = analyze("1702", d, {"successes": 0, "total": 10})["tables"][0]["rows"][0]
        self.assertEqual(zero[1], 0)
        self.assertAlmostEqual(zero[2], 1-.025**.1)
        all_ = analyze("1702", d, {"successes": 10, "total": 10})["tables"][0]["rows"][0]
        self.assertEqual(all_[2], 1)
        self.assertAlmostEqual(all_[1], .025**.1)

    def test_event_sample_size_minimal(self):
        d = dataset(["x"], [])
        row = analyze("1703", d, {"prevalence": 5, "events": 1, "probability": .95})["tables"][0]["rows"][0]
        self.assertEqual(row[0], 59)
        self.assertGreaterEqual(row[1], .95)
        self.assertLess(1-.95**58, .95)

    def test_c_chart_limits(self):
        d = dataset(["counts"], [[3], [4], [5]])
        row = analyze("4106", d, {"count_column": "counts"})["tables"][0]["rows"][0]
        self.assertEqual([row[2],row[4]], [4, 10])
        self.assertTrue(np.isnan(row[3]))

    def test_invalid_data_rejected(self):
        d = dataset(["x"], [[1], [None], [3], [4]])
        with self.assertRaisesRegex(ValueError, "preserve row"):
            analyze("1521", d, {"column": "x"})
        with self.assertRaises(ValueError):
            analyze("3100", d, {"count": -1})
        with self.assertRaises(ValueError):
            analyze("1702", d, {"total": 10, "successes": 11})
        with self.assertRaises(ValueError):
            analyze("1621", dataset(["t", "s"], [[1, 2], [2, 1], [3, 0]]), {"time": "t", "status": "s"})

    def test_every_catalog_command_smoke(self):
        rng = np.random.default_rng(891)
        n = 48
        d = dataset(["x", "y", "z", "time", "status", "group", "count", "size", "dose", "events", "total", "beta"], [
            [float(j+5+np.sin(j)), float(3+j*.5+rng.normal()), float(rng.normal()), float(rng.exponential(10)), j % 2, "A" if j % 2 else "B", j % 5, 10, 1+j/8, min(19, 1+j//3), 20, (j+1)/50] for j in range(n)
        ])
        opts = {
            "1501": {"column": "x", "lags": 8}, "1502": {"column": "x"},
            "1503": {"before": "x", "after": "y"}, "1510": {"column": "x", "period": 12},
            "1520": {"column": "x"}, "1521": {"column": "x"}, "1522": {"column": "x"},
            "1540": {"column": "x"}, "1530": {"column": "z"},
            "1523": {"real": "x"}, "1524": {"real": "x"},
            "1620": {"time": "time", "status": "status"}, "1621": {"time": "time", "status": "status", "group": "group"}, "1622": {"time": "time", "status": "status"},
            "1309": {"time": "time", "status": "status", "predictors": ["z"]},
            "1601": {"dose": "dose", "events": "events", "total": "total"},
            "1610": {"score": "z", "status": "status"}, "1611": {"columns": ["x", "z"], "status": "status"},
            "1630": {"first": "x", "second": "y"}, "3002": {"column": "x", "group": "group"},
            "3301": {"columns": ["x", "y"], "count": 10}, "3302": {"columns": ["x", "y"]},
            "3303": {"columns": ["x"], "condition_column": "x", "condition": "gt", "a": 10},
            "4002": {"x": "x", "y": "y"}, "4104": {"column": "x"}, "4108": {"column": "x"},
            "4105": {"count_column": "count", "size_column": "size"}, "4106": {"count_column": "count"}, "4107": {"count_column": "count", "size_column": "size"},
        }
        matrix = dataset(["a", "b", "c", "d"], [[4, 7, 1, 0], [2, 6, 0, 1]])
        for entry in catalog():
            i = entry["id"]
            with self.subTest(analysis=i):
                use = d
                o = opts.get(i, {"columns": ["x", "y"]})
                if i in ("3202", "3203"):
                    use, o = matrix, {"columns": ["a", "b"]}
                elif i == "3201": use, o = matrix, {"left": ["a", "b"], "right": ["c", "d"]}
                elif i == "4012": o = {"columns": ["beta"]}
                elif i.startswith("401"): o = {"columns": ["x"]}
                result = sanitize_json(analyze(i, use, o))
                self.assertEqual(result["analysis"], i)
                self.assertTrue(result["tables"] or result["charts"] or result.get("dataset"))


if __name__ == "__main__":
    unittest.main()
