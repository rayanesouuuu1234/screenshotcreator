"""Frame comparison helpers for scene-change detection."""

from __future__ import annotations

import cv2
import numpy as np

WHITE_LEVEL = 235
BLACK_LEVEL = 20
DIFF_THRESHOLD = 30
EDGE_BLEND_WEIGHT = 0.5
DHASH_DUPLICATE_DISTANCE = 8


def _background_mask(current: np.ndarray, previous: np.ndarray) -> np.ndarray:
    """Pixels unchanged in both frames and near-uniform white or black chrome."""
    both_white = (current >= WHITE_LEVEL) & (previous >= WHITE_LEVEL)
    both_black = (current <= BLACK_LEVEL) & (previous <= BLACK_LEVEL)
    return both_white | both_black


def _masked_pixel_change_percent(current: np.ndarray, previous: np.ndarray) -> float:
    diff = cv2.absdiff(current, previous)
    bg_mask = _background_mask(current, previous)
    content_mask = ~bg_mask
    content_count = int(np.count_nonzero(content_mask))
    total = current.size
    if content_count < max(1, int(total * 0.05)):
        _, global_mask = cv2.threshold(diff, DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
        global_mask = cv2.morphologyEx(global_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        changed = cv2.countNonZero(global_mask)
        return (changed / max(total, 1)) * 100.0

    changed_mask = np.zeros_like(diff, dtype=np.uint8)
    changed_mask[content_mask & (diff >= DIFF_THRESHOLD)] = 255
    changed_mask = cv2.morphologyEx(changed_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    changed = cv2.countNonZero(changed_mask)
    return (changed / max(content_count, 1)) * 100.0


def _edge_map(gray: np.ndarray) -> np.ndarray:
    edges = cv2.Canny(gray, 50, 150)
    return cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)


def _edge_change_percent(current: np.ndarray, previous: np.ndarray) -> float:
    edge_current = _edge_map(current)
    edge_previous = _edge_map(previous)
    return _masked_pixel_change_percent(edge_current, edge_previous)


def compute_scene_change_score(current: np.ndarray, baseline: np.ndarray) -> float:
    """Blended change score (0–100): masked pixels + edge structure."""
    pixel_score = _masked_pixel_change_percent(current, baseline)
    edge_score = _edge_change_percent(current, baseline)
    return (1.0 - EDGE_BLEND_WEIGHT) * pixel_score + EDGE_BLEND_WEIGHT * edge_score


def dhash(gray: np.ndarray) -> int:
    """Difference hash for near-duplicate detection."""
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    diff = small[:, 1:] > small[:, :-1]
    value = 0
    for bit, is_set in enumerate(diff.flatten()):
        if is_set:
            value |= 1 << bit
    return value


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def is_near_duplicate(left_hash: int | None, right_hash: int) -> bool:
    if left_hash is None:
        return False
    return hamming_distance(left_hash, right_hash) < DHASH_DUPLICATE_DISTANCE
