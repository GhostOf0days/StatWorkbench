"""Checks for finite-state Markov and ergodicity diagnostics."""
import json
import unittest

import numpy as np

from backend.analyses import stochastic as st
from backend.common import sanitize_json
from backend.worker import dispatch


def sequence_data(values):
    return {"columns": ["State"], "rows": [[value] for value in values]}


def summary(result):
    return {row[0]: row[1] for row in result["tables"][4]["rows"]}


def stationary(result):
    return {row[0]: row[1] for row in result["tables"][3]["rows"]}


class StochasticTests(unittest.TestCase):
    def test_registry_exposes_markov_workflow_in_time_series(self):
        entry = st.catalog()[0]
        self.assertEqual(entry["id"], "stochastic.markov_chain")
        self.assertEqual(entry["category"], "Time series")
        registered = [item for item in dispatch("catalog", {}) if item["id"] == entry["id"]]
        self.assertEqual(len(registered), 1)

    def test_ergodic_two_state_chain_recovers_stationary_probabilities(self):
        rng = np.random.default_rng(144)
        values = ["A"]
        for _ in range(30000):
            source = values[-1]
            values.append(rng.choice(["A", "B"], p=[.9, .1] if source == "A" else [.2, .8]))
        result = st.analyze("stochastic.markov_chain", sequence_data(values), {"column": "State"})
        diag = summary(result)
        self.assertTrue(diag["Irreducible on observed states"])
        self.assertEqual(diag["Irreducible-class period"], 1)
        self.assertTrue(diag["Ergodic on observed support"])
        probs = stationary(result)
        self.assertAlmostEqual(probs["A"], 2 / 3, delta=.025)
        self.assertAlmostEqual(probs["B"], 1 / 3, delta=.025)
        self.assertAlmostEqual(result["tables"][1]["rows"][0][1], .9, delta=.01)

    def test_period_two_alternation_has_unique_stationary_but_is_not_ergodic(self):
        result = st.analyze("stochastic.markov_chain", sequence_data(["A", "B"] * 30), {"column": "State"})
        diag = summary(result)
        self.assertTrue(diag["Irreducible on observed states"])
        self.assertEqual(diag["Irreducible-class period"], 2)
        self.assertFalse(diag["Aperiodic"])
        self.assertFalse(diag["Ergodic on observed support"])
        self.assertAlmostEqual(stationary(result)["A"], .5)
        self.assertAlmostEqual(stationary(result)["B"], .5)
        self.assertTrue(any("period 2" in item for item in result["warnings"]))

    def test_reducible_chain_with_one_closed_class_has_unique_stationary_law(self):
        # A sometimes transitions to B; B is the sole closed absorbing class.
        values = ["A"] * 5 + ["B"] * 20
        result = st.analyze("stochastic.markov_chain", sequence_data(values), {"column": "State"})
        diag = summary(result)
        self.assertFalse(diag["Irreducible on observed states"])
        self.assertTrue(diag["Stationary distribution unique and estimated"])
        self.assertEqual(stationary(result), {"A": 0., "B": 1.})

    def test_multiple_closed_classes_leave_stationary_distribution_unidentified(self):
        # Step 2 observes only within each constant block, not the boundary.
        values = ["A"] * 10 + [None] + ["B"] * 10
        result = st.analyze("stochastic.markov_chain", sequence_data(values), {"column": "State"})
        diag = summary(result)
        self.assertEqual(diag["Communicating classes"], 2)
        self.assertFalse(diag["Stationary distribution unique and estimated"])
        self.assertEqual(set(stationary(result).values()), {None})
        self.assertTrue(any("multiple closed" in item for item in result["warnings"]))

    def test_missing_endpoints_are_omitted_and_undefined_rows_are_flagged(self):
        result = st.analyze("stochastic.markov_chain", sequence_data(["A", None, "B", "B"]), {"column": "State"})
        diag = summary(result)
        self.assertEqual(diag["Usable transitions"], 1)
        self.assertEqual(diag["Pairs omitted for missing endpoints"], 2)
        self.assertFalse(diag["All empirical rows defined"])
        self.assertIsNone(result["tables"][1]["rows"][0][1])
        self.assertTrue(any("No observed outgoing transition" in item for item in result["warnings"]))

    def test_typed_state_label_collisions_remain_distinct_and_worker_json_is_strict(self):
        data = sequence_data([1, "1", 1, "1", 1])
        result = dispatch("analyze", {"analysis": "stochastic.markov_chain", "data": data, "options": {"column": "State"}})
        labels = [row[0] for row in result["tables"][0]["rows"]]
        self.assertEqual(labels, ["1 [number 1]", "1 [text 2]"])
        json.dumps(sanitize_json(result), allow_nan=False)

    def test_transition_step_and_state_space_are_bounded(self):
        with self.assertRaisesRegex(ValueError, "Transition step"):
            st.analyze("stochastic.markov_chain", sequence_data(["A", "B"]), {"column": "State", "step": 1.5})
        with self.assertRaisesRegex(ValueError, "more than 50"):
            st.analyze("stochastic.markov_chain", sequence_data(list(range(51)) * 2), {"column": "State"})


if __name__ == "__main__":
    unittest.main()
