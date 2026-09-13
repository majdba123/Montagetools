from __future__ import annotations

import copy
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'extension' / 'py'))


def main():
    builder = (ROOT / 'tools' / 'build_latest_release.ps1').read_text(encoding='utf-8')
    memory = (ROOT / 'extension' / 'py' / 'hexa_v31' / 'recovery' / 'memory.py').read_text(encoding='utf-8')

    assert "Join-Path $root 'recovery_data'" in builder
    assert "Join-Path $stage 'recovery_data'" in builder
    assert "Join-Path $stage 'extension\\recovery_data'" in builder
    assert "extension\\recovery_data\\proven_solutions.json" in builder
    assert "problem_registry.json" in builder
    assert "recovery_history.json" in builder

    # Installed runtime lookup must prefer the extension-local snapshot, while a
    # source checkout still resolves the root version-controlled authority.
    assert "parents[3] / 'recovery_data' / 'proven_solutions.json'" in memory
    assert "parents[4] / 'recovery_data' / 'proven_solutions.json'" in memory
    assert 'HEXA_RECOVERY_PROVEN_SOLUTIONS_PATH' in memory
    assert 'def record(' in memory
    assert 'Compatibility no-op' in memory

    # Every registered CI HARD_GATE must have one package-independent source recovery
    # owner. This is the permanence contract: once a family is known, no future Final
    # Package is allowed to bypass recovery/canonical re-QA and reach the encoder.
    from hexa_v31.recovery.permanence import (
        HARD_GATE_POLICIES,
        classify_failure,
        enforce_known_problem_permanence,
        load_registry,
        required_hard_gate_problem_ids,
        validate_policy_coverage,
    )

    registry = load_registry(ROOT / 'recovery_data' / 'problem_registry.json')
    coverage = validate_policy_coverage(registry)
    required = required_hard_gate_problem_ids(registry)
    assert coverage['pass'] is True
    assert required == set(HARD_GATE_POLICIES)
    assert required == {
        'HEXA_MOTION_PATH_OVERLAP',
        'HEXA_SETTLED_GEOMETRY_OVERLAP',
        'HEXA_VIEWPORT_CLIPPING',
    }

    # Different instance identity must still normalize to the same reusable family.
    assert classify_failure('VCARD_ALPHA@1.25s: motion-path overlap EVT_A x EVT_B=0.4>0.015') == 'HEXA_MOTION_PATH_OVERLAP'
    assert classify_failure('VCARD_Z99@88.10s: motion-path overlap OTHER_7 x OTHER_2=0.2>0.015') == 'HEXA_MOTION_PATH_OVERLAP'
    assert classify_failure('VCARD_X/PHASE_3: settled overlap A x B=0.2>0.01') == 'HEXA_SETTLED_GEOMETRY_OVERLAP'
    assert classify_failure('VCARD_Y/PHASE_9: OTHER: settled bbox outside safe frame') == 'HEXA_VIEWPORT_CLIPPING'
    assert classify_failure('WHATEVER: sustained viewport clipping 0.400s') == 'HEXA_VIEWPORT_CLIPPING'

    # A known family gets one bounded recertification opportunity and must pass the
    # same canonical QA afterward. A failed attempt rolls the full plan back.
    plan = {'events': [{'event_id': 'GENERIC'}], 'visual_cards': {'cards': []}, 'fixed': False}

    def known_qa(candidate):
        if candidate.get('fixed'):
            return {'pass': True, 'failures': []}
        return {'pass': False, 'failures': [
            'VCARD_RANDOM@3.14s: motion-path overlap ROOT_A x ROOT_B=0.8>0.015'
        ]}

    calls = []

    def recover_once(candidate, fps):
        calls.append(fps)
        candidate['fixed'] = True
        return candidate

    enforce_known_problem_permanence(plan, fps=30.0, qa_fn=known_qa, recertify=recover_once)
    assert calls == [30.0]
    assert plan['known_problem_permanence_gate']['known_problem_ids'] == ['HEXA_MOTION_PATH_OVERLAP']

    reject = {'events': [{'event_id': 'OTHER'}], 'visual_cards': {'cards': []}, 'marker': 'ORIGINAL'}
    snapshot = copy.deepcopy(reject)

    def still_bad(_candidate):
        return {'pass': False, 'failures': [
            'VCARD_ANY@6.00s: motion-path overlap X x Y=0.7>0.015'
        ]}

    def ineffective(candidate, _fps):
        candidate['marker'] = 'MUTATED'
        return candidate

    try:
        enforce_known_problem_permanence(reject, qa_fn=still_bad, recertify=ineffective)
        raise AssertionError('known hard gate escaped the permanence gate')
    except ValueError as exc:
        assert 'KNOWN_PROBLEM_PERMANENCE_HARD_FAIL' in str(exc), exc
    assert reject == snapshot

    # New families fail closed. Recovery must never guess by suppressing validation.
    try:
        enforce_known_problem_permanence(
            {'events': [], 'visual_cards': {'cards': []}},
            qa_fn=lambda _candidate: {'pass': False, 'failures': ['NEW_UNREGISTERED_GEOMETRY_FAILURE']},
            recertify=lambda candidate, _fps: candidate,
        )
        raise AssertionError('unregistered hard failure escaped the permanence gate')
    except ValueError as exc:
        assert 'KNOWN_PROBLEM_PERMANENCE_UNKNOWN_HARD_FAILURE' in str(exc), exc

    print('V31_RECOVERY_RELEASE_CONTRACT_PASS')


if __name__ == '__main__':
    main()
