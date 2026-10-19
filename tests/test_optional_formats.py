"""Synthetic interoperability checks for the parsers bundled with desktop releases."""
from pathlib import Path
import importlib.util
import struct
import tempfile
import unittest
from backend.file_io import import_file, export_file


def fixtures(folder):
    import pandas as pd
    import pyreadr
    import pyreadstat
    frame = pd.DataFrame({'Value': [1.5, 2.5, 4.0], 'Group': ['A', 'B', 'A']})
    frame.to_excel(folder / 'data.ods', engine='odf', index=False)
    frame.to_stata(folder / 'data.dta', write_index=False)
    pyreadstat.write_sav(frame, str(folder / 'data.sav'))
    pyreadstat.write_sav(frame, str(folder / 'data.zsav'), compress=True)
    pyreadstat.write_por(frame, str(folder / 'data.por'))
    pyreadstat.write_xport(frame, str(folder / 'data.xpt'), file_format_version=5)
    pyreadr.write_rdata(str(folder / 'data.rdata'), frame, df_name='Synthetic')
    pyreadr.write_rds(str(folder / 'data.rds'), frame)
    # Minimal dBASE III fixture; no writer dependency or bundled sample file.
    header=bytearray(32);header[0]=3;header[1:4]=bytes([126,10,16]);struct.pack_into('<IHH',header,4,3,97,21)
    fields=[]
    for name,kind,width,precision in [('Value','N',10,1),('Group','C',10,0)]:
        field=bytearray(32);field[:len(name)]=name.encode();field[11]=ord(kind);field[16]=width;field[17]=precision;fields.append(field)
    body=b''.join(b' '+f'{value:10.1f}'.encode()+group.encode().ljust(10) for value,group in zip(frame.Value,frame.Group))
    (folder/'data.dbf').write_bytes(header+b''.join(fields)+b'\r'+body+b'\x1a')
    return sorted(folder.glob('data.*'))

@unittest.skipUnless(all(importlib.util.find_spec(name) for name in ['pandas','pyreadr','pyreadstat','odf','dbfread']), 'Install requirements-formats.txt')
class OptionalFormatTests(unittest.TestCase):
    def test_synthetic_statistical_files_preserve_numeric_and_text_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            for file in fixtures(Path(tmp)):
                with self.subTest(format=file.suffix):
                    result=import_file(str(file))
                    self.assertEqual([name.lower() for name in result['columns']],['value','group'])
                    self.assertEqual(result['rows'],[[1.5,'A'],[2.5,'B'],[4.0,'A']])

    def test_spss_labels_user_missing_codes_unicode_and_metadata_json_roundtrip(self):
        import pandas as pd
        import pyreadstat
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'labelled.sav'
            frame = pd.DataFrame({'score': [1.5, 99., None], 'group': [1., 2., 1.], 'label': ['日本語', 'café', '']})
            pyreadstat.write_sav(frame, str(path), file_label='Independent fixture', column_labels={'score': 'Response score'}, variable_value_labels={'group': {1: 'Control', 2: 'Treatment'}}, missing_ranges={'score': [99]}, variable_measure={'score': 'scale', 'group': 'nominal'}, note='Missing code is retained as metadata')
            result = import_file(str(path))
            self.assertEqual(result['rows'], [[1.5, 1., '日本語'], [None, 2., 'café'], [None, 1., '']])
            metadata = result['formatMetadata']
            self.assertEqual(metadata['column_names_to_labels']['score'], 'Response score')
            self.assertEqual(metadata['variable_value_labels']['group']['1.0'], 'Control')
            self.assertEqual(metadata['userMissingCells'], [{'row': 1, 'column': 'score', 'value': 99.}])
            target = Path(tmp) / 'data.json'
            export_file(str(target), result)
            restored = import_file(str(target))
            self.assertEqual(restored['formatMetadata'], metadata)
            self.assertEqual(restored['rows'], result['rows'])

    def test_stata_labels_dates_missing_and_unicode_survive_as_data_and_metadata(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'labelled.dta'
            frame = pd.DataFrame({'score': [1., None, 3.], 'group': [1, 2, 1], 'date': pd.to_datetime(['2024-01-02', None, '2024-02-03']), 'text': ['日本語', 'café', 'NA']})
            frame.to_stata(path, write_index=False, version=118, convert_dates={'date': 'td'}, data_label='Independent fixture', variable_labels={'score': 'Measured score'}, value_labels={'group': {1: 'Control', 2: 'Treatment'}})
            result = import_file(str(path))
            self.assertEqual(result['rows'][0], [1., 1, '2024-01-02T00:00:00', '日本語'])
            self.assertEqual(result['rows'][1], [None, 2, None, 'café'])
            self.assertEqual(result['formatMetadata']['variableLabels']['score'], 'Measured score')
            self.assertEqual(result['formatMetadata']['valueLabels']['group']['2'], 'Treatment')

    def test_ods_multisheet_missing_literal_na_unicode_and_sheet_selection(self):
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sheets.ods'
            with pd.ExcelWriter(path, engine='odf') as writer:
                pd.DataFrame({'First': [1]}).to_excel(writer, sheet_name='First', index=False)
                pd.DataFrame({'Value': [1.5, None, -2.], 'Text': ['NA', '日本語', '001']}).to_excel(writer, sheet_name='Second', index=False)
            result = import_file(str(path), 'Second')
            self.assertEqual(result['sheets'], ['First', 'Second'])
            self.assertEqual(result['rows'], [[1.5, 'NA'], [None, '日本語'], [-2., '001']])

    def test_r_data_missing_and_unicode(self):
        import pandas as pd
        import pyreadr
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'mixed.rds'
            frame = pd.DataFrame({'Value': [1.5, None, 2.], 'Text': ['NA', '日本語', '001']})
            pyreadr.write_rds(str(path), frame)
            result = import_file(str(path))
            self.assertEqual(result['rows'], [[1.5, 'NA'], [None, '日本語'], [2., '001']])

if __name__=='__main__':unittest.main()
