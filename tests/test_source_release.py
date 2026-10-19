"""The source archive must contain the sources needed to build Windows artifacts."""
import importlib.util
from pathlib import Path
import unittest


class SourceReleaseTests(unittest.TestCase):
    def test_windows_adapter_and_addin_build_sources_are_in_allowlist(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('source_release', root / 'scripts/create_source_release.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        files = {p.relative_to(root).as_posix() for p in module.source_files()}
        expected = {
            '.gitattributes',
            'electron/windows/SpreadsheetBridge.cs', 'scripts/build_windows_bridge.py',
            'addin/windows/ExcelAddin.cs', 'addin/windows/Ribbon.xml',
            'addin/windows/Build.ps1', 'addin/windows/Install.ps1', 'addin/windows/Uninstall.ps1',
            'tests/fixtures/reference_descriptive.json', 'tests/fixtures/reference_crosstab.json',
        }
        self.assertTrue(expected.issubset(files), sorted(expected - files))
        self.assertFalse(any(p.startswith(('dist-windows/', 'release/', 'test-artifacts/')) for p in files))


if __name__ == '__main__':
    unittest.main()
