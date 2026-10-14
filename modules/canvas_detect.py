"""
识别微信窗口内最大的浅色矩形画布。
失败时返回 reason，由会话回退到手动点角。
"""

import sys

import cv2
import numpy as np

from modules.app_logger import log_error, log_info
from modules.platform_input import get_dpi_info

IS_MACOS = sys.platform == "darwin"

REASON_UNSUPPORTED = "当前系统不支持自动识别，请手动点角"
REASON_NO_WECHAT = "未找到微信窗口"
REASON_NO_CAPTURE = "未授权屏幕录制，或截图失败"
REASON_NO_CANVAS = "未找到浅色画布"


def quartz_bounds_to_topleft(bounds, screen_height):
    """Quartz 窗口框（原点在主屏左下）→ 左上角逻辑坐标。"""
    x = float(bounds.get("X", 0))
    y = float(bounds.get("Y", 0))
    width = float(bounds.get("Width", 0))
    height = float(bounds.get("Height", 0))
    top = float(screen_height) - y - height
    return x, top, width, height


def pixel_rect_to_logical(win_x, win_y, rect, scale):
    """窗口内像素矩形 → 屏幕逻辑点 (top_left, bottom_right)。"""
    scale = float(scale) if scale else 1.0
    rx, ry, rw, rh = rect
    left = win_x + rx / scale
    top = win_y + ry / scale
    return (int(round(left)), int(round(top))), (
        int(round(left + rw / scale)),
        int(round(top + rh / scale)),
    )


def find_light_rectangle(image_bgr, scale=1.0):
    """在截图中找最大的近白矩形。rect 为像素 (x, y, w, h)。"""
    if image_bgr is None or image_bgr.size == 0:
        return None
    height, width = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    title = int(max(20, 28 * float(scale or 1.0)))
    roi = gray[title:height, 0:width]
    if roi.size == 0:
        roi = gray
        title = 0
    _, binary = cv2.threshold(roi, 240, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0
    min_area = width * height * 0.08
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < min_area:
            continue
        ratio = w / float(h) if h else 0
        if ratio < 0.35 or ratio > 2.8:
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) < 4:
            continue
        fill = cv2.contourArea(contour) / float(area)
        if fill < 0.75:
            continue
        cx = x + w / 2
        cy = y + h / 2
        if cx < width * 0.08 or cx > width * 0.92:
            continue
        if cy < roi.shape[0] * 0.08 or cy > roi.shape[0] * 0.95:
            continue
        if area > best_area:
            best_area = area
            best = (x, y + title, w, h)
    return best


def _screen_height_logical():
    info = get_dpi_info()
    return float(info["logical_size"][1]), float(info.get("scale") or 1.0)


def _find_wechat_window_macos():
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGNullWindowID,
        kCGWindowListExcludeDesktopElements,
        kCGWindowListOptionOnScreenOnly,
    )

    options = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
    windows = CGWindowListCopyWindowInfo(options, kCGNullWindowID) or []
    candidates = []
    for window in windows:
        owner = str(window.get("kCGWindowOwnerName") or "")
        name = str(window.get("kCGWindowName") or "")
        blob = owner + name
        if "微信" not in blob and "WeChat" not in blob:
            continue
        if int(window.get("kCGWindowLayer") or 0) != 0:
            continue
        bounds = window.get("kCGWindowBounds") or {}
        width = float(bounds.get("Width") or 0)
        height = float(bounds.get("Height") or 0)
        if width < 200 or height < 200:
            continue
        candidates.append({
            "id": int(window.get("kCGWindowNumber") or 0),
            "bounds": bounds,
            "area": width * height,
            "owner": owner,
            "name": name,
        })
    if not candidates:
        return None
    return max(candidates, key=lambda item: item["area"])


def _capture_window_macos(window_id):
    from Quartz import (
        CGDataProviderCopyData,
        CGImageGetBitsPerPixel,
        CGImageGetBytesPerRow,
        CGImageGetDataProvider,
        CGImageGetHeight,
        CGImageGetWidth,
        CGRectNull,
        CGWindowListCreateImage,
        kCGWindowImageBoundsIgnoreFraming,
        kCGWindowListOptionIncludingWindow,
    )

    image = CGWindowListCreateImage(
        CGRectNull,
        kCGWindowListOptionIncludingWindow,
        window_id,
        kCGWindowImageBoundsIgnoreFraming,
    )
    if image is None:
        return None
    width = int(CGImageGetWidth(image))
    height = int(CGImageGetHeight(image))
    if width < 8 or height < 8:
        return None
    row_bytes = int(CGImageGetBytesPerRow(image))
    bpp = int(CGImageGetBitsPerPixel(image))
    raw = CGDataProviderCopyData(CGImageGetDataProvider(image))
    arr = np.frombuffer(bytes(raw), dtype=np.uint8)
    if bpp != 32:
        return None
    cols = max(width, row_bytes // 4)
    arr = arr.reshape(height, cols, 4)[:, :width, :]
    return arr[:, :, [2, 1, 0]].copy()


def detect_wechat_canvas():
    """
    返回 dict: ok, top_left, bottom_right, reason。
    不弹窗、不移动鼠标。
    """
    if not IS_MACOS:
        return {"ok": False, "top_left": None, "bottom_right": None, "reason": REASON_UNSUPPORTED}

    try:
        window = _find_wechat_window_macos()
    except Exception as exc:
        log_error("枚举窗口失败", exc)
        return {"ok": False, "top_left": None, "bottom_right": None, "reason": REASON_NO_WECHAT}

    if window is None:
        return {"ok": False, "top_left": None, "bottom_right": None, "reason": REASON_NO_WECHAT}

    screen_h, scale = _screen_height_logical()
    win_x, win_y, _win_w, _win_h = quartz_bounds_to_topleft(window["bounds"], screen_h)
    log_info(f"微信窗口 id={window['id']} 逻辑原点=({win_x:.0f},{win_y:.0f})")

    try:
        shot = _capture_window_macos(window["id"])
    except Exception as exc:
        log_error("截取微信窗口失败", exc)
        shot = None
    if shot is None:
        return {"ok": False, "top_left": None, "bottom_right": None, "reason": REASON_NO_CAPTURE}

    rect = find_light_rectangle(shot, scale=scale)
    if rect is None:
        return {"ok": False, "top_left": None, "bottom_right": None, "reason": REASON_NO_CANVAS}

    top_left, bottom_right = pixel_rect_to_logical(win_x, win_y, rect, scale)
    if bottom_right[0] <= top_left[0] or bottom_right[1] <= top_left[1]:
        return {"ok": False, "top_left": None, "bottom_right": None, "reason": REASON_NO_CANVAS}

    log_info(f"识别画布 {top_left} → {bottom_right}")
    return {
        "ok": True,
        "top_left": top_left,
        "bottom_right": bottom_right,
        "reason": "",
    }
