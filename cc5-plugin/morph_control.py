"""Deterministic anatomy morph access. Call on the CC5 main thread only."""
import math


def context(avatar_id=None):
    import RLPy
    avatars = list(RLPy.RScene.GetAvatars())
    if avatar_id is not None:
        avatars = [a for a in avatars if str(a.GetID()) == str(avatar_id)]
    if len(avatars) != 1:
        raise ValueError('Specify avatar_id; expected exactly one matching avatar')
    avatar = avatars[0]
    comp = avatar.GetAvatarShapingComponent()
    if comp is None: raise ValueError('Avatar has no shaping component')
    return avatar, comp


def catalog(avatar_id=None, query='', category=''):
    avatar, comp = context(avatar_id)
    entries = {}
    for cat in comp.GetShapingMorphCatergoryNames():
        if category.lower() not in cat.lower(): continue
        ids = comp.GetShapingMorphIDs(cat)
        names = comp.GetShapingMorphDisplayNames(cat)
        for i, mid in enumerate(ids):
            name = names[i] if i < len(names) else mid
            if query.lower() not in (name + ' ' + mid).lower(): continue
            if mid not in entries:
                pair = comp.GetShapingMorphMinMax(mid)
                lo, hi = (pair.first, pair.second) if hasattr(pair, 'first') else pair
                entries[mid] = {'morph_id': mid, 'display_name': name, 'minimum': lo,
                               'maximum': hi, 'value': comp.GetShapingMorphWeight(mid), 'categories': []}
            entries[mid]['categories'].append(cat)
    return {'success': True, 'avatar_id': str(avatar.GetID()), 'avatar_name': avatar.GetName(),
            'morphs': list(entries.values())}


def snapshot(avatar_id=None, morph_ids=None):
    data = catalog(avatar_id)
    entries = {m['morph_id']: m for m in data['morphs']}
    if morph_ids is not None:
        if not isinstance(morph_ids, list) or len(morph_ids) != len(set(morph_ids)):
            raise ValueError('morph_ids must be a unique list')
        if set(morph_ids)-set(entries): raise ValueError('Unknown morph ID')
        entries = {mid: entries[mid] for mid in morph_ids}
    return {'success': True, 'snapshot': {'version': 1, 'avatar_id': data['avatar_id'],
        'avatar_name': data['avatar_name'],
        'morphs': [{'morph_id': mid, 'value': m['value']} for mid, m in entries.items()]}}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Morph weights must be finite numbers')
    return float(value)

def refresh():
    import fitting
    fitting.no_modal()
    from PySide2.QtWidgets import QApplication,QAction
    from PySide2.QtCore import QTimer
    matches={}
    roots=list(QApplication.topLevelWidgets())
    for w in roots:
        for action in w.findChildren(QAction):
            if action.text().replace('&','').strip()=='Refresh Sliders':matches[action.objectName()]=action
    if len(matches)!=1:raise RuntimeError('Refresh Sliders action not available')
    action=list(matches.values())[0]
    if not action.isEnabled():raise RuntimeError('Refresh Sliders disabled')
    action.trigger()
    return {'success':True,'state':'refresh_requested'}

def apply(morphs, avatar_id=None):
    import RLPy
    if 'PySide2' in __import__('sys').modules:
        import fitting
        fitting.no_modal()
    avatar, comp = context(avatar_id)
    if not isinstance(morphs, list) or not 1 <= len(morphs) <= 10000:
        raise ValueError('Provide 1..10000 morph values')
    known = {m['morph_id']: m for m in catalog(str(avatar.GetID()))['morphs']}
    seen = set(); changes = []
    for entry in morphs:
        if not isinstance(entry, dict) or set(entry)-{'morph_id', 'id', 'value', 'expected_value'}:
            raise ValueError('Invalid morph entry')
        mid = entry.get('morph_id', entry.get('id'))
        if mid not in known or mid in seen: raise ValueError('Unknown or duplicate morph ID: '+str(mid))
        seen.add(mid)
        value = number(entry.get('value')); info = known[mid]
        if not info['minimum'] <= value <= info['maximum']:
            raise ValueError('Out of native range for '+mid+': '+str((info['minimum'], info['maximum'])))
        before = info['value']
        if 'expected_value' in entry and not math.isclose(before, number(entry['expected_value']), abs_tol=1e-6):
            raise ValueError('Morph changed since readback: '+mid)
        changes.append({'morph_id': mid, 'before': before, 'requested': value})
    attempted = []; error = None; rollback = []
    RLPy.RGlobal.BeginAction('MCP Set Anatomy Morphs')
    try:
        for item in changes:
            attempted.append(item)
            status = comp.SetShapingMorphWeight(item['morph_id'], item['requested'])
            if status.IsError(): raise RuntimeError('Native setter failed: '+item['morph_id'])
        RLPy.RGlobal.ObjectModified(avatar, RLPy.EObjectModifiedType_Attribute)
        # Read all values after all setters, so linked sliders are detected too.
        for item in changes:
            item['actual'] = comp.GetShapingMorphWeight(item['morph_id'])
            if not math.isclose(item['actual'], item['requested'], abs_tol=1e-6):
                raise RuntimeError('Native readback mismatch: '+item['morph_id'])
    except Exception as exc:
        error = str(exc)
        for item in reversed(attempted):
            try:
                status = comp.SetShapingMorphWeight(item['morph_id'], item['before'])
                rollback.append({'morph_id': item['morph_id'], 'native_error': bool(status.IsError())})
            except Exception as restore_error:
                rollback.append({'morph_id': item['morph_id'], 'error': str(restore_error)})
        RLPy.RGlobal.ObjectModified(avatar, RLPy.EObjectModifiedType_Attribute)
        for item in rollback:
            before = known[item['morph_id']]['value']
            item['actual'] = comp.GetShapingMorphWeight(item['morph_id'])
            item['restored'] = not item.get('error') and not item.get('native_error') and math.isclose(item['actual'], before, abs_tol=1e-6)
    finally:
        RLPy.RGlobal.EndAction()
    return {'success': error is None, 'avatar_id': str(avatar.GetID()), 'changes': changes,
            'error': error, 'rollback': rollback,
            'rollback_complete': all(r.get('restored', False) for r in rollback) if error else None}


def restore(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('version') != 1 or not snapshot.get('avatar_id'):
        raise ValueError('Invalid morph snapshot')
    return apply(snapshot['morphs'], snapshot['avatar_id'])
