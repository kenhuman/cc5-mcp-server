"""Headshot fitting controls. GUI-thread only; no likeness decisions or diffusion."""
import math
import hashlib
import json
import headshot

PANEL = 'IC::CCreateHeadSection'
REFINE = 'IC::CCCreateHeadStageTwoDlg'
REGIONS = ('contour', 'face', 'eyes', 'nose', 'mouth', 'ears')
_points = {}
_point_revision = None
_qt_roots = []
SCULPT = {'enabled':'qtViewportMorphLevelGroupBox', 'symmetrical':'qtSymmetricalCheckBox',
    'show_area':'qtShowAreaCheckBox', 'dark_mode':'qtAreaDarkColorCheckBox',
    'zoom_to_area':'qtAutoCamCheckBox'}
REFINE_NUMBERS=('qtPointSizeCombospinbox','qtPictureOpacityCombospinbox','qtPreviewPointSizeCombospinbox',
    'qtPreviewPictureOpacityCombospinbox','qtRotateXSlider','qtTranslateXSlider','qtTranslateZSlider','qtTranslateYSlider')
REFINE_TOGGLES={'mirror':'qtMirrorToolButton','skull':'qtSkullToolButton','eyes':'qtEyeToolButton',
    'nose':'qtNoseToolButton','lips':'qtLipToolButton'}

def refine_spins(d):
    _,_,W=headshot._qt();result={}
    for name in REFINE_NUMBERS:
        container=headshot.control(d,name)
        spins=container.findChildren(W.QAbstractSpinBox)
        if len(spins)!=1:raise RuntimeError('Unsupported numeric control layout: '+name)
        spin=spins[0]
        labels=[w.text() for w in container.findChildren(W.QLabel) if w.text()]
        result[name]=(spin,labels)
    return result

def widget(cls, required=True):
    global _qt_roots
    _,_,W=headshot._qt()
    # Retain top-level wrappers while using descendants: temporary PySide owners
    # can otherwise invalidate borrowed child wrappers between calls.
    _qt_roots=list(W.QApplication.topLevelWidgets())
    found=[w for w in W.QApplication.allWidgets() if w.metaObject().className()==cls]
    if len(found)!=1:
        if required:raise RuntimeError('Expected one '+cls)
        return None
    return found[0]

def no_modal():
    _,_,W=headshot._qt()
    if W.QApplication.activeModalWidget():raise RuntimeError('Close the modal dialog before changing sculpt or morph controls')
    d=widget(REFINE,False)
    if d is not None and d.isVisible():raise RuntimeError('Close face refinement before changing scene or sculpt controls')

def owns_modal():
    try:_,_,W=headshot._qt()
    except ImportError:return False
    modal=W.QApplication.activeModalWidget()
    return modal is not None and modal.metaObject().className()==REFINE

def sculpt_state():
    p=widget(PANEL)
    selected=[]
    for view in ('front','side'):
        for i,region in enumerate(REGIONS,1):
            c=headshot.control(p,'qtMorphLevel%dToolBtn'%i+('_2' if view=='side' else ''))
            if c.isChecked():selected.append({'view':view,'region':region})
    values={key:headshot.control(p,name).isChecked() for key,name in SCULPT.items()}
    return {'success':True,'settings':values,'selected':selected,
            'opacity':headshot.control(headshot.control(p,'qtAreaOpacityCombospinbox'),'qtSpinBox').value()}

def configure_sculpt(settings):
    no_modal()
    if set(settings)-set(SCULPT)-{'view','region','opacity'}:raise ValueError('Unknown sculpt setting')
    for key in set(settings)&set(SCULPT):
        if type(settings[key]) is not bool:raise ValueError(key+' must be boolean')
    if ('view' in settings)!=('region' in settings):raise ValueError('Provide both view and region')
    if settings.get('view','front') not in ('front','side') or settings.get('region','contour') not in REGIONS:
        raise ValueError('Invalid sculpt view or region')
    p=widget(PANEL)
    spin=headshot.control(headshot.control(p,'qtAreaOpacityCombospinbox'),'qtSpinBox')
    if 'opacity' in settings:
        n=settings['opacity']
        if type(n) is not int or not spin.minimum()<=n<=spin.maximum():raise ValueError('Opacity outside native integer range')
    # Enable first to make dependent native controls available, disable last.
    if settings.get('enabled') is True:headshot.control(p,SCULPT['enabled']).setChecked(True)
    if 'region' in settings:
        c=headshot.control(p,'qtMorphLevel%dToolBtn'%(REGIONS.index(settings['region'])+1)+('_2' if settings['view']=='side' else ''))
        if not c.isEnabled():raise ValueError('Enable sculpt mode before choosing a region')
        if not c.isChecked():c.click()
        if not c.isChecked():raise RuntimeError('Sculpt region did not apply')
    for key,name in SCULPT.items():
        if key not in settings or key=='enabled':continue
        c=headshot.control(p,name)
        if not c.isEnabled():raise ValueError('Sculpt setting disabled: '+key)
        c.setChecked(settings[key])
        if c.isChecked()!=settings[key]:raise RuntimeError('Sculpt setting readback mismatch: '+key)
    if 'opacity' in settings:
        if not spin.isEnabled():raise ValueError('Opacity disabled')
        spin.setValue(settings['opacity']);spin.editingFinished.emit()
        if spin.value()!=settings['opacity']:raise RuntimeError('Opacity readback mismatch')
    if settings.get('enabled') is False:headshot.control(p,SCULPT['enabled']).setChecked(False)
    return sculpt_state()

def open_refine(view):
    if view not in ('front','side'):raise ValueError('Invalid view')
    no_modal()
    d=widget(REFINE,False)
    if d and d.isVisible():raise RuntimeError('Close existing refinement before opening another view')
    p=widget(PANEL)
    button=headshot.control(p,'qtLandmarkEditor'+('Side' if view=='side' else '')+'PushButton')
    if not button.isEnabled():raise RuntimeError('Refinement unavailable for this character')
    C,_,_=headshot._qt();C.QTimer.singleShot(0,button.click)
    return {'success':True,'state':'opening','view':view}

def refine_state():
    global _points, _point_revision
    d=widget(REFINE,False)
    if d is None or not d.isVisible():
        _points={};_point_revision=None
        return {'success':True,'open':False}
    C,_,W=headshot._qt()
    import shiboken2
    views={}
    points={}
    for v in d.findChildren(W.QGraphicsView):
        if not v.isVisible():continue
        scene=v.scene()
        rows=[]
        for i,item in enumerate(scene.items() if scene else []):
            if not item.isVisible():continue
            pos=item.scenePos();rect=item.sceneBoundingRect()
            point_id=str(shiboken2.getCppPointer(item)[0])
            points[point_id]=(v.objectName(),item)
            rows.append({'point_id':point_id,'index':i,'type':item.type(),'python_type':type(item).__name__,
                'x':pos.x(),'y':pos.y(),'rect':[rect.x(),rect.y(),rect.width(),rect.height()],
                'movable':bool(item.flags() & W.QGraphicsItem.ItemIsMovable),
                'selectable':bool(item.flags() & W.QGraphicsItem.ItemIsSelectable),
                'data':[str(item.data(k)) for k in range(4)]})
        views[v.objectName()]={'items':rows}
    buttons={w.objectName():{'enabled':w.isEnabled(),'checked':w.isChecked(),'text':w.text()}
        for w in d.findChildren(W.QAbstractButton) if w.isVisible() and w.objectName()}
    import RLPy
    avatar_ids=[str(a.GetID()) for a in RLPy.RScene.GetAvatars()]
    numbers={name:{'value':s.value(),'minimum':s.minimum(),'maximum':s.maximum(),
        'visible':s.isVisible(),'enabled':s.isEnabled(),'labels':labels,'integer':isinstance(s,W.QSpinBox)}
        for name,(s,labels) in refine_spins(d).items()}
    revision=hashlib.sha256(json.dumps([avatar_ids,views,buttons,numbers],sort_keys=True).encode()).hexdigest()
    _points=points;_point_revision=revision
    return {'success':True,'open':True,'views':views,'controls':buttons,'numbers':numbers,'revision':revision,
            'coordinates':'Scene units. Point IDs are valid only in this live dialog; read fresh state after each action.'}

def configure_refine(revision, numbers=None, toggles=None):
    numbers=numbers or {};toggles=toggles or {}
    state=refine_state()
    if state.get('revision')!=revision:raise ValueError('Refinement state changed; read fresh state')
    if set(numbers)-set(REFINE_NUMBERS) or set(toggles)-set(REFINE_TOGGLES):raise ValueError('Unknown refinement setting')
    d=widget(REFINE);spins=refine_spins(d)
    for name,value in numbers.items():
        info=state['numbers'][name]
        if type(value) not in (int,float) or not math.isfinite(value) or not info['minimum']<=value<=info['maximum']:
            raise ValueError('Numeric value outside native range: '+name)
        if info['integer'] and value!=int(value):raise ValueError('Integer required: '+name)
        if not info['enabled'] or not info['visible']:raise ValueError('Numeric setting unavailable: '+name)
    for name,value in toggles.items():
        c=headshot.control(d,REFINE_TOGGLES[name])
        if type(value) is not bool or not c.isVisible() or not c.isEnabled():raise ValueError('Toggle unavailable: '+name)
    for name,value in toggles.items():
        c=headshot.control(d,REFINE_TOGGLES[name])
        if c.isChecked()!=value:c.click()
        if c.isChecked()!=value:raise RuntimeError('Toggle did not apply: '+name)
    for name,value in numbers.items():
        spin=spins[name][0];spin.setValue(value);spin.editingFinished.emit()
        if not math.isclose(spin.value(),value,abs_tol=1e-6):raise RuntimeError('Numeric setting did not apply: '+name)
    return refine_state()

def move_refine_point(revision, point_id, x, y):
    """Move one visible control through native scene mouse events, then read back."""
    if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for v in (x,y)):
        raise ValueError('Point coordinates must be finite numbers')
    state=refine_state()
    if state.get('revision')!=revision:raise ValueError('Refinement state changed; read fresh state')
    if point_id not in _points:raise ValueError('Unknown live point ID')
    C,G,W=headshot._qt()
    view_name,item=_points[point_id]
    d=widget(REFINE)
    view=headshot.control(d,view_name)
    if not item.flags() & W.QGraphicsItem.ItemIsMovable:raise ValueError('Item is not a movable control')
    before=item.scenePos();center=item.sceneBoundingRect().center()
    start=view.mapFromScene(center)
    end=view.mapFromScene(center+C.QPointF(x-before.x(),y-before.y()))
    if not view.viewport().rect().contains(start) or not view.viewport().rect().contains(end):
        raise ValueError('Point/target outside visible view; adjust framing first')
    selected=headshot.control(d,'qtSelectToolButton')
    if not selected.isChecked():selected.click()
    steps=[(C.QEvent.MouseButtonPress,start,C.Qt.LeftButton,C.Qt.LeftButton)]
    for fraction in (0.1,0.5,1.0):
        steps.append((C.QEvent.MouseMove,start+(end-start)*fraction,C.Qt.NoButton,C.Qt.LeftButton))
    steps.append((C.QEvent.MouseButtonRelease,end,C.Qt.LeftButton,C.Qt.NoButton))
    for event_type,pos,button,buttons in steps:
        event=G.QMouseEvent(event_type,C.QPointF(pos),C.QPointF(view.viewport().mapToGlobal(pos)),button,buttons,C.Qt.NoModifier)
        W.QApplication.sendEvent(view.viewport(),event)
    actual=item.scenePos()
    tolerance=max(1.0,abs(view.mapToScene(C.QPoint(1,0)).x()-view.mapToScene(C.QPoint(0,0)).x())*2)
    matches=abs(actual.x()-x)<=tolerance and abs(actual.y()-y)<=tolerance
    return {'success':matches,'before':{'x':before.x(),'y':before.y()},'requested':{'x':x,'y':y},
        'actual':{'x':actual.x(),'y':actual.y()},'tolerance':tolerance,
        'state':refine_state(), 'error':None if matches else 'Native control did not reach target'}

REFINE_ACTIONS={'preview_all':'qtPreviewAllPushButton','edit':'qtPreviewAllPushButton','preview_parts':'qtPreviewCurrentPushButton',
    'apply_all':'qtFixAllPushButton','apply_parts':'qtFixCurrentPartPushButton',
    'reset_view':'qtCResetViewToolButton','reset_points':'qtResetAllToolButton',
    'finish_alignment':'qtManualAlignToolButton', 'align':'qtStage2PushButton','adjust_alignment':'qtStage3PushButton'}

def refine_action(action, revision):
    if action not in REFINE_ACTIONS:raise ValueError('Unsupported refine action')
    state=refine_state()
    if state.get('revision')!=revision:raise ValueError('Refinement state changed; read fresh state')
    d=widget(REFINE)
    c=headshot.control(d,REFINE_ACTIONS[action])
    if not c.isVisible() or not c.isEnabled():raise ValueError('Refine action unavailable in current stage')
    if action in ('edit','preview_all') and ((c.text().strip()=='Edit') != (action=='edit')):
        raise ValueError('Requested action does not match current preview/edit stage')
    c.click()
    return {'success':True,'state':'native_action_returned','action':action,'readback':refine_state()}

def close_refine():
    d=widget(REFINE)
    d.close()
    return {'success':not d.isVisible(),'open':d.isVisible()}

def landmarks(view):
    if view not in ('front','side'):raise ValueError('Invalid view')
    import RLPy2
    data=RLPy2.Headshot3.GetInterface().GetLandmarks(view=='front')
    return {'success':True,'view':view,'points':[{'x':p.X,'y':p.Y} for p in data],
        'coordinate_system':'native Headshot coordinates; not normalized'}

def show_morph_panel():
    no_modal()
    p=widget(PANEL)
    c=headshot.control(p,'qtPresetMorphButton')
    if not c.isEnabled():raise ValueError('Headshot morph panel unavailable')
    c.click()
    return {'success':True,'state':'panel_requested','next':'Read get_anatomy_morphs after the native catalog populates'}

def load_side_reference(path):
    """Fill only the native file picker opened by this specific image command."""
    import ctypes
    import os
    from ctypes import wintypes
    image=headshot._image(path)
    C,_,W=headshot._qt()
    d=widget(REFINE)
    if not d.isVisible():raise ValueError('Open side refinement first')
    modal=W.QApplication.activeModalWidget()
    if modal is not None and modal is not d:raise ValueError('Unrelated modal dialog open')
    candidates=[headshot.control(d,n) for n in ('qtLoadSidePicturePushButton2','qtLoadSidePicturePushButton','qtLoadSideImageToolButton')]
    candidates=[c for c in candidates if c.isVisible() and c.isEnabled()]
    if not candidates:raise ValueError('Side image load control unavailable in current stage')
    user=ctypes.windll.user32
    user.GetDlgItem.argtypes=[wintypes.HWND,ctypes.c_int];user.GetDlgItem.restype=wintypes.HWND
    user.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    before=set();selected=[];errors=[]
    def pick(fill):
        @ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
        def visit(hwnd,_):
            pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            cls=ctypes.create_unicode_buffer(128);user.GetClassNameW(hwnd,cls,128)
            if pid.value!=os.getpid() or not user.IsWindowVisible(hwnd) or cls.value!='#32770':return True
            edit=user.GetDlgItem(hwnd,1148)
            if not fill:before.add(hwnd)
            elif hwnd not in before and edit and not selected:
                value=ctypes.create_unicode_buffer(image)
                user.SendMessageW(edit,12,0,ctypes.addressof(value))
                selected.append(int(hwnd))
                user.PostMessageW(hwnd,273,1,user.GetDlgItem(hwnd,1) or 0)
            return True
        user.EnumWindows(visit,0)
    pick(False)
    timer=C.QTimer()
    def tick():
        try:
            pick(True)
            if not selected:
                roots=list(W.QApplication.topLevelWidgets())
                for picker in roots:
                    if isinstance(picker,W.QFileDialog) and picker.isVisible():
                        picker.selectFile(image);picker.accept();selected.append('Qt file picker');break
        except Exception as error:errors.append(str(error));timer.stop()
        if selected:timer.stop()
    timer.timeout.connect(tick);timer.start(100)
    try:candidates[0].click()
    finally:timer.stop()
    if not selected:raise RuntimeError('Native image picker was not completed: '+str(errors))
    return {'success':True,'reference':image,'readback':refine_state()}
