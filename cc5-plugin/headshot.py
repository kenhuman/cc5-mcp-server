"""Headshot 3 Generate Character dialog adapter, using named Qt controls.

Uses the real dialog for options absent from RLPy2. Never invokes diffusion tools.
All functions must run on CC5's GUI thread.
"""
import hashlib
import json
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

RESOURCE = ':/plugin/CCHeadshot3/ccHeadShotAIPhoto.ui'
TABS = dict(zip(('face','forehead','cheeks','chin','eyes','nose','ears'),
    ('qtFaceDepthPresetTab','qtForeheadPresetTab','qtCheekPresetTab','qtChinPresetTab',
     'qtEyePresetTab','qtNosePresetTab','qtEarPresetTab')))
BODY = {
    'mode': {'type':'qtCreateBodyByTypeRadioButton','photo':'qtCreateBodyByPhotoRadioButton'},
    'type': {n:'qtBody'+q+'ToolBtn' for n,q in [('current','Current'),('neutral','Neutral'),('male','Male'),('female','Female'),('child','Kid'),('baby','Baby')]},
    'age': {n:'qtBodyAge'+q+'RadioButton' for n,q in [('adult','Adult'),('elder','Elder'),('teen','Teen')]},
    'shape': {n:'qtBodySlider'+q+'RadioButton' for n,q in [('normal','Normal'),('skinny','Skinny'),('heavy','Fat'),('strong','Strong')]},
    'photo_shape': {n:'qtFatPreference'+q+'RadioButton' for n,q in [('average','Average'),('heavy','Fat'),('slim','Thin')]},
    'photo_gender': {'male':'qtGenderPreferenceMaleRadioButton','female':'qtGenderPreferenceFemaleRadioButton'},
    'photo_physique': {'normal':'qtMusclePreferenceNoneRadioButton','muscular':'qtMusclePreferenceMuscleRadioButton'},
}
_prepared = None

def _qt():
    from PySide2 import QtCore, QtGui, QtWidgets
    return QtCore, QtGui, QtWidgets

def dialog(required=True):
    _,_,W = _qt()
    found=[w for w in W.QApplication.allWidgets() if w.metaObject().className()=='IC::CCGenerateCharacterDlg']
    if len(found)!=1:
        if required: raise RuntimeError('Open Headshot Generate Character first; expected one dialog')
        return None
    return found[0]

def owns_modal():
    try: _,_,W=_qt()
    except ImportError: return False
    modal=W.QApplication.activeModalWidget()
    return modal is not None and modal.metaObject().className()=='IC::CCGenerateCharacterDlg' and modal.objectName()==RESOURCE

def control(d,name):
    C,_,_=_qt()
    matches=d.findChildren(C.QObject,name)
    if len(matches)!=1: raise RuntimeError('Unsupported CC5 dialog layout: '+name)
    return matches[0]

def catalog():
    C,_,_=_qt()
    f=C.QFile(RESOURCE)
    if not f.open(C.QIODevice.ReadOnly): raise RuntimeError('Headshot 3 UI resource unavailable')
    raw=bytes(f.readAll()); f.close()
    root=ET.fromstring(raw)
    parents={c:p for p in root.iter() for c in p}
    result={}
    live=dialog(False)
    for tab,name in TABS.items():
        node=root.find('.//widget[@name="'+name+'"]')
        if node is None: raise RuntimeError('Missing Headshot tab: '+tab)
        options=[]
        for b in node.findall('.//widget[@class="QToolButton"]'):
            layout=parents[parents[b]]
            labels=layout.findall('./item/widget[@class="QLabel"]/property[@name="text"]/string')
            if len(labels)!=1: raise RuntimeError('Unrecognized preset label: '+b.get('name'))
            label=' '.join(''.join(labels[0].itertext()).split())
            key=re.sub(r'[^a-z0-9]+','_',label.lower()).strip('_')
            if live:
                label_widget=layout.find('./item/widget[@class="QLabel"]')
                label=' '.join(control(live,label_widget.get('name')).text().split())
            options.append({'id':key,'label':label,'control':b.get('name'),
                'exclusive_group':b.findtext('attribute[@name="buttonGroup"]/string')})
        result[tab]=options
    return {'tabs':result,'body':{k:list(v) for k,v in BODY.items()},
            'generate_hair':True,'references':['front','side','body'],
            'adapter':'Headshot3 named Qt controls','layout_sha256':hashlib.sha256(raw).hexdigest()}

def open_dialog(front=None):
    C,_,W=_qt()
    d=dialog(False)
    if d and d.isVisible(): return {'success':True,'state':'open'}
    if W.QApplication.activeModalWidget(): raise RuntimeError('Close the unrelated modal dialog first')
    buttons=[w for w in W.QApplication.allWidgets() if w.objectName()=='qtRegenerateToolButton' and w.isVisible()]
    if len(buttons)!=1: raise RuntimeError('Show the Headshot 3 IMAGE panel for the current character first')
    if buttons[0].isEnabled():
        C.QTimer.singleShot(0,buttons[0].click)
    else:
        if not front: raise ValueError('front image required to initialize the Headshot dialog')
        path=_image(front)
        panel=buttons[0].parent()
        labels=[w for w in panel.findChildren(W.QWidget) if w.metaObject().className()=='QItemLabel' and w.isVisible()]
        if len(labels)!=1: raise RuntimeError('Expected one front-image target, found: '+str([(w.objectName()) for w in labels]))
        C.QTimer.singleShot(0,lambda:drop_image(panel,labels[0].objectName(),path))
    return {'success':True,'state':'opening','next':'Call get_headshot_settings before configuring'}

def state():
    d=dialog(); cat=catalog()
    return {'success':True,'open':d.isVisible(),'generate_hair':control(d,'qtGenerateHairCheckBox').isChecked(),
        'face':{tab:[o['id'] for o in opts if control(d,o['control']).isChecked()] for tab,opts in cat['tabs'].items()},
        'body':{key:[value for value,name in mapping.items() if control(d,name).isChecked()] for key,mapping in BODY.items()},
        'enabled':{name:control(d,name).isEnabled() for mapping in BODY.values() for name in mapping.values()},
        'prepared_id':_prepared['id'] if _prepared else None}

def _image(path):
    _,G,_=_qt()
    p=Path(path)
    if not p.is_absolute() or not p.is_file(): raise ValueError('Reference must be an existing absolute local file')
    if G.QImage(str(p)).isNull(): raise ValueError('Cannot decode reference image: '+str(p))
    return str(p.resolve())

def drop_image(d,name,path):
    C,G,W=_qt(); target=control(d,name)
    before=target.pixmap().cacheKey() if target.pixmap() else None
    mime=C.QMimeData(); mime.setUrls([C.QUrl.fromLocalFile(path)])
    point=C.QPoint(10,10)
    enter=G.QDragEnterEvent(point,C.Qt.CopyAction,mime,C.Qt.LeftButton,C.Qt.NoModifier)
    W.QApplication.sendEvent(target,enter)
    if not enter.isAccepted(): raise RuntimeError('Headshot did not accept an image drop on '+name)
    drop=G.QDropEvent(C.QPointF(point),C.Qt.CopyAction,mime,C.Qt.LeftButton,C.Qt.NoModifier)
    W.QApplication.sendEvent(target,drop)
    after=target.pixmap().cacheKey() if target.pixmap() else None
    if not drop.isAccepted() and after==before: raise RuntimeError('Headshot rejected reference on '+name)

def configure(params):
    global _prepared
    d=dialog(); cat=catalog()
    if not d.isVisible(): raise RuntimeError('Generate Character dialog must be open')
    if set(params)-{'front','side','body_image','generate_hair','face','body'}: raise ValueError('Unknown Headshot parameter')
    if type(params.get('generate_hair')) is not bool: raise ValueError('generate_hair must be boolean')
    images={k:_image(v) for k,v in params.items() if k in ('front','side','body_image') and v is not None}
    if 'front' not in images: raise ValueError('front reference is required')
    face=params.get('face',{})
    if set(face)-set(TABS): raise ValueError('Unknown face tab')
    chosen=[]
    for tab,ids in face.items():
        if not isinstance(ids,list) or len(ids)!=len(set(ids)): raise ValueError('Face options must be unique lists')
        options={o['id']:o for o in cat['tabs'][tab]}; groups=set()
        for key in ids:
            if key not in options: raise ValueError('Unknown '+tab+' option: '+str(key))
            o=options[key]; group=o['exclusive_group']
            if group and group in groups: raise ValueError('Conflicting exclusive options in '+tab)
            if group: groups.add(group)
            chosen.append((tab,o['control']))
    body=params.get('body',{})
    if set(body)-set(BODY): raise ValueError('Unknown body field')
    for key,value in body.items():
        if value not in BODY[key]: raise ValueError('Invalid body '+key)
    mode=body.get('mode','type')
    if mode=='photo' and 'body_image' not in images: raise ValueError('Photo body mode needs body_image')
    if mode=='type' and any(k.startswith('photo_') for k in body): raise ValueError('Photo settings require photo body mode')
    if mode=='photo' and any(k in body for k in ('type','age','shape')): raise ValueError('Type settings require type body mode')
    # Resolve every named control before changing the dialog.
    for name in [n for _,n in chosen]+['qtClearSelectedPresetToolButton','qtGenerateHairCheckBox']+[n for m in BODY.values() for n in m.values()]: control(d,name)
    _prepared=None
    control(d,'qtStageHeadPushButton').click()
    for key,name in [('front','qtFrontHeadLabel'),('side','qtSideHeadLabel')]:
        if key in images: drop_image(d,name,images[key])
    if 'side' not in images:
        from PySide2.QtTest import QTest
        C,_,_=_qt()
        QTest.mouseClick(control(d,'qtSideHeadLabel'),C.Qt.LeftButton)
        delete=control(d,'qtDeleteHeadImageToolButton')
        if delete.isEnabled(): delete.click()
    control(d,'qtClearSelectedPresetToolButton').click()
    for tab,name in chosen:
        control(d,'qtFaceFeaturePresetTabWidget').setCurrentWidget(control(d,TABS[tab]))
        c=control(d,name)
        if not c.isEnabled(): raise ValueError('Face option disabled: '+name)
        if not c.isChecked(): c.click()
        if not c.isChecked(): raise RuntimeError('Face option did not apply: '+name)
    control(d,'qtGenerateHairCheckBox').setChecked(params['generate_hair'])
    control(d,'qtStageBodyushButton').click()
    control(d,BODY['mode'][mode]).click()
    if 'body_image' in images: drop_image(d,'qtBodyPhotoLabel',images['body_image'])
    for key,value in body.items():
        if key=='mode': continue
        c=control(d,BODY[key][value])
        if not c.isEnabled(): raise ValueError('Body option disabled for this combination: '+key+'='+value)
        c.click()
        if not c.isChecked(): raise RuntimeError('Body option did not apply: '+key)
    _prepared={'id':uuid.uuid4().hex,'references':images,'settings':params,'fingerprint':_fingerprint(d)}
    return dict(state(),references=images)

def generate(prepared_id):
    global _prepared
    d=dialog()
    if not _prepared or _prepared['id']!=prepared_id: raise ValueError('Prepare settings first; stale or missing prepared_id')
    if _prepared['fingerprint']!=_fingerprint(d): raise ValueError('Headshot settings changed since preparation; configure again')
    C,_,_= _qt()
    job=_prepared; _prepared=None
    if not C.QMetaObject.invokeMethod(d,'GenerateHead',C.Qt.DirectConnection): raise RuntimeError('GenerateHead slot unavailable')
    import RLPy
    return {'success':not d.isVisible(),'state':'returned' if not d.isVisible() else 'dialog_still_open',
        'references':job['references'],'settings':job['settings'],
        'avatars':[a.GetName() for a in RLPy.RScene.GetAvatars()]}

def _fingerprint(d):
    s=state(); s.pop('prepared_id',None); s.pop('enabled',None)
    for name in ('qtFrontHeadLabel','qtSideHeadLabel','qtBodyPhotoLabel'):
        pix=control(d,name).pixmap(); s[name]=pix.cacheKey() if pix else None
    return json.dumps(s,sort_keys=True)
