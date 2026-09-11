"""Vision layer and compatibility exports for ``hexa_v31.vision``."""
from __future__ import annotations

import hashlib
import pathlib

from . import vision as _implementation


def _source_dependency_sha256() -> str:
    """Bind scene-vision cache identity to the code that creates physical layers."""
    from hexa_v31.extraction import matting as extraction_matting
    from hexa_v31.extraction import reconstruction
    from hexa_v31.qa import actor_qa as actor_qa_module
    from hexa_v31 import hierarchy as hierarchy_module
    from hexa_v31 import occlusion as occlusion_module
    paths={
        pathlib.Path(_implementation.__file__).resolve(),
        pathlib.Path(extraction_matting.__file__).resolve(),
        pathlib.Path(reconstruction.__file__).resolve(),
        pathlib.Path(actor_qa_module.__file__).resolve(),
        pathlib.Path(hierarchy_module.__file__).resolve(),
        pathlib.Path(occlusion_module.__file__).resolve(),
    }
    digest=hashlib.sha256()
    for path in sorted(paths,key=lambda p:str(p).lower()):
        digest.update(path.name.encode('utf-8'));digest.update(b'\0')
        digest.update(path.read_bytes());digest.update(b'\0')
    return digest.hexdigest()


# Static semantic versions are useful diagnostics but are not sufficient cache keys:
# a production hotfix can change matting/reconstruction bytes without someone manually
# bumping every string. Add the actual implementation digest to the module-global cache
# contract used by analyze_scene/cached_final_foundation_scene.
_dependencies=dict(_implementation.VISION_CACHE_DEPENDENCIES)
_dependencies['physical_layer_source_sha256']=_source_dependency_sha256()
_implementation.VISION_CACHE_DEPENDENCIES=_dependencies

globals().update({key: value for key, value in vars(_implementation).items() if not key.startswith('__')})
VISION_CACHE_DEPENDENCIES=_dependencies
