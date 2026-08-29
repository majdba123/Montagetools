from hexa_v31.scene_grammar import classify_card

def e(uid,typ='ICON',role='SUPPORTING',**kw):
    x={'event_id':'E_'+uid,'semantic_unit_id':uid,'semantic_type':typ,'semantic_role':role,'semantic_mapping_confidence':.99}
    x.update(kw);return x
card={'card_id':'C'}
# Structural classification must not depend on script text/project topic.
base=[e('A','CONCEPT','PRIMARY'),e('B'),e('C'),e('D')]
g=classify_card(card,base,[{'units':[],'visual_progression':[]}]);assert g['archetype']=='HUB_AND_SPOKES',g
char=[e('M','MAIN_CHARACTER','PRIMARY'),e('O')]
g=classify_card(card,char,[{'units':[],'visual_progression':[]}]);assert g['archetype']=='CHARACTER_EXPLAINS_OBJECT',g
comp=[e('A','CONCEPT','PRIMARY'),e('B','CONCEPT','PRIMARY')]
g=classify_card(card,comp,[{'units':[],'visual_progression':[]}]);assert g['archetype']=='COMPARISON',g
units=[{'unit_id':'A'},{'unit_id':'B'},{'unit_id':'C'}]
sc={'units':units,'visual_progression':[{'targets':['A','B','C']}], 'script_span':{'text':'totally unrelated language content'}}
g=classify_card(card,[e('A','CONCEPT','PRIMARY'),e('B'),e('C')],[sc]);assert g['archetype']=='FLOW_PIPELINE',g
# Changing prose cannot change structural result.
sc2=dict(sc);sc2['script_span']={'text':'محتوى مختلف كلياً'}
g2=classify_card(card,[e('A','CONCEPT','PRIMARY'),e('B'),e('C')],[sc2]);assert g2['archetype']==g['archetype'] and g2['roles']==g['roles']
assert not g['topic_specific_rules']
print('V31_UNIVERSAL_SCENE_GRAMMAR_PASS')
