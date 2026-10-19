#!/usr/bin/env python3
"""Build the Windows COM adapter without changing or depending on PowerShell policy."""
import hashlib
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def verify_failure_paths(executable):
    """Exercise the compiled file protocol without locating or launching Excel."""
    valid = {'app': 'excel', 'operation': 'write', 'matrix': [[1, 2]], 'numberFormat': '0.00', 'font': 'Arial', 'fontSize': 11}
    cases = [
        ('operation', {'app': 'excel', 'operation': 'eval'}, 'Unsupported spreadsheet operation.'),
        ('relative-workbook-path', {'app': 'excel', 'operation': 'read', 'expectedWorkbookPath': 'Data.xlsx'}, 'Invalid expected workbook path.'),
        ('chart-inspection-operation', {**valid, 'inspectCharts': True}, 'Chart inspection requires a read operation.'),
        ('range-operation', {'app': 'excel', 'operation': 'read', 'range': 'A1'}, 'A selected range requires an activate operation.'),
        ('range-bounds', {'app': 'excel', 'operation': 'activate', 'range': 'A1:A100001'}, 'Spreadsheet range exceeds the supported limits.'),
        ('rectangular', {**valid, 'matrix': [[1, 2], [3]]}, 'Result must be rectangular.'),
        ('font', {**valid, 'fontSize': 100}, 'Invalid result font.'),
        ('format', {**valid, 'numberFormat': 'execute()'}, 'Invalid result format.'),
        ('malformed-json', None, None),
    ]
    checks = []
    with tempfile.TemporaryDirectory(prefix='statworkbench protocol ') as directory:
        for name, payload, expected in cases:
            # Spaces, apostrophes and Unicode must survive the one-argument API.
            request = Path(directory) / ("request's 日本語 " + name + '.json')
            request.write_text(json.dumps(payload) if payload is not None else '{not JSON', encoding='utf-8')
            result = subprocess.run([str(executable), str(request)], capture_output=True, text=True, encoding='utf-8', timeout=30)
            if result.returncode == 0 or result.stdout.strip() or not result.stderr.strip() or expected and expected not in result.stderr:
                raise RuntimeError(f'Compiled adapter did not reject {name} before Excel automation: {result.stdout} {result.stderr}')
            checks.append({'name': name, 'rejected': True})
        oversized = Path(directory) / 'oversized.json'
        with oversized.open('wb') as stream:
            stream.truncate(32 * 1024 * 1024 + 1)
        result = subprocess.run([str(executable), str(oversized)], capture_output=True, text=True, encoding='utf-8', timeout=30)
        if result.returncode == 0 or result.stdout.strip() or 'exceeds 32 MiB' not in result.stderr:
            raise RuntimeError('Compiled adapter did not enforce its input byte limit.')
        checks.append({'name': 'byte-limit', 'rejected': True})
    return checks


def verify_report_package(executable):
    """Validate actual builder output in compiled C# without opening Excel."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from backend.report_xlsx import export_report_xlsx
    png = 'data:image/png;base64,' + base64.b64encode((ROOT / 'assets/statworkbench.png').read_bytes()).decode('ascii')
    with tempfile.TemporaryDirectory(prefix='statworkbench report ') as directory:
        report = Path(directory) / 'report.xlsx'
        exported = export_report_xlsx(str(report), {'matrix': [['=literal', 42]], 'chartImages': [
            {'chart': {'type': 'scatter', 'series': [{'x': [1, 2, 3], 'y': [3, 2, 4]}]}, 'png': png},
            {'png': png},
        ]})
        result = subprocess.run([str(executable), '--verify-report', str(report), str(exported['nativeCharts']), str(exported['imageCharts'])], check=True, capture_output=True, text=True, timeout=30)
        verified = json.loads(result.stdout)
        if verified.get('verified') is not True or verified.get('excelAutomationVerified') is not False:
            raise RuntimeError('Compiled report-package verification failed.')
        return {**verified, 'nativeCharts': exported['nativeCharts'], 'imageCharts': exported['imageCharts']}


def main():
    if sys.platform != 'win32':
        raise SystemExit('Build this executable on Windows with .NET Framework 4.x installed.')
    source = ROOT / 'electron/windows/SpreadsheetBridge.cs'
    compiler = Path(os.environ.get('WINDIR', r'C:\Windows')) / 'Microsoft.NET/Framework/v4.0.30319/csc.exe'
    if not compiler.is_file():
        raise SystemExit('.NET Framework C# compiler was not found.')
    output = ROOT / 'dist-windows'
    output.mkdir(exist_ok=True)
    executable = output / 'StatWorkbench.SpreadsheetBridge.exe'
    subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:anycpu', '/optimize+', '/reference:System.Runtime.Serialization.dll', '/reference:System.IO.Compression.dll', '/reference:System.Xml.dll', '/out:' + str(executable), str(source)], check=True, timeout=120)
    result = subprocess.run([str(executable), '--self-test'], check=True, capture_output=True, text=True, timeout=30)
    verification = json.loads(result.stdout)
    if verification.get('verified') is not True or verification.get('managedRuntime') is not True or verification.get('workbookPathGuardVerified') is not True or verification.get('reportPackageVerified') is not True or verification.get('excelAutomationVerified') is not False:
        raise SystemExit('Windows managed runtime verification failed.')
    verification['compiledProtocolFailureChecks'] = verify_failure_paths(executable)
    verification['compiledReportPackageCheck'] = verify_report_package(executable)
    verification.update(platform='win32', architecture='anycpu', source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest())
    (output / 'build-verification.json').write_text(json.dumps(verification, indent=2) + '\n')
    evidence = ROOT / 'test-artifacts/windows-spreadsheet-bridge'
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / 'build-verification.json').write_text(json.dumps(verification, indent=2) + '\n')
    print(json.dumps(verification))


if __name__ == '__main__':
    main()
