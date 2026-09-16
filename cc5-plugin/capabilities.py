"""Inspect already-loaded modules only; no plugin loading or native operations."""
import sys


def get_capabilities():
    rlpy = sys.modules.get('RLPy')
    rlpy2 = sys.modules.get('RLPy2')
    return {
        'python': sys.version,
        'modules_loaded': {'RLPy': rlpy is not None, 'RLPy2': rlpy2 is not None},
        'symbols_present': {
            'RLPy.RHeadshot': 'RHeadshot' in vars(rlpy) if rlpy else False,
            'RLPy2.Headshot3': 'Headshot3' in vars(rlpy2) if rlpy2 else False,
            'RLPy.RExportFbxSetting': 'RExportFbxSetting' in vars(rlpy) if rlpy else False,
        },
        'qualification': {
            'headshot_front_side_generation': 'named_Qt_dialog_adapter_live_verified_front_side_hair_7_tabs_type_and_photo_body',
            'headshot_legacy_RLPy': 'unavailable_HeadshotInterface_null_lookup_on_CC5_with_Headshot3_only',
            'project_save_reopen': 'single_HS3_neutral_lab_API_save_fresh_process_GUI_reopen_verified',
            'blender_export': 'experimental_not_roundtrip_qualified',
            'measured_height_adjustment': 'blocked_pending_proportion_API_validation',
            'hair_generation': 'external_Blender_workflow',
        },
        'note': 'Symbol presence does not prove that calling the interface is safe or supported.',
    }
