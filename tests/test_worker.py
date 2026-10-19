"""Protocol tests use synthetic calculations and real NDJSON process boundaries."""

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from backend import worker
from backend.common import sanitize_json


class WorkerTests(unittest.TestCase):
    def test_ping_and_bad_method(self):
        self.assertTrue(worker.handle_request({"id": "p", "method": "ping"})["ok"])
        bad = worker.handle_request({"id": "e", "method": "eval", "params": {"code": "raise SystemExit"}})
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["id"], "e")

    def test_strict_json_sanitizes_scientific_types_and_nonfinite_results(self):
        result = sanitize_json({"a": np.array([1.0, np.nan, np.inf]), "b": np.int64(4), "c": np.bool_(True)})
        self.assertEqual(result, {"a": [1.0, None, None], "b": 4, "c": True})
        json.dumps(result, allow_nan=False)

    def test_analysis_validates_shape_before_dispatch_and_returns_numbers(self):
        called = []
        def calculate(identifier, data, options):
            called.append(data)
            return {"analysis": identifier, "mean": np.float64(3), "undefined": float("nan")}
        fake = SimpleNamespace(analyze=calculate)
        with patch.object(worker, "_load_registry", return_value=({"test": fake}, [])):
            invalid = worker.handle_request({"id": "bad", "method": "analyze", "params": {"analysis": "test", "data": {"columns": ["x", "y"], "rows": [[1]]}}})
            self.assertFalse(invalid["ok"])
            self.assertFalse(called)
            response = worker.handle_request({"id": "ok", "method": "analyze", "params": {"analysis": "test", "data": {"columns": ["x"], "rows": [[2], [4]]}}})
            self.assertEqual(response["result"]["mean"], 3)
            self.assertIsNone(response["result"]["undefined"])

    def test_unknown_analysis_has_clear_error(self):
        with patch.object(worker, "_load_registry", return_value=({}, [])):
            response = worker.handle_request({"method": "analyze", "params": {"analysis": "9999"}})
        self.assertFalse(response["ok"])
        self.assertIn("not implemented", response["error"])

    def test_params_must_be_object(self):
        response = worker.handle_request({"id": "x", "method": "ping", "params": []})
        self.assertFalse(response["ok"])

    def test_process_recovers_after_malformed_json_and_never_emits_nan(self):
        requests = '{broken}\n{"id":"nan","method":"ping","params":{"x":NaN}}\n{"id":"health","method":"ping"}\n'
        project = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-m", "backend.worker"], cwd=project, input=requests, text=True, capture_output=True, timeout=30, check=True)
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(responses), 3)
        self.assertFalse(responses[0]["ok"])
        self.assertFalse(responses[1]["ok"])
        self.assertTrue(responses[2]["ok"])
        self.assertEqual(responses[2]["id"], "health")

    def test_duplicate_request_json_fields_rejected(self):
        project = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-m", "backend.worker"], cwd=project, input='{"id":"x","method":"ping","method":"eval"}\n', text=True, capture_output=True, timeout=30, check=True)
        self.assertIn("Duplicate JSON field", json.loads(result.stdout)["error"])


if __name__ == "__main__":
    unittest.main()
