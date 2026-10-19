"""Global preference behavior at the real worker boundary."""
import unittest
from copy import deepcopy
from unittest.mock import patch
import numpy as np
from backend.worker import dispatch
from backend.preferences import apply_preferences


class PreferenceTests(unittest.TestCase):
    def test_casewise_deletes_only_selected_inputs(self):
        data={'columns':['x','y','unused'],'rows':[[1,10,None],[2,None,None],[3,30,None],[4,40,None]]}
        def run(mode):
            return dispatch('analyze',{'analysis':'1001','data':data,'options':{'columns':['x','y'],'missingValues':mode}})
        auto=run('automatic');case=run('casewise')
        self.assertFalse(any('Global casewise' in n for n in auto['notes']))
        self.assertTrue(any('removed 1 rows' in n for n in case['notes']))
        clean,_,deleted=apply_preferences(data,{'columns':['x'],'missingValues':'casewise'},{'fields':[{'key':'columns','type':'columns'}]})
        self.assertEqual(len(clean['rows']),4);self.assertEqual(deleted,0)

    def test_seed_precedence_and_zero_entropy(self):
        data={'columns':['x'],'rows':[[1]]}
        self.assertEqual(apply_preferences(data,{'randomSeed':73},{})[1]['seed'],73)
        self.assertEqual(apply_preferences(data,{'randomSeed':73,'seed':0},{})[1]['seed'],0)
        with patch('backend.preferences.secrets.randbits',return_value=845):
            self.assertEqual(apply_preferences(data,{'randomSeed':0},{})[1]['seed'],845)
        for bad in [-1,True,1.5,2**32]:
            with self.assertRaises(ValueError):apply_preferences(data,{'randomSeed':bad},{})

    def test_empty_text_is_missing_but_zero_is_not(self):
        data={'columns':['x','factor'],'rows':[[0,'a'],[1,' '],[2,'b'],[None,'c']]}
        clean,_,deleted=apply_preferences(data,{'columns':['x','factor'],'missingValues':'casewise'}, {})
        self.assertEqual(clean['rows'],[[0,'a'],[2,'b']]);self.assertEqual(deleted,2)

    def test_auxiliary_weight_vector_never_truncates_observations(self):
        data={'columns':['x','w'],'rows':[[1,1],[2,2],[3,None],[4,None],[5,None]]}
        result=dispatch('analyze',{'analysis':'1502','data':data,'options':{'column':'x','MOVING_AVERAGE':'0','sta.time.wma.weightsvar':'w','missingValues':'casewise'}})
        self.assertFalse(any('Global casewise' in n for n in result['notes']))
        entry={'id':'1130','fields':[{'key':'columns','type':'columns'},{'key':'initial_centers','type':'columns'}]}
        clean,_,deleted=apply_preferences(data,{'columns':['x'],'initial_centers':['w'],'missingValues':'casewise'},entry)
        self.assertEqual(deleted,0);self.assertEqual(len(clean['rows']),5)

    def test_casewise_deletion_preserves_independent_moving_average_weights(self):
        data={'columns':['x','w'],'rows':[[1,1],[None,2],[3,None],[4,None],[5,None]]}
        original=deepcopy(data)
        result=dispatch('analyze',{'analysis':'1502','data':data,'options':{
            'column':'x','MOVING_AVERAGE':'2','sta.time.wma.weightsvar':'w','missingValues':'casewise'}})
        np.testing.assert_allclose(result['dataset']['rows'],
            [[1,np.nan],[3,7/3],[4,11/3],[5,14/3]],equal_nan=True)
        self.assertEqual(data,original)

    def test_casewise_deletion_preserves_centers_and_aligns_case_labels(self):
        data={'columns':['x','y','ix','iy','label'],'rows':[
            [0,0,0,0,'a'],[None,0,10,10,'excluded'],[1,0,None,None,'b'],
            [0,1,None,None,'c'],[10,10,None,None,'d'],[11,10,None,None,'e'],[10,11,None,None,'f']]}
        result=dispatch('analyze',{'analysis':'1130','data':data,'options':{
            'columns':['x','y'],'clusters':2,'initial_centers':['ix','iy'],
            'sta.in.caselabels':'label','missingValues':'casewise'}})
        tables={table['title']:table for table in result['tables']}
        self.assertEqual(tables['Initial cluster centers']['rows'],[[1,0,0],[2,10,10]])
        self.assertEqual([row[0] for row in tables['Membership']['rows']],list('abcdef'))
        np.testing.assert_allclose([row[1:] for row in tables['Cluster centers (analysis scale)']['rows']],
            [[1/3,1/3],[31/3,31/3]])

    def test_casewise_deletion_keeps_bin_vector_longer_than_retained_data(self):
        data={'columns':['x','edges'],'rows':[[1,0],[None,2],[5,4],[None,6]]}
        result=dispatch('analyze',{'analysis':'1015','data':data,'options':{
            'columns':['x'],'sta.bst.freq.bins_var':'edges',
            'sta.bst.ds.hist.bins0':False,'missingValues':'casewise'}})
        np.testing.assert_allclose([row[:3] for row in result['tables'][0]['rows']],
            [[0,2,1],[2,4,0],[4,6,1]])

    def test_shared_observation_and_auxiliary_columns_have_independent_alignment(self):
        data={'columns':['x','w','label'],'rows':[[1,1,'a'],[None,2,'b'],[3,3,'c']]}
        entry={'fields':[{'key':'columns','type':'columns'},
            {'key':'initial_centers','type':'columns'}, {'key':'sta.in.caselabels','type':'column'}]}
        options={'columns':['x','w'],'initial_centers':['w'],'sta.in.caselabels':'label','missingValues':'casewise'}
        clean,mapped,deleted=apply_preferences(data,options,entry)
        values={name:[row[index] for row in clean['rows']] for index,name in enumerate(clean['columns'])}
        self.assertEqual(deleted,1)
        self.assertEqual(values['x'],[1,3,None]);self.assertEqual(values['w'],[1,3,None])
        self.assertEqual(values['label'],['a','c',None])
        self.assertEqual(values[mapped['initial_centers'][0]],[1,2,3])
        self.assertEqual(options['initial_centers'],['w'])
        # Preserve invalid selections for the analysis validator to reject.
        options['initial_centers']=['w','unknown']
        self.assertEqual(apply_preferences(data,options,entry)[1]['initial_centers'][1],'unknown')

    def test_inactive_subgroup_column_is_excluded(self):
        data={'columns':['x','group'],'rows':[[1,None],[2,'a'],[3,None]]}
        entry={'id':'4102','fields':[{'key':'columns','type':'columns'},{'key':'sta.cc.xbar.GROUPS','type':'column'}]}
        clean,_,deleted=apply_preferences(data,{'columns':['x'],'sta.cc.xbar.GROUPS':'group','sta.cc.datalayout':'3','missingValues':'casewise'},entry)
        self.assertEqual(deleted,0)
        clean,_,deleted=apply_preferences(data,{'columns':['x'],'sta.cc.xbar.GROUPS':'group','sta.cc.datalayout':'0','missingValues':'casewise'},entry)
        self.assertEqual(deleted,2)
