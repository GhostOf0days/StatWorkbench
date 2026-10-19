import unittest
import json
from pathlib import Path
import numpy as np
from backend.analyses.basic import analyze,catalog
from tests.test_basic import dataset,table,descriptive_values

class BasicOptionTests(unittest.TestCase):
    def test_reference_descriptive_fixture_all_72_values_and_wide_layout(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/reference_descriptive.json').read_text())
        columns=list(fixture['inputs']);data=dataset(columns,zip(*(fixture['inputs'][c] for c in columns)))
        result=analyze('1001',data,{'columns':columns,**fixture['options']})
        self.assertEqual(len(result['tables'][0]['columns']),6)
        self.assertTrue(result['tables'][0]['layout']['hideColumnHeaders'])
        for variable,expected in fixture['expected'].items():
            actual=descriptive_values(result,variable)
            self.assertEqual(len(actual),36)
            for name,value in expected.items():
                with self.subTest(variable=variable,statistic=name):
                    if value is None:self.assertIsNone(actual[name])
                    else:self.assertAlmostEqual(actual[name],value,places=10)
        for n in (1,2):
            r=analyze('1001',dataset(['x'],[[i] for i in range(n)]),{'columns':['x']})
            self.assertIsNone(descriptive_values(r)['Trimmed Mean (5%)'])
    def test_hypothesized_vector_maps_to_variables_not_rows(self):
        d=dataset(['a','b','mu'],[[1,10,2],[2,20,15],[3,30,None]])
        rows=table(analyze('1003',d,{'columns':['a','b'],'TTEST_OS_CONST':'mu'}),'Mean tests')['rows']
        self.assertEqual([r[3] for r in rows],[2,15]);self.assertEqual(rows[0][5],0)
        self.assertAlmostEqual(rows[1][5],np.sqrt(3)/2)
        self.assertEqual(table(analyze('1003',d,{'columns':['a'],'TTEST_OS_CONST':2}),'Mean tests')['rows'][0][5],0)
    def test_group_codes_select_and_order_groups(self):
        d=dataset(['v','g'],[[1,'A'],[2,'A'],[10,'B'],[12,'B'],[20,'C'],[22,'C']])
        r=analyze('10053',d,{'column':'v','group':'g','GROUP.1':'C','GROUP.2':'A'})
        self.assertEqual(r['tables'][0]['rows'][0][0],'C − A');self.assertEqual(r['tables'][0]['rows'][0][5],19.5)
        with self.assertRaises(ValueError):analyze('14063',d,{'column':'v','group':'g','GROUP.1':'A'})
    def test_weighted_categorical_frequencies_and_layers(self):
        d=dataset(['c','w','g'],[['a',2,'L'],['b',3,'L'],['a',4,'R'],[None,20,'R']])
        r=analyze('1012',d,{'columns':['c'],'sta.bst.freq.freqvar':'w','sta.bst.freq.layervar':'g','tables.plot.bar':'2'})
        self.assertEqual(len(r['tables']),2);self.assertEqual(r['tables'][0]['rows'][0],['a',2.,2.,.4,.4]);self.assertEqual(r['charts'][0]['series'][0]['y'],[40,60])
        r=analyze('1012',d,{'columns':['c'],'sta.bst.freq.freqvar':'w','tables.plot.bar':'0','output.percenstyleforpercentages':False})
        self.assertEqual(r['charts'],[]);self.assertAlmostEqual(r['tables'][0]['rows'][0][3],200/3)
    def test_continuous_start_width_overflow_and_plot_switch(self):
        d=dataset(['x','w'],[[-1,2],[0,1],[5,3],[10,4],[20,5]])
        r=analyze('1013',d,{'columns':['x'],'bins':3,'sta.bst.freq.minval2':'0','sta.bst.freq.width2':'5','sta.bst.freq.freqvar':'w'})
        self.assertEqual([row[2] for row in r['tables'][0]['rows']],[2,1,3,4,5]);self.assertEqual(r['charts'],[])
        self.assertIsNone(r['tables'][0]['rows'][0][0]);self.assertIsNone(r['tables'][0]['rows'][-1][1])
    def test_histogram_bin_range_pareto_and_empty_bins(self):
        d=dataset(['x','edges'],[[0,0],[1,2],[5,4],[5,6]])
        r=analyze('1015',d,{'columns':['x'],'sta.bst.freq.bins_var':'edges','sta.bst.pareto':True,'sta.bst.ds.hist.bins0':False})
        self.assertEqual([row[2] for row in r['tables'][0]['rows']],[2,2,0]);self.assertEqual([row[0] for row in r['tables'][0]['rows']],[0,4,2])
    def test_scalar_2x2_and_accuracy(self):
        opt={f'sta.nps.2x2.param.{i}':v for i,v in enumerate([30,10,5,55])}
        r=analyze('1401',{'columns':[],'rows':[]},opt)
        accuracy=dict(table(r,'Measures of accuracy')['rows']);self.assertEqual(accuracy['Accuracy'],.85);self.assertAlmostEqual(accuracy['Sensitivity'],6/7);self.assertAlmostEqual(accuracy['Specificity'],11/13)
        self.assertAlmostEqual(dict(table(r,'Measures of association')['rows'])['Odds ratio'],33)
        fields={f['key'] for f in next(c for c in catalog() if c['id']=='1401')['fields']};self.assertNotIn('columns',fields)
    def test_crosstab_frequency_conversion_pre_vs_post_aggregation(self):
        d=dataset(['r','c','n'],[['A','X',1.6],['A','X',1.6],['A','Y',2],['B','X',2],['B','Y',3],['A','Z',2],['B','Z',3]])
        opt={'row':'r','column':'c','sta.bst.freq.freqvar':'n','sta.chi.table_combined':'2'}
        a=analyze('1014',d,{**opt,'tables.freq.nonint':'0'});b=analyze('1014',d,{**opt,'tables.freq.nonint':'2'})
        self.assertEqual(table(a,'Observed counts')['rows'][0][1],2);self.assertEqual(table(b,'Observed counts')['rows'][0][1],3)
    def test_crosstab_report_switches_are_effective(self):
        d=dataset(['a','b'],[[10,20],[20,10]])
        opt={'columns':['a','b'],'sta.chi.table_combined':'0','sta.nps.chi.tests':False,'tables.measures':False,'tables.ui.kappaopt':False,'tables.ui.full2x2':False,'tables.plot.bar':'0','tables.plot.interaction':False}
        with self.assertRaisesRegex(ValueError,'report would be empty'):analyze('1411',d,opt)
        r=analyze('1411',d,{'columns':['a','b'],'tables.plot.bar':'3','tables.ui.tables.residuals':True})
        self.assertEqual(r['charts'][0]['stack'],'percent');self.assertAlmostEqual(sum(s['y'][0] for s in r['charts'][0]['series']),100)
        self.assertFalse(any(row[1]=='Chi-square contributions' for row in r['tables'][0]['rows']))
        self.assertEqual(len(table(r,'Chi-square contributions')['rows']),3)
    def test_native_crosstab_suppression_keeps_only_requested_statistics(self):
        d=dataset(['a','b','c'],[[12,8,10],[6,15,9]])
        opt={'columns':['a','b','c'],'sta.chi.table_combined':'0','tables.measures':False,'tables.ui.kappaopt':False,'tables.ui.full2x2':False,'tables.plot.bar':'0','tables.plot.interaction':False}
        r=analyze('1411',d,opt)
        self.assertEqual([t['title'] for t in r['tables']],['Chi-square tests'])
        self.assertEqual(r['charts'],[])
        # The same native option loader serves categorical and frequency inputs.
        rows=[[r,c,int(n)] for r,counts in zip(['A','B'],d['rows']) for c,n in zip(['X','Y','Z'],counts)]
        r=analyze('1014',dataset(['r','c','n'],rows),{**opt,'row':'r','column':'c','sta.bst.freq.freqvar':'n'})
        self.assertEqual([t['title'] for t in r['tables']],['Chi-square tests'])
    def test_native_crosstab_residuals_are_independent_and_adjusted(self):
        d=dataset(['a','b','c'],[[12,8,10],[6,15,9]])
        opt={'columns':['a','b','c'],'sta.chi.table_combined':'0','sta.nps.chi.tests':False,'tables.ui.tables.residuals':True,'tables.measures':False,'tables.ui.kappaopt':False,'tables.ui.full2x2':False,'tables.plot.bar':'0','tables.plot.interaction':False}
        r=analyze('1411',d,opt)
        self.assertEqual([t['title'] for t in r['tables']],['Residuals','Standardized residuals','Adjusted residuals','Chi-square contributions'])
        np.testing.assert_allclose(np.array(table(r,'Residuals')['rows'],dtype=object)[:,1:].astype(float),[[3,-3.5,.5],[-3,3.5,-.5]])
        adjusted=np.array(table(r,'Adjusted residuals')['rows'],dtype=object)[:,1:].astype(float)
        oracle=np.array([3/np.sqrt(3.15),-3.5/np.sqrt(851/240),.5/np.sqrt(779/240)])
        np.testing.assert_allclose(adjusted,[oracle,-oracle],rtol=1e-13)
        combined=analyze('1411',d,{**opt,'sta.chi.table_combined':'1'})
        self.assertEqual([row[0] for row in table(combined,'Combined crosstab')['rows']][1:5],['Expected','% within row','% within column','% of total'])
        np.testing.assert_allclose(np.array(table(combined,'Adjusted residuals')['rows'],dtype=object)[:,1:].astype(float),adjusted)
    def test_native_crosstab_chart_only_is_valid_and_empty_selection_is_not(self):
        d=dataset(['a','b','c'],[[12,8,10],[6,15,9]])
        opt={'columns':['a','b','c'],'sta.chi.table_combined':'0','sta.nps.chi.tests':False,'tables.measures':False,'tables.ui.kappaopt':False,'tables.plot.bar':'0','tables.plot.interaction':False}
        # Full-2x2 is not a gate in the native empty-report predicate.
        with self.assertRaisesRegex(ValueError,'report would be empty'):analyze('1411',d,{**opt,'tables.ui.full2x2':True})
        for plot,value in [('tables.plot.bar','1'),('tables.plot.interaction',True)]:
            r=analyze('1411',d,{**opt,plot:value})
            self.assertEqual(r['tables'],[]);self.assertEqual(len(r['charts']),1)
    def test_native_crosstab_avoids_duplicate_observed_table(self):
        d=dataset(['a','b','c'],[[12,8,10],[6,15,9]])
        r=analyze('1411',d,{'columns':['a','b','c'],'sta.chi.table_combined':'3','sta.chi.exp_freq':False,'tables.ui.tables.percentage':False})
        titles=[t['title'] for t in r['tables']]
        self.assertIn('Combined crosstab',titles);self.assertNotIn('Observed counts',titles)
    def test_native_adjusted_residuals_undefined_near_unit_margin(self):
        from backend.common import sanitize_json
        d=dataset(['a','b','c'],[[1,1,1],[1e14,1e14,1e14]])
        r=sanitize_json(analyze('1411',d,{'columns':['a','b','c'],'tables.ui.tables.residuals':True}))
        self.assertEqual(table(r,'Adjusted residuals')['rows'][1][1:],[None,None,None])
        self.assertEqual(table(r,'Standardized residuals')['rows'][1][1:],[0,0,0])
    def test_native_2x2_crosstab_has_no_individual_table_branch(self):
        d=dataset(['a','b'],[[12,8],[6,15]])
        opt={'columns':['a','b'],'sta.chi.table_combined':'2','sta.nps.chi.tests':False,'tables.measures':False,'tables.ui.kappaopt':False,'tables.ui.full2x2':False,'tables.plot.bar':'0','tables.plot.interaction':False}
        r=analyze('1411',d,opt)
        self.assertEqual(r['tables'],[]);self.assertEqual(r['charts'],[])
        self.assertTrue(any('individual count' in note.lower() and 'unavailable' in note.lower() for note in r['notes']))
        # Mode 3 still emits its combined table but no duplicate individual tables.
        both=analyze('1411',d,{**opt,'sta.chi.table_combined':'3'})
        self.assertEqual([t['title'] for t in both['tables']],['Combined crosstab'])
        residual=analyze('1411',d,{**opt,'tables.ui.tables.residuals':True})
        self.assertEqual(len(residual['tables']),4)
        # The shared route applies equally to weighted categorical crosstabs.
        raw=dataset(['r','c','n'],[['A','X',12],['A','Y',8],['B','X',6],['B','Y',15]])
        r=analyze('1014',raw,{**opt,'row':'r','column':'c','sta.bst.freq.freqvar':'n'})
        self.assertEqual(r['tables'],[])
        # Scalar 2x2 uses a separate native option loader and keeps its behavior.
        scalar={f'sta.nps.2x2.param.{i}':v for i,v in enumerate([12,8,6,15])}
        self.assertEqual(len(table(analyze('1401',{'columns':[],'rows':[]},scalar),'Observed counts')['rows']),2)
    def test_reference_crosstab_tables_margins_and_suppression(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/reference_crosstab.json').read_text())
        d=dataset(['r','c','n'],fixture['inputs'])
        opt={'row':'r','column':'c','sta.bst.freq.freqvar':'n','sta.nps.chi.tests':False,'tables.measures':False,'tables.ui.kappaopt':False,'tables.ui.full2x2':False,'tables.plot.bar':'0','tables.plot.interaction':False}
        combined=analyze('1014',d,{**opt,'sta.chi.table_combined':'3'})
        expected={'Combined crosstab':fixture['combined'],**fixture['individual']}
        for title,rows in expected.items():
            actual=table(combined,title)['rows']
            self.assertEqual([r[0] for r in actual],[r[0] for r in rows])
            np.testing.assert_allclose([r[1:] for r in actual],[r[1:] for r in rows],rtol=1e-13,atol=1e-14)
        self.assertEqual(len(combined['tables']),6)
        suppressed=analyze('1014',d,{**opt,'sta.chi.table_combined':'0','tables.ui.tables.residuals':True})
        self.assertEqual([t['title'] for t in suppressed['tables']],list(fixture['residuals']))
        for title,rows in fixture['residuals'].items():
            actual=table(suppressed,title)['rows']
            self.assertEqual([r[0] for r in actual],[r[0] for r in rows])
            np.testing.assert_allclose([r[1:] for r in actual],[r[1:] for r in rows],rtol=1e-13,atol=1e-14)
        # Native percent formatting stores fractions; plain formatting stores 0..100.
        plain=analyze('1014',d,{**opt,'sta.chi.table_combined':'1','output.percenstyleforpercentages':False})
        actual=table(plain,'Combined crosstab')['rows']
        for i,row in enumerate(fixture['combined']):
            np.testing.assert_allclose(actual[i][1:],np.array(row[1:])*(100 if row[0].startswith('%') else 1))
        native_rows=fixture['two_by_two_individual_nonempty_rows']
        self.assertEqual([int(row[0]) for row in native_rows],list(range(6)))
        omitted=analyze('1014',dataset(['r','c','n'],[['A','X',3],['A','Y',4],['B','X',6],['B','Y',4]]),{**opt,'sta.chi.table_combined':'2'})
        self.assertEqual(omitted['tables'],[])
    def test_correlation_output_switches_and_tail(self):
        d=dataset(['x','y'],[[1,2],[2,1],[3,5],[4,3],[5,6]])
        base=analyze('1009',d,{'columns':['x','y']});one=analyze('1009',d,{'columns':['x','y'],'sta.tail.h':'0','bst.corr.table.trse.ui':True,'sta.scatterplots':'1','ui.freezecols':True})
        self.assertAlmostEqual(base['tables'][0]['rows'][0][5]/2,one['tables'][0]['rows'][0][5]);self.assertEqual(len(one['charts']),1);self.assertTrue(one['tables'][0]['layout']['freezeFirstColumn'])
        off=analyze('1009',d,{'columns':['x','y'],'bst.corr.table.pval.ui':False});self.assertNotIn('p-value',off['tables'][0]['columns'])
    def test_normality_charts_and_rank_sort(self):
        d=dataset(['x'],[[3],[1],[4],[2],[9]])
        r=analyze('1011',d,{'columns':['x'],'sta.bst.ds.ao.0':True,'sta.chart.qq':True});self.assertEqual(len(r['charts']),2)
        r=analyze('1403',d,{'columns':['x'],'sta.sort.output':'1'});self.assertEqual([row[1] for row in r['tables'][0]['rows']],[1,2,3,4,9]);self.assertEqual([row[0] for row in r['dataset']['rows']],[1,2,3,4,9])

if __name__=='__main__':unittest.main()
