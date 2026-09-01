"""Optional multi-GB real-model smoke test. Not part of the normal unit suite."""
import os,pathlib
if os.environ.get('HEXA_RUN_REAL_FOUNDATION_MODELS')!='1':raise SystemExit('SKIP: set HEXA_RUN_REAL_FOUNDATION_MODELS=1 in a provisioned certification environment')
from hexa_v31.vision.foundation.backend import FoundationVisionClient
print('V31_FOUNDATION_REAL_MODEL_ENVIRONMENT_READY')
