from __future__ import annotations

"""Source-backed visible-ink projection used by layout and editorial QA."""

import pathlib
from PIL import Image, ImageChops


def perceptual_visible_fraction(image):
    """Fraction that survives the certified white-background ink threshold."""
    rgba = image.convert('RGBA')
    white = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
    rgb = Image.alpha_composite(white, rgba).convert('RGB')
    red, green, blue = rgb.split()
    darkest = ImageChops.darker(ImageChops.darker(red, green), blue)
    # Encoded acceptance is ``255 - min(rgb) > 10``.
    return float(sum(darkest.histogram()[:245])) / max(1, rgb.width * rgb.height)


class ProjectedVisibleInkModel:
    """Measure alpha support once, then project it through solved geometry."""

    algorithm_version = 'HEXA_PROJECTED_VISIBLE_INK_V2_PERCEPTUAL_WHITE_THRESHOLD'

    def __init__(self):
        self._fractions = {}

    @staticmethod
    def _fallback(event):
        matting = event.get('matting') or {}
        return max(0.0, min(1.0, float(event.get('visible_ink_fraction', matting.get('visible_ink_fraction', matting.get('opaque_foreground_fraction', 0.62))))))

    def visible_fraction(self, event):
        explicit = event.get('visible_ink_fraction')
        if explicit is not None:
            return max(0.0, min(1.0, float(explicit)))
        source = event.get('source_path') or event.get('mask_path')
        if not source:
            return self._fallback(event)
        path = pathlib.Path(source)
        try:
            stat = path.stat()
        except OSError:
            return self._fallback(event)
        key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
        if key in self._fractions:
            return self._fractions[key]
        try:
            # Coverage is stable at thumbnail scale and this avoids retaining full masks.
            with Image.open(path) as image:
                image.thumbnail((512, 512))
                value = perceptual_visible_fraction(image)
        except Exception:
            value = self._fallback(event)
        value = max(0.0, min(1.0, float(value)))
        self._fractions[key] = value
        return value

    def project(self, event, rect_norm, opacity=1.0, clip_rect=None):
        """Normalized visible ink after layout/motion transform and optional clipping."""
        x, y, w, h = map(float, rect_norm)
        if clip_rect is not None:
            cx, cy, cw, ch = map(float, clip_rect)
            x1, y1 = max(x, cx), max(y, cy)
            x2, y2 = min(x + w, cx + cw), min(y + h, cy + ch)
            w, h = max(0.0, x2 - x1), max(0.0, y2 - y1)
        return max(0.0, w) * max(0.0, h) * self.visible_fraction(event) * max(0.0, min(1.0, float(opacity)))
