from __future__ import annotations

import json
import os
import pathlib
import tempfile

from hexa_v31.recovery.memory import RecoveryMemory


def main():
    old_enabled = os.environ.get('HEXA_RECOVERY_MEMORY_ENABLED')
    old_path = os.environ.get('HEXA_RECOVERY_MEMORY_PATH')
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / 'memory.json'
            os.environ['HEXA_RECOVERY_MEMORY_ENABLED'] = '1'
            os.environ['HEXA_RECOVERY_MEMORY_PATH'] = str(path)

            memory = RecoveryMemory()
            family = 'DYNAMIC_CROSS_SCENE|PRIMARY|PRIMARY|ENTRY:A|EXIT:B'
            strategies = ['DELAY_0_LEAD_1', 'DELAY_2_LEAD_4']
            assert memory.rank(family, strategies) == strategies

            memory.record(family, strategies[1], True, cost=6.0)
            memory.record(family, strategies[0], False)
            loaded = RecoveryMemory()
            assert loaded.rank(family, strategies)[0] == strategies[1]
            payload = json.loads(path.read_text(encoding='utf-8'))
            assert payload['families'][family][strategies[1]]['successes'] == 1

            path.write_text('{broken json', encoding='utf-8')
            malformed = RecoveryMemory()
            assert malformed.rank(family, strategies) == strategies

        print('V31_RECOVERY_MEMORY_PASS')
    finally:
        if old_enabled is None:
            os.environ.pop('HEXA_RECOVERY_MEMORY_ENABLED', None)
        else:
            os.environ['HEXA_RECOVERY_MEMORY_ENABLED'] = old_enabled
        if old_path is None:
            os.environ.pop('HEXA_RECOVERY_MEMORY_PATH', None)
        else:
            os.environ['HEXA_RECOVERY_MEMORY_PATH'] = old_path


if __name__ == '__main__':
    main()
