from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
a=json.loads((ROOT/'extension/resources/HEXA_USER_PRESET_AUTHORITY_V31.json').read_text())
assert a['status']=='HARD_LOCK'
assert a['precedence']=='LATEST_USER_RULES_OVER_LEGACY_HEXA_MOTION_HEURISTICS'
assert [a['scene_rules']['visual_card_min_seconds'],a['scene_rules']['visual_card_max_seconds']]==[3.0,5.0]
assert [a['scene_rules']['primary_min'],a['scene_rules']['primary_max']]==[1,2]
assert [a['scene_rules']['secondary_min'],a['scene_rules']['secondary_max']]==[3,8]
p=a['preset_motion']
assert p['ENTRY_LEFT_TO_MIDDLE']['duration_seconds']==1.44
assert p['ENTRY_RIGHT_TO_MIDDLE']['duration_seconds']==1.4
assert p['EXIT_MIDDLE_TO_RIGHT']['duration_seconds']==1.48
assert p['EXIT_MIDDLE_TO_LEFT']['duration_seconds']==1.16
assert p['WITHIN_MIDDLE_TO_RIGHT']['duration_seconds']==0.9
assert p['WITHIN_MIDDLE_TO_DOWN']['duration_seconds']==1.28
assert p['APPEAR_HIGH_SCALE']['family']=='APPEARANCE'
assert p['DISAPPEAR_DOWN_SCALE']['family']=='DISAPPEARANCE'
for key,name in [('rules_pdf_sha256','HEXA_USER_MOTION_RULES_AUTHORITY.pdf'),('prfpset_sha256','presets.prfpset'),('samples_rar_sha256','presets_source.rar')]:
    path=ROOT/'extension/resources'/name
    assert path.is_file(),(key,path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==a['source_files'][key],key
print('V31_PRESET_AUTHORITY_PASS')
