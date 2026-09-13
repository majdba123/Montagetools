from __future__ import annotations

import pathlib
import tempfile

import cv2
import numpy as np

from hexa_v31.interaction import pixel_qa
from hexa_v31.render.preview import _event_state

FPS = 30.0
WIDTH = 640
HEIGHT = 360


def _event():
    return {
        'event_id': 'STATE_MOVING_ACTOR',
        'scene_id': 'FUTURE_SCENE',
        'visual_card_id': 'FUTURE_CARD',
        'render_mode': 'ROOT_ATOMIC',
        'planned_rect_norm': [0.16, 0.42, 0.18, 0.16],
        'object_rest_position_px': [0.25 * 1920.0, 0.50 * 1080.0],
        'preset_coordinate_mode': 'ABSOLUTE_OBJECT_CENTER',
        'start_seconds': 0.0,
        'settle_seconds': 0.8,
        'end_seconds': 1.2,
        'physical_start_seconds': 0.0,
        'physical_end_seconds': 1.2,
        'motion_start_seconds': 0.0,
        'motion_end_seconds': 1.2,
        'preset_entry': {
            'name': 'APPEAR_HIGH_SCALE',
            'start_seconds': 0.0,
            'duration_seconds': 0.8,
        },
        'preset_exit': None,
        'preset_actions': [],
        'composition_states': [{
            'state_id': 'STATE_GEOMETRY_DESTINATION',
            'scene_id': 'FUTURE_SCENE',
            'card_id': 'FUTURE_CARD',
            'start_seconds': 0.0,
            'transition_duration_seconds': 0.25,
            'center_norm': [0.76, 0.30],
            'scale_multiplier': 1.0,
            'visibility': 1.0,
            'role': 'BLOCKER',
            'focus_event_id': 'STATE_MOVING_ACTOR',
            'participating_event_ids': ['STATE_MOVING_ACTOR'],
            'layout_archetype': 'GENERIC_PAIR',
            'state_reason': 'TEST_RENDER_STATE_AUTHORITY',
            'translation_safe': False,
            'phase_center_authority': 'ABSOLUTE_PHASE_PLACEMENT_CENTER',
        }],
    }


def _plan(event):
    return {
        'fps': FPS,
        'events': [event],
        'interaction_engine': {
            'actionable_interaction_count': 1,
            'embodied_interaction_count': 1,
            'physical_actions': [{
                'interaction_id': 'INT::STATE_GEOMETRY',
                'event_id': event['event_id'],
                'phase': 'ACTION',
                'preset': 'APPEAR_HIGH_SCALE',
                'start_seconds': 0.0,
                'end_seconds': 0.8,
            }],
        },
    }


def _write_render_state_video(path: pathlib.Path, event: dict, white_only: bool = False):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), FPS, (WIDTH, HEIGHT))
    assert writer.isOpened()
    for frame_index in range(int(round(1.2 * FPS))):
        t = frame_index / FPS
        frame = np.full((HEIGHT, WIDTH, 3), 255, np.uint8)
        if not white_only:
            state = _event_state(event, t)
            if state is not None:
                center, scale, opacity = state
                if opacity > 0.01:
                    cx = int(round(float(center[0]) * WIDTH / 1920.0))
                    cy = int(round(float(center[1]) * HEIGHT / 1080.0))
                    rw = max(10, int(round(event['planned_rect_norm'][2] * WIDTH * float(scale))))
                    rh = max(10, int(round(event['planned_rect_norm'][3] * HEIGHT * float(scale))))
                    value = int(round(255.0 - 180.0 * max(0.0, min(1.0, float(opacity)))))
                    cv2.rectangle(
                        frame,
                        (max(0, cx - rw // 2), max(0, cy - rh // 2)),
                        (min(WIDTH - 1, cx + rw // 2), min(HEIGHT - 1, cy + rh // 2)),
                        (value, value, value),
                        -1,
                    )
        writer.write(frame)
    writer.release()


def main():
    event = _event()
    plan = _plan(event)
    with tempfile.TemporaryDirectory(prefix='hexa_pixel_state_geometry_') as raw:
        root = pathlib.Path(raw)
        video = root / 'state_geometry.mp4'
        _write_render_state_video(video, event)
        result = pixel_qa.verify_encoded_interactions(str(video), plan, FPS)
        assert result['pass'] and result['verified_action_count'] == 1, result
        row = result['actions'][0]
        assert row['start_state_geometry_resolved'] and row['end_state_geometry_resolved'], row
        assert row['start_roi_px'] != row['end_roi_px'], row
        assert row['end_nonwhite_pixels'] >= 20, row

        # Prove the historical static planned-rect ROI would miss the actor at
        # the appearance endpoint. This is the exact false-negative class fixed
        # by state-aware endpoint geometry.
        cap = cv2.VideoCapture(str(video))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        end_index = int(round((0.8 - 0.08) * FPS))
        end_frame = pixel_qa._read(cap, end_index, total)
        cap.release()
        assert end_frame is not None
        static_roi = pixel_qa._roi(event, 'APPEAR_HIGH_SCALE', WIDTH, HEIGHT)
        static_crop = pixel_qa._crop(end_frame, static_roi)
        static_nonwhite = int(np.count_nonzero(np.any(static_crop < 248, axis=2)))
        assert static_nonwhite == 0, (static_nonwhite, static_roi, row)

        white = root / 'white.mp4'
        _write_render_state_video(white, event, white_only=True)
        bad = pixel_qa.verify_encoded_interactions(str(white), plan, FPS)
        assert not bad['pass'] and bad['failures'], bad

    print('V31_INTERACTION_PIXEL_STATE_GEOMETRY_PASS')


if __name__ == '__main__':
    main()
