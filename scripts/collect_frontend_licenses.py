#!/usr/bin/env python3
"""Preserve notices from installed, locked production npm dependencies (MIT)."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LICENSE_PREFIXES = ("license", "licence", "copying", "notice", "copyright")


def collect(root=ROOT):
    lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
    overrides = json.loads((root / "licenses/upstream/sources.json").read_text(encoding="utf-8"))
    destination = root / "licenses/frontend"
    destination.mkdir(parents=True, exist_ok=True)
    records, missing = [], []
    for location, locked in sorted(lock["packages"].items()):
        if not location or locked.get("dev"):
            continue
        package_dir = root / location
        if not package_dir.is_dir() or (root / "node_modules").resolve() not in package_dir.resolve().parents:
            raise ValueError(f"Locked production package is not installed inside node_modules: {location}")
        metadata = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
        name, version = metadata["name"], metadata["version"]
        if version != locked["version"]:
            raise ValueError(f"Installed version differs from lockfile for {name}.")
        folder = destination / (re.sub(r"[^A-Za-z0-9_.-]", "_", name) + "-" + version)
        folder.mkdir(exist_ok=True)
        sources = []
        for candidate in sorted(package_dir.iterdir()):
            if candidate.is_file() and candidate.name.lower().startswith(LICENSE_PREFIXES):
                sources.append((candidate.read_bytes(), str(candidate.relative_to(root)), candidate.name))
        if not sources:
            # Some npm packages publish the complete permission text only in README.
            for candidate in sorted(package_dir.iterdir()):
                if not candidate.is_file() or candidate.name.lower() not in {"readme", "readme.md", "readme.markdown"}:
                    continue
                content = candidate.read_text(encoding="utf-8")
                headings = list(re.finditer(r"(?im)^#+\s+licen[cs]e\s*$", content))
                section = content[headings[-1].end():].strip() if headings else ""
                if "Permission" in section and "SOFTWARE" in section and "Copyright" in section:
                    sources.append(((html.unescape(section) + "\n").encode(), str(candidate.relative_to(root)) + "#license", "README-LICENSE.txt"))
        if not sources:
            override = overrides.get(f"{name}@{version}")
            if override:
                source = root / override["file"]
                sources.append((source.read_bytes(), override["provenance"], "UPSTREAM-LICENSE.txt"))
        files = []
        for index, (contents, source, filename) in enumerate(sources):
            if len(contents) > 1024 * 1024:
                raise ValueError(f"Unexpectedly large dependency notice: {source}")
            target = folder / (f"{index + 1:02d}-" + re.sub(r"[^A-Za-z0-9_.-]", "_", filename) + ".txt")
            target.write_bytes(contents)
            files.append({"path": str(target.relative_to(root)), "source": source, "sha256": hashlib.sha256(contents).hexdigest()})
        record = {"name": name, "version": version, "package_lock_location": location,
                  "license_metadata": metadata.get("license", locked.get("license")),
                  "repository": metadata.get("repository"), "license_files": files}
        records.append(record)
        if not files:
            missing.append(f"{name}@{version}")
    manifest = {"format": "statworkbench-frontend-notices-v1",
                "scope": "Installed production dependencies in package-lock.json; all are listed even when a particular export is removed by the renderer bundler. Metadata declarations do not override the preserved license texts.",
                "packages": records, "missing_license_files": missing}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Third-party notices", "", "StatWorkbench's original source is MIT licensed. Its open-source dependencies retain their respective license and copyright terms. The preserved texts and their provenance are indexed in [licenses/frontend/manifest.json](licenses/frontend/manifest.json).", "", "The spreadsheet interface uses unmodified Univer packages under Apache-2.0 and their dependencies. This inventory includes every locked production npm dependency, including modules the renderer build may omit. The collector is reproducible with `python scripts/collect_frontend_licenses.py` after `npm ci`.", "", "| Package | Version | Declared license | Preserved notice |", "|---|---|---|---|"]
    for record in records:
        declared = str(record["license_metadata"]).replace("|", "\\|")
        links = ", ".join(f"[text {index + 1}]({notice['path']})" for index, notice in enumerate(record["license_files"]))
        lines.append(f"| {record['name']} | {record['version']} | {declared} | {links or 'MISSING'} |")
    lines += ["", "Some upstream npm archives omit a standalone license file. Complete license sections in their READMEs are retained when present. Otherwise, explicit upstream sources are recorded in `licenses/upstream/sources.json`. The `ot-text-unicode` metadata declares ISC while its published README contains an MIT permission text; both declarations are retained without alteration.", "", "The packaged Python engine contains its own `engine/THIRD_PARTY_NOTICES.md` and `engine/licenses/` collection, generated by `scripts/collect_backend_licenses.py`. Electron's distribution includes its Electron, Chromium, Node.js and other runtime notices. Those runtime files must remain in the packaged desktop application."]
    (root / "THIRD_PARTY_NOTICES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if missing:
        raise ValueError("Missing dependency license texts: " + ", ".join(missing))
    print(f"Collected frontend notices for {len(records)} production package entries; no missing license texts.")
    return manifest


if __name__ == "__main__":
    collect()
