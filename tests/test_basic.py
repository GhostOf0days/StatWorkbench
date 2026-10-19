"""Numeric, design-validation and schema tests for the original statistical engine."""
import json
import math
import unittest
import numpy as np
from scipy import stats
from backend.analyses.basic import analyze, catalog


def dataset(columns, rows):
    return dict(columns=columns, rows=[list(r) for r in rows], name='Test')


def table(result, name):
    return next(t for t in result['tables'] if t['title']==name)


def descriptive_values(result, label=None):
    """Read values from the explicit report layout, independent of column order."""
    t = result['tables'][0] if label is None else table(result,label)
    if t['layout']['kind']=='combined':
        index=1 if label is None else t['columns'].index(label)
        return {r[0]:r[index] for r in t['rows']}
    values={r[0]:r[1] for r in t['rows'] if r[0]}
    if t['layout']['kind']=='separate_wide':
        for i in range(2,len(t['columns']),2):values.update({r[i]:r[i+1] for r in t['rows'] if r[i]})
        aliases={'N':'Count','Median Absolute Deviation':'MAD (Median Absolute Deviation)','Coefficient of Dispersion':'Coefficient of Dispersion (COD)',"Fisher's Skewness G1":"Skewness (Fisher's)","Fisher's Kurtosis G2":"Kurtosis (Fisher's)"}
        values={aliases.get(k,'Mean LCL' if k.startswith('Mean LCL ') else 'Mean UCL' if k.startswith('Mean UCL ') else k):v for k,v in values.items()}
    return values


class BasicTests(unittest.TestCase):
    def test_descriptive_known_moments_and_quantile_defaults(self):
        d=dataset(['x'],[[1],[2],[3],[4],[5],[None]])
        r=descriptive_values(analyze('1001',d,{'columns':['x']}))
        self.assertEqual(r['Count'],5)
        self.assertEqual(r['Mean'],3)
        self.assertAlmostEqual(r['Variance'],2.5)
        self.assertEqual((r['Percentile 25% (Q1)'],r['Median'],r['Percentile 75% (Q3)']),(2,3,4))
        self.assertAlmostEqual(r["Kurtosis (Fisher's)"],-1.2)
        self.assertLess(r['Mean LCL'],3)
        self.assertAlmostEqual(r['Second Moment'],2)
        self.assertEqual(r['Adjusted Sum Squares'],10)
        self.assertEqual(r['Total Sum Squares'],55)
        self.assertEqual(r['Sum'],15)
        self.assertAlmostEqual(r['Sum Standard Error'],math.sqrt(12.5))
        self.assertIsNone(r['Mode'])  # all five values tie for maximum count
        self.assertAlmostEqual(r['Median Error'],math.sqrt(math.pi/2)*math.sqrt(2.5)/5)
        self.assertEqual(r['MAD (Median Absolute Deviation)'],0)

    def test_grouped_descriptive_accepts_single_group_and_reserved_column(self):
        d=dataset(['_group','label'],[[1,'A'],[2,'A'],[3,'A']])
        result=analyze('1002',d,dict(column='_group',group='label'))
        r=descriptive_values(result)
        self.assertEqual(result['tables'][0]['title'],'A')
        self.assertEqual((r['Count'],r['Mean']),(3,2.))

    def test_lda_does_not_overwrite_predictor_named_group(self):
        d=dataset(['_group','x','label'],[[1,1,'a'],[2,1,'a'],[1,2,'a'],[5,4,'b'],[6,4,'b'],[5,5,'b']])
        r=analyze('1110',d,dict(columns=['_group','x'],group='label'))
        means=table(r,'Class means')['rows']
        self.assertAlmostEqual(means[0][1],4/3)
        self.assertAlmostEqual(means[1][1],16/3)

    def test_all_nine_quantile_definitions(self):
        d=dataset(['x'],[[1],[2],[3],[4],[5],[6],[7],[8]])
        expected={1:2,2:2.5,3:2,4:2,5:2.5,6:2.25,7:2.75,8:29/12,9:2.4375}
        for definition,q1 in expected.items():
            result=analyze('1001',d,{'columns':['x'],'sta.percentile.def':str(definition-1)})
            self.assertAlmostEqual(descriptive_values(result)['Percentile 25% (Q1)'],q1,places=12)

    def test_descriptive_source_defaults_and_all_report_layouts(self):
        d=dataset(['a','b'],[[1,10],[2,20],[3,30],[4,40]])
        entry=next(c for c in catalog() if c['id']=='1001')
        defaults={f['key']:f.get('default') for f in entry['fields']}
        self.assertEqual(defaults['sta.percentile.def'],'6')
        self.assertEqual(defaults['sta.bst.ds.report'],'2')
        self.assertFalse(defaults['sta.bst.ds.ao.0'])
        by_layout=[]
        for mode in range(3):
            r=analyze('1001',d,{'columns':['a','b'],'sta.bst.ds.report':str(mode)})
            by_layout.append(descriptive_values(r))
            self.assertEqual(len(r['tables']),1 if mode==1 else 2)
            self.assertEqual(r['charts'],[])
        self.assertEqual(by_layout[0],by_layout[1])
        self.assertEqual(by_layout[1],by_layout[2])
        combined=analyze('1001',d,{'columns':['a','b'],'sta.bst.ds.report':'1'})['tables'][0]
        self.assertEqual(combined['columns'],['Statistic','a','b'])
        self.assertEqual(next(r for r in combined['rows'] if r[0]=='Mean'),['Mean',2.5,25.])

    def test_descriptive_sort_orders_are_stable(self):
        d=dataset(['z','a','b'],[[1,9,1],[3,11,3]])
        expected={0:['z','a','b'],1:['a','b','z'],2:['z','b','a'],3:['z','b','a'],4:['a','z','b']}
        for mode,names in expected.items():
            r=analyze('1001',d,{'columns':['z','a','b'],'vars.ui.sortby':str(mode)})
            self.assertEqual(r['layout']['variableOrder'],names)

    def test_descriptive_group_sort_and_missing_policy(self):
        d=dataset(['x','g'],[[9,'b'],[1,'a'],[11,'b'],[3,'a'],[100,None],[None,'a']])
        r=analyze('1002',d,{'column':'x','group':'g','vars.ui.sortby':'3'})
        self.assertEqual(r['layout']['variableOrder'],['a','b'])
        self.assertEqual(descriptive_values(r)['Count'],2)
        self.assertEqual(descriptive_values(r)['Mean'],2)

    def test_descriptive_histogram_overlay_is_count_scaled(self):
        x=np.arange(1,11,dtype=float)
        r=analyze('1001',dataset(['x'],[[v] for v in x]),{'columns':['x'],'sta.bst.ds.ao.0':True,'sta.bst.ds.ao.1':True,'sta.bst.ds.ao.2':3})
        h=r['charts'][0]
        self.assertEqual(h['type'],'histogram')
        self.assertEqual(h['binEdges'],[0.,5.,10.])
        self.assertEqual(sum(h['series'][0]['y']),10)
        self.assertEqual(h['series'][1]['type'],'spline')
        curve=h['series'][1]
        self.assertEqual(len(curve['x']),31)
        np.testing.assert_allclose(curve['y'],stats.norm.pdf(curve['x'],loc=5.5,scale=np.std(x,ddof=1))*50)
        off=analyze('1001',dataset(['x'],[[1],[2],[3]]),{'columns':['x'],'sta.bst.ds.ao.1':True})
        self.assertEqual(off['charts'],[])

    def test_descriptive_bins_and_options_validate_input_domains(self):
        d=dataset(['x'],[[1],[2],[3]])
        for bad in (1,2,-1,2.5,10001,float('inf'),True):
            with self.assertRaises(ValueError):
                analyze('1001',d,{'columns':['x'],'sta.bst.ds.ao.2':bad})
        for key,value in [('sta.percentile.def',9),('sta.bst.ds.report',3),('vars.ui.sortby',5),('sta.chart.qq','yes')]:
            with self.assertRaises(ValueError):analyze('1001',d,{'columns':['x'],key:value})

    def test_descriptive_qq_reference_and_constant_series(self):
        r=analyze('1001',dataset(['x'],[[3],[1],[2],[4]]),{'columns':['x'],'sta.chart.qq':True})
        c=r['charts'][0]
        np.testing.assert_allclose(c['series'][0]['x'],[1,2,3,4])
        np.testing.assert_allclose(c['series'][0]['y'],stats.norm.ppf((np.arange(1,5)-.375)/4.25,loc=2.5,scale=np.std([1,2,3,4],ddof=1)))
        constant=analyze('1001',dataset(['x'],[[2],[2]]),{'columns':['x'],'sta.chart.qq':True,'sta.bst.ds.ao.0':True,'sta.bst.ds.ao.1':True})
        self.assertEqual(len(constant['charts']),0)
        self.assertTrue(any('histogram is omitted' in w for w in constant['warnings']))
        self.assertTrue(any('Q-Q plot omitted' in w for w in constant['warnings']))

    def test_descriptive_standard_errors_and_small_sample_domains(self):
        r=analyze('1001',dataset(['x'],[[1],[2],[2],[4]]),{'columns':['x']})
        v=descriptive_values(r)
        self.assertEqual(v['Mode'],2)
        self.assertEqual(r['unavailableStatistics'],[])
        self.assertAlmostEqual(v['Skewness Standard Error'],math.sqrt(18/35))
        self.assertAlmostEqual(v['Kurtosis Standard Error'],math.sqrt(192/63)/3)
        n34=descriptive_values(analyze('1001',dataset(['x'],[[i] for i in range(34)]),{'columns':['x']}))
        self.assertAlmostEqual(n34['Skewness Standard Error'],.39102,places=5)
        self.assertAlmostEqual(n34['Kurtosis Standard Error'],.71772,places=5)
        for n in (1,2,3):
            values=descriptive_values(analyze('1001',dataset(['x'],[[i] for i in range(n)]),{'columns':['x']}))
            self.assertIsNone(values['Kurtosis Standard Error'])
            self.assertEqual(values['Skewness Standard Error'] is None,n==1)

    def test_descriptive_mad_preserves_native_order_bug_and_exposes_standard_value(self):
        results=[analyze('1001',dataset(['x'],[[v] for v in data]),{'columns':['x']})
                 for data in ([0,10,2,4],[0,2,4,10])]
        self.assertEqual([descriptive_values(r)['MAD (Median Absolute Deviation)'] for r in results],[4,1])
        self.assertEqual([r['conventionalMAD'][0]['value'] for r in results],[2,2])
        self.assertTrue(all(any('order-sensitive' in w for w in r['warnings']) for r in results))
        d=dataset(['x'],[[1],[9],[3],[20],[8]])
        default=analyze('1001',d,{'columns':['x']})
        type4=analyze('1001',d,{'columns':['x'],'sta.percentile.def':'3'})
        self.assertEqual(descriptive_values(default)['MAD (Median Absolute Deviation)'],5)
        self.assertEqual(descriptive_values(type4)['MAD (Median Absolute Deviation)'],2.5)

    def test_descriptive_cod_uses_absolute_median(self):
        r=descriptive_values(analyze('1001',dataset(['x'],[[-5],[-3],[-1]]),{'columns':['x']}))
        self.assertAlmostEqual(r['Coefficient of Dispersion (COD)'],4/9)

    def test_descriptive_nonpositive_domain_and_single_observation(self):
        r=descriptive_values(analyze('1001',dataset(['x'],[[-1],[0],[1]]),{'columns':['x']}))
        self.assertIsNone(r['Coefficient of Variation'])
        self.assertIsNone(r['Coefficient of Dispersion (COD)'])
        self.assertIsNone(r['Geometric Mean'])
        self.assertIsNone(r['Harmonic Mean'])
        single=descriptive_values(analyze('1001',dataset(['x'],[[4]]),{'columns':['x']}))
        self.assertEqual(single['Count'],1)
        self.assertEqual(single['Mean'],4)
        self.assertIsNone(single['Mean LCL'])
        self.assertIsNone(single['Standard Deviation'])

    def test_descriptive_confidence_and_legacy_quantile_alias(self):
        d=dataset(['x'],[[1],[2],[4],[8],[10]])
        lo=descriptive_values(analyze('1001',d,{'columns':['x'],'confidence':.90,'quantile':'1'}))
        hi=descriptive_values(analyze('1001',d,{'columns':['x'],'confidence':.99,'sta.percentile.def':'0'}))
        self.assertLess(hi['Mean LCL'],lo['Mean LCL'])
        self.assertGreater(hi['Mean UCL'],lo['Mean UCL'])
        self.assertEqual(hi['Percentile 25% (Q1)'],lo['Percentile 25% (Q1)'])

    def test_one_sample_t_golden(self):
        r=analyze('1003',dataset(['x'],[[2],[4],[6],[8],[10]]),{'columns':['x'],'mean':5})['tables'][0]['rows'][0]
        self.assertAlmostEqual(r[5],1/math.sqrt(2))
        self.assertEqual(r[6],4)
        self.assertAlmostEqual(r[7],.5185185185185183,places=12)

    def test_known_variance_z(self):
        r=analyze('1004',dataset(['x'],[[1],[2],[3],[4]]),{'column':'x','mean':2,'variance':1})['tables'][0]['rows'][0]
        self.assertAlmostEqual(r[5],1)
        self.assertAlmostEqual(r[7],.31731050786291415)

    def test_pooled_and_summary_equivalent(self):
        d=dataset(['a','b'],[[1,4],[2,5],[3,7],[4,None]])
        raw=analyze('1005',d,{'x':'a','y':'b'})['tables'][0]['rows'][0]
        summary=analyze('10052',{},dict(n1=4,mean1=2.5,sd1=math.sqrt(5/3),n2=3,mean2=16/3,sd2=math.sqrt(7/3)))['tables'][0]['rows'][0]
        np.testing.assert_allclose(raw[1:],summary[1:])
        self.assertEqual(raw[9],5)

    def test_welch_summary_degrees_of_freedom(self):
        r=analyze('10052',{},dict(n1=10,mean1=1,sd1=2,n2=20,mean2=2,sd2=3,test_type='welch'))['tables'][0]['rows'][0]
        se2=4/10+9/20
        df=se2**2/((4/10)**2/9+(9/20)**2/19)
        self.assertAlmostEqual(r[8],-1/math.sqrt(se2))
        self.assertAlmostEqual(r[9],df)

    def test_paired_missingness_preserves_matching(self):
        d=dataset(['a','b'],[[5,2],[None,99],[4,2],[8,3],[7,None]])
        r=analyze('1005',d,dict(x='a',y='b',test_type='paired'))['tables'][0]['rows'][0]
        self.assertEqual((r[1],r[2]),(3,3))
        self.assertAlmostEqual(r[5],10/3)
        self.assertEqual(r[9],2)

    def test_directional_pvalues(self):
        d=dataset(['a'],[[2],[3],[5],[7]])
        results=[analyze('1003',d,dict(columns=['a'],mean=0,alternative=a))['tables'][0]['rows'][0][7] for a in ['less','greater','two-sided']]
        self.assertAlmostEqual(results[0]+results[1],1)
        self.assertAlmostEqual(results[1]*2,results[2])

    def test_independent_and_paired_zero_variance_rejected(self):
        d=dataset(['x','y'],[[1,2],[1,2],[1,2]])
        for aid,opt in [('1003',dict(columns=['x'])),('1005',dict(x='x',y='y')),('1005',dict(x='x',y='y',test_type='paired')),('1008',dict(x='x',y='y'))]:
            with self.assertRaises(ValueError):
                analyze(aid,d,opt)

    def test_covariance_pairwise_deletion(self):
        d=dataset(['x','y'],[[1,2],[2,4],[3,6],[4,None]])
        t=analyze('1010',d,dict(columns=['x','y']))['tables'][0]
        self.assertAlmostEqual(t['rows'][0][2],2)
        self.assertAlmostEqual(t['rows'][0][1],5/3)

    def test_partial_correlation_removes_confounding(self):
        # Orthogonal vectors x_error and y_error ensure residual r=0 exactly.
        z=np.array([-2,-1,0,1,2.])
        u=np.array([1,-2,2,-2,1.])
        v=np.array([-1,2,0,-2,1.])
        d=dataset(['x','y','z'],np.column_stack([10*z+u,10*z+v,z]))
        r=analyze('1016',d,dict(columns=['x','y'],controls=['z']))['tables'][0]['rows'][0]
        self.assertAlmostEqual(r[4],0,places=12)
        self.assertAlmostEqual(r[5],1,places=12)

    def test_histogram_closed_edges(self):
        d=dataset(['x'],[[0],[1],[2],[3]])
        left=analyze('1015',d,dict(columns=['x'],bins=3,closed='left'))['tables'][0]
        right=analyze('1015',d,dict(columns=['x'],bins=3,closed='right'))['tables'][0]
        # Native automatic boundaries expand the open outer endpoint.
        self.assertEqual([r[2] for r in left['rows']],[1,1,1,1])
        self.assertEqual([r[2] for r in right['rows']],[1,1,1,1])
        self.assertEqual(left['rows'][0][:2],[0.,1.])
        self.assertEqual(right['rows'][0][:2],[-1.,0.])

    def test_contingency_known_chisquare(self):
        d=dataset(['a','b'],[[10,20],[20,10]])
        r=analyze('1401',d,dict(columns=['a','b'],correction=False))
        summary=dict(table(r,'Measures of association')['rows'])
        self.assertAlmostEqual(table(r,'Chi-square tests')['rows'][0][1],20/3)
        self.assertAlmostEqual(summary['Cramér V'],1/3)
        self.assertAlmostEqual(table(r,'Fisher exact (two-sided)')['rows'][0][0],.25)
        rounded=analyze('1401',dataset(['a','b'],[[1.2,3],[4,5]]),dict(columns=['a','b']))
        self.assertEqual(table(rounded,'Observed counts')['rows'][0][1],1)

    def test_oneway_anova_hand_computation(self):
        d=dataset(['A','B','C'],[[1,3,5],[2,4,6],[3,5,7]])
        t=analyze('1102',d,dict(columns=['A','B','C'],tukey=False))['tables'][0]
        self.assertEqual(t['rows'][0][1],24)
        self.assertEqual(t['rows'][1][1],6)
        self.assertEqual(t['rows'][0][4],12)
        self.assertEqual(t['rows'][0][2],2)
        self.assertEqual(t['rows'][1][2],6)

    def test_latin_square_validation(self):
        rows=[]
        for i in range(3):
            for j in range(3):
                rows.append([str(i+1),str(j+1),str((i+j)%3+1),i+2*j+3*((i+j)%3)+.1*((i-j)**2)])
        d=dataset(['row','col','treat','y'],rows)
        r=analyze('1201',d,dict(response='y',factors=['row','col','treat']))
        self.assertTrue(r['tables'])
        d['rows'][0][2]='2'
        with self.assertRaisesRegex(ValueError,'once'):
            analyze('1201',d,dict(response='y',factors=['row','col','treat']))

    def test_designs_reject_missing_data(self):
        for aid in ['1202','1203','1205','1206','1207','1208']:
            with self.assertRaises(ValueError):
                analyze(aid,{}, {})

    def test_repeated_measures_matches_reference(self):
        # Hand calculation: n=4, k=3, treatment SS=26, residual SS=4.
        x=np.array([[1,2,4],[2,4,5],[3,3,6],[4,6,7.]])
        d=dataset(['a','b','c'],x)
        t=analyze('1108',d,dict(columns=['a','b','c']))['tables'][0]
        ss=4*np.sum((x.mean(axis=0)-x.mean())**2)
        error=x-x.mean(axis=1,keepdims=True)-x.mean(axis=0)+x.mean()
        f=(ss/2)/(np.sum(error**2)/6)
        self.assertAlmostEqual(t['rows'][0][4],f)
        self.assertGreaterEqual(t['rows'][1][2],1)
        self.assertLessEqual(t['rows'][1][2],2)

    def test_mixed_two_timepoints_equals_between_t_on_differences(self):
        rows=[['a',1,2],['a',2,4],['a',3,7],['b',2,5],['b',4,9],['b',5,11]]
        r=analyze('1106',dataset(['g','t1','t2'],rows),dict(group='g',columns=['t1','t2']))
        interaction=next(row for row in r['tables'][0]['rows'] if '×' in row[0])
        expected=stats.ttest_ind([1,2,4],[3,5,6],equal_var=True)
        self.assertAlmostEqual(interaction[4],expected.statistic**2,places=12)
        self.assertAlmostEqual(interaction[5],expected.pvalue,places=12)

    def test_mixed_unbalanced_rejected(self):
        d=dataset(['g','a','b'],[['x',1,2],['x',2,4],['y',3,5],['y',4,8],['y',5,7]])
        with self.assertRaisesRegex(ValueError,'equal cell sizes'):
            analyze('1106',d,dict(group='g',columns=['a','b']))

    def test_pca_trace_reconstruction_and_scores(self):
        d=dataset(['a','b','c'],[[1,3,2],[2,1,5],[3,2,3],[4,5,1],[5,4,6]])
        r=analyze('1120',d,dict(columns=['a','b','c']))
        eig=table(r,'Eigenvalues')['rows']
        self.assertAlmostEqual(sum(row[1] for row in eig),3)
        self.assertAlmostEqual(eig[-1][3],1)
        coeff=np.array([row[1:] for row in table(r,'Component coefficients')['rows']])
        np.testing.assert_allclose(coeff.T@coeff,np.eye(3),atol=1e-12)
        scores=np.array([row[1:] for row in table(r,'Scores')['rows']])
        np.testing.assert_allclose(np.var(scores,axis=0,ddof=1),[row[1] for row in eig],atol=1e-12)

    def test_factor_rotation_preserves_communality(self):
        rng=np.random.default_rng(3)
        d=dataset(['a','b','c','d'],rng.normal(size=(20,4)))
        r=analyze('1121',d,dict(columns=d['columns'],retention='count',threshold=2,rotation='varimax'))
        original=np.array([row[1:] for row in table(r,'Initial component-factor loadings')['rows']])
        rotated=np.array([row[1:] for row in table(r,'Rotated loadings')['rows']])
        np.testing.assert_allclose(np.sum(original**2,axis=1),np.sum(rotated**2,axis=1),atol=1e-12)

    def test_kmeans_separates_two_blobs(self):
        d=dataset(['x','y'],[[0,0],[0,1],[1,0],[10,10],[10,11],[11,10]])
        r=analyze('1130',d,dict(columns=['x','y'],clusters=2))
        labels=[row[1] for row in table(r,'Membership')['rows']]
        self.assertEqual(len(set(labels[:3])),1)
        self.assertEqual(len(set(labels[3:])),1)
        self.assertNotEqual(labels[0],labels[-1])
        self.assertAlmostEqual(dict(table(r,'Fit summary')['rows'])['Within-cluster sum of squares'],8/3)

    def test_native_ward_accepts_squared_euclidean_proximity(self):
        d=dataset(['x'],[[1],[2],[3]])
        result=analyze('1132',d,dict(columns=['x'],linkage='ward'))
        self.assertAlmostEqual(table(result,'Linkage')['rows'][-1][3],3.)

    def test_regression_known_solution(self):
        # Residual vector is orthogonal to intercept and x.
        x=np.arange(5.)
        e=np.array([1,-2,2,-2,1.])
        d=dataset(['x','y'],np.column_stack([x,2+3*x+e]))
        r=analyze('1301',d,dict(response='y',predictors=['x']))
        coeff=table(r,'Coefficients')['rows']
        self.assertAlmostEqual(coeff[0][1],2)
        self.assertAlmostEqual(coeff[1][1],3)
        self.assertEqual(dict(table(r,'Model summary')['rows'])['Residual df'],3)

    def test_wls_weight_semantics(self):
        d=dataset(['x','y','w'],[[0,0,1],[1,1,1],[2,4,4],[3,3,1]])
        r=analyze('1302',d,dict(response='y',predictors=['x'],weights='w'))
        x=np.column_stack([np.ones(4),[0,1,2,3]])
        expected=np.linalg.solve(x.T@np.diag([1,1,4,1])@x,x.T@np.diag([1,1,4,1])@np.array([0,1,4,3]))
        np.testing.assert_allclose([row[1] for row in table(r,'Coefficients')['rows']],expected)

    def test_singular_regression_rejected(self):
        d=dataset(['x','z','y'],[[1,2,3],[2,4,6],[3,6,8],[4,8,12]])
        with self.assertRaisesRegex(ValueError,'full-rank'):
            analyze('1301',d,dict(response='y',predictors=['x','z']))

    def test_polynomial_prediction(self):
        x=np.arange(-3,4.)
        d=dataset(['x','y'],np.column_stack([x,1+2*x+3*x*x]))
        r=analyze('1303',d,dict(response='y',predictor='x',degree=2))
        np.testing.assert_allclose([row[1] for row in table(r,'Coefficients')['rows']],[1,2,3],atol=1e-12)

    def test_exponential_curve_original_scale(self):
        x=np.arange(1,6.)
        d=dataset(['x','y'],np.column_stack([x,2*np.exp(.3*x)]))
        r=analyze('1310',d,dict(response='y',predictor='x',model='exponential'))
        np.testing.assert_allclose([row[2] for row in table(r,'Predictions on original response scale')['rows']],2*np.exp(.3*x),atol=1e-12)
        self.assertTrue(any('log(response)' in note for note in r['notes']))
        self.assertEqual(r['charts'][-1]['series'][-1]['type'],'line')

    def test_logistic_separation_rejected(self):
        d=dataset(['x','y'],[[-3,0],[-2,0],[-1,0],[1,1],[2,1],[3,1]])
        with self.assertRaises(ValueError):
            analyze('1306',d,dict(response='y',predictors=['x']))

    def test_rank_and_percentile_preserve_missing_rows(self):
        r=analyze('1403',dataset(['x'],[[4],[None],[1],[4]]),dict(columns=['x']))
        self.assertEqual([row[0] for row in r['tables'][0]['rows']],[1,3,4])
        self.assertEqual([row[2] for row in r['tables'][0]['rows']],[2.5,1,2.5])
        self.assertEqual(len(r['dataset']['rows']),4)

    def test_rank_correlations_extremes_and_ties(self):
        d=dataset(['x','y'],[[1,2],[2,2],[3,5],[4,9]])
        r=analyze('1404',d,dict(columns=['x','y']))
        rows=r['tables'][0]['rows']
        self.assertAlmostEqual(rows[2][4],1)
        self.assertIsNone(rows[2][5])
        self.assertLess(rows[1][4],1)

    def test_friedman_perfect_ordering(self):
        d=dataset(['a','b','c'],[[1,2,3],[4,5,6],[7,8,9],[10,11,12]])
        row=analyze('1409',d,dict(columns=['a','b','c']))['tables'][0]['rows'][0]
        self.assertEqual(row[2],8)
        self.assertEqual(row[-1],1)

    def test_subject_identifier_prevents_false_pairing(self):
        d=dataset(['s','g','v'],[['s1','A',1],['s1','A',2],['s2','B',3]])
        with self.assertRaisesRegex(ValueError,'exactly one'):
            analyze('14092',d,dict(column='v',group='g',subject='s'))

    def test_invalid_numeric_input_is_not_silently_missing(self):
        d=dataset(['x'],[[1],[2],['typo'],[4]])
        with self.assertRaisesRegex(ValueError,'nonnumeric'):
            analyze('1001',d,dict(columns=['x']))
        with self.assertRaisesRegex(ValueError,'infinity'):
            analyze('1001',dataset(['x'],[[1],[float('inf')]]),dict(columns=['x']))

    def test_catalog_inventory_coverage_and_defaults(self):
        entries=catalog()
        self.assertEqual(len(entries),60)
        self.assertEqual(len({e['id'] for e in entries}),60)
        for item in entries:
            self.assertIn('limitations',item)
            keys=[f['key'] for f in item['fields']]
            self.assertEqual(len(keys),len(set(keys)),item['id'])
        c={e['id']:e for e in entries}
        self.assertEqual(next(f['default'] for f in c['1005']['fields'] if f['key']=='test_type'),'pooled')
        self.assertEqual(next(f['default'] for f in c['1132']['fields'] if f['key']=='mv.distancemeasure'),'1')


class AllProcedureSmokeTests(unittest.TestCase):
    def test_all_supported_catalog_entries_return_structured_results(self):
        rng=np.random.default_rng(12)
        n=48
        x=rng.normal(size=n)
        z=rng.normal(size=n)
        noise=rng.normal(size=n)
        rows=[]
        for i in range(n):
            a=str((i//4)%2); b=str((i//2)%2); c=str(i%2)
            g='a' if i<n//2 else 'b'
            y=2+1.3*x[i]+.2*z[i]+noise[i]
            rows.append([x[i],z[i],y,math.exp(.2*x[i]+.1*noise[i]),g,a,b,c,
                         float(rng.random()<1/(1+math.exp(-x[i]))),
                         float(rng.integers(0,2)),float(rng.integers(0,2)),float(rng.integers(0,2))])
        data=dataset(['x','z','y','positive','group','a','b','c','binary','q1','q2','q3'],rows)
        options={
            '1001':dict(columns=['x','y']), '1002':dict(column='x',group='group'),
            '1003':dict(columns=['x']), '1004':dict(column='x',variance=1),
            '1005':dict(x='x',y='y'),'1007':dict(x='x',y='y',variance_x=1,variance_y=1),
            '10052':dict(n1=10,mean1=1,sd1=2,n2=20,mean2=2,sd2=3),
            '10053':dict(column='x',group='group'),'1008':dict(x='x',y='z'),
            '1009':dict(columns=['x','y']),'1010':dict(columns=['x','y']),
            '1016':dict(columns=['x','y'],controls=['z']), '1011':dict(columns=['x']),
            '1012':dict(columns=['group']),'1013':dict(columns=['x']),
            '1014':dict(row='group',column='a'),'1015':dict(columns=['x']),
            '1102':dict(columns=['x','y','z']),'1103':dict(column='x',group='group'),
            '1104':dict(response='y',factors=['a','b']), '1105':dict(response='y',factors=['a','b','c']),
            '1106':dict(group='group',columns=['x','z','y']),
            '1107':dict(factors=['a','b'],columns=['x','z','y']),
            '1108':dict(columns=['x','z','y']), '1109':dict(response='y',factors=['a'],predictors=['x','z']),
            '1110':dict(columns=['x','z'],group='group',cross_validate=True),
            '1120':dict(columns=['x','y','z']), '1121':dict(columns=['x','y','z']),
            '1130':dict(columns=['x','z']), '1132':dict(columns=['x','z']),
            '1301':dict(response='y',predictors=['x','z']),
            '1302':dict(response='y',predictors=['x','z'],weights='positive'),
            '1303':dict(response='y',predictor='x'),'1310':dict(response='positive',predictor='x',model='exponential'),
            '1304':dict(response='y',predictors=['x','z']), '1305':dict(response='y',predictors=['x','z']),
            '1307':dict(response='y',predictors=['x','z']), '1306':dict(response='binary',predictors=['x','z']),
            '1320':dict(residuals='y',predictors=['x','z']),
            '1403':dict(columns=['x','z']), '1404':dict(columns=['x','z']), '1405':dict(columns=['x','z']),
            '1406':dict(x='x',y='z'), '14063':dict(column='x',group='group'),
            '1407':dict(columns=['x','z','y']), '14072':dict(column='x',group='group'),
            '1408':dict(x='x',y='z'), '1409':dict(columns=['x','z','y']), '1410':dict(columns=['q1','q2','q3'])}
        alternate={
          '1401':(dataset(['a','b'],[[10,20],[20,10]]),dict(columns=['a','b'])),
          '1411':(dataset(['a','b'],[[10,20],[20,10],[5,15]]),dict(columns=['a','b'])),
          '14092':(dataset(['subject','group','value'],[[s,g,s*3+g+float(rng.normal())] for s in range(10) for g in range(3)]),dict(column='value',group='group',subject='subject'))}
        latin=[]
        for i in range(3):
            for j in range(3):
                for rep in range(2):
                    latin.append([str(i+1),str(j+1),str((i+j)%3+1),str((i+2*j)%3+1),float(rng.normal())])
        square=dataset(['r','c','l','g','y'],latin)
        alternate['1201']=(square,dict(response='y',factors=['r','c','l']))
        alternate['1204']=(square,dict(response='y',factors=['r','c','l','g']))
        tested=set()
        for item in catalog():
            aid=item['id']
            if item['coverage']=='unsupported' or aid in ['1202','1203','1205','1206','1207','1208']:
                continue  # These six designs have dedicated published-example tests in test_doe.py.
            with self.subTest(aid=aid):
                d,opt=alternate.get(aid,(data,options.get(aid)))
                self.assertIsNotNone(opt,aid)
                result=analyze(aid,d,opt)
                self.assertEqual(result['analysis'],aid)
                self.assertTrue(result['tables'])
                for t in result['tables']:
                    self.assertTrue(all(len(row)==len(t['columns']) for row in t['rows']), (aid,t['title']))
                self.assertIsInstance(result['notes'],list)
                self.assertIsInstance(result['warnings'],list)
                tested.add(aid)
        self.assertEqual(len(tested),54)


if __name__=='__main__':
    unittest.main()
