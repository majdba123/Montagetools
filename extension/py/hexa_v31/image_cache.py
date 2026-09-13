from __future__ import annotations

from PIL import Image


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
