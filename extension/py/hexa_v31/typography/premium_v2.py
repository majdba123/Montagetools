from __future__ import annotations

"""Hero/title treatment extension for the premium V31 typography layer."""

from PIL import ImageDraw

from . import premium as _v1

build_text_plan=_v1.build_text_plan


def render_text_rgba(event,canvas_w=1920,canvas_h=1080):
    role=str(event.get('typography_role') or 'KEYWORD').upper()
    if role!='HERO':
        return _v1.render_text_rgba(event,canvas_w,canvas_h)

    # Titles are concept labels, not subtitles. Give them a larger editorial
    # hierarchy while retaining the certified offline Arabic font and transparent
    # glyph-only treatment. The base renderer supplies shaping and a restrained
    # vertical semantic tick; V2 adds a short asymmetric hero rule.
    hero=dict(event)
    hero['typography_role']='KEYWORD'
    geom=dict(hero.get('text_geometry') or {})
    if geom.get('font_size'):
        geom['font_size']=int(round(float(geom['font_size'])*1.12))
    hero['text_geometry']=geom
    img=_v1.render_text_rgba(hero,canvas_w,canvas_h)
    draw=ImageDraw.Draw(img)
    w,h=img.size
    accent=(47,145,188,235)
    rule=max(24,int(w*.24));margin=max(5,int(h*.10));y=max(margin,h-margin-2)
    rtl=bool(_v1._ARABIC_RE.search(str(event.get('text') or '')))
    if rtl:
        x1=w-margin;x0=max(margin,x1-rule)
    else:
        x0=margin;x1=min(w-margin,x0+rule)
    draw.line((x0,y,x1,y),fill=accent,width=max(2,int(h*.025)))
    r=max(2,int(h*.022));cx=x0 if rtl else x1
    draw.ellipse((cx-r,y-r,cx+r,y+r),fill=accent)
    img.info['hexa_typography_role']='HERO'
    img.info['hexa_typography_version']='HEXA_PREMIUM_TYPOGRAPHY_V2'
    return img
