"""Strict newline-delimited JSON worker for the desktop app (MIT licensed)."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib
import json
from pathlib import Path
import sys
import traceback

# Both `python -m backend.worker` and the frozen executable use the same imports.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.common import MAX_REQUEST_BYTES, validate_dataset, sanitize_json, reject_json_constant, unique_json_object
from backend.file_io import import_file, export_file, export_spjs
from backend.preferences import apply_preferences

_registry = None
_catalog = None


def _load_registry():
    global _registry, _catalog
    if _registry is not None:
        return _registry, _catalog
    registry, entries = {}, []
    for module_name in ("backend.analyses.basic", "backend.analyses.advanced", "backend.analyses.copulas", "backend.analyses.dependence", "backend.analyses.stochastic"):
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ValueError(f"The analysis engine is incomplete ({exc.name}). Install requirements.txt using this app's Python environment.") from exc
        for entry in module.catalog():
            identifier = str(entry["id"])
            if identifier in registry:
                raise RuntimeError(f"Duplicate analysis registry ID: {identifier}")
            registry[identifier] = module
            entries.append(entry)
    _registry, _catalog = registry, entries
    return registry, entries


def dispatch(method, params):
    if method == "ping":
        return {"name": "StatWorkbench engine", "version": "0.1.0", "protocol": 1, "python": sys.version.split()[0]}
    if method == "catalog":
        return _load_registry()[1]
    if method == "analyze":
        identifier = params.get("analysis")
        if not isinstance(identifier, str):
            raise ValueError("Analysis ID must be text.")
        registry, catalog = _load_registry()
        if identifier not in registry:
            raise ValueError(f"Analysis {identifier!r} is not implemented in this release.")
        data = validate_dataset(params.get("data"))
        options = params.get("options", {})
        if not isinstance(options, dict):
            raise ValueError("Analysis options must be an object.")
        entry = next((item for item in catalog if str(item['id']) == identifier), {})
        data, options, deleted = apply_preferences(data, options, entry)
        result = registry[identifier].analyze(identifier, data, options)
        if deleted:
            result.setdefault('notes', []).append(f'Global casewise deletion removed {deleted} rows missing a selected input; reported row numbers refer to retained rows.')
        return result
    if method == "import_file":
        return import_file(params.get("path"), params.get("sheet"))
    if method == "export_file":
        return export_file(params.get("path"), params.get("data"))
    if method == "export_spjs":
        return export_spjs(params.get("path"), params.get("workbook"))
    if method == "export_report_xlsx":
        from backend.report_xlsx import export_report_xlsx
        return export_report_xlsx(params.get("path"), params.get("report"))
    raise ValueError("Unknown method. Expected ping, catalog, analyze, import_file or export_file.")


def handle_request(request):
    identifier = request.get("id") if isinstance(request, dict) else None
    if not isinstance(identifier, (str, int, type(None))) or isinstance(identifier, bool):
        identifier = None
    try:
        if not isinstance(request, dict):
            raise ValueError("A request must be a JSON object.")
        method = request.get("method")
        if not isinstance(method, str):
            raise ValueError("Request method must be text.")
        params = request.get("params", {})
        if not isinstance(params, dict):
            raise ValueError("Request params must be an object.")
        # Third-party print calls must never contaminate the response channel.
        with redirect_stdout(sys.stderr):
            result = sanitize_json(dispatch(method, params))
        if isinstance(result, dict) and "dataset" in result:
            result["dataset"] = validate_dataset(result["dataset"])
        return {"id": identifier, "ok": True, "result": result}
    except (ValueError, TypeError, KeyError, OSError, UnicodeError) as exc:
        return {"id": identifier, "ok": False, "error": str(exc) or "The request could not be completed."}
    except Exception:
        traceback.print_exc(file=sys.stderr)
        return {"id": identifier, "ok": False, "error": "The operation failed unexpectedly. Details were written to the engine error log."}


def main():
    incoming = sys.stdin.buffer
    while True:
        raw = incoming.readline(MAX_REQUEST_BYTES + 1)
        if not raw:
            break
        try:
            if len(raw) > MAX_REQUEST_BYTES:
                # Discard the rest of this single oversized request, then keep serving.
                while raw and not raw.endswith(b"\n"):
                    raw = incoming.readline(MAX_REQUEST_BYTES + 1)
                raise ValueError("The request exceeds the 64 MiB limit.")
            if not raw.strip():
                continue
            request = json.loads(raw.decode("utf-8"), parse_constant=reject_json_constant, object_pairs_hook=unique_json_object)
            response = handle_request(request)
        except (ValueError, UnicodeError, RecursionError) as exc:
            response = {"id": None, "ok": False, "error": str(exc)}
        encoded = json.dumps(response, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        if len(encoded) > MAX_REQUEST_BYTES:
            encoded = json.dumps({"id": response.get("id"), "ok": False, "error": "The result exceeds the 64 MiB response limit. Reduce the selected data or output size."})
        sys.stdout.write(encoded + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
