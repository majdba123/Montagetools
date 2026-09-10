from __future__ import annotations
import hashlib,pathlib,sys
import numpy as np

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension/py'))

from hexa_v31.typography import render_text_rgba
from hexa_v31.typography.premium import _display_copy_quality

BASE={
    'text':'قيمة التحويل',
    'w_norm':0.34,
    'h_norm':0.15,
    'text_geometry':{'font_size':64,'rendered_text':'قيمة التحويل'},
}

hashes={}
opaque={}
for role in ('VALUE','RESULT','WARNING','STATUS','KEYWORD','MICRO_LABEL','COMPARISON_LABEL'):
    event=dict(BASE,typography_role=role,treatment=role+'_TEST')
    img=render_text_rgba(event,1280,720)
    arr=np.asarray(img)
    assert arr.shape[2]==4 and int(arr[:,:,3].max())>0,role
    alpha=arr[:,:,3]
    # Typography must remain a transparent glyph/decor treatment, never a broad
    # subtitle rectangle or opaque generic panel.
    opaque_fraction=float(np.mean(alpha>220))
    assert opaque_fraction<0.32,(role,opaque_fraction)
    opaque[role]=opaque_fraction
    hashes[role]=hashlib.sha256(arr.tobytes()).hexdigest()

# Roles must be materially distinct in encoded pixels, not metadata aliases.
assert len(set(hashes.values()))==len(hashes),hashes

ok,reason=_display_copy_quality({'text':'لكن في','typography_role':'KEYWORD','semantic_source':'SCENE_SCRIPT_LITERAL_SUBPHRASE'})
assert not ok and reason=='WEAK_DISCOURSE_BOUNDARY',(ok,reason)
ok,reason=_display_copy_quality({'text':'قيمة التحويل','typography_role':'KEYWORD','semantic_source':'SCENE_SCRIPT_LITERAL_SUBPHRASE'})
assert ok,(ok,reason)

print('V31_PREMIUM_TYPOGRAPHY_PIXELS_PASS',hashes,opaque)
