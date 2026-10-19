"""Independent fixtures for chart, time-series and survival controls."""
import unittest
import numpy as np
from scipy import stats
from backend.analyses.advanced import analyze,catalog
from backend.common import sanitize_json


def data(names,rows):return dict(columns=names,rows=np.asarray(rows,dtype=object).tolist(),name='Fixture')
def table(r,title):return next(t for t in r['tables'] if title in t['title'])


class AdvancedControlTests(unittest.TestCase):
    def test_qq_all_plotting_positions_and_tie_rules(self):
        d=data(['x'],[[1],[1],[2],[5]])
        for pos,offset in enumerate([.375,.5,1/3,0]):
            for mode,rank in enumerate([[1.5,1.5,3,4],[2,2,3,4],[1,1,3,4],[1,2,3,4]]):
                r=analyze('4011',d,{'columns':['x'],'sta.qq.proportion.method':str(pos),'sta.rankperc.tie':str(mode),'sta.distr.params.estimate.opt':False,'DS_AVERAGE':2,'DS_STDDEV':3,'sta.qq.swapaxes':True})
                expected=(np.asarray(rank)-offset)/(5-2*offset)
                np.testing.assert_allclose(np.asarray(r['tables'][0]['rows'])[:,0],expected)
                np.testing.assert_allclose(r['charts'][0]['series'][0]['x'],stats.norm.ppf(expected,loc=2,scale=3))
                self.assertEqual(len(r['charts']),2)
        r=analyze('4011',d,{'columns':['x'],'sta.qq.detrended.show':False,'sta.qq.plot.showline':False})
        self.assertEqual(len(r['charts']),1);self.assertEqual(len(r['charts'][0]['series']),1)

    def test_qq_native_auto_parameter_formulas(self):
        y=np.array([1.,2,3,5,8]);d=data(['x'],y[:,None]);p=(np.arange(1,6)-.375)/5.25
        normal=analyze('4011',d,{'columns':['x']});np.testing.assert_allclose(np.array(normal['tables'][0]['rows'])[:,1],stats.norm.ppf(p,y.mean(),y.std(ddof=1)))
        gamma=analyze('4014',d,{'columns':['x']});np.testing.assert_allclose(np.array(gamma['tables'][0]['rows'])[:,1],stats.gamma.ppf(p,y.mean()**2/y.var(ddof=1),scale=y.mean()/y.var(ddof=1)))
        log=analyze('4015',d,{'columns':['x']});np.testing.assert_allclose(np.array(log['tables'][0]['rows'])[:,1],stats.lognorm.ppf(p,np.log(y).std(ddof=1),scale=np.exp(np.log(y).mean())))
        weibull=analyze('4018',d,{'columns':['x']});slope,intercept=np.polyfit(np.log(y),np.log(-np.log1p(-p)),1)
        np.testing.assert_allclose(np.array(weibull['tables'][0]['rows'])[:,1],stats.weibull_min.ppf(p,slope,scale=np.exp(-intercept/slope)))

    def test_qq_manual_parameter_branches(self):
        d=data(['x'],[[.1],[.2],[.4],[.7],[.8]])
        opts={'columns':['x'],'sta.distr.params.estimate.opt':False}
        for id,params in [('4012',{'sta.beta.alpha':2,'sta.beta.beta':3}),('4014',{'sta.gamma.shapek':2,'sta.gamma.scaletheta':3}),('4015',{'sta.distr.shape':1,'sta.distr.scale':.5}),('4017',{'DS_MIN':0,'DS_MAX':2}),('4018',{'sta.gamma.shapek':2,'sta.weibull.scalelambda':3})]:
            r=analyze(id,d,{**opts,**params});self.assertTrue(np.isfinite(np.asarray(r['tables'][0]['rows'],float)).all())

    def test_live_weibull_reference_quantiles_and_perpendicular_deviation(self):
        d=data(['x'],[[1],[2],[3],[5],[8]])
        r=analyze('4018',d,{'columns':['x'],'sta.distr.params.estimate.opt':False,'sta.gamma.shapek':2,'sta.weibull.scalelambda':3})
        expected=[1.0680661733957755,1.8257502826706746,2.497663833473093,3.2487662808205338,4.376538055660365]
        np.testing.assert_allclose(r['charts'][0]['series'][0]['y'],expected,rtol=1e-10)
        np.testing.assert_allclose(r['charts'][1]['series'][0]['y'],[-.04813005277757221,.12321315674340502,.3552053097864307,1.2383092382743386,2.562174512213948],rtol=1e-10)
        np.testing.assert_allclose(r['charts'][0]['series'][1]['x'],[.30075409004951714,6.4378980788680416],rtol=1e-10)

    def test_box_quantiles_whiskers_are_serialized(self):
        x=np.array([1,2,3,4,8,20]);d=data(['x'],x[:,None])
        for method in range(9):
            for whisker in range(4):
                r=analyze('4001',d,{'columns':['x'],'sta.percentile.def':str(method),'sta.chart.box.whisker.def':str(whisker),'sta.chart.box.whisker.percentile':10,'sta.chart.legend':False})
                box=r['charts'][0]['series'][0]['box'];row=r['tables'][0]['rows'][0]
                np.testing.assert_allclose([box[k] for k in ['q1','median','q3','low','high']],row[2:]);self.assertFalse(r['charts'][0]['legend'])
                if whisker==1:self.assertEqual([box['low'],box['high']],[1,20])
                if whisker==2:self.assertAlmostEqual(box['low'],x.mean()-x.std(ddof=1))

    def test_scatter_group_and_ellipse_regions(self):
        d=data(['x','y','g'],[[0,1,'a'],[1,0,'a'],[2,3,'a'],[3,2,'a'],[4,2,'b'],[5,4,'b'],[6,3,'b'],[7,6,'b']])
        r=analyze('4002',d,{'x':'x','y':'y','group':'g','charts.scatter.group.plots':'0','charts.ellipses.add':'3','ellipse.values.ui':'90,95','sta.plotxy.reverseaxes':'3'})
        self.assertEqual(len(r['charts']),2)
        for c in r['charts']:
            self.assertEqual(len(c['series']),5);self.assertTrue(c['reverseX']);self.assertTrue(c['reverseY'])
            self.assertTrue(all(s['type']=='line' for s in c['series'][1:]))
        self.assertEqual(len(analyze('4002',d,{'x':'x','y':'y','group':'g','charts.scatter.group.plots':'1'})['charts']),1)

    def test_stem_leaf_spacing_order(self):
        d=data(['x'],[[12],[13],[21]])
        r=analyze('4003',d,{'columns':['x'],'sta.chart.stemleaf.opt.addspaces':False,'sta.chart.stemleaf.opt.reverseorder':True})
        self.assertEqual(r['tables'][0]['rows'],[['2','1'],['1','23']])

    def test_acf_differencing_and_errors(self):
        y=np.arange(1.,31)**2;d=data(['x'],y[:,None]);o={'column':'x','lags':4,'sta.time.acf.ao.3':True,'sta.time.acf.ao.4':2,'sta.time.acf.ao.5':1,'sta.time.acf.ao.2':True,'sta.time.acf.ao.0':False,'sta.time.acf.ao.1':False,'sta.time.acf.ao.6':True}
        r=analyze('1501',d,o);self.assertFalse(r['charts']);np.testing.assert_allclose(np.asarray(r['dataset']['rows'])[:,0],y[2:]-y[:-2]);np.testing.assert_allclose(np.asarray(r['tables'][0]['rows'])[1:,3],np.sqrt((28-np.arange(1,5))/(28*30)))
        other=analyze('1501',d,{**o,'sta.time.acf.ao.6':False});self.assertGreater(other['tables'][0]['rows'][2][3],r['tables'][0]['rows'][2][3])

    def test_spencer_native_padding_preserves_constant_and_cubic_interior(self):
        for mode,width in [('3',15),('4',21)]:
            y=np.arange(35.)**3;d=data(['x'],y[:,None]);r=analyze('1502',d,{'column':'x','MOVING_AVERAGE':mode,'sta.charts.plot':'0'})
            out=np.asarray(r['dataset']['rows'])[:,1];half=width//2
            self.assertTrue(np.isfinite(out).all());np.testing.assert_allclose(out[half:-half],y[half:-half],atol=1e-9)
            constant=analyze('1502',data(['x'],np.ones((5,1))*4),{'column':'x','MOVING_AVERAGE':mode});np.testing.assert_allclose(np.asarray(constant['dataset']['rows'])[:,1],4)

    def test_ma_weights_se_and_residual_plots(self):
        d=data(['x','w'],[[1,1],[3,2],[2,1],[6,None],[5,None],[8,None],[7,None],[9,None]])
        r=analyze('1502',d,{'column':'x','MOVING_AVERAGE':'2','sta.time.wma.weightsvar':'w','sta.charts.plot':'2','report.residuals.plothistogram':True,'report.residuals.plotqq':True,'sta.reg.lin.ao.resorder':True})
        self.assertAlmostEqual(r['dataset']['rows'][2][1],2.25);self.assertEqual(len(r['charts']),4)
        r=analyze('1502',d,{'column':'x','sta.time.ma.showexcelse':True,'sta.time.ma.se_denom':'2'})
        self.assertTrue(np.isfinite(table(r,'Excel')['rows'][2][1]));self.assertTrue(np.isnan(table(r,'Forecast errors')['rows'][2][1]))

    def test_smoothing_initial_values_forecast_and_reports(self):
        d=data(['x'],[[2],[4],[3],[7],[6],[8]])
        for mode,initial in [('0',3),('1',5),('2',2),('3',9)]:
            r=analyze('1522',d,{'column':'x','ts.expsm.inits0':mode,'ts.expsm.inits0.m':2 if mode=='0' else 9,'ts.report.forecast':False,'ts.report.plot.actual_smoothed':False})
            self.assertAlmostEqual(r['tables'][0]['rows'][0][2],initial);self.assertEqual(len(r['tables']),2);self.assertFalse(r['charts'])
        for mode,firstfit in [('0',2.6),('1',2*np.sqrt(2)),('2',-2.8)]:
            r=analyze('1540',d,{'column':'x','sta.time.dp.expsm':mode})
            self.assertAlmostEqual(r['tables'][0]['rows'][0][2],firstfit)
        r=analyze('1540',d,{'column':'x','ts.expsm.init.custom':True,'ts.expsm.inits0':10,'ts.expsm.initt0':2,'ts.report.forecast':True,'ts.report.forecast.n':3})
        self.assertEqual(r['tables'][0]['rows'][0][2],12);self.assertEqual(len(table(r,'Forecast')['rows']),3)

    def test_decomposition_native_smoothing(self):
        y=np.arange(24.)+np.tile([1,-1,2,-2],6);r=analyze('1510',data(['x'],y[:,None]),{'column':'x','period':4,'time.decompose.opt.centerma':True,'time.decompose.opt.printsi':True,'time.sas':True,'time.stc':True,'time.opt.si':'2'})
        rows=np.asarray(r['dataset']['rows']);expected=np.convolve(rows[:,4],[1/9,2/9,3/9,2/9,1/9],'valid')
        np.testing.assert_allclose(rows[2:-2,5],expected);self.assertEqual(len(r['charts']),3);self.assertEqual(len(table(r,'Seasonal indices')['rows']),4)

    def test_unitroot_test_selection_and_separate_terms(self):
        rng=np.random.default_rng(44);y=np.cumsum(rng.normal(size=80));d=data(['x'],y[:,None]);r=analyze('1530',d,{'column':'x','sta.reg.modelsum.opt':True,'sta.time.reg.include__df_adf':'0','sta.time.reg.include__pp':'2','sta.time.reg.include__kpss':'1','sta.time.lag__pp':'1','sta.time.lag__kpss':'0','sta.time.adf.lag.selection':'0'})
        rows=r['tables'][0]['rows'];self.assertEqual([z[0] for z in rows],['ADF','PP','KPSS']);self.assertEqual(rows[0][3],0);self.assertGreater(rows[1][3],rows[2][3]);self.assertEqual(len(r['tables']),7);self.assertEqual(rows[2][3],int(3*np.sqrt(80)/13));self.assertIn(rows[2][2],[.1,.05,.025,.01,0])
        from backend.analyses.advanced_time import unitroots
        r2=analyze('1530',d,{'column':'x','sta.time.test.df-adf':False,'sta.time.test.kpss':False,'sta.plot.series':False});self.assertEqual(r2['tables'][0]['rows'][0][0],'PP');self.assertFalse(r2['charts'])

    def test_survival_codes_unknown_and_plots(self):
        d=data(['t','s'],[[1,'dead'],[2,'alive'],[3,'?'],[4,'dead']]);o={'time':'t','status':'s','sta.surv.code.fail':'dead','sta.surv.code.censor':'alive','sta.surv.roc.code.unknown':'0','sta.charts.showci':True}
        r=analyze('1621',d,o);self.assertEqual(len(r['tables'][0]['rows']),4);self.assertEqual(len(r['charts']),4);self.assertEqual(len(r['charts'][0]['series']),3)
        r=analyze('1621',d,{**o,'sta.surv.roc.code.unknown':'2','sta.surv.lt.report.plot.sdf':False,'sta.surv.lt.report.plot.sdf1m':False,'sta.surv.lt.report.plot.sdflog':False,'sta.surv.lt.report.plot.hazard.cumulative':False});self.assertEqual(len(r['tables'][0]['rows']),3);self.assertFalse(r['charts'])

    def test_native_survival_intervals_and_blank_status(self):
        d=data(['t','s'],[[1,'0'],[2,'01'],[3,'0'],[4,''],[5,None],[6,'1']]);o={'time':'t','status':'s','sta.surv.roc.code.unknown':'0','sta.charts.showci':True}
        km=analyze('1621',d,o)['tables'][0]['rows']
        self.assertEqual([row[0] for row in km],[1,2,3,6]);self.assertTrue(np.isnan(km[0][5]));se=(2/3)*np.sqrt(1/6)
        self.assertAlmostEqual(km[1][5],max(0,2/3-stats.norm.isf(.025)*se));self.assertEqual(km[1][5:],km[2][5:]);self.assertEqual(km[2][5:],km[3][5:])
        na=analyze('1622',d,o)['tables'][0]['rows'];self.assertLess(na[1][-2],0);self.assertEqual(na[1][-2:],na[2][-2:])
        empty=analyze('1621',d,{**o,'sta.surv.code.fail':''});self.assertIn(4,[row[0] for row in empty['tables'][0]['rows']])

    def test_life_table_limits_density_hazard(self):
        d=data(['t','s'],[[1,1],[2,0],[3,1],[5,0]]);r=analyze('1620',d,{'time':'t','status':'s','sta.surv.lt.maxtime.ui':4,'sta.surv.lt.timeintw':2,'sta.surv.lt.plotstaircase':False})
        rows=r['tables'][0]['rows'];self.assertEqual(len(rows),3);self.assertAlmostEqual(rows[0][8],.125);self.assertAlmostEqual(rows[0][9],.25/(2*.875));self.assertEqual(len(r['charts']),5);self.assertEqual([c['type'] for c in r['charts']],['line','line','line','scatter','scatter'])
        np.testing.assert_allclose(np.asarray(rows)[:,7],[.75,.45,.45]);np.testing.assert_allclose(np.asarray(rows)[:,10],[.21650635094610965,.26622359023948267,.26622359023948267]);np.testing.assert_allclose(np.asarray(rows)[:,11],[.10825317547305482,.12399596767637247,0]);np.testing.assert_allclose(np.asarray(rows)[:,12],[.14139190265868384,.24206145913796356,0]);self.assertAlmostEqual(table(r,'Survival summary')['rows'][0][-1],3.6666666666666665)

    def test_roc_strict_and_inclusive_thresholds_with_ci(self):
        d=data(['score','s'],[[1,'n'],[2,'n'],[2,'p'],[3,'p']]);base={'score':'score','status':'s','sta.surv.roc.code.positive.ui':'p','sta.surv.roc.code.negative.ui':'n'}
        for mode,sens,spec in [('0',.5,1),('1',1,.5),('2',.5,0),('3',0,.5)]:
            r=analyze('1610',d,{**base,'sta.surv.roc.threshold.cond':mode});row=next(z for z in table(r,'ROC coordinates')['rows'] if z[0]==2);self.assertEqual(row[1:3],[sens,spec])
        r=analyze('1610',d,{**base,'sta.surv.roc.report.ss.opt':False});self.assertEqual(len(r['tables']),1)

    def test_probit_models_rounding_and_extra_series(self):
        d=data(['dose','events','n'],[[1,0,20],[2,4.2,20],[3,8.2,20],[4,13.2,20],[5,18.2,20],[6,20,20]])
        base={'dose':'dose','events':'events','total':'n','sta.surv.probit.algo':'2','sta.surv.probit.opt0':True,'PROBIT_S_0.N':'dose','PROBIT_S_1.N':'events','PROBIT_S_3.N':'n'}
        r=analyze('1601',d,base);self.assertEqual(len(r['charts']),4);self.assertTrue(all(c['yLabel'].startswith('Probit') for c in r['charts']))
        self.assertAlmostEqual(table(r,'MLE coefficient of cumulation')['rows'][0][2],1);self.assertAlmostEqual(table(r,'LS coefficient of cumulation')['rows'][0][2],1)
        first=table(r,'MLE log10(Dose) adjusted')['rows'];self.assertEqual(first[1][1],4);self.assertAlmostEqual(first[0][3],.25/20)
        r=analyze('1601',d,{**base,'sta.surv.probit.opt.intC':False,'sta.surv.prob_perc_cor':'1'});first=table(r,'MLE log10(Dose) adjusted')['rows'];self.assertEqual(first[1][1],4.2);self.assertAlmostEqual(first[0][3],.49/20)

    def test_repeated_bland_altman_native_variance(self):
        d=data(['a','b','s'],[[3,1,'a'],[5,1,'a'],[7,1,'b'],[9,1,'b'],[11,1,'b']]);r=analyze('1630',d,{'first':'a','second':'b','ba.groups.subject':'s','sta.surv.ba.tablediffaverage.opt':True})
        row=r['tables'][0]['rows'][0];self.assertEqual(row[:3],[2,5,5.5]);within=10/3;between=12.5;expected=between+(1-(1/2+1/3)/2)*within
        self.assertAlmostEqual(row[5],expected);self.assertAlmostEqual(row[6],5.5-stats.norm.ppf(.975)*np.sqrt(expected));self.assertEqual(len(r['tables']),2)

    def test_controlchart_layouts_unequal_and_options(self):
        d=data(['x','g'],[[1,'a'],[3,'a'],[2,'b'],[4,'b'],[6,'b'],[5,'c'],[7,'c']]);base={'columns':['x'],'sta.cc.datalayout':'0','sta.cc.xbar.GROUPS':'g'}
        r=analyze('4103',d,base);self.assertEqual(len(r['tables'][0]['rows']),3);widths=[z[4]-z[3] for z in r['tables'][0]['rows']];self.assertGreater(widths[0],widths[1])
        r=analyze('4103',d,{**base,'sta.cc.uneqgroup.title':'1'});np.testing.assert_allclose([z[4]-z[3] for z in r['tables'][0]['rows']],r['tables'][0]['rows'][0][4]-r['tables'][0]['rows'][0][3])
        d2=data(['x','z'],[[1,4],[2,5],[3,6],[4,8]])
        for mode,fields in [('1',{'columns':['x'],'sta.cc.xbar.d2.subgrsize':2}),('2',{'columns':['x','z']}),('3',{'columns':['x','z']})]:self.assertTrue(analyze('4102',d2,{**fields,'sta.cc.datalayout':mode})['charts'])

    def test_attribute_chart_constant_size_targets_and_tables(self):
        d=data(['c'],[[1],[2],[3],[0]])
        r=analyze('4105',d,{'count_column':'c','sta.cc.subgr_size':10,'sta.cc.p.prop.target.opt':.2,'sta.charts.plot':'0','sta.showstatsfor':'2'});self.assertEqual(len(r['charts']),1);self.assertFalse(r['tables']);np.testing.assert_allclose(r['charts'][0]['series'][1]['y'],.2)
        self.assertTrue(analyze('4107',d,{'count_column':'c','sta.cc.subgr_size':'10'})['tables'])

    def test_cusum_manual_target_vmask_grouping(self):
        d=data(['x','g'],[[1,1],[2,1],[4,2],[5,2],[3,3],[7,3]]);r=analyze('4104',d,{'column':'x','GROUPS':'g','sta.cc.target.auto':False,'sta.cc.target':2,'sta.cc.subgr_center':2,'H':3,'K':.25,'sta.cc.ao.nosigmas':2})
        self.assertEqual(len(r['charts']),1);vmask=r['charts'][0];np.testing.assert_allclose(vmask['series'][0]['y'],[-.5,2,5]);self.assertEqual(len(vmask['series'][1]['x']),3)
        scale=np.std([1,2,4,5,3,7],ddof=1)/np.sqrt(2)
        np.testing.assert_allclose(vmask['series'][2]['y'],2-6*scale+np.arange(3)*.25*scale)
        self.assertEqual(r['tables'][1]['rows'][0][3],2)

    def test_catalog_native_controls_replace_shadowed_aliases(self):
        entries={entry['id']:entry for entry in catalog()}
        for id,keys in {'1620':['width'],'1610':['direction'],'1611':['direction'],'4104':['k','h'],'4102':['sigmas'],'4103':['sigmas'],'4105':['sigmas'],'4107':['sigmas'],'4108':['sigmas']}.items():
            fields={field['key'] for field in entries[id]['fields']}
            self.assertFalse(fields.intersection(keys),id)

    def test_catalog_keys_unique_and_defaults_valid(self):
        for entry in catalog():
            keys=[f['key'] for f in entry['fields']];self.assertEqual(len(keys),len(set(keys)),entry['id'])
            for f in entry['fields']:
                if f['type']=='select':self.assertIn(f['default'],[v['value'] for v in f['options']])

if __name__=='__main__':unittest.main()
