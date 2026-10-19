"""Independent density references, sampling properties and analysis behavior."""
import json
import unittest
from unittest.mock import patch

import numpy as np
from scipy import stats
from statsmodels.distributions.copula.api import (GaussianCopula, StudentTCopula,
    ClaytonCopula, FrankCopula, GumbelCopula)

from backend.analyses import copulas as cp
from backend.common import sanitize_json


class CopulaTests(unittest.TestCase):
    def data(self, n=120, rho=.6, seed=72):
        return dict(columns=['X', 'Y'], rows=cp.simulate('gaussian', [rho], n, seed).tolist())

    def test_rank_transform_average_ties_and_open_bounds(self):
        u = cp.pseudo_observations([[1, 5], [2, 3], [2, 4], [9, 8]])
        np.testing.assert_allclose(u, [[.2,.6],[.5,.2],[.5,.4],[.8,.8]])

    def test_density_matches_independent_statsmodels_reference(self):
        u = np.array([[.001,.99],[.1,.2],[.25,.75],[.63,.41],[.95,.98]])
        cases = [('gaussian', [.7], GaussianCopula(.7)),
                 ('gaussian', [-.4], GaussianCopula(-.4)),
                 ('student', [.5,4], StudentTCopula(.5,df=4)),
                 ('clayton', [2.3], ClaytonCopula(2.3)),
                 ('gumbel', [1.7], GumbelCopula(1.7)),
                 ('frank', [8.], FrankCopula(8)),
                 ('frank', [-8.], FrankCopula(-8))]
        for family, p, reference in cases:
            with self.subTest(family=family, p=p):
                np.testing.assert_allclose(cp.log_density(family,u,p),(np.log(reference.pdf(u)) if family == 'frank' and p[0] < 0 else reference.logpdf(u)),rtol=2e-10,atol=2e-10)

    def test_densities_at_independence_limits(self):
        u = np.array([[.02,.97],[.2,.3],[.9,.8]])
        for family, p in [('independence', []),('gaussian',[0]),('clayton',[0]),('frank',[0]),('gumbel',[1])]:
            np.testing.assert_allclose(cp.log_density(family,u,p),0,atol=1e-14)

    def test_extreme_supported_parameters_have_finite_densities(self):
        u = np.array([[1e-9,1-1e-9],[1-1e-9,1-1e-9],[1e-9,1e-9]])
        for family, p in [('gaussian',[.995]),('student',[-.995,2.01]),('clayton',[30]),('gumbel',[25]),('frank',[35]),('frank',[-35])]:
            self.assertTrue(np.isfinite(cp.log_density(family,u,p)).all(),family)

    def test_invalid_density_bounds_are_rejected(self):
        for u in [[[0,.5]],[[.5,1]],[[np.nan,.5]],[[.5,.5,.5]]]:
            with self.assertRaises(ValueError):
                cp.log_density('gaussian',u,[.5])
        with self.assertRaises(ValueError):
            cp.log_density('student',[[.5,.5]],[1,4])

    def test_student_tail_formula_and_archimedean_limits(self):
        lower, upper = cp.tail_dependence('student',[.5,4])
        self.assertAlmostEqual(lower,.25316999510032273,places=12)
        self.assertEqual(lower,upper)
        self.assertEqual(cp.tail_dependence('clayton',[2]),(2**(-.5),0))
        self.assertEqual(cp.tail_dependence('gumbel',[2]),(0,2-2**.5))
        self.assertEqual(cp.tail_dependence('gaussian',[.8]),(0,0))

    def test_seeded_simulation_uniform_margins_and_target_dependence(self):
        cases = [('gaussian',[.65],2/np.pi*np.arcsin(.65)),
                 ('student',[.65,4],2/np.pi*np.arcsin(.65)),
                 ('clayton',[2],.5),('gumbel',[2],.5),
                 ('frank',[6],FrankCopula(6).tau()),('frank',[-6],FrankCopula(-6).tau()),
                 ('independence',[],0)]
        for family,p,tau in cases:
            with self.subTest(family=family,p=p):
                s=cp.simulate(family,p,6000,9)
                np.testing.assert_array_equal(s,cp.simulate(family,p,6000,9))
                self.assertTrue(((s>0)&(s<1)).all())
                np.testing.assert_allclose(s.mean(axis=0),.5,atol=.015)
                self.assertAlmostEqual(stats.kendalltau(s[:,0],s[:,1]).statistic,tau,delta=.03)
                for j in range(2):
                    self.assertLess(stats.kstest(s[:,j],'uniform').statistic,.03)

    def test_gaussian_fit_recovers_parameter_and_improves_independence(self):
        model=cp.fit('gaussian',cp.pseudo_observations(cp.simulate('gaussian',[.7],1500,44)))
        self.assertAlmostEqual(model['parameters'][0],.7,delta=.04)
        self.assertGreater(model['logLikelihood'],100)
        self.assertLess(model['bic'],0)
        self.assertFalse(model['boundary'])

    def test_negative_frank_fit(self):
        model=cp.fit('frank',cp.pseudo_observations(cp.simulate('frank',[-5],1000,72)))
        self.assertAlmostEqual(model['parameters'][0],-5,delta=.7)

    def test_student_fit_recovers_heavy_tail(self):
        model=cp.fit('student',cp.pseudo_observations(cp.simulate('student',[.6,4],1800,44)))
        self.assertAlmostEqual(model['parameters'][0],.6,delta=.06)
        self.assertGreater(model['parameters'][1],2.1)
        self.assertLess(model['parameters'][1],7.)
        self.assertLess(model['bic'],cp.fit('gaussian',cp.pseudo_observations(cp.simulate('student',[.6,4],1800,44)))['bic'])

    def test_complete_analysis_reports_diagnostics_and_simulated_dataset(self):
        result=cp.analyze(cp.COMMAND,self.data(),dict(x='X',y='Y',samples=30))
        self.assertEqual(len(result['copula']['models']),6)
        self.assertEqual(set(result['copula']['models']),set(cp.FAMILIES))
        self.assertEqual(result['copula']['selectedFamily'],min(result['copula']['models'].values(),key=lambda model:model['bic'])['family'])
        self.assertEqual(len(result['tables']),5)
        self.assertEqual(len(result['dataset']['rows']),30)
        self.assertEqual(len(result['charts']),2)
        self.assertEqual(result['tables'][3]['rows'][0][1:3],[96,24])
        json.dumps(sanitize_json(result),allow_nan=False)
        for row in result['dataset']['rows']:
            self.assertTrue(0<row[0]<1 and 0<row[1]<1)

    def test_no_simulation_and_minimum_size_diagnostics(self):
        r=cp.analyze(cp.COMMAND,self.data(25),dict(x='X',y='Y',family='gaussian',samples=0))
        self.assertNotIn('dataset',r)
        self.assertEqual(len(r['tables']),3)
        self.assertTrue(any('40 complete' in w for w in r['warnings']))

    def test_monotone_marginal_invariance(self):
        d=self.data(60)
        transformed=dict(d,rows=[[np.exp(x),100+y**3] for x,y in d['rows']])
        opts=dict(x='X',y='Y',family='gaussian',diagnostics=False,samples=0)
        a=cp.analyze(cp.COMMAND,d,opts)
        b=cp.analyze(cp.COMMAND,transformed,opts)
        self.assertEqual(a['copula']['models'],b['copula']['models'])

    def test_pairwise_missing_and_ties_are_explicit(self):
        d=self.data(60)
        d['rows'] += [[None,1],['bad',2],d['rows'][1]]
        r=cp.analyze(cp.COMMAND,d,dict(x='X',y='Y',family='gaussian',diagnostics=False,samples=0))
        self.assertEqual(r['copula']['observations'],61)
        self.assertTrue(any('Excluded 2 rows' in w for w in r['warnings']))
        self.assertTrue(any('Ties use average ranks' in w for w in r['warnings']))

    def test_validation_rejects_invalid_options_and_singular_data(self):
        for change in [dict(samples=-1),dict(samples=1.5),dict(samples=10001),dict(seed=True),dict(seed=-1),dict(diagnostics='yes'),dict(family='unknown'),dict(tail_probability=0),dict(x='Y')]:
            with self.subTest(change=change),self.assertRaises(ValueError):
                cp.analyze(cp.COMMAND,self.data(),dict(x='X',y='Y',**change)) if 'x' not in change else cp.analyze(cp.COMMAND,self.data(),dict(y='Y',**change))
        for d in [self.data(19),dict(columns=['X','Y'],rows=[[1,i] for i in range(30)]),dict(columns=['X','Y'],rows=[[i,i] for i in range(30)])]:
            with self.assertRaises(ValueError):
                cp.analyze(cp.COMMAND,d,dict(x='X',y='Y'))

    def test_failed_student_optimizer_is_not_reported_as_success(self):
        with patch.object(cp.optimize,'minimize',return_value=type('Failed',(),dict(success=False))()):
            with self.assertRaisesRegex(ValueError,'did not converge'):
                cp.fit('student',cp.pseudo_observations(np.asarray(self.data()['rows'])))

    def test_regime_change_is_visible_in_holdout_and_window_diagnostics(self):
        d = self.data(200, -.85)
        d['rows'] += self.data(200, .85, 93)['rows']
        r = cp.analyze(cp.COMMAND, d, dict(x='X', y='Y', family='gaussian', samples=0))
        first, second = r['tables'][4]['rows']
        self.assertLess(first[2], -.5)
        self.assertGreater(second[2], .5)
        self.assertTrue(any('stationary copula' in w for w in r['warnings']))

    def test_empirical_margin_simulation_preserves_observed_range(self):
        d = self.data(100)
        d['rows'] = [[100+x*20, -1000+y*10] for x,y in d['rows']]
        r = cp.analyze(cp.COMMAND,d,dict(x='X', y='Y', family='gaussian', diagnostics=False, samples=100))
        samples = np.asarray(r['dataset']['rows'])[:,2:]
        original = np.asarray(d['rows'])
        self.assertTrue((samples.min(axis=0) >= original.min(axis=0)).all())
        self.assertTrue((samples.max(axis=0) <= original.max(axis=0)).all())

    def test_catalog_is_independent_and_omits_internal_audit_metadata(self):
        entry=cp.catalog()[0]
        self.assertEqual(entry['id'],'copula.bivariate')
        self.assertEqual(entry['coverage'],'extension')
        entry['fields'][0]['key']='changed'
        self.assertEqual(cp.catalog()[0]['fields'][0]['key'],'x')


if __name__=='__main__':
    unittest.main()
