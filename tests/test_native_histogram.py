"""Histogram bin boundaries and edge handling."""
import unittest
import numpy as np
from backend.analyses.native_histogram import neat_bounds, frequency_edges, descriptive_histogram
from backend.analyses.basic import analyze
from tests.test_basic import dataset


class NativeHistogramTests(unittest.TestCase):
    def test_neat_width_strict_decision_boundaries(self):
        for desired, expected in [(1.,1.),(1.4,1.),(1.400001,2.),(2.8,2.),
                                  (2.800001,5.),(7.,5.),(7.000001,10.)]:
            with self.subTest(desired=desired):
                self.assertEqual(neat_bounds(0,desired*10,10)[2],expected)
        self.assertEqual(neat_bounds(-2.6,12.4,5),(-5.,15.,5.,4))

    def test_continuous_open_endpoint_expansion_and_negative_bounds(self):
        np.testing.assert_array_equal(frequency_edges([0,1,2,3],3,'left'),[0,1,2,3,4])
        np.testing.assert_array_equal(frequency_edges([0,1,2,3],3,'right'),[-1,0,1,2,3])
        np.testing.assert_array_equal(frequency_edges([-3,-2,-1,0],3,'left'),[-3,-2,-1,0,1])
        np.testing.assert_array_equal(frequency_edges([-3,-2,-1,0],3,'right'),[-4,-3,-2,-1,0])

    def test_weighted_auto_bins_use_rows_not_sum_of_weights(self):
        x=np.arange(15)*.8+.3
        d=dataset(['x','w'],zip(x,np.arange(15)+1))
        options={'columns':['x'],'sta.bst.ds.hist.bins0':False}
        plain=analyze('1013',d,options)['tables'][0]['rows']
        weighted=analyze('1013',d,{**options,'sta.bst.freq.freqvar':'w'})['tables'][0]['rows']
        self.assertEqual([r[:2] for r in plain],[r[:2] for r in weighted])
        self.assertEqual(sum(r[2] for r in weighted),120)

    def test_descriptive_ceil_target_and_final_catch_all(self):
        counts,edges=descriptive_histogram(np.arange(1,11),3)
        np.testing.assert_array_equal(edges,[0,5,10])
        np.testing.assert_array_equal(counts,[4,6])
        counts,edges=descriptive_histogram([1,2,3,4,5,6])
        np.testing.assert_array_equal(edges,[1,2,3,4,5,6])
        np.testing.assert_array_equal(counts,[1,1,1,1,2])

    def test_tiny_nonconstant_range_is_enclosed(self):
        low,high,width,count=neat_bounds(1.,np.nextafter(1.,2.),5)
        self.assertLessEqual(low,1.);self.assertGreaterEqual(high,np.nextafter(1.,2.))
        self.assertGreater(width,0);self.assertGreaterEqual(count,1)

    def test_custom_open_outer_endpoints_have_overflow_bins(self):
        d=dataset(['x','edges'],[[0,0],[1,2],[2,4],[4,None]])
        for closed in ['left','right']:
            rows=analyze('1015',d,{'columns':['x'],'closed':closed,'sta.bst.freq.bins_var':'edges'})['tables'][0]['rows']
            self.assertEqual(sum(row[2] for row in rows),4)
            if closed=='left':self.assertEqual(rows[-1][:3],[4.,None,1.])
            else:self.assertEqual(rows[0][:3],[None,0.,1.])

    def test_descriptive_histogram_native_variation_gate_and_axes(self):
        for values in [[1,1,1],[1.,1.+1e-8,1.+2e-8]]:
            r=analyze('1001',dataset(['x'],zip(values)),{'columns':['x'],'sta.bst.ds.ao.0':True})
            self.assertEqual(r['charts'],[])
        r=analyze('1001',dataset(['x'],zip(range(1,11))),{'columns':['x'],'sta.bst.ds.ao.0':True,'sta.bst.ds.ao.1':True,'sta.bst.ds.ao.2':3})
        c=r['charts'][0]
        self.assertEqual([c['xMin'],c['xMax'],c['yMin'],c['yMax']],[0.,10.,0.,8.])
