from __future__ import annotations

from PIL import Image
import os
import pathlib
import tempfile


def cached_image_complete(path, expected_size=None) -> bool:
    """Require an intact container and a decodable pixel payload for cache hits."""
    if not path:
        return False
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            return expected_size is None or image.size == tuple(expected_size)
    except (OSError, ValueError, SyntaxError):
        return False


def save_cached_image(image, path) -> None:
    """Publish only verified PNG bytes; retry bounded incomplete writes."""
    target = pathlib.Path(path)
    for attempt in range(3):
        fd, name = tempfile.mkstemp(prefix=target.stem+'.', suffix='.png', dir=target.parent)
        staged = pathlib.Path(name)
        try:
            with os.fdopen(fd, 'wb') as stream:
                image.save(stream, format='PNG')
                stream.flush()
                os.fsync(stream.fileno())
            if not cached_image_complete(staged, image.size):
                raise OSError('Incomplete encoded image: '+str(target))
            os.replace(staged, target)
            return
        except OSError:
            if attempt == 2:
                raise
        finally:
            staged.unlink(missing_ok=True)
