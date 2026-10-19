"""SPJS fixtures exercise the legacy project file boundary."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from backend.file_io import import_file, export_spjs


class SpjsProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "study.spjs"

    def tearDown(self):
        self.temp.cleanup()

    def load(self, document, sheet=None):
        self.path.write_text(json.dumps(document), encoding="utf-8")
        return import_file(str(self.path), sheet)

    @staticmethod
    def document():
        # Authored here from documented/observed field semantics; no source app
        # binary, source code, image or native saved document is redistributed.
        return {"workbook": {"version": "test-format", "activeSheetIndex": 1, "namedStyles": [
            {"name": "numeric", "formatter": "0.0000", "hAlign": 2, "vAlign": 2},
            {"name": "highlight", "parentName": "numeric", "backColor": "#eeddcc"},
        ], "sheets": {
            "Report": {"index": 1, "name": "Report", "rowCount": 20, "columnCount": 8,
                       "columns": [{"size": 164.5}, {"size": 88}], "rows": [{"size": 32}],
                       "spans": [{"row": 0, "col": 0, "rowCount": 1, "colCount": 4}],
                       "printInfo": {"fitPagesWide": 1}, "activeRow": 3, "activeCol": 1,
                       "data": {"defaultDataNode": {"style": {"vAlign": 2}}, "dataTable": {
                           "0": {"0": {"value": "Independent report", "style": {"font": "700 16px Arial", "borderBottom": {"style": 2, "color": "#808080"}}}, "3": {"style": {"borderBottom": {"style": 6}}}},
                           "2": {"0": {"value": "Average", "style": {"font": "italic 13.333333px Arial"}}, "1": {"value": 2.5, "style": "highlight"}},
                       }}},
            "Raw data": {"index": 0, "name": "Raw data", "rowCount": 12, "columnCount": 5,
                         "data": {"dataTable": {"0": {"0": {"value": "X"}, "1": {"value": "=SUM(1,2)"}}, "1": {"0": {"value": 2}}, "2": {"0": {"value": 3}}}}},
        }}, "charts": [], "creatorData": {"independent": True}}

    def test_all_sheets_keep_original_coordinates_order_and_active_sheet(self):
        data = self.load(self.document())
        book = data["workbook"]
        sheets = [book["sheets"][key] for key in book["sheetOrder"]]
        self.assertEqual([s["name"] for s in sheets], ["Raw data", "Report"])
        self.assertEqual(book["custom"]["statworkbenchActiveSheetId"], sheets[1]["id"])
        self.assertEqual(sheets[0]["cellData"]["0"]["0"]["v"], "X")
        self.assertEqual(sheets[0]["cellData"]["1"]["0"]["v"], 2)
        self.assertEqual(sheets[0]["cellData"]["0"]["1"], {"v": "=SUM(1,2)", "t": 1})
        self.assertEqual((sheets[0]["rowCount"], sheets[0]["columnCount"]), (12, 5))
        self.assertEqual(data["rows"][2][:2], ["Average", 2.5])
        selected = self.load(self.document(), "Raw data")["workbook"]
        self.assertEqual(selected["sheets"][selected["custom"]["statworkbenchActiveSheetId"]]["name"], "Raw data")

    def test_report_layout_named_styles_and_metadata_are_translated(self):
        book = self.load(self.document())["workbook"]
        report = book["sheets"][book["sheetOrder"][1]]
        self.assertEqual(report["mergeData"], [{"startRow": 0, "endRow": 0, "startColumn": 0, "endColumn": 3}])
        self.assertEqual(report["columnData"], {"0": {"w": 164.5}, "1": {"w": 88}})
        self.assertEqual(report["rowData"], {"0": {"h": 32}})
        self.assertEqual(report["defaultStyle"], {"vt": 3})
        title = report["cellData"]["0"]["0"]["s"]
        self.assertEqual((title["fs"], title["ff"], title["bl"]), (12, "Arial", 1))
        self.assertEqual(title["bd"]["b"], {"s": 8, "cl": {"rgb": "#808080"}})
        # Styling-only cells must not disappear just because there is no value.
        self.assertEqual(report["cellData"]["0"]["3"]["s"]["bd"]["b"]["s"], 7)
        value = report["cellData"]["2"]["1"]["s"]
        self.assertEqual(value, {"ht": 3, "vt": 3, "n": {"pattern": "0.0000"}, "bg": {"rgb": "#eeddcc"}})
        self.assertEqual(report["cellData"]["2"]["0"]["s"]["fs"], 10)
        self.assertEqual(report["custom"]["statplusImport"]["printInfo"], {"fitPagesWide": 1})
        self.assertEqual(book["custom"]["statplusImport"]["documentMetadata"], {"creatorData": {"independent": True}})

    def test_standard_formulas_recalculate_and_unsupported_cache_is_not_current_data(self):
        document = self.document()
        table = document["workbook"]["sheets"]["Raw data"]["data"]["dataTable"]
        table["3"] = {
            "0": {"formula": " SUM($A$2:A3) ", "value": 777},
            "1": {"formula": "'Raw data'!A2*2", "value": 999},
            "2": {"formula": "CUSTOM(1)", "value": 1000},
            "3": {"formula": "A4+C4", "value": 1777},
            "4": {"formula": 'IF(A2>1,"yes","no")', "value": "yes"},
        }
        data = self.load(document)
        cells = data["workbook"]["sheets"][data["workbook"]["sheetOrder"][0]]["cellData"]["3"]
        self.assertEqual(cells["0"]["f"], "=SUM($A$2:A3)")
        self.assertEqual(cells["1"]["f"], "='Raw data'!A2*2")
        self.assertEqual(cells["2"]["f"], "=NA()")
        self.assertIsNone(cells["2"]["v"])
        self.assertEqual(cells["2"]["custom"]["statplusImport"], {"formula": "CUSTOM(1)", "cachedValue": 1000, "formulaStatus": "unsupported"})
        self.assertEqual(cells["3"]["f"], "=A4+C4")
        self.assertEqual(cells["4"]["f"], '=IF(A2>1,"yes","no")')
        self.assertTrue(any("1 unsupported" in note for note in data["notes"]))
        self.assertTrue(any("Raw data R4C3" in note for note in data["notes"]))

    def test_native_relative_name_bases_mixed_dollars_and_nested_scope(self):
        # Native 8.0.4 reopening confirms G2/G3/G5 = 16/26/46, I2/I3/I5 =
        # 11/21/41, J2/J3/J5 = 11 and the remaining blank references = 0.
        document=self.document(); sheet=document['workbook']['sheets']['Raw data']
        sheet['columnCount']=12;sheet['rowCount']=20
        definitions=[('Relative','A1'),('RowAbsolute','A$1'),('ColumnAbsolute','$A1'),('Absolute','$A$1'),('Qualified',"'Report'!A1"),('Nested','Relative+1')]
        sheet['names']=[{'name':name,'formula':formula,'row':1,'col':1} for name,formula in definitions]
        sheet['data']['dataTable']={str(r):{str(c):{'value':(r+1)*10+c+1} for c in range(6)} for r in range(6)}
        for r in (1,2,4):
            for c,(name,_) in enumerate(definitions,6):sheet['data']['dataTable'][str(r)][str(c)]={'formula':name,'value':987}
        book=self.load(document)['workbook'];cells=book['sheets'][book['sheetOrder'][0]]['cellData']
        for r in (1,2,4):
            expected=[f"=('Raw data'!F{r})", "=('Raw data'!G$1)", f"=('Raw data'!$A{r})", "=('Raw data'!$A$1)", f"=('Report'!J{r})", f"=(('Raw data'!K{r})+1)"]
            self.assertEqual([cells[str(r)][str(c)]['f'] for c in range(6,12)],expected)
            self.assertTrue(all(cells[str(r)][str(c)]['v'] is None for c in range(6,12)))
        # Invalid relative bases, cycles, and negative shifted references never
        # fall back to an unrelated global definition or stale cached value.
        document['workbook']['names']=[{'name':'Broken','formula':'2'}]
        sheet['names'] += [{'name':'Broken','formula':'A1'}, {'name':'Cycle','formula':'Cycle','row':0,'col':0}]
        sheet['data']['dataTable']['0']['0']={'formula':'Relative','value':99}
        sheet['data']['dataTable']['0']['1']={'formula':'Broken','value':98}
        sheet['data']['dataTable']['0']['2']={'formula':'Cycle','value':97}
        book=self.load(document)['workbook'];cells=book['sheets'][book['sheetOrder'][0]]['cellData']['0']
        self.assertEqual([cells[str(c)]['f'] for c in range(3)],['=NA()']*3)

    def test_native_formula_families_use_implemented_functions(self):
        from backend.spjs_import import _FUNCTIONS, _formula
        expressions = ['SIN(PI()/2)', 'COS(0)', 'TEXT(12.5,"0.00")', 'DATE(2024,1,2)', 'YEAR(DATE(2024,1,2))', 'CONCATENATE("ab",UPPER("cd"))', 'NORM.DIST(0,0,1,TRUE)', 'PMT(0,10,100)', 'LOG10(100)', 'TRUE()', 'RAND()', 'TODAY()', 'LINEST(A1:A3,,TRUE,TRUE)']
        self.assertGreater(len(_FUNCTIONS), 380)
        for expression in expressions:
            with self.subTest(expression=expression):
                self.assertEqual(_formula(expression, set()), '=' + expression)
        for expression in ['WEBSERVICE("https://invalid")', 'RTD("server",,"topic")', 'CUSTOM(1)']:
            self.assertIsNone(_formula(expression, set()))

    def test_array_expansion_is_budgeted_before_allocating_output(self):
        from backend.spjs_import import _expand_arrays
        from unittest.mock import patch
        def table(height, expression='A1'):
            return {'0': {'1': {'formula': expression, 'arrayInfo': {'row': 0, 'col': 1, 'rowCount': height, 'colCount': 2}}}}
        # A compact long-formula array must be rejected before deepcopy or any
        # target-cell allocation, not after millions of provenance entries exist.
        with patch('backend.spjs_import.copy.deepcopy', side_effect=AssertionError('allocated before budget')):
            with self.assertRaisesRegex(ValueError, 'expanded formula and metadata limit'):
                _expand_arrays(table(100000, 'A1+' * 500 + 'A1'), set(), {}, [], 'Sheet')
        shared = [0]
        with patch('backend.spjs_import.MAX_TEXT_CHARACTERS', 2000):
            _expand_arrays(table(4), set(), {}, [], 'First', shared)
            with self.assertRaisesRegex(ValueError, 'expanded formula and metadata limit'):
                _expand_arrays(table(4), set(), {}, [], 'Second', shared)
        output = _expand_arrays(table(2, 'RAND()'), set(), {}, [], 'Sheet')
        self.assertEqual(output['0']['1']['formula'], '=SWB.CSE(RAND(),2,2)')
        self.assertTrue(output['1']['2']['statworkbenchArray']['supported'])
        self.assertTrue(output['1']['2']['statworkbenchArray']['singleEvaluation'])
        self.assertNotIn('formula', output['1']['2'])

    def test_volatile_array_roundtrip_restores_one_native_group_without_overwriting_edits(self):
        document = self.document()
        info = {'row': 4, 'col': 0, 'rowCount': 2, 'colCount': 2}
        table = document['workbook']['sheets']['Raw data']['data']['dataTable']
        table['4'] = {'0': {'formula': 'RAND()+A2:A3', 'arrayInfo': info, 'value': 999}}
        book = self.load(document)['workbook']
        cells = book['sheets'][book['sheetOrder'][0]]['cellData']
        self.assertEqual(cells['4']['0']['f'], '=SWB.CSE(RAND()+A2:A3,2,2)')
        self.assertIsNone(cells['4']['0']['v'])
        self.assertNotIn('f', cells['5']['1'])
        target = Path(self.temp.name) / 'volatile.spjs'
        export_spjs(str(target), book)
        saved = json.loads(target.read_text())['workbook']['sheets']['Raw data']['data']['dataTable']
        self.assertEqual(saved['4']['0']['formula'], 'RAND()+A2:A3')
        self.assertEqual(saved['4']['0']['arrayInfo'], info)
        cells['5']['1']['v'] = 42
        result = export_spjs(str(target), book)
        saved = json.loads(target.read_text())['workbook']['sheets']['Raw data']['data']['dataTable']
        self.assertEqual(saved['5']['1']['value'], 42)
        self.assertEqual(saved['4']['0']['formula'], 'NA()')
        self.assertNotIn('arrayInfo', saved['4']['0'])
        self.assertTrue(any('volatile array' in note for note in result['notes']))

    def test_unknown_named_and_malformed_formulas_remain_explicitly_unsupported(self):
        for expression in ('UnknownName+1', 'Missing!A1', 'WEBSERVICE("https://invalid")', '{1,2;3}', '{1,}', 'SUM(A1', 'SUM(A1))', '1 2', 'A100001', 'ZZZ1'):
            with self.subTest(expression=expression):
                document = self.document()
                document["workbook"]["sheets"]["Report"]["data"]["dataTable"]["3"] = {"0": {"formula": expression, "value": 987}}
                book = self.load(document)["workbook"]
                cell = book["sheets"][book["sheetOrder"][1]]["cellData"]["3"]["0"]
                self.assertEqual(cell["f"], "=NA()")
                self.assertIsNone(cell["v"])
                self.assertEqual(cell["custom"]["statplusImport"]["formula"], expression)

    def test_chart_series_positions_axes_and_originals_are_preserved(self):
        document = self.document()
        chart = {"sheetIndex": 1, "options": {"title": "X against expectation", "col": 0, "row": 5, "width": 500, "height": 300, "legend": 0,
            "axis": {"x": {"label": "Observed", "min": 0, "max": 4}, "y": {"label": "Expected", "min": -1, "max": 5}},
            "series": [{"type": "scatter", "label": "Points", "x": [1, 2, 3], "y": [1.2, 2.1, 3.3], "color": "#123456"}, {"type": "line", "label": "Reference", "x": [0, 4], "y": [0, 4]}]}}
        document["charts"] = [chart, {"sheetIndex": 1, "options": {"series": [{"type": "pie", "y": [1, 2]}]}}]
        before = copy.deepcopy(document)
        data = self.load(document)
        translated = data["importedCharts"]
        self.assertEqual(len(translated), 1)
        self.assertEqual(translated[0]["position"], {"row": 5, "column": 0, "width": 500, "height": 300})
        self.assertEqual(translated[0]["chart"]["series"][0]["y"], [1.2, 2.1, 3.3])
        self.assertEqual(translated[0]["chart"]["yMin"], -1)
        self.assertEqual(translated[0]["chart"]["xLabel"], "Observed")
        self.assertFalse(translated[0]["chart"]["legend"])
        self.assertEqual(data["workbook"]["custom"]["statplusImport"]["charts"], before["charts"])
        self.assertEqual(document, before)
        self.assertTrue(any("Chart 2" in note for note in data["notes"]))

    def test_combined_acf_chart_keeps_category_centers_and_confidence_limits(self):
        document = self.document()
        document["charts"] = [{"sheetIndex": 1, "options": {
            "title": "ACF", "row": 5, "col": 0,
            "axis": {"x": {"min": 0, "max": 3, "categories": ["1", "2", "3"]}},
            "series": [{"type": "bar", "y": [0.4, 0.2, -0.1]}, {"type": "line", "x": [0.5, 1.5, 2.5], "y": [0.6, 0.5, 0.4]}],
        }}]
        chart = self.load(document)["importedCharts"][0]["chart"]
        self.assertEqual(chart["type"], "bar")
        self.assertEqual(chart["series"][0]["x"], [0.5, 1.5, 2.5])
        self.assertEqual(chart["series"][1]["x"], chart["series"][0]["x"])
        self.assertEqual(chart["xTicks"], [{"value": 0.5, "label": "1"}, {"value": 1.5, "label": "2"}, {"value": 2.5, "label": "3"}])

    def test_spline_marker_width_and_grid_size_are_translated(self):
        document = self.document()
        document["charts"] = [{"sheetIndex": 1, "options": {"row": 5, "col": 0, "cwidth": 3, "cheight": 10, "series": [{"type": "spline", "x": [0, 1, 0, -1, 0], "y": [1, 0, -1, 0, 1], "width": 3, "markers": {"visible": False, "r": 4}, "dashStyle": "dash"}]}}]
        imported = self.load(document)["importedCharts"][0]
        self.assertEqual(imported["chart"]["series"][0]["type"], "spline")
        self.assertEqual(imported["chart"]["series"][0]["markers"], {"visible": False, "radius": 4})
        self.assertEqual(imported["position"]["width"], 316.5)
        self.assertEqual(imported["position"]["height"], 200)

    def test_defined_names_resolve_absolute_ranges_constants_and_local_shadowing(self):
        document = self.document()
        document["workbook"]["names"] = [{"name": "Rate", "formula": "2", "row": 0, "col": 0}, {"name": "Cycle", "formula": "Cycle"}]
        sheet = document["workbook"]["sheets"]["Raw data"]
        sheet["names"] = [{"name": "Rate", "formula": "3"}, {"name": "Inputs", "formula": "$A$2:$A$3"}, {"name": "Relative", "formula": "A2", "row": 0, "col": 0}]
        sheet["data"]["dataTable"]["3"] = {"0": {"formula": "SUM(Inputs)*Rate"}, "1": {"formula": "Cycle"}, "2": {"formula": "Relative"}}
        book = self.load(document)["workbook"]
        cells = book["sheets"][book["sheetOrder"][0]]["cellData"]["3"]
        self.assertEqual(cells["0"]["f"], "=SUM(('Raw data'!$A$2:$A$3))*(3)")
        self.assertEqual(cells["1"]["f"], "=NA()")
        self.assertEqual(cells["2"]["f"], "=('Raw data'!C5)")

    def test_elementwise_arrays_are_live_and_unsupported_array_ranges_are_all_errors(self):
        document = self.document()
        table = document["workbook"]["sheets"]["Raw data"]["data"]["dataTable"]
        table["4"] = {"0": {"formula": "A2:A3*2", "arrayInfo": {"row": 4, "col": 0, "rowCount": 2, "colCount": 1}, "value": 999}}
        table["5"] = {"0": {"value": 888}}
        table["7"] = {"0": {"formula": "FUTUREARRAY(A2:A3)", "arrayInfo": {"row": 7, "col": 0, "rowCount": 2, "colCount": 1}, "value": 777}}
        table["8"] = {"0": {"value": 666}}
        book = self.load(document)["workbook"]
        cells = book["sheets"][book["sheetOrder"][0]]["cellData"]
        self.assertEqual(cells["4"]["0"]["f"], "=$A$2*2")
        self.assertEqual(cells["5"]["0"]["f"], "=$A$3*2")
        self.assertEqual(cells["7"]["0"]["f"], "=NA()")
        self.assertEqual(cells["8"]["0"]["f"], "=NA()")
        self.assertIsNone(cells["8"]["0"]["v"])

    def test_matrix_reducer_and_constant_arrays_keep_live_shape_aware_formulas(self):
        from backend.spjs_import import _array_projection
        document = self.document()
        table = document['workbook']['sheets']['Raw data']['data']['dataTable']
        expressions = ['MMULT(A1:B2,D1:E2)', 'MINVERSE(A1:B2)', 'TRANSPOSE(A1:B2)', 'SUM(A1:B2*2)', '{1,2;3,4}', 'SUMPRODUCT(A1:B2,A1:B2)']
        for i, expression in enumerate(expressions):
            row = 5 + i * 4
            table[str(row)] = {'0': {'formula': expression, 'value': 999, 'arrayInfo': {'row': row, 'col': 0, 'rowCount': 3, 'colCount': 3}}}
        book = self.load(document)['workbook']
        cells = book['sheets'][book['sheetOrder'][0]]['cellData']
        for i, expression in enumerate(expressions):
            row = 5 + i * 4
            for dr in range(3):
                for dc in range(3):
                    cell = cells[str(row + dr)][str(dc)]
                    self.assertEqual(cell['f'], _array_projection('=' + expression, dr, dc))
                    self.assertIsNone(cell['v'])
                    self.assertEqual(cell['custom']['statplusImport']['formulaStatus'], 'translated')
        # Native external workbook references fail as #REF!, not a stale cache.
        table['40'] = {str(i): {'formula': f, 'value': 777} for i, f in enumerate(['[elsewhere.xlsx]Report!A1', "'[elsewhere.xlsx]Report'!A1", '#REF!', '#DIV/0!'])}
        book = self.load(document)['workbook']
        values = book['sheets'][book['sheetOrder'][0]]['cellData']['40']
        self.assertEqual([values[str(i)]['f'] for i in range(4)], ['=#REF!', '=#REF!', '=#REF!', '=#DIV/0!'])
        self.assertTrue(all(cell['v'] is None for cell in values.values()))

    def test_qualified_names_use_the_named_sheet_scope(self):
        document = self.document()
        raw = document['workbook']['sheets']['Raw data']
        report = document['workbook']['sheets']['Report']
        raw['names'] = [{'name': 'Rate', 'formula': '2'}, {'name': 'Nested', 'formula': 'Rate+1'}, {'name': 'Inputs', 'formula': '$A$2:$A$3'}]
        report['names'] = [{'name': 'Rate', 'formula': '9'}]
        report['data']['dataTable']['4'] = {str(i): {'formula': f, 'value': 999} for i, f in enumerate(["'Raw data'!Nested", "SUM('Raw data'!Inputs)*Rate", "'[Other.xlsx]Raw data'!Rate"])}
        book = self.load(document)['workbook']
        cells = book['sheets'][book['sheetOrder'][1]]['cellData']['4']
        self.assertEqual(cells['0']['f'], '=(((2)+1))')
        self.assertEqual(cells['1']['f'], "=SUM((('Raw data'!$A$2:$A$3)))*(9)")
        self.assertEqual(cells['2']['f'], '=#REF!')

    def test_intact_matrix_groups_restore_native_array_metadata_but_edits_are_preserved(self):
        document = self.document()
        table = document['workbook']['sheets']['Raw data']['data']['dataTable']
        info = {'row': 5, 'col': 0, 'rowCount': 2, 'colCount': 2}
        table['5'] = {'0': {'formula': 'TRANSPOSE(A1:B2)', 'arrayInfo': info}}
        book = self.load(document)['workbook'];sid = book['sheetOrder'][0]
        target = Path(self.temp.name) / 'matrix.spjs'
        export_spjs(str(target), book)
        saved = json.loads(target.read_text())['workbook']['sheets']['Raw data']['data']['dataTable']
        self.assertEqual(saved['5']['0']['formula'], 'TRANSPOSE(A1:B2)')
        self.assertEqual(saved['5']['0']['arrayInfo'], info)
        self.assertNotIn('formula', saved['6']['1'])
        self.assertEqual(import_file(str(target))['workbook']['sheets'].popitem()[1]['name'], 'Report')
        book['sheets'][sid]['cellData']['6']['1']['f'] = '=123'
        export_spjs(str(target), book)
        saved = json.loads(target.read_text())['workbook']['sheets']['Raw data']['data']['dataTable']
        self.assertNotIn('arrayInfo', saved['5']['0'])
        self.assertEqual(saved['6']['1']['formula'], '123')
        self.assertTrue(saved['5']['0']['formula'].startswith('INDEX(TRANSPOSE('))

    def test_embedded_pictures_keep_data_geometry_flags_and_live_export_edits(self):
        # Independently generated one-pixel PNG: no original artwork.
        import base64, struct, zlib
        def chunk(kind, data):return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
        png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\0\x20\x40\x80\xff')) + chunk(b'IEND', b'')
        source = 'data:image/png;base64,' + base64.b64encode(png).decode()
        document = self.document()
        pictures = [{'floatingObjectType': 1, 'name': 'Sample picture', 'src': source, 'x': 12.5, 'y': 45, 'width': 120, 'height': 80, 'dynamicMove': False, 'pictureStretch': 2, 'unknownPictureOption': 'keep'}, {'floatingObjectType': 0, 'name': 'HTML', 'content': '<script>must remain inert</script>'}, {'floatingObjectType': 1, 'name': 'External image', 'src': 'https://invalid.test/image.png', 'width': 10, 'height': 10}]
        document['workbook']['sheets']['Report']['floatingObjects'] = pictures
        imported = self.load(document)
        book = imported['workbook']; sid = book['sheetOrder'][1]
        images = book['custom']['statplusImport']['importedImages']
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]['native'], pictures[0])
        self.assertEqual(images[0]['position'], {'left': 12.5, 'top': 45, 'width': 120, 'height': 80})
        self.assertEqual(book['sheets'][sid]['custom']['statplusImport']['managedImageIndices'], [0])
        self.assertTrue(any('HTML' in note for note in imported['notes']))
        book['custom']['statworkbenchImages'] = [{**images[0], 'drawingId': 'live', 'position': {'left': 40, 'top': 60, 'width': 240, 'height': 160}}]
        target = Path(self.temp.name) / 'pictures.spjs'
        export_spjs(str(target), book)
        saved = json.loads(target.read_text())['workbook']['sheets']['Report']['floatingObjects']
        moved = next(p for p in saved if p['name'] == 'Sample picture')
        self.assertEqual((moved['x'], moved['y'], moved['width'], moved['height']), (40,60,240,160))
        self.assertFalse(moved['dynamicMove']);self.assertEqual(moved['unknownPictureOption'], 'keep')
        self.assertIn(pictures[1], saved);self.assertIn(pictures[2], saved)
        current = book['custom']['statworkbenchImages'][0]
        current['native'] = {**current['native'], 'dynamicMove': True, 'fixedPosition': True, 'pictureStretch': 0, 'borderStyle': 'none', 'borderWidth': 0, 'backColor': None}
        current['flattenedStyle'] = True
        export_spjs(str(target), book)
        doc = json.loads(target.read_text())
        flattened = next(p for p in doc['workbook']['sheets']['Report']['floatingObjects'] if p['name'] == 'Sample picture')
        self.assertTrue(flattened['dynamicMove']);self.assertTrue(flattened['fixedPosition'])
        self.assertEqual(flattened['pictureStretch'], 0);self.assertEqual(flattened['borderWidth'], 0)
        self.assertTrue(any('displayed appearance' in note for note in doc['statworkbenchExportWarnings']))
        book['custom']['statworkbenchImages'] = []
        export_spjs(str(target), book)
        self.assertEqual(json.loads(target.read_text())['workbook']['sheets']['Report']['floatingObjects'], pictures[1:])
        book['custom']['statworkbenchImages'] = [{'sheetId': sid, 'source': 'data:image/png;base64,AAAA', 'position': images[0]['position']}]
        before = target.read_bytes()
        with self.assertRaises(ValueError):export_spjs(str(target), book)
        self.assertEqual(target.read_bytes(), before)

    def test_spjs_export_keeps_edits_layout_unknown_metadata_and_chart_sheet_mapping(self):
        document = self.document()
        document["charts"] = [{"sheetIndex": 1, "options": {"row": 5, "col": 0, "series": [{"type": "spline", "y": [1, 2, 1]}]}}]
        data = self.load(document)
        book = data["workbook"]
        raw, report = book["sheetOrder"]
        book["sheets"][raw]["cellData"]["1"]["0"]["v"] = 42
        book["sheets"][raw]["cellData"]["3"] = {"0": {"f": "=SUM(A2:A3)", "v": 45}}
        book["sheetOrder"] = [report, raw]
        target = Path(self.temp.name) / "edited.spjs"
        result = export_spjs(str(target), book)
        self.assertEqual(result["sheets"], 2)
        saved = json.loads(target.read_text())
        self.assertEqual(saved["creatorData"], {"independent": True})
        self.assertEqual(saved["charts"][0]["sheetIndex"], 0)
        restored = import_file(str(target))["workbook"]
        sheets = [restored["sheets"][s] for s in restored["sheetOrder"]]
        self.assertEqual([s["name"] for s in sheets], ["Report", "Raw data"])
        self.assertEqual(sheets[1]["cellData"]["1"]["0"]["v"], 42)
        self.assertEqual(sheets[1]["cellData"]["3"]["0"]["f"], "=SUM(A2:A3)")
        self.assertEqual(sheets[0]["mergeData"], book["sheets"][report]["mergeData"])
        self.assertEqual(sheets[0]["cellData"]["2"]["1"]["s"], book["sheets"][report]["cellData"]["2"]["1"]["s"])

    def test_spjs_export_failure_does_not_replace_existing_file(self):
        book = self.load(self.document())["workbook"]
        self.path.write_text("original")
        book["sheets"][book["sheetOrder"][0]]["cellData"]["999999"] = {"0": {"v": 4}}
        with self.assertRaises(ValueError):
            export_spjs(str(self.path), book)
        self.assertEqual(self.path.read_text(), "original")
        self.assertFalse(list(Path(self.temp.name).glob(".statworkbench-*")))

    def test_created_and_edited_chart_definitions_export_and_reimport(self):
        document = self.document()
        document['charts'] = [{'sheetIndex': 1, 'options': {'title': 'Original', 'row': 5, 'col': 0, 'legend': 2,
            'nativeExtra': 'retain', 'series': [{'type': 'line', 'y': [1, 2], 'markers': {'visible': True, 'type': 'rect'}, 'width': 4}]}}]
        imported = self.load(document)
        book = imported['workbook']; raw, report = book['sheetOrder']
        original = imported['importedCharts'][0]
        book['custom']['statworkbenchCharts'] = [{**original, 'drawingId': 'old'}, {'sheetId': raw, 'drawingId': 'new',
            'chart': {'type': 'scatter', 'title': 'Created', 'legend': False, 'xLabel': 'X', 'yLabel': 'Y', 'xMin': -1, 'xMax': 4,
                'reverseY': True, 'series': [{'name': 'Points', 'x': [0, 1, 2], 'y': [1, None, 3], 'color': '#123456', 'markers': {'visible': True, 'radius': 6, 'style': 'nofill'}},
                {'name': 'Fit', 'type': 'line', 'x': [0, 3], 'y': [0, 3], 'dash': 'dash', 'width': 3}]},
            'position': {'row': 7, 'column': 1, 'width': 510, 'height': 320}}]
        target = Path(self.temp.name) / 'charts.spjs'
        export_spjs(str(target), book)
        saved = json.loads(target.read_text())
        self.assertEqual(len(saved['charts']), 2)
        unchanged = saved['charts'][0]['options']
        self.assertEqual(unchanged['legend'], 2)
        self.assertEqual(unchanged['series'][0]['markers']['type'], 'rect')
        self.assertEqual(unchanged['nativeExtra'], 'retain')
        restored = import_file(str(target))['importedCharts'][1]
        self.assertEqual(restored['position'], {'row': 7, 'column': 1, 'width': 510, 'height': 320})
        self.assertEqual(restored['chart']['series'][0]['y'], [1, None, 3])
        self.assertEqual(restored['chart']['series'][1]['dash'], 'dash')
        self.assertTrue(restored['chart']['reverseY'])
        self.assertFalse(restored['chart']['legend'])
        # Editing the semantic chart replaces its native original, not a duplicate.
        original['chart']['title'] = 'Edited'; original['chart']['series'][0]['y'] = [4, 5]
        book['sheetOrder'] = [report, raw]
        export_spjs(str(target), book)
        saved = json.loads(target.read_text())
        self.assertEqual([c['sheetIndex'] for c in saved['charts']], [0, 1])
        self.assertEqual(saved['charts'][0]['options']['title'], 'Edited')
        self.assertEqual(saved['charts'][0]['options']['series'][0]['y'], [4, 5])
        # Removing an image removes that managed chart from the exported project.
        book['custom']['statworkbenchCharts'] = []
        export_spjs(str(target), book)
        self.assertEqual(json.loads(target.read_text())['charts'], [])

    def test_exported_categorical_stacked_histogram_and_step_chart_fields(self):
        book = self.load(self.document())['workbook']; sheet = book['sheetOrder'][1]
        charts = [
            {'type': 'bar', 'title': 'Stack', 'stack': 'normal', 'series': [{'name': 'a', 'x': ['A', 'B'], 'y': [2, 3]}, {'name': 'b', 'x': ['A', 'B'], 'y': [4, 5]}]},
            {'type': 'histogram', 'title': 'Histogram', 'xMin': 1, 'xMax': 4, 'binEdges': [1, 2, 3, 4], 'xTicks': [{'value': 1.5, 'label': '1 To 2'}, {'value': 2.5, 'label': '2 To 3'}, {'value': 3.5, 'label': '3 and over'}], 'series': [{'x': [1.5, 2.5, 3.5], 'y': [1, 3, 2], 'barWidth': 95}, {'type': 'spline', 'x': [1, 2, 3, 4], 'y': [1, 2, 2, 1]}]},
            {'type': 'step', 'title': 'Survival', 'series': [{'x': [0, 1, 2], 'y': [1, .8, .5]}]},
        ]
        book['custom']['statworkbenchCharts'] = [{'sheetId': sheet, 'chart': chart, 'position': {'row': i*5, 'column': 0, 'width': 500, 'height': 300}} for i,chart in enumerate(charts)]
        target = Path(self.temp.name) / 'kinds.spjs'
        export_spjs(str(target), book)
        saved = json.loads(target.read_text())['charts']
        self.assertEqual(saved[0]['options']['axis']['x']['categories'], ['A', 'B'])
        self.assertEqual(saved[0]['options']['series'][0]['bar-style'], 'stacked')
        self.assertEqual(saved[0]['options']['axis']['y']['min'],0)
        self.assertGreater(saved[0]['options']['axis']['y']['max'],8)
        self.assertEqual(saved[1]['options']['axis']['y']['min'],0)
        self.assertEqual(saved[1]['options']['series'][0]['width'], 95)
        self.assertEqual(saved[1]['options']['series'][0]['type'], 'bar')
        self.assertEqual(saved[2]['options']['series'][0]['type'], 'step')
        restored = import_file(str(target))['importedCharts']
        self.assertEqual(restored[0]['chart']['stack'], 'normal')
        self.assertEqual(restored[2]['chart']['series'][0]['type'], 'step')

    def test_unsupported_new_chart_is_retained_inert_and_reported(self):
        book = self.load(self.document())['workbook']
        book['custom']['statworkbenchCharts'] = [{'sheetId': book['sheetOrder'][0], 'chart': {'type': 'pie', 'title': 'Unsupported pie', 'series': [{'y': [1, 2, 3]}]}}]
        target = Path(self.temp.name) / 'unsupported.spjs'
        result = export_spjs(str(target), book)
        saved = json.loads(target.read_text())
        self.assertEqual(saved['charts'], [])
        self.assertEqual(saved['statworkbenchUnsupportedCharts'][0]['chart']['type'], 'pie')
        self.assertTrue(any("unsupported 'pie'" in note for note in result['notes']))
        book['custom']['statworkbenchCharts'][0]['chart'] = {'type': 'line', 'series': [{'x': [1], 'y': [1, 2]}]}
        before = target.read_bytes()
        with self.assertRaises(ValueError):export_spjs(str(target), book)
        self.assertEqual(target.read_bytes(), before)

    def test_all_sheets_and_style_only_cells_are_bounded(self):
        for row, column in (("100000", "0"), ("0", "1000"), ("000", "1")):
            document = self.document()
            document["workbook"]["sheets"]["Raw data"]["data"]["dataTable"][row] = {column: {"style": {"font": "12pt Arial"}}}
            with self.subTest(row=row, column=column), self.assertRaisesRegex(ValueError, "limits|index"):
                self.load(document)
        document = self.document()
        document["workbook"]["sheets"]["Raw data"]["rowCount"] = 100001
        with self.assertRaisesRegex(ValueError, "limits"):
            self.load(document)

    def test_invalid_merges_names_and_metadata_are_rejected(self):
        for patch in ({"spans": [{"row": 0, "col": 0, "rowCount": 1, "colCount": 3}, {"row": 0, "col": 2, "rowCount": 1, "colCount": 2}]}, {"spans": [{"row": 19, "col": 1, "rowCount": 2, "colCount": 2}]}, {"name": "Raw data"}, {"columns": {"99999": {"size": 1}}}):
            document = self.document()
            document["workbook"]["sheets"]["Report"].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.load(document)


if __name__ == "__main__":
    unittest.main()
