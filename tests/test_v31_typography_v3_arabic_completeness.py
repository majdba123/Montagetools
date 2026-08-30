from hexa_v31.typography import ArabicPhraseCompletenessAnalyzer, _exact_subphrases, certified_arabic_font_status

a=ArabicPhraseCompletenessAnalyzer()
assert not a.assess('ولكن في')['pass']
assert not a.assess('يؤدي إلى')['pass']
assert a.assess('تم رفض الطلب')['pass']
assert a.assess('القيمة ١٠٠')['pass']
assert a.assess('أعلى من الحد')['pass']

canonical='عند الفحص تم رفض الطلب فوراً'
rows=_exact_subphrases(canonical)
assert rows and all(text in canonical for text,_ in rows)
assert any(text=='تم رفض الطلب' for text,_ in rows)
assert not a.assess('رفض غير موجود',canonical)['pass']

font=certified_arabic_font_status()
assert font['status'] in {'CERTIFIED','DEGRADED_REVIEW_REQUIRED'}
if font['pass']:
    assert font['shaping_authority'] in {'PILLOW_RAQM_HARFBUZZ','UHARFBUZZ_0_56_0_GLYPH_PLAN_WITH_PRESENTATION_FORM_RASTER'}
    assert len(font['sha256'])==64

print('V31_TYPOGRAPHY_V3_ARABIC_COMPLETENESS_PASS',font['status'])
