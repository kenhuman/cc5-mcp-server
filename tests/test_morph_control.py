import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cc5-plugin'))
import morph_control as m

class MorphTests(unittest.TestCase):
    def setUp(self):
        self.weights={'a':0.2,'b':0.3}
        self.comp=Mock()
        self.comp.GetShapingMorphCatergoryNames.return_value=['Head']
        self.comp.GetShapingMorphIDs.return_value=['a','b']
        self.comp.GetShapingMorphDisplayNames.return_value=['A','B']
        self.comp.GetShapingMorphMinMax.side_effect=lambda mid:(0,1) if mid=='a' else (-0.5,1)
        self.comp.GetShapingMorphWeight.side_effect=self.weights.__getitem__
        self.status=Mock();self.status.IsError.return_value=False
        def put(mid,value):self.weights[mid]=value;return self.status
        self.comp.SetShapingMorphWeight.side_effect=put
        self.avatar=Mock();self.avatar.GetID.return_value=7;self.avatar.GetName.return_value='Test'
        self.avatar.GetAvatarShapingComponent.return_value=self.comp
        self.native=types.SimpleNamespace(RGlobal=Mock(),RScene=Mock(),EObjectModifiedType_Attribute=1)
        self.native.RScene.GetAvatars.return_value=[self.avatar]
        p=patch.dict(sys.modules,{'RLPy':self.native});p.start();self.addCleanup(p.stop)

    def test_native_range_and_nonfinite_rejected_before_mutation(self):
        for value in (-0.1,float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):m.apply([{'morph_id':'a','value':value}])
        self.comp.SetShapingMorphWeight.assert_not_called()

    def test_unknown_duplicate_and_stale_are_rejected(self):
        cases=[[{'morph_id':'missing','value':0}],
            [{'morph_id':'a','value':0},{'morph_id':'a','value':1}],
            [{'morph_id':'a','value':0.4,'expected_value':0.9}]]
        for case in cases:
            with self.assertRaises(ValueError):m.apply(case)
        self.comp.SetShapingMorphWeight.assert_not_called()

    def test_apply_and_restore_exact_snapshot(self):
        saved=m.snapshot()['snapshot']
        result=m.apply([{'morph_id':'a','value':0.5}])
        self.assertTrue(result['success']);self.assertEqual(result['changes'][0]['actual'],0.5)
        self.assertTrue(m.restore(saved)['success']);self.assertEqual(self.weights,{'a':0.2,'b':0.3})

    def test_linked_slider_readback_mismatch_rolls_back(self):
        def put(mid,value):
            self.weights[mid]=value
            if mid=='b' and value==0.7:self.weights['a']=0.8
            return self.status
        self.comp.SetShapingMorphWeight.side_effect=put
        result=m.apply([{'morph_id':'a','value':0.5},{'morph_id':'b','value':0.7}])
        self.assertFalse(result['success']);self.assertTrue(result['rollback_complete'])
        self.assertEqual(self.weights,{'a':0.2,'b':0.3})

    def test_wrong_avatar_snapshot_refused(self):
        saved=m.snapshot()['snapshot'];saved['avatar_id']='wrong'
        with self.assertRaises(ValueError):m.restore(saved)
        self.comp.SetShapingMorphWeight.assert_not_called()

    def test_multiple_avatars_require_exact_id(self):
        other=Mock();other.GetID.return_value=8
        self.native.RScene.GetAvatars.return_value=[self.avatar,other]
        with self.assertRaises(ValueError):m.snapshot()
        self.assertEqual(m.snapshot('7')['snapshot']['avatar_id'],'7')

    def test_native_swig_pair_uses_fields_not_iterator(self):
        self.comp.GetShapingMorphMinMax.side_effect=lambda mid:types.SimpleNamespace(first=-0.5,second=1.0)
        self.assertEqual(m.catalog()['morphs'][0]['minimum'],-0.5)

    def test_failed_restore_is_explicit(self):
        failed=Mock();failed.IsError.return_value=True
        def put(mid,value):
            if value==0.5:self.weights[mid]=0.6;return failed
            return failed
        self.comp.SetShapingMorphWeight.side_effect=put
        result=m.apply([{'morph_id':'a','value':0.5}])
        self.assertFalse(result['success']);self.assertFalse(result['rollback_complete'])
