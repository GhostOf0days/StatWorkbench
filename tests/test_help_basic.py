"""Documented report requirements tested against refits and numeric identities."""
import itertools
import math
import unittest
import numpy as np
from scipy import stats
import statsmodels.api as sm
from backend.analyses.basic import analyze, catalog
from backend.analyses.basic_help_reports import native_lilliefors, rosenbaum, native_run_counts, runs_exact_distribution
from tests.test_basic import dataset, table


class HelpBasicTests(unittest.TestCase):
    def regression_data(self):
        x=np.arange(1.,11.)
        z=np.array([2,4,1,5,3,7,6,3,9,8.])
        y=3+2*x-.7*z+np.array([.2,-.4,.5,1.,-1.,.7,-.8,.6,.3,-.2])
        return x,z,y

    def test_ols_press_matches_independent_leave_one_out_refits(self):
        x,z,y=self.regression_data();design=np.column_stack([np.ones(len(x)),x,z])
        result=analyze('1301',dataset(['x','z','y'],zip(x,z,y)),{'response':'y','predictors':['x','z'],'sta.reg.lin.ao.norm-qq-hist':False,'sta.reg.lin.ao.res.ht-tests':False})
        summary=dict(table(result,'Model summary')['rows'])
        deleted=[]
        for i in range(len(y)):
            keep=np.arange(len(y))!=i
            beta=np.linalg.lstsq(design[keep],y[keep],rcond=None)[0]
            deleted.append(y[i]-design[i]@beta)
        self.assertAlmostEqual(summary['PRESS'],np.dot(deleted,deleted),places=10)
        self.assertAlmostEqual(summary['PRESS RMSE'],np.sqrt(np.mean(np.square(deleted))),places=10)
        self.assertAlmostEqual(summary['Predicted R²'],1-np.dot(deleted,deleted)/np.sum((y-y.mean())**2),places=10)
        details=table(result,'Fitted values and residuals');j=details['columns'].index('PRESS residual')
        np.testing.assert_allclose([row[j] for row in details['rows']],deleted,atol=1e-12)
        a=table(result,'Regression ANOVA')['rows'];self.assertAlmostEqual(a[0][1]+a[1][1],a[2][1],places=10)

    def test_wls_leverage_and_press_use_whitened_design(self):
        x,z,y=self.regression_data();weights=np.arange(1.,11.)**2;design=np.column_stack([np.ones(len(x)),x,z])
        result=analyze('1302',dataset(['x','z','y','w'],zip(x,z,y,weights)),{'response':'y','predictors':['x','z'],'weights':'w'})
        deleted=[]
        for i in range(len(y)):
            keep=np.arange(len(y))!=i;root=np.sqrt(weights[keep])
            beta=np.linalg.lstsq(design[keep]*root[:,None],y[keep]*root,rcond=None)[0]
            deleted.append(y[i]-design[i]@beta)
        self.assertAlmostEqual(dict(table(result,'Model summary')['rows'])['PRESS'],np.dot(weights,np.square(deleted)),places=9)
        diag=table(result,'Fitted values and residuals');h=diag['columns'].index('Leverage')
        expected=weights*np.einsum('ij,jk,ik->i',design,np.linalg.inv(design.T@(weights[:,None]*design)),design)
        np.testing.assert_allclose([r[h] for r in diag['rows']],expected,atol=1e-12)

    def test_influence_vif_tolerance_match_independent_reference(self):
        x,z,y=self.regression_data();fit=sm.OLS(y,np.column_stack([np.ones(len(x)),x,z])).fit()
        result=analyze('1301',dataset(['x','z','y'],zip(x,z,y)),{'response':'y','predictors':['x','z'],'sta.reg.lin.ao.norm-qq-hist':False,'sta.reg.lin.ao.res.ht-tests':False})
        diag=table(result,'Fitted values and residuals');coef=table(result,'Coefficients')
        influence=fit.get_influence()
        for name,expected in [('Cook distance',influence.cooks_distance[0]),('DFFITS',influence.dffits[0]),('Deleted t residual',influence.resid_studentized_external)]:
            j=diag['columns'].index(name);np.testing.assert_allclose([r[j] for r in diag['rows']],expected,rtol=1e-10)
        vif=1/(1-np.corrcoef(x,z)[0,1]**2)
        for row in coef['rows'][1:]:
            self.assertAlmostEqual(row[coef['columns'].index('VIF')],vif)
            self.assertAlmostEqual(row[coef['columns'].index('Tolerance')],1/vif)

    def test_no_intercept_anova_is_uncentered(self):
        x,z,y=self.regression_data()
        r=analyze('1302',dataset(['x','y','w'],zip(x,y,np.ones(len(x)))),{'response':'y','predictors':['x'],'weights':'w','sta.reg.nointercept':True})
        total=table(r,'Regression ANOVA')['rows'][-1]
        self.assertAlmostEqual(total[1],np.dot(y,y));self.assertEqual(total[2],len(y))

    def test_best_subsets_reports_every_nonempty_size(self):
        x,z,y=self.regression_data()
        r=analyze('1307',dataset(['x','z','y'],zip(x,z,y)),{'response':'y','predictors':['x','z'],'glm.showcorrs':True})
        for size in [1,2]:
            self.assertTrue(table(r,f'Best subset with {size} predictors — Regression ANOVA')['rows'])
            self.assertEqual(len(table(r,f'Best subset with {size} predictors — Coefficients')['rows']),size+1)
            self.assertEqual(len(table(r,f'Best subset with {size} predictors — Partial correlations with response')['rows']),size)
            self.assertEqual(len(table(r,f'Best subset with {size} predictors — Partial correlation matrix')['rows']),size+1)
        rows=table(r,'Best model for each size')['rows']
        self.assertAlmostEqual(sum(row[-1] for row in rows),rows[-1][-2])

    def test_stepwise_full_reports_obey_show_steps(self):
        x,z,y=self.regression_data();data=dataset(['x','z','y'],zip(x,z,y))
        for aid in ['1304','1305']:
            r=analyze(aid,data,{'response':'y','predictors':['x','z'],'sta.reg.show_steps':True,'glm.showcorrs':True})
            self.assertTrue(table(r,'Initial model — Regression ANOVA')['rows'])
            for step in table(r,'Selection steps')['rows']:
                self.assertTrue(table(r,f'Step {step[0]} — Coefficients')['rows'])
            hidden=analyze(aid,data,{'response':'y','predictors':['x','z'],'sta.reg.show_steps':False})
            self.assertFalse(any(t['title'].startswith('Initial model') for t in hidden['tables']))

    def test_normality_component_tests_sum_to_omnibus(self):
        x=np.array([1,2,3,4,5,7,8,11,12,15,20,23.])
        r=analyze('1011',dataset(['x'],zip(x)),{'columns':['x']})
        rows={v[1]:v for v in table(r,'Normality tests')['rows']}
        self.assertAlmostEqual(rows['D’Agostino skewness Z'][3],stats.skewtest(x).statistic)
        self.assertAlmostEqual(rows['D’Agostino kurtosis Z'][3],stats.kurtosistest(x).statistic)
        self.assertAlmostEqual(rows['D’Agostino K²'][3],rows['D’Agostino skewness Z'][3]**2+rows['D’Agostino kurtosis Z'][3]**2)
        self.assertTrue(.01<=rows['KS/Stephens (bounded reference)'][4]<=.15)
        self.assertAlmostEqual(table(r,'Normality descriptive statistics')['rows'][0][5],stats.skew(x,bias=True))

    def test_native_lilliefors_large_sample_d_quirk(self):
        x=np.arange(1.,151.);d,p,raw=native_lilliefors(x)
        ks=stats.kstest(x,'norm',args=(x.mean(),x.std(ddof=1)))
        self.assertAlmostEqual(raw,ks.statistic)
        self.assertAlmostEqual(d,raw*1.5**.49)
        self.assertTrue(0<=p<=1)

    def test_summarized_z_matches_raw_without_synthetic_observations(self):
        x=np.array([3.,5.,7.,9.]);options={'mean':4,'variance':16}
        raw=analyze('1004',dataset(['x'],zip(x)),{'column':'x',**options})
        summary=analyze('1004',{'columns':[],'rows':[]},{'help.z.input_mode':'summary','help.z.n':4,'help.z.sample_mean':6,**options})
        a=table(raw,'Mean tests')['rows'][0];b=table(summary,'Mean tests')['rows'][0]
        np.testing.assert_allclose([v for v in a[1:] if v is not None],[v for v in b[1:] if v is not None])
        tails=table(summary,'Test tails and critical values')['rows'][0]
        self.assertAlmostEqual(tails[2]+tails[3],1);self.assertAlmostEqual(tails[4],2*stats.norm.sf(1))
        with self.assertRaises(ValueError):analyze('1004',{'columns':[],'rows':[]},{'help.z.input_mode':'summary','help.z.n':2.5,'help.z.sample_mean':6,'variance':16})

    def test_mean_reports_pooled_variance_and_difference(self):
        r=analyze('10052',{},dict(n1=10,n2=20,mean1=5,mean2=8,sd1=2,sd2=3))
        self.assertAlmostEqual(dict(table(r,'Pooled variance')['rows'])['Pooled variance'],207/28)
        r=analyze('1003',dataset(['x'],[[2],[4],[6]]),{'columns':['x'],'mean':1})
        self.assertEqual(table(r,'Mean tests')['rows'][0][-1],3)

    def test_f_test_uses_documented_listwise_deletion(self):
        r=analyze('1008',dataset(['x','y'],[[1,2],[3,4],[5,8],[100,None],[None,400]]),{'x':'x','y':'y'})
        row=table(r,'Variance ratio')['rows'][0]
        self.assertEqual(row[:2],[3,3]);self.assertAlmostEqual(row[4],np.var([1,3,5],ddof=1)/np.var([2,4,8],ddof=1))
        tails=table(r,'F-test tails and critical values')['rows'][0];self.assertAlmostEqual(tails[4]+tails[5],1)

    def test_pearson_sort_uses_absolute_coefficient_and_has_matrix(self):
        d=dataset(['x','y','z'],[[1,5,1],[2,4,3],[3,3,2],[4,2,5],[5,1,4]])
        r=analyze('1009',d,{'columns':['x','y','z']})
        first=table(r,'Correlations')['rows'][0];self.assertEqual(first[:2],['x','y']);self.assertAlmostEqual(first[4],-1)
        m=table(r,'Correlation matrix');self.assertAlmostEqual(m['rows'][0][2],-1)

    def test_casewise_covariance_preference(self):
        d=dataset(['x','y','z'],[[1,2,3],[3,6,2],[8,9,None],[4,8,1]])
        pair=table(analyze('1010',d,{'columns':['x','y','z']}),'Sample covariance')['rows'][0][2]
        case=table(analyze('1010',d,{'columns':['x','y','z'],'missing':'casewise'}),'Sample covariance')['rows'][0][2]
        self.assertNotEqual(pair,case);self.assertAlmostEqual(case,np.cov([1,3,4],[2,6,8])[0,1])

    def test_rank_correlations_include_pearson_and_inversions(self):
        r=analyze('1404',dataset(['x','y'],[[1,4],[2,1],[3,3],[4,2]]),{'columns':['x','y']})
        rows={r[2]:r for r in table(r,'Correlations')['rows']};self.assertIn('Pearson',rows)
        detail=table(r,'Rank-correlation diagnostics')['rows'][0];self.assertEqual(detail[2:5],[2,4,0])
        self.assertAlmostEqual(rows['Goodman–Kruskal gamma'][4],-1/3)

    def test_rank_descending_and_listwise_alignment(self):
        r=analyze('1403',dataset(['x','y'],[[4,1],[1,None],[9,2],[4,3]]),{'columns':['x','y']})
        rows=table(r,'x')['rows'];self.assertEqual([v[0] for v in rows],[1,3,4])
        self.assertEqual([v[2] for v in rows],[1.5,3,1.5]);self.assertEqual([v[4] for v in rows],[2.5,1,2.5])

    def test_native_rank_percentile_endpoints_and_all_tie_methods(self):
        d=dataset(['x'],[[4],[1],[4],[9]])
        expectations={'average':([2.5,1,2.5,4],[2.5,4,2.5,1]),
            'max':([3,1,3,4],[3,4,3,1]),'min':([2,1,2,4],[2,4,2,1]),
            'ordinal':([2,1,3,4],[3,4,2,1])}
        for ties,(rank,descending) in expectations.items():
            with self.subTest(ties=ties):
                r=analyze('1403',d,{'columns':['x'],'ties':ties});report=table(r,'x')
                self.assertEqual([v[2] for v in report['rows']],rank)
                self.assertEqual([v[4] for v in report['rows']],descending)
                np.testing.assert_allclose([v[3] for v in report['rows']],(np.array(rank)-1)/3)
                self.assertEqual(report['columnFormats']['3'],'0.00%')
        with self.assertRaisesRegex(ValueError,'At least two'):
            analyze('1403',dataset(['x'],[[1]]),{'columns':['x']})

    def test_native_fechner_keeps_zero_signs_and_constant_variables(self):
        # Exact native sign equality counts both zero signs as matching and
        # a zero/nonzero pair as discordant; dropping zeros changes the answer.
        data=dataset(['x','y'],[[0,0],[1,2],[2,1],[3,3],[4,4]])
        r=analyze('1405',data,{'columns':['x','y']})
        self.assertEqual(r['tables'][0]['rows'][0][3],5)
        self.assertAlmostEqual(r['tables'][0]['rows'][0][4],.2)
        r=analyze('1405',dataset(['x','y'],[[5,1],[5,2],[5,3]]),{'columns':['x','y']})
        self.assertAlmostEqual(r['tables'][0]['rows'][0][4],-1/3)
        r=analyze('1405',dataset(['x','y'],[[5,9]]),{'columns':['x','y']})
        self.assertEqual(r['tables'][0]['rows'][0][3:5],[1,1.])

    def test_runs_exact_distribution_matches_exhaustive_label_permutations(self):
        for n1,n2 in itertools.product(range(2,6),repeat=2):
            counts={}
            for positions in itertools.combinations(range(n1+n2),n1):
                sequence=np.zeros(n1+n2,dtype=int);sequence[list(positions)]=1
                runs=1+int(np.sum(sequence[1:]!=sequence[:-1]));counts[runs]=counts.get(runs,0)+1
            runs,prob=runs_exact_distribution(n1,n2)
            np.testing.assert_allclose(prob,[counts.get(int(r),0)/math.comb(n1+n2,n1) for r in runs],atol=2e-15)

    def test_native_tied_runs_ordering_and_pvalue_quirks(self):
        x=[1,2,2,4];y=[2,2,3,5]
        self.assertEqual(native_run_counts(x,y),([4,6],1,4))
        # The greedy 'maximum' is not a global maximum for this block.
        self.assertEqual(native_run_counts([1,1,1],[1,1]),([2,4],1,5))
        r=analyze('1406',dataset(['x','y'],zip(x,y)),{'x':'x','y':'y'})
        report=table(r,'Wald–Wolfowitz runs test')['rows']
        self.assertEqual([v[1] for v in report],[4,6]);self.assertEqual(report[1][6],1.)
        self.assertAlmostEqual(report[0][-1],52/70);self.assertAlmostEqual(report[1][-1],52/70)
        self.assertAlmostEqual(report[0][7]-report[0][4],.5/math.sqrt(12/7))

    def test_native_mann_whitney_zero_z_has_blank_corrected_approximation(self):
        r=analyze('1406',dataset(['x','y'],[[1,1],[2,2],[3,3]]),{'x':'x','y':'y'})
        row=table(r,'Mann–Whitney inference')['rows'][1]
        self.assertEqual(row[1:],[None,None,None])

    def test_mann_whitney_native_rows_do_not_switch_at_extension_threshold(self):
        for size in (3,8,9,20):
            r=analyze('1406',dataset(['x','y'],zip(range(size),range(size,2*size))),{'x':'x','y':'y'})
            rows=table(r,'Mann–Whitney inference')['rows']
            self.assertEqual(len(rows),4)
            sd=math.sqrt(size*size*(2*size+1)/12)
            z=-size*size/2/sd;corrected=z+.5/sd
            for row,statistic,tail in zip(rows,[z,corrected,z,corrected],
                    [stats.norm.sf(abs(z)),stats.norm.sf(abs(corrected)),stats.t.sf(abs(z),2*size-1),stats.t.sf(abs(corrected),2*size-1)]):
                np.testing.assert_allclose(row[1:],[statistic,tail,2*tail],rtol=1e-13)
            extension=table(r,'Additional Mann–Whitney inference (StatWorkbench extension)')['rows'][0]
            self.assertEqual(extension[0],'exact' if size<=8 else 'asymptotic')
            self.assertIsNone(r['tables'][0]['rows'][0][2])

    def test_mann_whitney_rank_summary_ties_and_direction(self):
        x=[1,2,2,7];y=[2,4,9,10]
        r=analyze('1406',dataset(['x','y'],zip(x,y)),{'x':'x','y':'y','alternative':'greater'})
        summaries=table(r,'Mann–Whitney sample ranks')['rows'];ranks=stats.rankdata(x+y)
        self.assertEqual(summaries[0][2],16+10-sum(ranks[:4]))
        self.assertEqual(summaries[0][3],sum(ranks[:4]))
        self.assertEqual(summaries[0][-1],sum(ranks[:4])/4)
        self.assertEqual(dict(table(r,'Mann–Whitney statistics')['rows'])['Tied value sets'],1)
        extension=table(r,'Additional Mann–Whitney inference (StatWorkbench extension)')['rows'][0]
        self.assertEqual(extension[:2],['asymptotic','greater'])
        self.assertAlmostEqual(extension[-1],stats.mannwhitneyu(x,y,alternative='greater',method='asymptotic').pvalue)
        mirrored=analyze('1406',dataset(['x','y'],zip(y,x)),{'x':'x','y':'y','alternative':'less'})
        self.assertEqual(table(r,'Mann–Whitney inference'),table(mirrored,'Mann–Whitney inference'))

    def test_mann_whitney_rejects_single_observation_as_native_report_does(self):
        with self.assertRaises(ValueError):
            analyze('1406',dataset(['x','y'],[[1,2],[None,3]]),{'x':'x','y':'y'})

    def test_independent_tests_min_u_ks_and_rosenbaum(self):
        r=analyze('1406',dataset(['x','y'],zip(range(11,22),range(11))),{'x':'x','y':'y'})
        rows={r[0]:r for r in r['tables'][0]['rows']};self.assertEqual(rows['Mann–Whitney U'][1],0)
        self.assertEqual(rows['Kolmogorov–Smirnov D'][1],1)
        self.assertEqual(table(r,'Rosenbaum Q criterion')['rows'][0][2:4],[22,6])
        self.assertEqual(rosenbaum(np.arange(11),np.arange(11)+11,.99),(22,9))
        self.assertIsNone(rosenbaum(np.arange(10),np.arange(10)+10,.95)[1])

    def test_signed_rank_z_corrects_absolute_ties(self):
        r=analyze('1408',dataset(['x','y'],[[2,1],[1,3],[4,2],[4,4],[5,2]]),{'x':'x','y':'y'})
        row=table(r,'Paired tests')['rows'][-1]
        self.assertAlmostEqual(row[1],-2.5/math.sqrt(177/24))

    def test_cochran_proportions_complete_cases(self):
        d=dataset(['a','b','c'],[[1,1,0],[0,1,0],[1,0,1],[0,0,1],[1,None,0]])
        r=analyze('1410',d,{'columns':['a','b','c']})
        p=table(r,'Proportions statistics')['rows'];self.assertEqual(p,[['a',2.,.5,.5],['b',2.,.5,.5],['c',2.,.5,.5]])
        self.assertEqual(table(r,'Cochran Q')['rows'][0][0],4)

    def test_stacked_friedman_matches_wide_by_order(self):
        x=np.array([[1,3,2],[3,2,1],[4,2,3],[1,4,2.]])
        wide=analyze('1409',dataset(['a','b','c'],x),{'columns':['a','b','c']})
        long=dataset(['value','group'],[(x[i,j],str(j)) for j in range(3) for i in range(4)])
        stacked=analyze('14092',long,{'column':'value','group':'group'})
        np.testing.assert_allclose(wide['tables'][0]['rows'][0],stacked['tables'][0]['rows'][0])

    def test_native_friedman_accepts_two_groups_and_two_subjects(self):
        r=analyze('1409',dataset(['a','b'],[[1,4],[2,3],[5,2]]),{'columns':['a','b']})
        row=table(r,'Friedman and concordance')['rows'][0]
        self.assertEqual(row[:2],[3,2]);self.assertAlmostEqual(row[2],1/3)
        r=analyze('1409',dataset(['a','b','c'],[[1,2,3],[2,1,3]]),{'columns':['a','b','c']})
        self.assertAlmostEqual(table(r,'Friedman and concordance')['rows'][0][2],3.)

    def test_stacked_friedman_ignores_empty_group_and_truncates_tail(self):
        stacked=dataset(['v','g'],[[1,'a'],[4,'b'],[2,'a'],[3,'b'],[5,'a'],[2,'b'],[9,'a'],[100,''],[100,'<null>']])
        r=analyze('14092',stacked,{'column':'v','group':'g'})
        row=table(r,'Friedman and concordance')['rows'][0]
        self.assertEqual(row[:2],[3,2]);self.assertAlmostEqual(row[2],1/3)

    def test_stacked_friedman_deletes_missing_rows_before_ordinal_pairing(self):
        values={'A':[1,None,3,8],'B':[2,4,5,7],'C':[3,1,6,2]}
        stacked=dataset(['v','g','subject'],[(value,group,i) for group,column in values.items() for i,value in enumerate(column)])
        native=analyze('14092',stacked,{'column':'v','group':'g'})
        row=table(native,'Friedman and concordance')['rows'][0]
        expected=stats.friedmanchisquare([1,3,8],[2,4,5],[3,1,6])
        self.assertEqual(row[:2],[3,3])
        self.assertAlmostEqual(row[2],expected.statistic)
        self.assertAlmostEqual(row[4],expected.pvalue)
        explicit=analyze('14092',stacked,{'column':'v','group':'g','subject':'subject'})
        explicit_row=table(explicit,'Friedman and concordance')['rows'][0]
        aligned=stats.friedmanchisquare([1,3,8],[2,5,7],[3,6,2])
        self.assertAlmostEqual(explicit_row[2],aligned.statistic)
        self.assertNotAlmostEqual(row[2],explicit_row[2])

    def test_repeated_anova_ss_decomposition_and_descriptives(self):
        x=np.array([[1,2,4],[2,5,5],[4,4,7],[3,6,9.]])
        r=analyze('1108',dataset(['a','b','c'],x),{'columns':['a','b','c']})
        rows=table(r,'ANOVA decomposition')['rows'];self.assertAlmostEqual(sum(row[1] for row in rows[:3]),np.sum((x-x.mean())**2))
        self.assertEqual(sum(row[2] for row in rows[:3]),x.size-1)
        np.testing.assert_allclose([row[2] for row in table(r,'Treatment descriptive statistics')['rows']],x.mean(axis=0))

    def test_categorical_logit_equals_explicit_indicator_design(self):
        rows=[]
        for group,successes in [('A',2),('B',4),('C',7)]:
            rows += [[int(i<successes),group] for i in range(10)]
        r=analyze('1306',dataset(['y','g'],rows),{'response':'y','predictors':['g'],'help.logit.categorical':['g']})
        beta={row[0]:row[1] for row in table(r,'Logit coefficients')['rows']}
        reference=math.log(.7/.3)
        self.assertAlmostEqual(beta['Intercept'],reference,places=10)
        self.assertAlmostEqual(beta['g[A]'],math.log(.2/.8)-reference,places=10)
        self.assertAlmostEqual(beta['g[B]'],math.log(.4/.6)-reference,places=10)

    def test_crosstab_contributions_marginals_and_phi_square(self):
        opt={f'sta.nps.2x2.param.{i}':v for i,v in enumerate([10,20,30,40])}
        r=analyze('1401',{'columns':[],'rows':[]},opt)
        assoc=dict(table(r,'Measures of association')['rows'])
        self.assertAlmostEqual(assoc['Phi-square'],assoc['Phi']**2)
        self.assertEqual(table(r,'Crosstab marginal totals')['rows'][-1][-1],100)
        contribution=sum(sum(row[1:]) for row in table(r,'Chi-square contributions')['rows'])
        self.assertAlmostEqual(contribution,table(r,'Chi-square tests')['rows'][0][1])

    def test_published_frequency_grades_example(self):
        # The official Frequency Tables help and shipped sample have 22 grades;
        # the article reports 22.7% in (40,60] and 45% at or below 60.
        grades=[21,95,43,49,30,46,90,46,77,65,85,35,80,53,79,93,93,65,17,19,70,70]
        r=analyze('1013',dataset(['Grade'],zip(grades)),{'columns':['Grade'],'bins':5,'closed':'right','sta.bst.freq.minval2':'0','sta.bst.freq.width2':'20'})
        row=r['tables'][0]['rows'][2]
        self.assertEqual(row[:4],[40.,60.,5.,10.]);self.assertAlmostEqual(row[4],5/22);self.assertAlmostEqual(row[5],10/22)

    def test_discrete_numeric_sort_and_cumulative_value_semantics(self):
        data=dataset(['x'],[[1],[10],[2],[2],[2]])
        ascending=analyze('1012',data,{'columns':['x']})['tables'][0]['rows']
        self.assertEqual([r[0] for r in ascending],['1','2','10'])
        descending=analyze('1012',data,{'columns':['x'],'order':'count_desc'})['tables'][0]['rows']
        self.assertEqual(descending[0][:3],['2',3.,4.])

    def test_continuous_automatic_neat_width_and_histogram_sturges(self):
        values=np.arange(1.,30.)*3.1
        r=analyze('1013',dataset(['x'],zip(values)),{'columns':['x'],'sta.bst.ds.hist.bins0':False})
        rows=r['tables'][0]['rows'];width=rows[0][1]-rows[0][0]
        self.assertIn(round(width/10**math.floor(math.log10(width)),10),(1,2,5))
        self.assertEqual(sum(r[2] for r in rows),len(values));self.assertLessEqual(rows[0][0],min(values));self.assertGreaterEqual(rows[-1][1],max(values))

    def test_repeated_box_variance_reference(self):
        # Reference values for repeated-measures inputs.
        values=[[1,2,4],[2,5,5],[4,4,7],[3,6,9],[5,6,8],[7,7,10],[6,8,11],[9,8,14]]
        r=analyze('1108',dataset(['a','b','c'],values),{'columns':['a','b','c']})
        actual=dict(table(r,'Box’s M Test For Homogeneity')['rows'])
        for name,expected in [('Sample covariance determinant',8.221938775510209),('Assumed covariance determinant',362.9092816277773),('M',87.10897750711219),('Chi-square',68.44276804130243),('df',4),('p-value',4.8405723873656825e-14)]:
            self.assertAlmostEqual(actual[name],expected,places=11)
        assumed=table(r,'Assumed population variance-covariance matrix')['rows']
        self.assertAlmostEqual(assumed[0][1],7.303571428571428);self.assertAlmostEqual(assumed[0][2],1.1674107142857142)
        self.assertAlmostEqual(table(r,'Repeated measures ANOVA')['rows'][0][4],29.508287292817627)

    def test_f_ratio_help_control_changes_null_test_not_confidence_interval(self):
        d=dataset(['x','y'],[[1,2],[2,5],[4,6],[5,8]])
        a=analyze('1008',d,{'x':'x','y':'y'})['tables'][0]['rows'][0]
        c=analyze('1008',d,{'x':'x','y':'y','help.f.ratio':2})['tables'][0]['rows'][0]
        self.assertAlmostEqual(c[4],a[4]/2);self.assertEqual(a[8:],c[8:])


if __name__=='__main__':unittest.main()
