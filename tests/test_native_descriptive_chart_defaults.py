"""Presentation policies checked against a native exported descriptive report."""
import unittest
import numpy as np
from backend.analyses.basic import analyze
from tests.test_basic import dataset


class NativeDescriptiveChartDefaults(unittest.TestCase):
    def charts(self,values):
        return analyze('1001',dataset(['Value'],[[v] for v in values]),{
            'columns':['Value'],'sta.bst.ds.ao.0':True,
            'sta.bst.ds.ao.1':True,'sta.chart.qq':True})['charts']

    def test_native_histogram_interval_labels_and_terminal_catch_all(self):
        histogram,_=self.charts(range(1,7))
        self.assertEqual([t['label'] for t in histogram['xTicks']],
                         ['1 To 2','2 To 3','3 To 4','4 To 5','5 and over'])
        np.testing.assert_allclose([t['value'] for t in histogram['xTicks']],[1.5,2.5,3.5,4.5,5.5])
        self.assertEqual(histogram['series'][0]['y'],[1,1,1,1,2])
        self.assertEqual(histogram['series'][0]['barWidth'],95)
        self.assertEqual(histogram['series'][1]['type'],'spline')
        self.assertEqual(histogram['series'][1]['markers'],{'visible':False})
        self.assertEqual([s['color'] for s in histogram['series']],['#386D9E','#9F386D'])
        self.assertFalse(histogram['legend']);self.assertEqual(histogram['xLabel'],'')

    def test_interval_labels_follow_negative_translated_bins(self):
        histogram,_=self.charts(np.arange(1,7)*2-20)
        edges=histogram['binEdges']
        self.assertEqual(histogram['xTicks'][0]['label'],f'{edges[0]:g} To {edges[1]:g}')
        self.assertEqual(histogram['xTicks'][-1]['label'],f'{edges[-2]:g} and over')

    def test_native_qq_hollow_markers_and_unmarked_black_reference(self):
        _,qq=self.charts(range(1,7))
        self.assertEqual(qq['title'],'Normal Q-Q Plot - Value')
        self.assertEqual(qq['yLabel'],'Expected Value');self.assertEqual(qq['xLabel'],'')
        self.assertFalse(qq['legend'])
        points,reference=qq['series']
        self.assertEqual(points['markers'],{'visible':True,'style':'nofill','radius':4})
        self.assertEqual(reference['color'],'#000000');self.assertFalse(reference['markers']['visible'])

    def test_four_native_fixtures_match_bounds_and_tick_spacing(self):
        fixtures=[
            (range(1,7),(0,7,1,6,.5,.5)),
            ([-12,-9,-7,-6,-5,-1],(-14,0,-12,0,2,2)),
            ([100.01,100.02,100.03,100.04,100.05,100.06],(100,100.06,100.01,100.06,.01,.005)),
            ([.01,.02,.1,1,3,20],(0,25,-10,15,1,5)),
        ]
        for values,expected in fixtures:
            with self.subTest(values=list(values)):
                histogram,qq=self.charts(values)
                np.testing.assert_allclose([qq[k] for k in ['xMin','xMax','yMin','yMax','xMajorUnit','yMajorUnit']],expected,rtol=1e-13,atol=1e-13)
                self.assertTrue(qq['clip'])
                self.assertGreater(qq['series'][0]['layer'],qq['series'][1].get('layer',0))
                self.assertEqual(histogram['yMajorUnit'],1 if expected[1]==25 else .5)

    def test_general_grid_never_crops_finite_nonconstant_points(self):
        from backend.analyses.native_chart_axes import descriptive_qq_axes
        rng=np.random.default_rng(7)
        for scale in [1e-5,1,1e5]:
            for offset in [-100,0,100]:
                x=offset+scale*rng.normal(size=20)
                axes=descriptive_qq_axes(x,x*.7+3)
                self.assertLessEqual(axes['xMin'],min(x)+abs(min(x))*1e-14)
                self.assertGreaterEqual(axes['xMax'],max(x)-abs(max(x))*1e-14)
                self.assertGreater(axes['xMajorUnit'],0)
