#!/usr/bin/env python3
"""Create a source-only release from an explicit allowlist (MIT licensed)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CONTRACT.md", ".gitignore", ".gitattributes", "package.json",
    "package-lock.json", "electron-builder.config.cjs", "vite.config.mjs", "requirements.txt", "requirements-formats.txt", "requirements-test.txt",
    ".github/workflows/build.yml",
    "electron/main.cjs", "electron/preload.cjs", "electron/project.cjs", "electron/procedures.json", "electron/favorites.cjs",
    "renderer/app.js", "renderer/charts.js", "renderer/index.html", "renderer/styles.css",
    "renderer/workbook.js", "renderer/workbook-data.mjs", "renderer/analysis-input.js", "renderer/dialog-controls.js", "renderer/procedure-layouts.json",
)
DIRECTORY_PATTERNS = {
    "addin": ("*.cs", "*.xml", "*.ps1", "*.md"),
    "assets": ("*.png", "*.ico", "*.icns", "*.md", "*.json"),
    "electron": ("*.cjs", "*.json", "*.js", "*.ps1", "*.cs", "*.applescript"),
    "renderer": ("*.js", "*.mjs", "*.css", "*.json", "index.html"),
    "backend": ("*.py", "*.md", "requirements-build.txt"),
    "scripts": ("*.py", "*.cjs"),
    "tests": ("__init__.py", "reference_descriptive.json", "reference_crosstab.json", "test_*.py", "test_*.cjs", "test_*.mjs", "workbook-harness.html"),
    "docs": ("ARCHITECTURE.md", "CODE_SIGNING.md", "COMPATIBILITY.md", "MAC_SPREADSHEETS.md", "SPJS_INTEROPERABILITY.md", "WINDOWS_EXCEL.md", "copulas.md", "dependence.md", "stochastic-processes.md"),
    "licenses": ("*.txt", "*.json"),
}
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "build", "dist", "dist-backend", "dist-windows", "release", "test-artifacts", "results", "private-evidence"}


def source_files():
    paths = {ROOT / name for name in ROOT_FILES}
    for directory, patterns in DIRECTORY_PATTERNS.items():
        for pattern in patterns:
            paths.update((ROOT / directory).rglob(pattern))
    result = []
    for path in sorted(paths):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if not path.is_file():
            raise ValueError(f"An allowlisted release file is missing: {relative}")
        if path.is_symlink() or ROOT not in path.resolve().parents:
            raise ValueError(f"Refusing to include a source symlink/outside path: {relative}")
        if path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError(f"Unexpectedly large source file: {relative}")
        result.append(path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print the source inventory without writing a ZIP or release files.")
    args = parser.parse_args()
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    version = package["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("Package version is not a safe release filename component.")
    contents = [(str(path.relative_to(ROOT)).replace(os.sep, "/"), path.read_bytes()) for path in source_files()]
    if sum(len(data) for _, data in contents) > 50 * 1024 * 1024:
        raise ValueError("The source release exceeds the 50 MiB safety bound.")
    entries = [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()} for name, data in contents]
    manifest = {
        "format": "statworkbench-source-manifest-v1", "version": version,
        "scope": "StatWorkbench source, selected user documentation, tests and configuration. Runtime environments, generated logs, build outputs and local results are excluded.",
        "file_count": len(entries), "files": entries,
        "manifest_note": "This manifest does not hash itself; the separate SHA256SUMS file hashes the final ZIP.",
    }
    if args.dry_run:
        print(json.dumps({"archive": f"release/statworkbench-{version}-source.zip", "file_count": len(entries), "uncompressed_bytes": sum(e["bytes"] for e in entries), "files": [e["path"] for e in entries]}, indent=2))
        return
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    basename = f"statworkbench-{version}-source"
    archive_path = release / (basename + ".zip")
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".source-release-", suffix=".zip", dir=release)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in [*contents, ("SOURCE_MANIFEST.json", manifest_bytes)]:
                info = zipfile.ZipInfo(f"statworkbench-{version}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        # Do not package an inconsistent snapshot while another task edits source.
        for entry in entries:
            if hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
                raise RuntimeError("Source changed during packaging; retry after edits finish.")
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("Source ZIP integrity check failed.")
        os.replace(temporary, archive_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    (release / (basename + ".manifest.json")).write_bytes(manifest_bytes)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    (release / (basename + ".SHA256SUMS")).write_text(digest + "  " + archive_path.name + "\n", encoding="utf-8")
    print(json.dumps({"archive": str(archive_path), "sha256": digest, "source_files": len(entries), "bytes": archive_path.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
