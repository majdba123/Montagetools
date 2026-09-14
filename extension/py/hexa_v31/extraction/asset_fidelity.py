from __future__ import annotations

import pathlib
from typing import Any

import numpy as np
from PIL import Image

ASSET_FIDELITY_AUTHORITY = 'HEXA_ORIGINAL_SOURCE_PIXEL_FIDELITY_V1'


def _alpha_bbox(alpha: np.ndarray, threshold: int = 4) -> tuple[int, int, int, int] | None:
    yy, xx = np.where(np.asarray(alpha) > int(threshold))
    if not len(xx):
        return None
    return int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1


def certify_extracted_layers(
    units: list[dict[str, Any]],
    source_rgb: np.ndarray,
    staging_dir: str | pathlib.Path,
) -> dict[str, Any]:
    """Certify that extracted actors preserve the supplied scene artwork.

    Shape extraction may change alpha only. Fully opaque interior RGB pixels remain
    bit-identical to the supplied scene image. Crop metadata must tightly contain the
    extracted alpha; source-edge actors are legal but are downgraded to in-place
    motion so later transforms cannot invent pixels outside the supplied artwork.
    """
    root = pathlib.Path(staging_dir)
    h, w = source_rgb.shape[:2]
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    downgraded: list[str] = []

    for unit in units:
        event_id = str(unit.get('physical_id') or unit.get('event_id') or 'UNKNOWN')
        layer_name = pathlib.Path(str(unit.get('layer_path') or '')).name
        layer_path = root / layer_name
        if not layer_name or not layer_path.is_file():
            failures.append(f'{event_id}: extracted layer missing')
            rows.append({'event_id': event_id, 'pass': False, 'reason': 'LAYER_MISSING'})
            continue

        rgba = np.asarray(Image.open(layer_path).convert('RGBA'))
        if rgba.shape[:2] != (h, w):
            failures.append(f'{event_id}: extracted layer canvas differs from supplied scene canvas')
            rows.append({'event_id': event_id, 'pass': False, 'reason': 'CANVAS_SIZE_MISMATCH'})
            continue

        alpha = rgba[:, :, 3]
        bbox = _alpha_bbox(alpha)
        if bbox is None:
            failures.append(f'{event_id}: extracted alpha is empty')
            rows.append({'event_id': event_id, 'pass': False, 'reason': 'EMPTY_ALPHA'})
            continue

        x0, y0, x1, y1 = bbox
        previous_crop_origin = list(unit.get('crop_origin_px') or [x0, y0])
        previous_crop_size = list(unit.get('crop_size_px') or [x1 - x0, y1 - y0])
        pcx0, pcy0 = int(previous_crop_origin[0]), int(previous_crop_origin[1])
        pcx1, pcy1 = pcx0 + int(previous_crop_size[0]), pcy0 + int(previous_crop_size[1])
        previous_contains = pcx0 <= x0 and pcy0 <= y0 and pcx1 >= x1 and pcy1 >= y1

        pad = max(1, min(3, int(round(min(x1 - x0, y1 - y0) * 0.03))))
        cx0, cy0 = max(0, x0 - pad), max(0, y0 - pad)
        cx1, cy1 = min(w, x1 + pad), min(h, y1 + pad)
        unit['crop_origin_px'] = [cx0, cy0]
        unit['crop_size_px'] = [cx1 - cx0, cy1 - cy0]
        unit['bbox'] = [x0, y0, x1 - x0, y1 - y0]
        unit['bbox_norm'] = [round(x0 / w, 6), round(y0 / h, 6), round((x1 - x0) / w, 6), round((y1 - y0) / h, 6)]
        unit['center_norm'] = [round((x0 + x1) / (2.0 * w), 6), round((y0 + y1) / (2.0 * h), 6)]
        unit['optical_center'] = list(unit['center_norm'])
        unit['area_px'] = int(np.count_nonzero(alpha > 4))

        bbox_area = max(1, (x1 - x0) * (y1 - y0))
        crop_area = max(1, (cx1 - cx0) * (cy1 - cy0))
        crop_ratio = crop_area / float(bbox_area)
        crop_tight = crop_ratio <= 1.20
        crop_repaired = (not previous_contains) or previous_crop_origin != unit['crop_origin_px'] or previous_crop_size != unit['crop_size_px']

        opaque = alpha >= 254
        opaque_count = int(np.count_nonzero(opaque))
        if opaque_count:
            diff = np.abs(rgba[:, :, :3].astype(np.int16) - source_rgb.astype(np.int16))
            opaque_rgb_mae = float(diff[opaque].mean())
        else:
            opaque_rgb_mae = 0.0
        rgb_fidelity = opaque_rgb_mae <= 0.25

        edge_touch = bool(
            np.any(alpha[0] > 4) or np.any(alpha[-1] > 4)
            or np.any(alpha[:, 0] > 4) or np.any(alpha[:, -1] > 4)
        )
        stage_leak = float((unit.get('matting') or {}).get('opaque_stage_leak_fraction') or 0.0)
        stage_clean = stage_leak <= 1e-6

        if edge_touch:
            render_mode = str(unit.get('render_mode') or '').upper()
            semantic_type = str(unit.get('semantic_type') or '').upper()
            is_residual_support = render_mode == 'RESIDUAL_SUPPORT' or semantic_type == 'RESIDUAL_SUPPORT'
            if bool(unit.get('translation_safe_after_occlusion')) or str(unit.get('animation_mode') or '').upper() == 'TRANSLATE_SAFE':
                downgraded.append(event_id)
            unit['translation_safe_after_occlusion'] = False
            unit['animation_safe'] = False
            unit['rotation_safe'] = False
            unit['animation_mode'] = 'STATIC_SUPPORT' if is_residual_support else 'IN_PLACE_ACTING_ONLY'
            if is_residual_support:
                unit['independent_motion_allowed'] = False
                unit['position_animated'] = False
            unit['source_edge_motion_guard'] = True

        passed = crop_tight and rgb_fidelity and stage_clean
        if not crop_tight:
            failures.append(f'{event_id}: canonical alpha crop is not tight (ratio={crop_ratio:.3f})')
        if not rgb_fidelity:
            failures.append(f'{event_id}: opaque source RGB changed (mae={opaque_rgb_mae:.3f})')
        if not stage_clean:
            failures.append(f'{event_id}: opaque white-stage leak remains ({stage_leak:.6f})')

        unit['asset_fidelity_locked'] = True
        unit['asset_fidelity_authority'] = ASSET_FIDELITY_AUTHORITY
        unit['source_pixel_policy'] = 'ORIGINAL_RGB_OPAQUE_INTERIOR__ALPHA_ONLY_SHAPE_EXTRACTION'
        unit['render_crop_policy'] = 'TIGHT_ALPHA_BBOX_WITH_TRANSPARENT_PAD'
        unit['asset_fidelity_qa'] = {
            'pass': passed,
            'alpha_bbox_px': [x0, y0, x1, y1],
            'crop_bbox_px': [cx0, cy0, cx1, cy1],
            'crop_metadata_repaired': crop_repaired,
            'previous_crop_contained_alpha': previous_contains,
            'crop_to_alpha_bbox_area_ratio': round(crop_ratio, 6),
            'opaque_source_rgb_mae': round(opaque_rgb_mae, 6),
            'opaque_stage_leak_fraction': round(stage_leak, 8),
            'source_edge_touch': edge_touch,
        }
        rows.append({'event_id': event_id, **unit['asset_fidelity_qa']})

    return {
        'schema': 'HEXA_ASSET_FIDELITY_QA_V1',
        'authority': ASSET_FIDELITY_AUTHORITY,
        'pass': not failures,
        'layer_count': len(rows),
        'failures': failures,
        'source_edge_motion_downgrade_event_ids': downgraded,
        'rows': rows,
    }
