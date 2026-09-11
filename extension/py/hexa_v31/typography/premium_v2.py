from __future__ import annotations

"""Hero/title and treatment-variant extension for premium V31 typography.

The semantic role remains the stable art-direction authority. ``treatment`` is a
secondary, deterministic variant inside that role and may only add transparent
text-adjacent marks; it never creates a subtitle panel or mutates motion geometry.
"""

from PIL import ImageDraw

from . import premium as _v1

build_text_plan=_v1.build_text_plan


def _decorate_treatment_variant(img,event):
    """Add a small treatment-specific mark without changing text layout.

    TypographyDirectorV2 intentionally rotates treatments inside the same semantic
    role. Those treatment names must therefore survive as real pixel differences,
    not metadata aliases. Decorations stay inside the already allocated transparent
    text canvas and are deliberately modest so role hierarchy remains dominant.
    """
    treatment=str(event.get('treatment') or '').upper()
    if not treatment or treatment in {'FREE_KEYWORD','KEY_TERM','VALUE_LOCKUP','RESULT_LOCKUP','WARNING_BADGE','STATUS_BADGE','COMPARISON_LABELS','MICRO_CONTEXT'}:
        return img

    draw=ImageDraw.Draw(img)
    w,h=img.size
    margin=max(5,int(round(h*.10)))
    width=max(2,int(round(h*.018)))
    accent=(47,145,188,225)
    rtl=bool(_v1._ARABIC_RE.search(str(event.get('text') or '')))

    if treatment in {'SIDE_CALLOUT','SIDE_RESULT'}:
        x=w-margin if rtl else margin
        y0=max(margin,int(h*.24));y1=min(h-margin,int(h*.76))
        draw.line((x,y0,x,y1),fill=accent,width=width)
        arm=max(10,int(w*.055));direction=-1 if rtl else 1
        draw.line((x,y0,x+direction*arm,y0),fill=accent,width=width)
    elif treatment in {'BOTTOM_RESULT'}:
        y=h-margin
        span=max(22,int(w*.20))
        if rtl:
            x1=w-margin;x0=max(margin,x1-span)
        else:
            x0=margin;x1=min(w-margin,x0+span)
        draw.line((x0,y,x1,y),fill=accent,width=width)
        short=max(8,int(span*.32))
        draw.line((x0 if rtl else x1-short,y-max(4,width*2),x0+short if rtl else x1,y-max(4,width*2)),fill=accent,width=max(1,width-1))
    elif treatment in {'INLINE_LABEL'}:
        y=margin
        span=max(18,int(w*.14))
        if rtl:
            x1=w-margin;x0=max(margin,x1-span)
        else:
            x0=margin;x1=min(w-margin,x0+span)
        draw.line((x0,y,x1,y),fill=accent,width=width)
    elif treatment in {'OBJECT_ADJACENT_LABEL'}:
        r=max(2,int(round(h*.022)))
        cx=margin+r if rtl else w-margin-r
        cy=max(margin+r,int(h*.50))
        draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill=accent)
        direction=1 if rtl else -1
        draw.line((cx+direction*r,cy,cx+direction*max(12,int(w*.06)),cy),fill=accent,width=width)
    elif treatment in {'HERO_KEYWORD','NUMERIC_HERO'}:
        # Compatibility treatment used by earlier V31 planners and tests. Keep
        # it visually meaningful when paired with a non-HERO semantic role.
        y=margin
        span=max(24,int(w*.24))
        if rtl:
            x1=w-margin;x0=max(margin,x1-span);cx=x0
        else:
            x0=margin;x1=min(w-margin,x0+span);cx=x1
        draw.line((x0,y,x1,y),fill=accent,width=max(width,2))
        r=max(2,int(round(h*.020)))
        draw.ellipse((cx-r,y-r,cx+r,y+r),fill=accent)

    img.info['hexa_typography_treatment']=treatment
    img.info['hexa_typography_version']='HEXA_PREMIUM_TYPOGRAPHY_V2'
    return img


def render_text_rgba(event,canvas_w=1920,canvas_h=1080):
    role=str(event.get('typography_role') or 'KEYWORD').upper()
    if role!='HERO':
        return _decorate_treatment_variant(_v1.render_text_rgba(event,canvas_w,canvas_h),event)

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