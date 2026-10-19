"""Exact search checked against independently fitted exhaustive models."""
import itertools
import unittest
from unittest.mock import patch
import numpy as np
from scipy.linalg import hadamard
import statsmodels.api as sm
from backend.analyses.best_subsets import best_subsets
from backend.analyses.basic import analyze
from tests.test_basic import dataset,table


def residual_ss(x,y,indices):
    design=np.column_stack([np.ones(len(y)),x[:,indices]])
    residual=y-design@np.linalg.lstsq(design,y,rcond=None)[0]
    return float(residual@residual)


class BestSubsetsTests(unittest.TestCase):
    def assert_exact(self,x,y,rtol=1e-10):
        winners,info=best_subsets(x,y)
        self.assertTrue(info['complete']);self.assertEqual(info['retained_models'],x.shape[1]+1)
        for size,winning in enumerate(winners):
            oracle=min((residual_ss(x,y,list(c)),c) for c in itertools.combinations(range(x.shape[1]),size))
            actual=residual_ss(x,y,list(winning))
            self.assertLessEqual(actual,oracle[0]+rtol*max(1,oracle[0]),(size,winning,oracle))
        return winners,info

    def test_correlated_designs_match_exhaustive_refits(self):
        for seed in range(8):
            with self.subTest(seed=seed):
                rng=np.random.default_rng(seed);x=rng.normal(size=(30,7))
                x[:,2]=.97*x[:,0]+.16*x[:,2];x[:,5]=x[:,1]-.8*x[:,3]+.1*x[:,5]
                y=3+x@rng.normal(size=7)+rng.normal(size=30)
                self.assert_exact(x,y)

    def test_scaled_and_near_collinear_designs_match_refits(self):
        rng=np.random.default_rng(53);x=rng.normal(size=(35,6))
        x[:,1]=x[:,0]+1e-7*x[:,1]
        y=x[:,0]+2*x[:,2]+rng.normal(size=35)
        self.assert_exact(x,y,rtol=2e-8)
        x[:,3]*=1e5;x[:,4]*=1e-4
        self.assert_exact(x,y,rtol=2e-8)

    def test_deterministic_ties_choose_lexicographic_predictors(self):
        h=hadamard(16);x=h[:,1:6].astype(float);y=x.sum(axis=1)+.5*h[:,8]
        winners,_=self.assert_exact(x,y)
        self.assertEqual(winners,[tuple(range(k)) for k in range(6)])

    def test_missing_rows_are_deleted_before_search(self):
        rng=np.random.default_rng(4);x=rng.normal(size=(25,5));y=2*x[:,1]+x[:,3]+rng.normal(size=25)
        rows=np.column_stack([x,y]).tolist();rows[2][0]=None;rows[8][5]=None
        result=analyze('1307',dataset(['a','b','c','d','e','y'],rows),{'response':'y','predictors':list('abcde')})
        keep=np.ones(25,dtype=bool);keep[[2,8]]=False
        for row in table(result,'Best model for each size')['rows']:
            indices=[list('abcde').index(c) for c in row[1].split(', ')] if row[0] else []
            actual=residual_ss(x[keep],y[keep],indices)
            expected=min(residual_ss(x[keep],y[keep],list(c)) for c in itertools.combinations(range(5),row[0]))
            self.assertAlmostEqual(actual,expected,places=10)

    def test_rank_deficient_inputs_still_reject(self):
        x=np.column_stack([np.arange(10.),np.arange(10.)*2]);y=np.arange(10.)**2
        with self.assertRaisesRegex(ValueError,'full-rank'):
            best_subsets(x,y)
        with self.assertRaisesRegex(ValueError,'full-rank'):
            analyze('1307',dataset(['a','b','y'],np.column_stack([x,y])),{'response':'y','predictors':['a','b']})

    def test_thirteen_predictors_only_fit_winning_models(self):
        rng=np.random.default_rng(127);x=rng.normal(size=(45,13));y=3*x[:,0]-2*x[:,4]+x[:,8]+rng.normal(size=45)
        names=[f'x{i}' for i in range(13)];ols=sm.OLS
        with patch('backend.analyses.basic.sm.OLS',wraps=ols) as fit:
            result=analyze('1307',dataset(names+['y'],np.column_stack([x,y])),{'response':'y','predictors':names})
        self.assertEqual(fit.call_count,14)
        self.assertEqual(len(table(result,'Best model for each size')['rows']),14)
        self.assertTrue(result['subsetSearch']['complete'])
        self.assertGreater(result['subsetSearch']['pruned_branches'],0)
        # Independent exhaustive oracle includes all 8192 subsets for this
        # formerly rejected input, not only the seeded forward sequence.
        report=table(result,'Best model for each size')['rows']
        for size,row in enumerate(report):
            expected=min(residual_ss(x,y,list(c)) for c in itertools.combinations(range(13),size))
            actual=(1-row[5])*np.sum((y-y.mean())**2)
            self.assertAlmostEqual(actual,expected,places=9)

    def test_interrupt_does_not_return_a_best_so_far_result(self):
        rng=np.random.default_rng(91);x=rng.normal(size=(20,5));y=rng.normal(size=20)
        with patch('backend.analyses.best_subsets.np.linalg.lstsq',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):best_subsets(x,y)


if __name__=='__main__':unittest.main()
