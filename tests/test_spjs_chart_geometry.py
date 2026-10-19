import copy
import json
from pathlib import Path
import tempfile
import unittest
from backend.file_io import export_spjs, import_file
from backend.spjs_import import _export_chart, _export_images


class NativeGeometryTests(unittest.TestCase):
    def test_box_statistics_and_extreme_outliers_are_native_xy_geometry(self):
        spec={'type':'box','title':'Group statistics','series':[{'name':'First','y':[1,2,3], 'box':{'q1':1.5,'q3':2.5,'median':2,'mean':2.1,'low':1,'high':3,'mildOutliers':[-10],'extremeOutliers':[20]}}]}
        exported, note = _export_chart({'chart':spec},0)
        self.assertIn('fill is omitted',note)
        opts=exported['options'];series=opts['series']
        self.assertEqual(opts['axis']['x']['categories'],['First'])
        self.assertLess(opts['axis']['y']['min'],-10)
        self.assertGreater(opts['axis']['y']['max'],20)
        self.assertEqual(series[1]['y'],[2,2]);self.assertEqual(series[2]['y'],[2.1,2.1])
        self.assertEqual(series[3]['y'],[-10]);self.assertEqual(series[3]['markers']['style'],'nofill')
        self.assertEqual(series[4]['type'],'line')
        self.assertEqual(exported['statworkbenchSourceChart'],spec)

    def test_unequal_histogram_keeps_actual_edges_overlay_and_missing_bins(self):
        spec={'type':'histogram','title':'Unequal','series':[{'name':'Counts','x':[.5,2,4],'y':[2,None,5],'binEdges':[0,1,3,5]},{'name':'Curve','type':'line','x':[0,2,5],'y':[1,3,1]}]}
        exported,note=_export_chart({'chart':spec},0)
        series=exported['options']['series'];self.assertIn('exact numeric boundaries',note)
        self.assertEqual(series[0]['x'],[0,0,1,1,None,3,3,5,5,None])
        self.assertEqual(series[0]['y'],[0,2,2,0,None,0,5,5,0,None])
        self.assertEqual(series[1]['x'],[0,2,5])

    def test_geometry_survives_actual_file_export_and_import(self):
        sheet={'id':'s','name':'Data','rowCount':100,'columnCount':26,'cellData':{'0':{'0':{'v':1}}}}
        chart={'type':'box','series':[{'name':'Group','y':[1,2,3]}]}
        book={'sheetOrder':['s'],'sheets':{'s':sheet},'custom':{'statworkbenchCharts':[{'sheetId':'s','chart':chart}]}}
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'geometry.spjs';result=export_spjs(str(p),book)
            self.assertTrue(result['notes']);saved=json.loads(p.read_text())
            self.assertEqual(len(saved['charts']),1);self.assertEqual(saved.get('statworkbenchUnsupportedCharts',[]),[])
            restored=import_file(str(p));self.assertEqual(len(restored['importedCharts']),1)

    def test_mixed_equal_and_unequal_histograms_keep_all_bin_boundaries(self):
        spec={'type':'histogram','series':[{'name':'Equal','x':[1,3],'y':[2,4],'binEdges':[0,2,4]}, {'name':'Unequal','x':[-2,.5],'y':[3,5],'binEdges':[-4,0,1]}]}
        exported,note=_export_chart({'chart':spec},0)
        series=exported['options']['series']
        self.assertTrue(note)
        self.assertEqual([s['type'] for s in series],['line','line'])
        self.assertEqual(series[0]['x'],[0,0,2,2,None,2,2,4,4,None])
        self.assertEqual(series[1]['x'],[-4,-4,0,0,None,0,0,1,1,None])
        self.assertLessEqual(exported['options']['axis']['x']['min'],-4)
        self.assertGreaterEqual(exported['options']['axis']['x']['max'],4)

    def test_copied_picture_names_are_unique_against_retained_objects(self):
        png='data:image/png;base64,iVBORw0KGgo='
        native={'floatingObjects':[{'name':'Picture','floatingObjectType':0}]}
        entry={'sheetId':'s','source':png,'position':{'left':0,'top':0,'width':10,'height':10},'native':{'name':'Picture'}}
        _export_images(native,'s',[entry,copy.deepcopy(entry)],[])
        self.assertEqual([p['name'] for p in native['floatingObjects']],['Picture','Picture (2)','Picture (3)'])

    def test_invalid_geometry_is_rejected(self):
        for spec in [{'type':'box','series':[{'y':[1,2],'box':{'q1':3,'q3':1}}]}, {'type':'histogram','series':[{'x':[1,2],'y':[2,3],'binEdges':[0,2,1]}]}]:
            with self.assertRaises(ValueError):_export_chart({'chart':spec},0)
