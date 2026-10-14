"""
设置读写：config/settings.json 为主；heytea_presets.json 仅作迁移回退，不再写入。
存储短键：drawing_method="仿真人"，extraction_method="Anime2Sketch"。
"""

import json
import os

from modules.app_logger import log_error, log_info

APP_NAME = "Heytea Painter"
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_DIR = os.path.join(APP_ROOT, "config")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")
LEGACY_PRESET_FILE = os.path.join(APP_ROOT, "heytea_presets.json")

SAFE_LIFT_PAUSE_SECONDS = 5.0
MIN_LIFT_PAUSE_SECONDS = 1.0

DEFAULTS = {
    "extraction_method": "Anime2Sketch",
    "sigma_s": 60,
    "sigma_r": 0.4,
    "shade_factor": 0.05,
    "canny_blur": 3,
    "canny_low": 50,
    "canny_high": 150,
    "simplify_epsilon": 1.0,
    "preview_thickness": 2,
    "spline_smoothness": 0,
    "jitter_correction": 0,
    "stroke_len": 15,
    "min_drag_dist": 5,
    "draw_delay": 5,
    "drawing_method": "仿真人",
    "anime_threshold": 127,
    "anime_morph_size": 2,
    "anime_morph_iter": 1,
    "anime_min_area": 10,
    "anime_contour_mode": "外部轮廓",
    "anime_pre_blur": 0,
    "anime_edge_enhance": 0,
    "anime_sigmoid_threshold": 0.5,
    "anime_invert": False,
    "anime_adaptive": False,
    "thin_contours": False,
    "taper_paths": True,
    "taper_layers": 3,
    "taper_ratio": 0.18,
    "taper_spacing": 1.0,
    "skip_points": 1,
    "hand_shake": 1,
    "think_pause": 3,
    "corner_sharpness": 5,
    "lift_pause": 5.0,
    "speed_multiplier": 1.0,
    "canvas_calib": "manual",
    "lineart_detect_resolution": 512,
    "lineart_min_area": 10,
    "lineart_contour_mode": "中心线",
    "lineart_invert": True,
    "ui_mode": "simple",
    "bbox_cell_size": 0.0,  # 0=自动分块边长
    "show_chunk_grid": False,  # 预览上叠加分块网格
}

EXTRACT_ALIASES = {
    "Pencil Sketch (V19)": "Pencil Sketch",
    "Pencil Sketch": "Pencil Sketch",
    "Canny 边缘检测": "Canny",
    "Canny": "Canny",
    "Anime2Sketch": "Anime2Sketch",
    "LineartAnime": "LineartAnime",
}

DRAW_ALIASES = {
    "方法 1: 短行程 (推荐)": "短行程",
    "短行程": "短行程",
    "方法 2: 智能拖动 (蜘蛛网?)": "智能拖动",
    "智能拖动": "智能拖动",
    "方法 3: 仿真人绘画 🎨": "仿真人",
    "仿真人": "仿真人",
    "压感": "压感",
    "压感重绘": "压感",
}

CONTOUR_MODE_ALIASES = {
    "外部轮廓 (快速)": "外部轮廓",
    "外部轮廓": "外部轮廓",
    "所有轮廓 (详细)": "所有轮廓",
    "所有轮廓": "所有轮廓",
    "骨架提取 (推荐)": "中心线",
    "骨架提取": "中心线",
    "中心线": "中心线",
}

CALIB_ALIASES = {
    "手动定画布": "manual",
    "manual": "manual",
    "自动识别画布": "auto",
    "auto": "auto",
}

CALIB_TO_UI = {
    "manual": "手动定画布",
    "auto": "自动识别画布",
}

# 简单模式只保留 AI 提取；Pencil/Canny 收进高级模式
SIMPLE_EXTRACT_METHODS = ["Anime2Sketch", "LineartAnime"]
ALL_EXTRACT_METHODS = ["Pencil Sketch", "Canny", "Anime2Sketch", "LineartAnime"]

ANIME_MODE_TO_PROCESSOR = {
    "外部轮廓": "外部轮廓 (快速)",
    "所有轮廓": "所有轮廓 (详细)",
    "骨架提取": "中心线",
    "中心线": "中心线",
}


def apply_beginner_preset(values):
    """一键推荐：识图准、绘制稳、适合小白。"""
    values = dict(values)
    values["extraction_method"] = "Anime2Sketch"
    values["drawing_method"] = "仿真人"
    values["preview_thickness"] = 2
    values["lift_pause"] = SAFE_LIFT_PAUSE_SECONDS
    values["jitter_correction"] = 0
    values["speed_multiplier"] = 1.0
    values["ui_mode"] = "simple"
    return values


def normalize_settings(raw):
    """接受旧版显示字符串，返回短键设置。缺项用 DEFAULTS。"""
    src = raw if isinstance(raw, dict) else {}
    values = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        if key in src:
            values[key] = src[key]
    values["extraction_method"] = EXTRACT_ALIASES.get(
        str(values.get("extraction_method", "")), DEFAULTS["extraction_method"]
    )
    values["drawing_method"] = DRAW_ALIASES.get(
        str(values.get("drawing_method", "")), DEFAULTS["drawing_method"]
    )
    values["anime_contour_mode"] = CONTOUR_MODE_ALIASES.get(
        str(values.get("anime_contour_mode", "")), DEFAULTS["anime_contour_mode"]
    )
    values["canvas_calib"] = CALIB_ALIASES.get(
        str(values.get("canvas_calib", "")), DEFAULTS["canvas_calib"]
    )
    values["lineart_contour_mode"] = CONTOUR_MODE_ALIASES.get(
        str(values.get("lineart_contour_mode", "")), DEFAULTS["lineart_contour_mode"]
    )
    mode = str(values.get("ui_mode", "simple")).lower()
    values["ui_mode"] = "advanced" if mode in ("advanced", "expert", "高级") else "simple"
    try:
        lift = float(values.get("lift_pause", SAFE_LIFT_PAUSE_SECONDS))
    except (TypeError, ValueError):
        lift = SAFE_LIFT_PAUSE_SECONDS
    if values["ui_mode"] == "simple":
        lift = max(lift, SAFE_LIFT_PAUSE_SECONDS)
    else:
        lift = max(lift, MIN_LIFT_PAUSE_SECONDS)
    values["lift_pause"] = lift
    try:
        values["preview_thickness"] = max(1, int(float(values.get("preview_thickness", 2))))
    except (TypeError, ValueError):
        values["preview_thickness"] = 2
    try:
        cell = float(values.get("bbox_cell_size", 0.0))
    except (TypeError, ValueError):
        cell = 0.0
    # 0 = 自动；允许 20–2000 手动
    if cell < 0:
        cell = 0.0
    elif cell > 0:
        cell = max(20.0, min(2000.0, cell))
    values["bbox_cell_size"] = cell
    values["show_chunk_grid"] = bool(values.get("show_chunk_grid", False))
    return values

def load_settings():
    """
    读取 config/settings.json；不存在则回退 heytea_presets.json。
    返回 (normalized_dict, source_path)；都没有则 (None, None)。
    """
    path = SETTINGS_FILE if os.path.isfile(SETTINGS_FILE) else None
    if path is None and os.path.isfile(LEGACY_PRESET_FILE):
        path = LEGACY_PRESET_FILE
    if path is None:
        return None, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return normalize_settings(raw), path
    except Exception as exc:
        log_error("加载设置失败", exc)
        return None, path


def save_settings(values):
    """写入短键到 config/settings.json。永不写回 heytea_presets.json。"""
    canonical = normalize_settings(values)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(canonical, f, indent=4, ensure_ascii=False)
    log_info(f"设置已写入 {SETTINGS_FILE}")
    return SETTINGS_FILE
