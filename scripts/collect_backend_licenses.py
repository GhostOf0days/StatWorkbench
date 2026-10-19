#!/usr/bin/env python3
"""Preserve installed dependency license texts alongside the frozen engine."""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import re
import shutil
import sys
import sysconfig


def collect(project, engine):
    from PyInstaller.archive.readers import ZlibArchiveReader
    pyz = project / "build" / "backend" / "statworkbench-engine" / "PYZ-00.pyz"
    modules = ZlibArchiveReader(str(pyz)).toc
    roots = {name.split(".", 1)[0] for name in modules}
    internal = engine / "_internal"
    if internal.exists():
        roots.update(path.name.split(".", 1)[0] for path in internal.iterdir())
    packages = metadata.packages_distributions()
    names = {name for root in roots for name in packages.get(root, [])}
    names.update(["numpy", "scipy", "pandas", "statsmodels", "scikit-learn", "openpyxl", "pyinstaller"])
    destination = engine / "licenses"
    destination.mkdir(exist_ok=True)
    upstream_root = project / 'licenses' / 'backend-upstream'
    upstream_manifest = upstream_root / 'manifest.json'
    upstream = json.loads(upstream_manifest.read_text())['packages'] if upstream_manifest.is_file() else []
    records = []
    missing = []
    for name in sorted(names, key=str.lower):
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        normalized = re.sub(r"[^A-Za-z0-9_.-]", "_", dist.metadata.get("Name", name))
        folder = destination / normalized
        folder.mkdir(exist_ok=True)
        files = []
        for relative in dist.files or []:
            parts = Path(relative).parts
            filename = Path(relative).name.lower()
            is_license = any(part.lower() in {"licenses", "licences"} for part in parts) or filename.startswith(("license", "licence", "copying", "notice", "copyright"))
            if not is_license:
                continue
            source = Path(dist.locate_file(relative))
            if not source.is_file() or source.stat().st_size > 5 * 1024 * 1024:
                continue
            if source.suffix.lower() in {".py", ".pyc", ".so", ".dll", ".dylib"}:
                continue
            suffix = hashlib.sha256(str(relative).encode()).hexdigest()[:8]
            target = folder / (suffix + "-" + source.name)
            shutil.copyfile(source, target)
            files.append({"installed_path": str(relative), "included_path": str(target.relative_to(engine)), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        if not files:
            for source_record in upstream:
                if source_record['name'].lower() != name.lower() or source_record['version'] != dist.version:
                    continue
                for notice in source_record['files']:
                    source = upstream_root / notice['path']
                    if hashlib.sha256(source.read_bytes()).hexdigest() != notice['sha256']:
                        raise ValueError('Upstream dependency notice does not match its recorded hash: '+str(source))
                    target = folder / ('upstream-'+source.name)
                    shutil.copyfile(source, target)
                    files.append({'upstream_source': source_record['source'], 'source_archive_sha256': source_record['source_archive_sha256'], 'included_path': str(target.relative_to(engine)), 'sha256': notice['sha256']})
        license_text = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "Not declared in installed distribution metadata."
        meta = {"name": dist.metadata.get("Name", name), "version": dist.version, "license_metadata": license_text, "project_urls": dist.metadata.get_all("Project-URL") or [], "license_files": files}
        (folder / "distribution-metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        records.append(meta)
        if not files:
            missing.append(meta["name"])
    python_candidates = [
        Path(os.environ["STATWORKBENCH_PYTHON_LICENSE"]) if os.environ.get("STATWORKBENCH_PYTHON_LICENSE") else None,
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / "LICENSE",
        Path(sysconfig.get_path("stdlib")) / "LICENSE.txt",
        Path(sys.base_prefix) / "Resources" / "English.lproj" / "Documentation" / "license.html",
        Path(f"/usr/share/doc/python{sys.version_info.major}.{sys.version_info.minor}/copyright"),
    ]
    python_license = next((p for p in python_candidates if p and p.is_file()), None)
    if python_license:
        target = destination / ("Python-" + sys.version.split()[0] + "-" + python_license.name)
        shutil.copyfile(python_license, target)
        python_record = {"version": sys.version.split()[0], "license_file": str(target.relative_to(engine)), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    else:
        missing.append("Python runtime license file (set STATWORKBENCH_PYTHON_LICENSE)")
        python_record = {"version": sys.version.split()[0], "license_file": None}
    manifest = {"python": python_record, "packages": records, "missing_license_files": missing, "scope": "Installed license files for direct and discovered frozen Python-package dependencies, including bundled-library notices. Electron/runtime shell notices are handled by the desktop packager."}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = ["# Third-party engine notices", "", "The application source is MIT licensed. Bundled Python components retain their own licenses. Installed license texts are preserved in the `licenses` directory; this index does not replace those terms.", "", "Python " + python_record["version"] + ": " + (python_record["license_file"] or "license file not found"), "", "| Distribution | Version | Included license files |", "|---|---|---|"]
    for record in records:
        lines.append(f"| {record['name']} | {record['version']} | {len(record['license_files'])} |")
    if missing:
        lines += ["", "License-file review required for: " + ", ".join(missing) + ". Metadata has been included for these packages."]
    lines += ["", "The PyInstaller distribution notice includes its bootloader exception. NumPy/SciPy package license files include notices for their bundled numerical libraries. Electron and its bundled Chromium/Node components have separate notices in the desktop distribution."]
    (engine / "THIRD_PARTY_NOTICES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Collected third-party notices for {len(records)} packages; {len(missing)} missing license-file entries.")
    return manifest


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    collect(root, root / "dist-backend" / "statworkbench-engine")
