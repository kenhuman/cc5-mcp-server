import sys
from pathlib import Path
import unittest
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'cc5-plugin'))
import fitting

class FittingTests(unittest.TestCase):
    def test_stale_point_cannot_dispatch_mouse_events(self):
        with patch.object(fitting,'refine_state',return_value={'revision':'new'}),patch.object(fitting.headshot,'_qt') as qt:
            with self.assertRaisesRegex(ValueError,'changed'):fitting.move_refine_point('old','p',1,2)
            qt.assert_not_called()

    def test_nonfinite_point_cannot_read_or_mutate_scene(self):
        with patch.object(fitting,'refine_state') as state:
            for value in (float('nan'),float('inf'),True):
                with self.assertRaises(ValueError):fitting.move_refine_point('r','p',value,0)
            state.assert_not_called()

    def test_stale_apply_cannot_click(self):
        with patch.object(fitting,'refine_state',return_value={'revision':'new'}),patch.object(fitting,'widget') as widget:
            with self.assertRaises(ValueError):fitting.refine_action('apply_all','old')
            widget.assert_not_called()

    def test_preview_action_cannot_silently_toggle_to_edit(self):
        button=Mock();button.text.return_value='Edit'
        with patch.object(fitting,'refine_state',return_value={'revision':'r'}),patch.object(fitting,'widget'),patch.object(fitting.headshot,'control',return_value=button):
            with self.assertRaises(ValueError):fitting.refine_action('preview_all','r')
            button.click.assert_not_called()

    def test_sculpt_invalid_region_is_prevalidated(self):
        with patch.object(fitting,'no_modal'),patch.object(fitting,'widget') as widget:
            with self.assertRaises(ValueError):fitting.configure_sculpt({'view':'side','region':'bad'})
            widget.assert_not_called()

    def test_refinement_numeric_bounds_prevalidated(self):
        state={'revision':'r','numbers':{'qtRotateXSlider':{'minimum':-100,'maximum':100,'visible':True,'enabled':True,'integer':False}}}
        spin=Mock()
        with patch.object(fitting,'refine_state',return_value=state),patch.object(fitting,'widget'),patch.object(fitting,'refine_spins',return_value={'qtRotateXSlider':(spin,[])}):
            with self.assertRaises(ValueError):fitting.configure_refine('r',{'qtRotateXSlider':101})
            spin.setValue.assert_not_called()
