from __future__ import annotations

"""Production typography art-direction layer for V31.

This module deliberately sits above the literal-copy planner. It does not invent
copy and it does not mutate the protected motion plan. It only rejects weak display
phrases, bounds their lifetime to the spoken semantic beat, and renders role-specific
Arabic treatments that are materially distinct in pixels.
"""

import re
from PIL import Image, ImageDraw, ImageFont, features

from . import typography as _base

_PREMIUM_VERSION = 'HEXA_PREMIUM_TYPOGRAPHY_V1'
_ARABIC_RE = re.compile(r'[\u0600-\u06FF]')
_DIGIT_RE = re.compile(r'[0-9٠-٩]')
_TRIM = " \t\r\n،,.;:؛!?؟-–—()[]{}\"'"
_WEAK_BOUNDARY = {
    'و','أو','او','لكن','لأن','لان','إذا','اذا','حتى','مع','من','في','على','عن','إلى','الى',
    'ثم','بعد','قبل','عند','هو','هي','هم','قد','إن','ان','إنه','انه','هذا','هذه','هذي','ذلك','تلك',
}
_ROLE_READ_LIMIT = {
    'VALUE': 3.0,
    'RESULT': 3.0,
    'WARNING': 2.5,
    'STATUS': 2.4,
    'COMPARISON_LABEL': 2.8,
    'KEYWORD': 2.25,
    'MICRO_LABEL': 1.9,
}


def _clean_words(text: str) -> list[str]:
    return [w.strip(_TRIM) for w in str(text or '').split() if w.strip(_TRIM)]


def _display_copy_quality(event: dict) -> tuple[bool, str]:
    """Reject narration fragments that do not work as intentional on-screen copy."""
    text = ' '.join(str(event.get('text') or '').split())
    words = _clean_words(text)
    if not text or not words:
        return False, 'EMPTY_COPY'
    if len(words) > 4 and not _DIGIT_RE.search(text):
        return False, 'DISPLAY_COPY_TOO_LONG'
    if words[0] in _WEAK_BOUNDARY or words[-1] in _WEAK_BOUNDARY:
        return False, 'WEAK_DISCOURSE_BOUNDARY'
    if len(text) > 32 and not _DIGIT_RE.search(text):
        return False, 'DISPLAY_COPY_TOO_WIDE'

    role = str(event.get('typography_role') or 'KEYWORD').upper()
    source = str(event.get('semantic_source') or '')
    content = [w for w in words if w not in _WEAK_BOUNDARY]

    # Scene-span fallbacks are the highest-risk source of subtitle-like prose.
    # Keep them only when they are compact enough to behave as visual copy.
    if source == 'SCENE_SCRIPT_LITERAL_SUBPHRASE':
        if role in {'KEYWORD', 'MICRO_LABEL'} and len(content) < 2 and not _DIGIT_RE.search(text):
            return False, 'WEAK_SCRIPT_FALLBACK'
        if len(content) > 4:
            return False, 'SCRIPT_FALLBACK_TOO_SENTENTIAL'
    return True, 'PASS'


def _bound_event_lifetime(event: dict) -> dict:
    row = dict(event)
    role = str(row.get('typography_role') or 'KEYWORD').upper()
    start = float(row.get('start_seconds', 0.0))
    anchor = float(row.get('semantic_anchor_seconds', row.get('impact_seconds', start)))
    end = float(row.get('end_seconds', start))
    limit = float(_ROLE_READ_LIMIT.get(role, 2.25))
    bounded_end = min(end, max(start + 0.82, anchor + limit))
    if bounded_end < end - 1e-6:
        row['end_seconds'] = round(bounded_end, 6)
        row['readable_end_seconds'] = round(max(float(row.get('readable_start_seconds', start)), bounded_end - 0.18), 6)
        row['fade_out_seconds'] = min(float(row.get('fade_out_seconds', 0.18)), 0.18)
        row['source_lifetime_authority'] = 'VOICE_ANCHOR_BOUNDED_PREMIUM_COPY'
    row['typography_art_direction'] = _PREMIUM_VERSION
    return row


def build_text_plan(package, alignment, vision_results, motion_plan, logger=None):
    """Source-grounded planner with a strict visual-copy quality gate."""
    plan = _base.build_text_plan(package, alignment, vision_results, motion_plan, logger=logger)
    kept = []
    rejected = list(plan.get('skipped_opportunities') or [])
    for event in plan.get('events') or []:
        ok, reason = _display_copy_quality(event)
        if not ok:
            rejected.append({
                'scene_id': event.get('scene_id'),
                'text': event.get('text'),
                'reason': reason,
                'stage': _PREMIUM_VERSION,
            })
            continue
        kept.append(_bound_event_lifetime(event))
    out = dict(plan)
    out['events'] = kept
    out['text_event_count'] = len(kept)
    out['coverage_scene_percent'] = round(100.0 * len(kept) / max(1, int(plan.get('scene_count') or 0)), 2)
    out['skipped_opportunities'] = rejected
    out['typography_art_direction'] = _PREMIUM_VERSION
    out['display_copy_quality_gate'] = True
    if logger:
        logger.log(
            'PASS', 'PREMIUM_TYPOGRAPHY_COPY_GATE',
            kept=len(kept), rejected=len(rejected), version=_PREMIUM_VERSION,
        )
    return out


def _font_and_text(event: dict, canvas_h: int):
    role = str(event.get('typography_role') or 'KEYWORD').upper()
    geom = event.get('text_geometry') or {}
    base = int(geom.get('font_size') or 64)
    role_scale = {
        'VALUE': 1.08, 'RESULT': 1.04, 'WARNING': 1.00, 'STATUS': .96,
        'COMPARISON_LABEL': .94, 'KEYWORD': 1.00, 'MICRO_LABEL': .86,
    }.get(role, 1.0)
    size = max(18, int(round(base * role_scale * (canvas_h / 1080.0))))
    path = _base.find_arabic_font(role.lower())
    if not path:
        raise RuntimeError('No suitable Arabic system font found.')
    font = ImageFont.truetype(path, size=size)
    text = str(event.get('text') or '')
    use_raqm = bool(features.check('raqm'))
    rendered = str(geom.get('rendered_text') or (text if use_raqm else _base._fallback_shape(text)))
    rtl = bool(_ARABIC_RE.search(text))
    return role, size, font, rendered, rtl, use_raqm


def _measure(draw, text, font, size, rtl, use_raqm):
    kw = {'font': font, 'spacing': int(size * .16), 'align': 'right' if rtl else 'left'}
    if rtl and use_raqm:
        kw.update(direction='rtl', language='ar')
    try:
        box = draw.multiline_textbbox((0, 0), text, **kw)
    except (TypeError, ValueError):
        kw.pop('direction', None); kw.pop('language', None)
        box = draw.multiline_textbbox((0, 0), text, **kw)
    return box, kw


def _draw_text(draw, xy, text, kw, *, fill, stroke_width=0, stroke_fill=None):
    args = dict(kw)
    args.update(fill=fill)
    if stroke_width:
        args.update(stroke_width=stroke_width, stroke_fill=stroke_fill or (255,255,255,220))
    try:
        draw.multiline_text(xy, text, **args)
    except (TypeError, ValueError):
        args.pop('direction', None); args.pop('language', None)
        draw.multiline_text(xy, text, **args)


def render_text_rgba(event, canvas_w=1920, canvas_h=1080):
    """Render materially distinct premium role treatments without subtitle panels."""
    w = max(48, int(round(float(event.get('w_norm', .34)) * canvas_w)))
    h = max(38, int(round(float(event.get('h_norm', .15)) * canvas_h)))
    role, size, font, text, rtl, use_raqm = _font_and_text(event, canvas_h)
    img = Image.new('RGBA', (w, h), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    box, kw = _measure(draw, text, font, size, rtl, use_raqm)
    tw, th = box[2]-box[0], box[3]-box[1]
    pad = max(6, int(size * .12))
    x = max(pad, w - tw - pad) if rtl else max(pad, min(w - tw - pad, pad))
    y = max(pad, (h - th) / 2.0 - box[1])

    palette = {
        'VALUE': ((19,73,116,255), (55,153,195,245)),
        'RESULT': ((20,103,72,255), (49,161,111,245)),
        'WARNING': ((151,45,54,255), (217,78,78,245)),
        'STATUS': ((31,104,139,255), (58,164,196,245)),
        'COMPARISON_LABEL': ((38,88,116,255), (91,166,191,235)),
        'MICRO_LABEL': ((65,78,88,255), (118,151,166,220)),
        'KEYWORD': ((21,48,66,255), (65,145,178,230)),
    }
    color, accent = palette.get(role, palette['KEYWORD'])
    treatment = str(event.get('treatment') or '').upper()

    # Soft text-only shadow for hero/result roles. It follows glyph alpha; there is
    # intentionally no opaque rectangle or generic subtitle card behind the text.
    if role in {'VALUE','RESULT','WARNING'}:
        _draw_text(draw, (x+2, y+3), text, kw, fill=(0,0,0,42))

    stroke = max(1, int(round(size * .028))) if role in {'WARNING','STATUS'} else 0
    _draw_text(draw, (x, y), text, kw, fill=color, stroke_width=stroke,
               stroke_fill=(255,255,255,225) if stroke else None)

    line_w = max(2, int(round(size * .035)))
    ax_right = min(w-pad, int(x+tw))
    ax_left = max(pad, int(x))
    baseline = min(h-pad, int(y+th+max(3, size*.08)))

    if role == 'VALUE':
        draw.line((ax_left, baseline, ax_right, baseline), fill=accent, width=max(3,line_w))
        tick_x = ax_right if rtl else ax_left
        draw.line((tick_x, max(pad,int(y)), tick_x, min(h-pad,int(y+th))), fill=accent, width=max(4,line_w+1))
    elif role == 'RESULT':
        draw.line((ax_left, baseline, ax_right, baseline), fill=accent, width=max(3,line_w))
        r=max(3,int(size*.055)); cx=ax_left if rtl else ax_right
        draw.ellipse((cx-r,baseline-r,cx+r,baseline+r), fill=accent)
    elif role == 'WARNING':
        mark_x = max(pad, ax_left-int(size*.18)) if rtl else min(w-pad,ax_right+int(size*.18))
        r=max(4,int(size*.07))
        draw.ellipse((mark_x-r,int(y+th*.35)-r,mark_x+r,int(y+th*.35)+r), outline=accent, width=max(2,line_w))
        draw.line((mark_x,int(y+th*.25),mark_x,int(y+th*.38)), fill=accent, width=max(2,line_w))
        draw.ellipse((mark_x-1,int(y+th*.48)-1,mark_x+2,int(y+th*.48)+2), fill=accent)
    elif role == 'STATUS':
        r=max(3,int(size*.05)); dot_x=ax_right if rtl else ax_left
        dot_y=max(pad,int(y+th*.52))
        draw.ellipse((dot_x-r,dot_y-r,dot_x+r,dot_y+r), fill=accent)
        short=max(18,int(tw*.28))
        if rtl: draw.line((ax_right-short,baseline,ax_right,baseline),fill=accent,width=line_w)
        else: draw.line((ax_left,baseline,ax_left+short,baseline),fill=accent,width=line_w)
    elif role == 'COMPARISON_LABEL':
        arm=max(10,int(size*.16)); top=max(pad,int(y)-2); bottom=min(h-pad,int(y+th)+2)
        edge=ax_right if rtl else ax_left
        draw.line((edge,top,edge,bottom),fill=accent,width=line_w)
        direction=-1 if rtl else 1
        draw.line((edge,top,edge+direction*arm,top),fill=accent,width=line_w)
        draw.line((edge,bottom,edge+direction*arm,bottom),fill=accent,width=line_w)
    elif role == 'MICRO_LABEL':
        short=max(16,int(tw*.22))
        if rtl: draw.line((ax_right-short,baseline,ax_right,baseline),fill=accent,width=max(1,line_w-1))
        else: draw.line((ax_left,baseline,ax_left+short,baseline),fill=accent,width=max(1,line_w-1))
    else:  # KEYWORD
        tick_x=ax_right if rtl else ax_left
        draw.line((tick_x, max(pad,int(y+th*.20)), tick_x, min(h-pad,int(y+th*.80))), fill=accent, width=max(2,line_w))

    # Treatment metadata may select a semantic variant, but visual role remains the
    # stable cross-package art-direction authority.
    img.info['hexa_typography_version'] = _PREMIUM_VERSION
    img.info['hexa_typography_role'] = role
    img.info['hexa_typography_treatment'] = treatment
    return img
