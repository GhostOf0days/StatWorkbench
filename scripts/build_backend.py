#!/usr/bin/env python3
"""Build the native worker with the selected interpreter; no source app is required."""

from pathlib import Path
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime, timezone


def main():
    project = Path(__file__).resolve().parents[1]
    sources = sorted((project / "backend").rglob("*.py"))
    source_hashes = {path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    python = os.environ.get("STATWORKBENCH_PYTHON", sys.executable)
    runtime = json.loads(subprocess.check_output([python, "-c", "import json,platform,struct,sys;print(json.dumps({'platform':sys.platform,'machine':platform.machine().lower(),'bits':struct.calcsize('P')*8}))"], text=True, timeout=30))
    architecture = {"aarch64": "arm64", "arm64": "arm64", "amd64": "x64", "x86_64": "x64", "i386": "ia32", "i686": "ia32", "x86": "ia32", "armv7l": "armv7l"}.get(runtime["machine"])
    if runtime["bits"] == 32 and architecture == "x64":
        architecture = "ia32"
    if architecture is None:
        raise RuntimeError("Unsupported worker architecture: " + runtime["machine"])
    command = [
        python, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", "statworkbench-engine",
        "--distpath", str(project / "dist-backend"),
        "--workpath", str(project / "build" / "backend"),
        "--specpath", str(project / "build"),
        "--paths", str(project),
        "--hidden-import", "backend.analyses.basic",
        "--hidden-import", "backend.analyses.advanced",
        "--hidden-import", "backend.analyses.copulas",
        "--hidden-import", "backend.analyses.dependence",
        "--hidden-import", "backend.analyses.stochastic",
        "--hidden-import", "backend.report_xlsx",
        "--hidden-import", "openpyxl",
        "--hidden-import", "xlrd",
        "--hidden-import", "odf",
        "--hidden-import", "pyreadstat",
        "--hidden-import", "dbfread",
        "--hidden-import", "pyreadr",
        "--hidden-import", "pandas",
        "--hidden-import", "statsmodels.api",
        "--hidden-import", "sklearn.cluster",
        "--hidden-import", "sklearn.decomposition",
        "--hidden-import", "sklearn.discriminant_analysis",
        "--collect-data", "scipy",
        "--collect-data", "statsmodels",
        "--collect-data", "sklearn",
        "--exclude-module", "tkinter",
        "--exclude-module", "matplotlib",
        "--exclude-module", "IPython",
        "--exclude-module", "torch",
        "--exclude-module", "tensorflow",
        "--exclude-module", "jax",
        "--exclude-module", "jaxlib",
        "--exclude-module", "cupy",
        "--exclude-module", "dask",
        "--exclude-module", "distributed",
        "--exclude-module", "numba",
        "--exclude-module", "llvmlite",
        "--exclude-module", "pytest",
        "--exclude-module", "pandas_gbq",
        "--exclude-module", "google",
        "--exclude-module", "grpc",
        "--exclude-module", "opentelemetry",
        "--exclude-module", "sqlalchemy",
        "--exclude-module", "azure",
        "--exclude-module", "boto3",
        "--exclude-module", "botocore",
        "--exclude-module", "s3fs",
        "--exclude-module", "gcsfs",
        "--exclude-module", "fsspec",
        "--exclude-module", "pyarrow",
        "--exclude-module", "polars",
        "--exclude-module", "xarray",
        "--exclude-module", "fastparquet",
        "--exclude-module", "tables",
        "--exclude-module", "h5py",
        "--exclude-module", "PIL",
        "--exclude-module", "cv2",
        "--exclude-module", "PyQt5",
        "--exclude-module", "PyQt6",
        "--exclude-module", "PySide6",
        str(project / "backend" / "worker.py"),
    ]
    (project / "build").mkdir(exist_ok=True)
    build_environment = os.environ.copy()
    build_environment["PYINSTALLER_CONFIG_DIR"] = str(project / "build" / ".pyinstaller-cache")
    print("Building backend with", python, flush=True)
    subprocess.run(command, cwd=project, env=build_environment, check=True)
    current_sources = {path.relative_to(project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((project / "backend").rglob("*.py"))}
    if current_sources != source_hashes:
        raise RuntimeError("Backend source changed during the build; rebuild after source changes finish.")
    suffix = ".exe" if os.name == "nt" else ""
    executable = project / "dist-backend" / "statworkbench-engine" / ("statworkbench-engine" + suffix)
    framework = executable.parent / "_internal" / "Python.framework"
    if sys.platform == "darwin" and framework.is_dir():
        # PyInstaller may sign the framework executable before collecting its
        # resources. Seal the completed generated bundle (never installed Python).
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(framework)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(framework)], check=True)
    requests = [
        {"id": "build-health", "method": "ping"},
        {"id": "build-catalog", "method": "catalog"},
        {"id": "build-numerical", "method": "analyze", "params": {"analysis": "1001", "data": {"columns": ["Value"], "rows": [[1], [2], [3]]}, "options": {"columns": ["Value"], "quantile": "7", "confidence": .95}}},
    ]
    extension_data = {"columns": ["X", "Y", "Z", "State"], "rows": [
        [math.sin(i*.37)+.1*math.cos(i*.08), .65*math.sin(i*.37)+math.sin(i*.19)+.03*math.cos(i*.23), math.cos(i*.13)+.2*math.sin(i*.29), "A" if i % 2 == 0 else "B"]
        for i in range(100)
    ]}
    extension_cases = [
        ("build-copula", "copula.bivariate", {"x": "X", "y": "Y", "family": "auto", "samples": 5, "seed": 7, "diagnostics": True}),
        ("build-association", "dependence.association", {"columns": ["X", "Y", "Z"], "method": "spearman"}),
        ("build-partial", "dependence.partial", {"x": "X", "y": "Y", "controls": ["Z"]}),
        ("build-distance", "dependence.distance", {"x": "X", "y": "Y", "permutations": 9, "seed": 4}),
        ("build-mutual-information", "dependence.mutual_information", {"x": "X", "y": "Y", "bins": 6, "permutations": 9, "seed": 4}),
        ("build-tail-coexceedance", "dependence.tail_coexceedance", {"x": "X", "y": "Y", "tail_probability": .1}),
        ("build-lead-lag", "dependence.lead_lag", {"x": "X", "y": "Y", "max_lag": 3}),
        ("build-markov", "stochastic.markov_chain", {"column": "State"}),
    ]
    requests.extend({"id": request_id, "method": "analyze", "params": {"analysis": identifier, "data": extension_data, "options": options}}
                    for request_id, identifier, options in extension_cases)
    subprocess.run([python, str(project / "scripts" / "collect_backend_licenses.py")], cwd=project, check=True)
    verification = {"built_at": datetime.now(timezone.utc).isoformat(), "platform": runtime["platform"], "architecture": architecture, "source_sha256": source_hashes, "checks": [], "verified": False}
    started = time.monotonic()
    try:
        # A cold macOS policy assessment may take longer than a warm engine
        # start. Keep a finite bound, while allowing the OS to finish checking.
        check = subprocess.run([str(executable)], input="".join(json.dumps(r) + "\n" for r in requests), text=True, capture_output=True, timeout=120, check=True)
        responses = [json.loads(line) for line in check.stdout.splitlines()]
        verification["checks"] = [{"id": response.get("id"), "ok": response.get("ok", False)} for response in responses]
        if [r.get("id") for r in responses] != [r["id"] for r in requests] or any(not response.get("ok") for response in responses):
            raise RuntimeError("Frozen backend checks failed: " + check.stdout + "\n" + check.stderr)
        if not isinstance(responses[1].get("result"), list) or len(responses[1]["result"]) != 125:
            raise RuntimeError("Frozen backend registry does not contain all 117 core procedures and eight extensions.")
        mean_values = [row[i + 1] for table in responses[2]["result"]["tables"] for row in table["rows"] for i in range(0, len(row) - 1, 2) if row[i] == "Mean"]
        if mean_values != [2.0]:
            raise RuntimeError("Frozen backend numerical check did not reproduce mean([1, 2, 3]) = 2.")
        by_id = {response["id"]: response for response in responses}
        copula = by_id["build-copula"]["result"]["copula"]
        if set(copula["models"]) != {"independence", "gaussian", "student", "clayton", "frank", "gumbel"}:
            raise RuntimeError("Frozen backend copula comparison did not return all six supported families.")
        selected_bic = min(copula["models"].values(), key=lambda model: model["bic"])["family"]
        if copula["selectedFamily"] != selected_bic:
            raise RuntimeError("Frozen backend copula selection did not choose the minimum-BIC converged model.")
        extension_results = [by_id[request_id] for request_id, _, _ in extension_cases]
        if any(not response.get("ok") for response in extension_results):
            raise RuntimeError("One or more frozen independent extensions failed: " + repr([response.get("id") for response in extension_results if not response.get("ok")]))
        markov_summary = dict(next(table["rows"] for table in by_id["build-markov"]["result"]["tables"] if table["title"] == "Chain summary"))
        if markov_summary.get("Irreducible-class period") != 2 or markov_summary.get("Ergodic on observed support") is not False:
            raise RuntimeError("Frozen backend Markov check did not reproduce the irreducible period-2 alternation fixture.")
        verification["catalog_procedures"] = len(responses[1]["result"])
        verification["numerical_mean"] = mean_values[0]
        verification["markov_period"] = markov_summary["Irreducible-class period"]
        verification["markov_ergodic"] = markov_summary["Ergodic on observed support"]
        verification["extension_procedures"] = [identifier for _, identifier, _ in extension_cases]
        verification["copula_families"] = sorted(copula["models"])
        verification["copula_selected_family"] = copula["selectedFamily"]
        verification["verified"] = True
    except Exception as exc:
        verification["error"] = str(exc)
        raise
    finally:
        verification["runtime_check_seconds"] = round(time.monotonic() - started, 3)
        (executable.parent / "build-verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    print("Frozen worker health, 125-entry registry, numerical, copula and eight extension checks passed:", executable)


if __name__ == "__main__":
    main()
