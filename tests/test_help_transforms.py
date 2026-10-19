"""Direct transform definitions and the zero-mean invariant."""
import unittest
import numpy as np
from backend.analyses.advanced import analyze
from tests.test_advanced import dataset


class HelpTransformTests(unittest.TestCase):
    def test_complex_fourier_coefficients_and_inverse_normalization(self):
        z=np.array([1+2j,3-1j,-2+4j,5+0j,2-3j])
        data=dataset(['Re','Im'],np.column_stack([z.real,z.imag]).tolist())
        forward=analyze('1523',data,{'real':'Re','imaginary':'Im'})
        actual=np.array(forward['dataset']['rows'])
        expected=np.array([sum(z[n]*np.exp(-2j*np.pi*k*n/len(z)) for n in range(len(z))) for k in range(len(z))])
        np.testing.assert_allclose(actual[:,0]+1j*actual[:,1],expected,atol=1e-12)
        inverse=analyze('1524',data,{'real':'Re','imaginary':'Im'})
        actual=np.array(inverse['dataset']['rows'])
        expected=np.array([sum(z[k]*np.exp(2j*np.pi*k*n/len(z)) for k in range(len(z)))/len(z) for n in range(len(z))])
        np.testing.assert_allclose(actual[:,0]+1j*actual[:,1],expected,atol=1e-12)

    def test_remove_mean_preserves_differences_and_centers_series(self):
        values=np.array([-3.,2.,7.,14.])
        result=analyze('1520',dataset(['X'],[[v] for v in values]),{'column':'X'})
        output=np.array(result['dataset']['rows'])[:,-1]
        np.testing.assert_allclose(output,values-values.mean())
        self.assertAlmostEqual(output.sum(),0.)

