import json
import pathlib
import subprocess
import tempfile

from hexa_v31.pipeline import _source_commit


ROOT = pathlib.Path(__file__).resolve().parents[1]
expected = subprocess.check_output(
    ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True
).strip()
assert _source_commit(ROOT / 'extension', {'source_commit': 'STALE_INSTALL'}) == expected

with tempfile.TemporaryDirectory() as raw:
    extension = pathlib.Path(raw)
    resources = extension / 'resources'
    resources.mkdir()
    (resources / 'HEXA_RELEASE_IDENTITY_V31.json').write_text(
        json.dumps({'source_commit': 'SEALED_RELEASE'}), encoding='utf-8'
    )
    assert _source_commit(extension, {'source_commit': 'STALE_INSTALL'}) == 'SEALED_RELEASE'

print('V31_SOURCE_COMMIT_IDENTITY_PASS')
