import numpy as np
from hexa_v31.typography import TypographyDirectorV2,render_text_rgba

assert not TypographyDirectorV2.phrase_complete('and')
assert TypographyDirectorV2.phrase_complete('Clear result')
base={'text':'Clear result','w_norm':.34,'h_norm':.14,'typography_role':'RESULT'}
a=np.array(render_text_rgba(dict(base,treatment='HERO_KEYWORD')))
b=np.array(render_text_rgba(dict(base,treatment='RESULT_LOCKUP')))
c=np.array(render_text_rgba(dict(base,treatment='WARNING_BADGE',typography_role='WARNING')))
assert a.sum()>0 and b.sum()>0 and c.sum()>0
assert not np.array_equal(a,b) and not np.array_equal(b,c)
print('V31_TYPOGRAPHY_DIRECTOR_V2_PASS')
