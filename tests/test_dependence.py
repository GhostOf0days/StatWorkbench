"""Numerical checks for the additional Dependence category extensions."""
import json
import unittest
from pathlib import Path

import numpy as np
from scipy import stats

from backend.analyses import dependence as dp
from backend.common import sanitize_json
from backend.worker import dispatch


def dataset(**columns):
    names = list(columns)
    return {"columns": names, "rows": np.column_stack([columns[name] for name in names]).tolist()}


class DependenceTests(unittest.TestCase):
    def test_catalog_has_six_distinct_procedures_in_dependence_category(self):
        entries = dp.catalog()
        self.assertEqual(len(entries), 6)
        self.assertEqual(len({item["id"] for item in entries}), 6)
        self.assertTrue(all(item["category"] == "Dependence models" and item["coverage"] == "extension" for item in entries))
        catalog = dispatch("catalog", {})
        self.assertEqual(sum(item["category"] == "Dependence models" for item in catalog), 7)
        renderer_ids = {item["id"] for item in json.loads(Path("electron/extension-procedures.json").read_text())}
        backend_ids = {item["id"] for item in catalog if item["coverage"] == "extension"}
        self.assertEqual(renderer_ids, backend_ids)

    def test_all_new_procedures_run_through_the_strict_worker_boundary(self):
        rng = np.random.default_rng(22)
        x = rng.normal(size=100)
        y = np.roll(x, 2) + rng.normal(scale=.1, size=100)
        data = dataset(X=x, Y=y, Z=rng.normal(size=100))
        data["columns"].append("State")
        for index, row in enumerate(data["rows"]):
            row.append("A" if index % 2 == 0 else "B")
        cases = [
            ("copula.bivariate", {"x": "X", "y": "Y", "family": "auto", "samples": 5, "seed": 7, "diagnostics": True}),
            ("dependence.association", {"columns": ["X", "Y", "Z"], "method": "spearman"}),
            ("dependence.partial", {"x": "X", "y": "Y", "controls": ["Z"]}),
            ("dependence.distance", {"x": "X", "y": "Y", "permutations": 9, "seed": 4}),
            ("dependence.mutual_information", {"x": "X", "y": "Y", "bins": 6, "permutations": 9, "seed": 4}),
            ("dependence.tail_coexceedance", {"x": "X", "y": "Y", "tail_probability": .1}),
            ("dependence.lead_lag", {"x": "X", "y": "Y", "max_lag": 3}),
            ("stochastic.markov_chain", {"column": "State"}),
        ]
        for identifier, options in cases:
            with self.subTest(identifier=identifier):
                response = dispatch("analyze", {"analysis": identifier, "data": data, "options": options})
                self.assertEqual(response["analysis"], identifier)
                json.dumps(sanitize_json(response), allow_nan=False)

    def test_association_matrix_pairwise_counts_alternatives_and_bh(self):
        data = {"columns": ["X", "Y", "Z"], "rows": [[i, i, 10-i] for i in range(20)] + [[None, 99, 3]]}
        result = dp.analyze("dependence.association", data, {"columns": ["X", "Y", "Z"], "method": "spearman", "adjustment": "bh"})
        corr, raw, adjusted, count = result["tables"]
        self.assertEqual(corr["rows"][0][1:], [1, 1, -1])
        self.assertEqual(count["rows"][0][1:], [20, 20, 20])
        self.assertEqual(raw["rows"][0][2], 0)
        self.assertEqual(adjusted["rows"][0][2], 0)
        self.assertTrue(any("independent observations" in note for note in result["notes"]))
        self.assertEqual(result["warnings"], [])

    def test_association_listwise_missing_and_constant_variable_are_explicit(self):
        data = {"columns": ["X", "Y", "Constant"], "rows": [[i, i, 1] for i in range(10)] + [[None, 11, 1]]}
        r = dp.analyze("dependence.association", data, {"columns": ["X", "Y", "Constant"], "method": "pearson", "missing": "listwise"})
        self.assertEqual(r["tables"][3]["rows"][0][1:], [10, 10, 10])
        self.assertIsNone(r["tables"][0]["rows"][0][3])
        self.assertIsNone(r["tables"][1]["rows"][0][3])
        json.dumps(sanitize_json(r), allow_nan=False)

    def test_kendall_tau_b_ties_and_pearson_one_sided_pvalue(self):
        x, y = np.array([1, 1, 2, 3, 4, 4, 5, 6], dtype=float), np.array([2, 1, 3, 5, 4, 7, 8, 6], dtype=float)
        result = dp.analyze("dependence.association", dataset(X=x, Y=y), {"columns": ["X", "Y"], "method": "kendall", "adjustment": "none"})
        self.assertAlmostEqual(result["tables"][0]["rows"][0][2], stats.kendalltau(x, y, variant="b").statistic, places=5)
        one_sided = dp.analyze("dependence.association", dataset(X=x, Y=y), {"columns": ["X", "Y"], "method": "pearson", "alternative": "greater", "adjustment": "none"})
        self.assertAlmostEqual(one_sided["tables"][1]["rows"][0][2], stats.pearsonr(x, y, alternative="greater").pvalue, places=5)

    def test_partial_correlation_removes_shared_linear_driver(self):
        rng = np.random.default_rng(218)
        z = rng.normal(size=500)
        x, y = z + rng.normal(scale=.6, size=500), z + rng.normal(scale=.6, size=500)
        self.assertGreater(stats.pearsonr(x, y).statistic, .6)
        result = dp.analyze("dependence.partial", dataset(X=x, Y=y, Z=z), {"x": "X", "y": "Y", "controls": ["Z"]})
        row = result["tables"][0]["rows"][0]
        self.assertEqual(row[3], 500)
        self.assertLess(abs(row[5]), .12)
        self.assertEqual(row[6], 497)
        self.assertGreaterEqual(row[8], 0)
        self.assertLessEqual(row[8], 1)

    def test_partial_correlation_without_controls_is_a_valid_simple_correlation(self):
        x, y = np.arange(30, dtype=float), np.arange(30, dtype=float) + np.sin(np.arange(30))
        result = dp.analyze("dependence.partial", dataset(X=x, Y=y), {"x": "X", "y": "Y"})
        self.assertAlmostEqual(result["tables"][0]["rows"][0][5], stats.pearsonr(x, y).statistic)
        controls = next(field for field in dp.catalog()[1]["fields"] if field["key"] == "controls")
        self.assertFalse(controls["required"])

    def test_distance_correlation_detects_nonlinear_association_and_is_seeded(self):
        rng = np.random.default_rng(404)
        x = rng.uniform(-1, 1, 120)
        y = x*x + rng.normal(scale=.04, size=len(x))
        data = dataset(X=x, Y=y)
        opts = {"x": "X", "y": "Y", "permutations": 99, "seed": 18}
        a = dp.analyze("dependence.distance", data, opts)
        b = dp.analyze("dependence.distance", data, opts)
        row = a["tables"][0]["rows"][0]
        self.assertGreater(row[3], .4)
        self.assertLessEqual(row[5], .02)
        self.assertEqual(row, b["tables"][0]["rows"][0])

    def test_distance_budget_and_constant_series(self):
        d = dataset(X=np.arange(40), Y=np.ones(40))
        r = dp.analyze("dependence.distance", d, {"x": "X", "y": "Y", "permutations": 0})
        self.assertEqual(r["tables"][0]["rows"][0][3], 0)
        with self.assertRaisesRegex(ValueError, "computation budget"):
            dp.analyze("dependence.distance", dataset(X=np.arange(1000), Y=np.arange(1000)), {"x": "X", "y": "Y", "permutations": 999})

    def test_binned_mutual_information_detects_nonlinear_association(self):
        rng = np.random.default_rng(301)
        x = rng.uniform(-1, 1, 300)
        y = x*x + rng.normal(scale=.03, size=len(x))
        result = dp.analyze("dependence.mutual_information", dataset(X=x, Y=y), {"x": "X", "y": "Y", "bins": 8, "permutations": 99, "seed": 5})
        row = result["tables"][0]["rows"][0]
        self.assertGreater(row[6], .3)
        self.assertGreater(row[7], 0)
        self.assertLessEqual(row[9], .02)

    def test_tail_coexceedance_reports_four_quadrants_and_independence_rates(self):
        rng = np.random.default_rng(77)
        x = rng.normal(size=2000)
        y = .8*x + np.sqrt(1-.8**2)*rng.normal(size=len(x))
        result = dp.analyze("dependence.tail_coexceedance", dataset(X=x, Y=y), {"x": "X", "y": "Y", "tail_probability": .1})
        rows = result["tables"][0]["rows"]
        self.assertEqual(len(rows), 4)
        upper_upper = rows[0]
        self.assertGreater(upper_upper[7], upper_upper[9] * 2)
        self.assertGreater(upper_upper[8], upper_upper[6])

    def test_lead_lag_positive_lag_means_x_leads_y(self):
        rng = np.random.default_rng(102)
        x = rng.normal(size=500)
        y = np.r_[rng.normal(size=3), x[:-3] + rng.normal(scale=.12, size=497)]
        result = dp.analyze("dependence.lead_lag", dataset(X=x, Y=y), {"x": "X", "y": "Y", "max_lag": 8})
        rows = result["tables"][0]["rows"]
        peak = max(rows, key=lambda row: -1 if row[2] is None else row[2])
        self.assertEqual(peak[0], 3)
        self.assertGreater(peak[2], .95)
        self.assertIn("Positive lag", result["notes"][-1])

    def test_invalid_controls_and_incomplete_pairs_are_rejected_or_reported(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            dp.analyze("dependence.partial", dataset(X=[1, 2, 3, 4, 5], Y=[2, 4, 1, 3, 7]), {"x": "X", "y": "Y", "controls": ["X"]})
        result = dp.analyze("dependence.distance", {"columns": ["X", "Y"], "rows": [[1, 1], [2, 3], [None, 2], [4, 5], [5, 2]]}, {"x": "X", "y": "Y", "permutations": 0})
        self.assertTrue(any("Excluded 1 rows" in warning for warning in result["warnings"]))
        for options in ({"x": "X", "y": "Y", "permutations": 1.5}, {"x": "X", "y": "Y", "seed": True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                dp.analyze("dependence.distance", dataset(X=np.arange(10), Y=np.arange(10)), options)


if __name__ == "__main__":
    unittest.main()
