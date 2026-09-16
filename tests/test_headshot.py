"""Validation tests without starting CC5 or importing Qt."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cc5-plugin'))
import headshot

class HeadshotValidation(unittest.TestCase):
    def setUp(self):
        self.dialog=Mock(); self.dialog.isVisible.return_value=True
        self.patches=[patch.object(headshot,'dialog',return_value=self.dialog),
            patch.object(headshot,'catalog',return_value={'tabs':{'face':[
                {'id':'oval','control':'oval','exclusive_group':'one'},
                {'id':'round','control':'round','exclusive_group':'one'}]}}),
            patch.object(headshot,'_image',side_effect=lambda p:p)]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])

    def test_conflicting_presets_fail_before_mutation(self):
        with patch.object(headshot,'control') as control:
            with self.assertRaisesRegex(ValueError,'Conflicting'):
                headshot.configure({'front':'G:/front.png','generate_hair':False,'face':{'face':['oval','round']}})
            control.assert_not_called()

    def test_photo_mode_requires_reference(self):
        with patch.object(headshot,'control') as control:
            with self.assertRaisesRegex(ValueError,'body_image'):
                headshot.configure({'front':'G:/front.png','generate_hair':False,'body':{'mode':'photo'}})
            control.assert_not_called()

    def test_hair_requires_boolean(self):
        with self.assertRaisesRegex(ValueError,'boolean'):
            headshot.configure({'front':'G:/front.png','generate_hair':'false'})

    def test_stale_generation_cannot_call_native_code(self):
        with patch.object(headshot,'_prepared',{'id':'one','fingerprint':'old'}),patch.object(headshot,'_fingerprint',return_value='changed'),patch.object(headshot,'_qt') as qt:
            with self.assertRaisesRegex(ValueError,'changed'):
                headshot.generate('one')
            qt.assert_not_called()

    def test_duplicate_request_token_cannot_generate_again(self):
        with patch.object(headshot,'_prepared',None),patch.object(headshot,'_qt') as qt:
            with self.assertRaises(ValueError):headshot.generate('consumed')
            qt.assert_not_called()

if __name__=='__main__':unittest.main()
