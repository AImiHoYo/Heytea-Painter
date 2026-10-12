"""
UI state and parameter model for Heytea Painter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


DEFAULT_PRESET: Dict[str, Any] = {
    "extraction_method": "Pencil Sketch (V19)",
    "sigma_s": 60,
    "sigma_r": 0.4,
    "shade_factor": 0.05,
    "canny_blur": 3,
    "canny_low": 50,
    "canny_high": 150,
    "simplify_epsilon": 1.0,
    "preview_thickness": 1,
    "spline_smoothness": 0,
    "jitter_correction": 0,
    "stroke_len": 15,
    "min_drag_dist": 5,
    "draw_delay": 5,
    "drawing_method": "方法 1: 短行程 (推荐)",
    "anime_threshold": 127,
    "anime_morph_size": 2,
    "anime_morph_iter": 1,
    "anime_min_area": 10,
    "anime_contour_mode": "外部轮廓 (快速)",
    "anime_pre_blur": 0,
    "anime_edge_enhance": 0,
    "anime_sigmoid_threshold": 0.5,
    "anime_invert": False,
    "anime_adaptive": False,
    "thin_contours": False,
    "skip_points": 1,
    "hand_shake": 1,
    "think_pause": 3,
    "corner_sharpness": 5,
    "lift_pause": 5,
    "speed_multiplier": 1.0,
}

RANGES: Dict[str, tuple[float, float]] = {
    "sigma_s": (1, 200),
    "sigma_r": (0.01, 1.0),
    "shade_factor": (0.0, 1.0),
    "canny_blur": (1, 21),
    "canny_low": (1, 500),
    "canny_high": (1, 1000),
    "simplify_epsilon": (0.1, 5.0),
    "preview_thickness": (1, 20),
    "spline_smoothness": (0, 5000),
    "jitter_correction": (0, 10),
    "stroke_len": (5, 100),
    "min_drag_dist": (1, 20),
    "draw_delay": (1, 100),
    "anime_threshold": (50, 200),
    "anime_morph_size": (1, 5),
    "anime_morph_iter": (1, 3),
    "anime_min_area": (5, 100),
    "anime_pre_blur": (0, 9),
    "anime_edge_enhance": (0, 3.0),
    "anime_sigmoid_threshold": (0.3, 0.9),
    "skip_points": (1, 5),
    "hand_shake": (0, 5),
    "think_pause": (1, 10),
    "corner_sharpness": (0, 10),
    "lift_pause": (3, 15),
    "speed_multiplier": (0.1, 5.0),
}


def _clamp(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    if number < low:
        return low
    if number > high:
        return high
    return number


def normalize_preset(values: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(values, dict):
        return dict(DEFAULT_PRESET)

    merged: Dict[str, Any] = dict(DEFAULT_PRESET)
    merged.update(values)

    for key, (low, high) in RANGES.items():
        merged[key] = _clamp(merged.get(key), low, high)

    merged["canny_blur"] = int(merged["canny_blur"])
    if merged["canny_blur"] % 2 == 0:
        merged["canny_blur"] += 1
        if merged["canny_blur"] > 21:
            merged["canny_blur"] = 21

    for key in (
        "preview_thickness",
        "jitter_correction",
        "stroke_len",
        "min_drag_dist",
        "draw_delay",
        "anime_threshold",
        "anime_morph_size",
        "anime_morph_iter",
        "anime_min_area",
        "anime_pre_blur",
        "skip_points",
        "hand_shake",
        "think_pause",
        "corner_sharpness",
        "lift_pause",
    ):
        merged[key] = int(merged[key])

    merged["anime_invert"] = bool(merged.get("anime_invert", False))
    merged["anime_adaptive"] = bool(merged.get("anime_adaptive", False))
    merged["thin_contours"] = bool(merged.get("thin_contours", False))

    return merged


@dataclass
class AppRuntimeState:
    file_path: str | None = None
    contours: list | None = None
    img_w: int = 0
    img_h: int = 0
