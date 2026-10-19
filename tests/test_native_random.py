"""Published MT19937 vectors and distribution conventions."""
import math
import unittest
import numpy as np
from backend.analyses.native_random import NativeRandom
from backend.analyses.advanced import analyze


class NativeRandomTests(unittest.TestCase):
    # Standard MT19937 reference output for init_genrand(5489).
    WORDS = np.array([3499211612,581869302,3890346734,3586334585,545404204,
                      4161255391,3922919429,949333985,2715962298,1323567403], dtype=np.uint32)

    def test_published_mt19937_seed_vector(self):
        np.testing.assert_array_equal(NativeRandom(5489).words(10),self.WORDS)
        np.testing.assert_array_equal(NativeRandom(5489+2**32).words(10),self.WORDS)

    def test_uniform_uses_one_word_and_column_order(self):
        report=analyze('3101',{'columns':[],'rows':[]},{'count':5,'variables':2,'seed':5489,'low':0,'high':1})
        np.testing.assert_array_equal(report['dataset']['rows'],(self.WORDS.astype(float)/2**32).reshape(2,5).T)

    def test_integer_multiply_high_and_exclusive_upper_bound(self):
        expected=np.array([int(int(word)*10//2**32)-5 for word in self.WORDS])
        np.testing.assert_array_equal(NativeRandom(5489).integers(-5,5,10),expected)
        report=analyze('3100',{'columns':[],'rows':[]},{'count':100,'seed':5489,'low':9,'high':10})
        self.assertEqual(report['dataset']['rows'],[[9]]*100)

    def test_polar_normal_discards_second_value(self):
        # The first reference MT pair falls inside the unit circle; the next
        # two are rejected. The fourth pair supplies the second normal.
        expected=[]
        for j in range(0,len(self.WORDS),2):
            u=float(self.WORDS[j])/2**31-1;v=float(self.WORDS[j+1])/2**31-1
            radius=u*u+v*v
            if radius<1:expected.append(u*math.sqrt(-2*math.log(radius)/radius))
        np.testing.assert_allclose(NativeRandom(5489).normal(len(expected)),expected,rtol=2e-15)

    def test_rejection_stream_is_independent_of_call_sizes(self):
        whole=NativeRandom(927).normal(1000)
        split=NativeRandom(927)
        np.testing.assert_allclose(whole,np.r_[split.normal(1),split.normal(23),split.normal(976)],rtol=0,atol=0)

    def test_chi_square_and_f_follow_observation_draw_order(self):
        normals=NativeRandom(5489).normal(12).reshape(3,4)
        np.testing.assert_allclose(NativeRandom(5489).sum_squares(3,4),np.sum(normals**2,axis=1))
        np.testing.assert_allclose(NativeRandom(5489).sum_squares(3,1,3),normals[:,0]**2/np.sum(normals[:,1:]**2,axis=1))

    def test_f_native_quirk_is_explicit_and_conventional_scaling_available(self):
        options={'count':20,'seed':42,'df':5,'df2':4}
        native=analyze('3104',{'columns':[],'rows':[]},options)
        conventional=analyze('3104',{'columns':[],'rows':[]},{**options,'help.random.f_scaling':'conventional'})
        np.testing.assert_allclose(conventional['dataset']['rows'],np.asarray(native['dataset']['rows'])*4/5)
        self.assertIn('unscaled chi-square ratio',' '.join(native['notes']))

    def test_native_validation_and_fractional_df_truncation(self):
        empty={'columns':[],'rows':[]}
        for aid,options in [('3101',{'low':0,'high':1e-7}),('3102',{'sd':0}),('3103',{'df':.9}),('3100',{'low':-2**31,'high':2**31-1})]:
            with self.assertRaises(ValueError):analyze(aid,empty,options)
        a=analyze('3103',empty,{'seed':12,'df':3.9})
        b=analyze('3103',empty,{'seed':12,'df':3})
        self.assertEqual(a['dataset'],b['dataset'])


if __name__=='__main__':unittest.main()
