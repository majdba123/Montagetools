from __future__ import annotations
import ast,json,os,pathlib,subprocess,sys,xml.etree.ElementTree as ET
ROOT=pathlib.Path(__file__).resolve().parents[1]
RUNTIME_CONFIG=pathlib.Path(os.environ.get('LOCALAPPDATA',''))/'HEXA'/'VideoBuilderV31'/'runtime_config.json'
def run(cmd,timeout=300):
    env=os.environ.copy();src=str(ROOT/'extension/py');env['PYTHONPATH']=src+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    if RUNTIME_CONFIG.is_file():
        cfg=json.loads(RUNTIME_CONFIG.read_text(encoding='utf-8'))
        if cfg.get('ffmpeg_path'):env['HEXA_FFMPEG']=str(cfg['ffmpeg_path'])
        if cfg.get('ffprobe_path'):env['HEXA_FFPROBE']=str(cfg['ffprobe_path'])
    print('RUN',' '.join(map(str,cmd)),flush=True);cp=subprocess.run([str(x) for x in cmd],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,env=env);print(cp.stdout,flush=True)
    if cp.returncode:raise SystemExit(cp.returncode)
count=0
for p in (ROOT/'extension/py').rglob('*.py'):ast.parse(p.read_text(encoding='utf-8'));count+=1
for p in [ROOT/'tools/install_v31.py',ROOT/'tools/selftest_v31.py']:ast.parse(p.read_text(encoding='utf-8-sig'));count+=1
ET.parse(ROOT/'extension/CSXS/manifest.xml');print('PYTHON_XML_SYNTAX_PASS',count)
run(['node','--check',ROOT/'extension/js/main.js'])
cp=subprocess.run(['node','--check'],input=(ROOT/'extension/jsx/host.jsx').read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT);print(cp.stdout.decode('utf-8',errors='replace'));assert cp.returncode==0;print('HOST_JSX_SYNTAX_PASS')
for f in ['test_v31_preset_authority.py','test_v31_motion_cards.py','test_v31_explicit_relationships.py','test_v31_absolute_preset_state.py','test_v31_cutout_integrity.py','test_v31_stage_leak_matting.py','test_v31_continuous_render.py','test_v31_no_legacy_motion.py','test_v31_semantic_mapping_guard.py','test_v31_reference_critic_no_free_acting.py','test_v31_failure_log_card_compiler.py','test_v31_primary_wave_scheduler.py','test_v31_identity_persistence.py','test_v31_secondary_shortfall_review.py','test_v31_universal_scene_grammar.py','test_v31_visual_sample_calibration.py','test_v31_collision_solver.py','test_v31_generalization_layout_stress.py','test_v31_atomic_composite_exclusivity.py','test_v31_motion_path_collision_guard.py','test_v31_no_project_hardcoding.py']:
    run([sys.executable,ROOT/'tests'/f],timeout=480)
for f in ['test_v31_0_1_large_support_fallback.py','test_v31_0_1_atomic_character_split.py','test_v31_0_1_adaptive_phase_recovery.py','test_v31_0_1_large_geometry_stress.py']:
    run([sys.executable,ROOT/'tests'/f],timeout=480)
for f in ['test_v31_0_2_spatiotemporal_phase_contract.py','test_v31_0_2_cache_invalidation.py']:
    run([sys.executable,ROOT/'tests'/f],timeout=480)
run([sys.executable,ROOT/'tests'/'test_v31_0_3_visual_density.py'],timeout=480)
run([sys.executable,ROOT/'tests'/'test_v31_projected_visible_ink.py'],timeout=480)
run([sys.executable,ROOT/'tests'/'test_v31_hierarchical_asset_decomposer.py'],timeout=480)
run([sys.executable,ROOT/'tests'/'test_v31_typography_director_v2.py'],timeout=480)
run([sys.executable,ROOT/'tests'/'test_v31_0_4_audio_semantic_design.py'],timeout=480)
# Platform/runtime regression guards remain part of the V31 shipping suite.
for f in ['test_v31_install_path_hotfix.py','test_v31_runtime_import_path_contract.py','test_v31_media_probe_fallback.py']:
    run([sys.executable,ROOT/'tests'/f],timeout=480)
for f in ['test_v31_premiere_animated_host_mock.js','test_v31_windows_path_contract.js']:
    run(['node',ROOT/'tests'/f],timeout=480)
print('V31_0_9_SEMANTIC_PHASE_REPARTITION_COMPILER_TEST_SUITE_PASS')
