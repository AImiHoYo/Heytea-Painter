"""
绘画引擎模块
包含画布校准、路径精简，以及统一的 draw_paths 循环。
"""

import time
import random
import numpy as np

from modules.platform_input import (
    get_dpi_info,
    is_abort_pressed,
    mouse_down,
    mouse_up,
    move_to,
    start_hotkey_listener,
    stop_hotkey_listener,
)
from modules.app_logger import log_error, log_info


class DrawingAborted(KeyboardInterrupt):
    """用户请求中止绘画。"""


# 小程序画布经常吃不到过短的 mouse_up；在空中移动到下一条线之前必须先松开并停够。
MIN_PEN_UP_SETTLE = 0.12
MIN_AIR_MOVE_SETTLE = 0.04


def human_delay(base_delay, randomness=0.3):
    """可中止的延迟。换线停顿可达数秒，必须分段睡眠并检查中止标志。"""
    variation = base_delay * randomness
    actual_delay = max(0.0, base_delay + random.uniform(-variation, variation))
    deadline = time.time() + actual_delay
    while True:
        if is_abort_pressed():
            raise DrawingAborted("用户中止")
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(0.05, remaining))


def stroke_gap_seconds(lift_pause):
    """换线等待：至少 MIN_PEN_UP_SETTLE，避免滑块被拉到 0.05s 时连笔。"""
    return max(MIN_PEN_UP_SETTLE, float(lift_pause or 0.0))


def finish_stroke(lift_pause):
    """收笔：重复抬笔，再等到小程序确认松开。之后才能空中移动。"""
    mouse_up()
    human_delay(0.02, randomness=0)
    mouse_up()
    pause = stroke_gap_seconds(lift_pause)
    human_delay(pause, randomness=0.15)


def begin_stroke(x, y, pre_delay=0.0):
    """空中移动到下一条线的起点，到位后再按下。"""
    move_to(x, y)
    human_delay(max(MIN_AIR_MOVE_SETTLE, float(pre_delay or 0.0)), randomness=0)
    mouse_down()
    human_delay(0.025, randomness=0)


def clamp(value, min_val, max_val):
    """限制值在范围内"""
    return max(min_val, min(value, max_val))


def calculate_angle_change(p1, p2, p3):
    """计算三点之间的角度变化"""
    v1 = np.array([p2[0] - p1[0], p2[1] - p1[1]])
    v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])

    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)

    if norm1 < 1e-6 or norm2 < 1e-6:
        return 0

    cos_angle = np.dot(v1, v2) / (norm1 * norm2)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    angle = np.arccos(cos_angle)

    return np.degrees(angle)


def calculate_path_complexity(points):
    """计算路径复杂度（基于角度变化）"""
    if len(points) < 3:
        return 0

    total_angle_change = 0
    for i in range(1, len(points) - 1):
        angle = calculate_angle_change(points[i - 1], points[i], points[i + 1])
        total_angle_change += angle

    return total_angle_change / (len(points) - 2) if len(points) > 2 else 0


def _user_log(app, message):
    """用户可见进度：走 GUI 控制台（线程安全由 app.log 处理）。"""
    logger_fn = getattr(app, "log", None)
    if callable(logger_fn):
        logger_fn(message)
    else:
        print(message)


def _progress(app, done, total, last_mark):
    """大约每 25% 报一次，避免绘画过程刷屏。"""
    if total <= 0:
        return last_mark
    pct = done * 100 // total
    mark = (pct // 25) * 25
    if mark >= 25 and mark > last_mark and mark < 100:
        _user_log(app, f"进度 {done}/{total}")
        return mark
    return last_mark


def compute_canvas_calibration(top_left, bottom_right, img_w, img_h):
    """
    根据主线程采集的两个角点计算绘画区域。
    不要在后台线程里创建 pynput.Listener，macOS 会 SIGTRAP 崩溃。
    """
    dpi_info = get_dpi_info()
    screen_x, screen_y = top_left[0], top_left[1]
    bottom_x, bottom_y = bottom_right[0], bottom_right[1]
    screen_w = bottom_x - screen_x
    screen_h = bottom_y - screen_y

    log_info(
        f"标定 角点={top_left}->{bottom_right} 画布={screen_w}x{screen_h} "
        f"图={img_w}x{img_h} 屏={dpi_info['logical_size']} "
        f"缩放={dpi_info['scale']:.2f} ({dpi_info['awareness_method']})"
    )

    if screen_w <= 0 or screen_h <= 0:
        log_error("标定坐标无效")
        return None, None, None, None, None, None, None, None, None

    scale_x = screen_w / img_w
    scale_y = screen_h / img_h
    scale_factor = min(scale_x, scale_y)

    actual_w = img_w * scale_factor
    actual_h = img_h * scale_factor
    offset_x = screen_x + (screen_w - actual_w) / 2
    offset_y = screen_y + (screen_h - actual_h) / 2

    safe_x_min = int(offset_x)
    safe_x_max = int(offset_x + actual_w)
    safe_y_min = int(offset_y)
    safe_y_max = int(offset_y + actual_h)

    canvas_usage = (actual_w * actual_h) / (screen_w * screen_h) * 100
    log_info(
        f"绘画区域 ({safe_x_min},{safe_y_min})→({safe_x_max},{safe_y_max}) "
        f"比例={scale_factor:.3f} 利用率={canvas_usage:.0f}%"
    )
    if scale_factor < 0.5:
        log_info(f"画布相对图像偏小，细节可能损失（建议画布至少 {img_w // 2}x{img_h // 2}）")

    return screen_x, screen_y, scale_factor, offset_x, offset_y, safe_x_min, safe_x_max, safe_y_min, safe_y_max


CORNER_KEEP_DEG = 30.0


def resample_contours_for_canvas(contours, scale_factor, corner_deg=CORNER_KEEP_DEG):
    """
    按画布精度精简：约 1 个点对应 1 个目标像素，转角大于 corner_deg 的点强制保留。
    返回 (新轮廓, 原点数, 新点数)。
    """
    if not contours:
        return contours, 0, 0

    try:
        scale = float(scale_factor)
    except (TypeError, ValueError):
        return contours, 0, 0
    if scale <= 0:
        return contours, 0, 0

    min_step = max(1.0, 1.0 / scale)
    min_sq = min_step * min_step
    resampled = []
    n_old = 0
    n_new = 0

    for path in contours:
        pts = np.asarray(path).reshape(-1, 2)
        n_old += len(pts)
        if len(pts) == 0:
            continue
        if len(pts) == 1:
            kept = pts
        else:
            kept = [pts[0]]
            for i in range(1, len(pts)):
                p = pts[i]
                dx = float(p[0]) - float(kept[-1][0])
                dy = float(p[1]) - float(kept[-1][1])
                far = dx * dx + dy * dy >= min_sq
                corner = False
                if 0 < i < len(pts) - 1:
                    corner = calculate_angle_change(pts[i - 1], pts[i], pts[i + 1]) >= corner_deg
                if far or corner or i == len(pts) - 1:
                    if float(kept[-1][0]) != float(p[0]) or float(kept[-1][1]) != float(p[1]):
                        kept.append(p)
            kept = np.asarray(kept)

        if len(kept) == 0:
            continue
        resampled.append(np.asarray(kept).reshape(-1, 1, 2).astype(np.int32))
        n_new += len(kept)

    return resampled, n_old, n_new


def order_paths_nearest(paths):
    """最近邻接笔（委托 path_planner，避免双份实现）。"""
    from modules.path_planner import order_paths_nearest as _order
    return _order(paths)


def _screen_xy(point, offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max):
    return (
        clamp(int(offset_x + point[0] * scale_factor), safe_x_min, safe_x_max),
        clamp(int(offset_y + point[1] * scale_factor), safe_y_min, safe_y_max),
    )


def _raise_if_abort():
    if is_abort_pressed():
        raise DrawingAborted("用户中止")


def pressure_envelope(n, taper=0.22, min_p=0.12):
    """笔画压感：两端轻、中间重。taper 是起收笔各占长度的比例。"""
    n = int(n)
    if n <= 0:
        return np.zeros(0, dtype=np.float64)
    if n == 1:
        return np.array([min_p], dtype=np.float64)
    taper = float(np.clip(taper, 0.05, 0.45))
    env = np.ones(n, dtype=np.float64)
    head = max(1, int(round(n * taper)))
    head = min(head, max(1, n // 2))
    for i in range(head):
        u = (i + 1) / float(head)
        s = u * u * (3.0 - 2.0 * u)
        val = min_p + (1.0 - min_p) * s
        env[i] = val
        env[n - 1 - i] = min(env[n - 1 - i], val)
    return env


def polyline_normals(points):
    """折线单位切向与法向（法向为切向左转 90°）。"""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    n = len(pts)
    tangents = np.zeros((n, 2), dtype=np.float64)
    for i in range(n):
        if i == 0:
            delta = pts[min(1, n - 1)] - pts[0]
        elif i == n - 1:
            delta = pts[-1] - pts[-2]
        else:
            delta = pts[i + 1] - pts[i - 1]
        norm = float(np.linalg.norm(delta))
        tangents[i] = delta / norm if norm > 1e-6 else np.array([1.0, 0.0])
    normals = np.column_stack((-tangents[:, 1], tangents[:, 0]))
    return tangents, normals


def split_strokes_at_corners(points, corner_deg=48.0, min_len=3):
    """在锐角处拆成独立笔划，每段各自有起收笔。"""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < min_len + 1:
        return [pts]
    cuts = [0]
    for i in range(1, len(pts) - 1):
        if calculate_angle_change(pts[i - 1], pts[i], pts[i + 1]) >= corner_deg:
            if i - cuts[-1] >= min_len:
                cuts.append(i)
    cuts.append(len(pts) - 1)
    strokes = []
    for start, end in zip(cuts, cuts[1:]):
        seg = pts[start : end + 1]
        if len(seg) >= 2:
            strokes.append(seg)
    return strokes or [pts]


def pressure_overstrokes(points, width_img, taper=0.22, threshold=0.38):
    """压感高的中段生成左右偏移折线，用来把固定笔宽「画厚」。"""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 4 or float(width_img) <= 0.05:
        return []
    env = pressure_envelope(len(pts), taper=taper)
    _tangents, normals = polyline_normals(pts)
    extras = []
    start = None
    ranges = []
    for i, heavy in enumerate(env >= threshold):
        if heavy and start is None:
            start = i
        elif not heavy and start is not None:
            ranges.append((start, i - 1))
            start = None
    if start is not None:
        ranges.append((start, len(env) - 1))
    for left, right in ranges:
        if right - left < 2:
            continue
        sl = slice(left, right + 1)
        mag = (env[sl] * float(width_img))[:, None]
        extras.append(pts[sl] + normals[sl] * mag)
        extras.append(pts[sl] - normals[sl] * mag)
    return extras


def _draw_short_chunks(path_points, bounds, stroke_len, draw_delay, lift_pause):
    """方法1 短行程：按 stroke_len 切段，每段抬笔；下一段与上一段重叠一点以免接缝错位。"""
    offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max = bounds
    step = max(1, int(stroke_len))
    start = 0
    while start < len(path_points):
        _raise_if_abort()
        end = min(len(path_points), start + step + 1)
        sub_path = path_points[start:end]
        if len(sub_path) == 0:
            break
        start_x, start_y = _screen_xy(
            sub_path[0], offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max
        )
        begin_stroke(start_x, start_y)
        for point in sub_path[1:]:
            _raise_if_abort()
            draw_x, draw_y = _screen_xy(
                point, offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max
            )
            move_to(draw_x, draw_y)
            human_delay(draw_delay)
        finish_stroke(lift_pause)
        if end >= len(path_points):
            break
        start = end - 1


def _draw_smart_drag(path_points, bounds, min_drag_dist, draw_delay, lift_pause):
    """方法2 智能拖动：跳过屏幕距离过近的点。"""
    offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max = bounds
    if len(path_points) == 0:
        return
    start_x, start_y = _screen_xy(
        path_points[0], offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max
    )
    begin_stroke(start_x, start_y)
    last_drawn = (start_x, start_y)
    threshold = max(1, int(min_drag_dist))
    for point in path_points[1:]:
        _raise_if_abort()
        new_x, new_y = _screen_xy(
            point, offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max
        )
        dist = abs(new_x - last_drawn[0]) + abs(new_y - last_drawn[1])
        if dist >= threshold:
            move_to(new_x, new_y)
            last_drawn = (new_x, new_y)
            human_delay(draw_delay)
    finish_stroke(lift_pause)


def _human_like_pause(draw_delay, think_pause, corner_sharpness, angle_change):
    """方法3 转角停顿：锐利度控制转角处停顿，不抬笔。"""
    is_corner = angle_change > 30
    if is_corner:
        if corner_sharpness >= 8:
            pause_multiplier = 2.0 + (corner_sharpness - 8) * 0.5
            if angle_change > 90:
                pause_multiplier *= 1.5
            human_delay(draw_delay * pause_multiplier)
            if angle_change > 120 and random.random() < 0.3:
                human_delay(draw_delay * think_pause * 0.3)
        elif corner_sharpness >= 5:
            pause_multiplier = 1.0 + (corner_sharpness - 5) * 0.3
            if angle_change > 90:
                pause_multiplier *= 1.3
            human_delay(draw_delay * pause_multiplier)
        elif corner_sharpness >= 3:
            pause_multiplier = 0.6 + (corner_sharpness - 3) * 0.2
            if angle_change > 90:
                pause_multiplier *= 1.2
            human_delay(draw_delay * pause_multiplier)
        else:
            pause_multiplier = 0.3 - corner_sharpness * 0.05
            human_delay(draw_delay * pause_multiplier)
    else:
        human_delay(draw_delay * 0.3)


def _draw_human_like(path_points, bounds, draw_delay, lift_pause, hand_shake, think_pause, corner_sharpness):
    """方法3 仿真人：抖动 + 思考停顿 + 转角锐利度。"""
    offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max = bounds
    if len(path_points) < 2:
        return
    shake = int(hand_shake)
    start_point = path_points[0]
    start_x, start_y = _screen_xy(
        start_point, offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max
    )
    begin_stroke(
        start_x + random.randint(-shake, shake),
        start_y + random.randint(-shake, shake),
        pre_delay=max(draw_delay * 2, MIN_AIR_MOVE_SETTLE),
    )
    last_point = start_point
    for i, point in enumerate(path_points[1:], 1):
        _raise_if_abort()
        target_x_raw = offset_x + point[0] * scale_factor
        target_y_raw = offset_y + point[1] * scale_factor
        shake_x = random.randint(-shake, shake)
        shake_y = random.randint(-shake, shake)
        target_x = clamp(int(target_x_raw + shake_x), safe_x_min, safe_x_max)
        target_y = clamp(int(target_y_raw + shake_y), safe_y_min, safe_y_max)
        angle_change = calculate_angle_change(
            last_point, point, path_points[min(i + 1, len(path_points) - 1)]
        )
        move_to(target_x, target_y)
        _human_like_pause(draw_delay, think_pause, corner_sharpness, angle_change)
        last_point = point
    human_delay(max(0.02, draw_delay * 0.5), randomness=0)
    finish_stroke(lift_pause)


def _draw_poly_variable_speed(path_points, bounds, draw_delay, envelope=None):
    """单笔：按压感调速度，起收笔慢、中段稍快。不负责抬笔。"""
    offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max = bounds
    pts = np.asarray(path_points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 2:
        return
    start_x, start_y = _screen_xy(
        pts[0], offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max
    )
    begin_stroke(start_x, start_y)
    for i, point in enumerate(pts[1:], 1):
        _raise_if_abort()
        draw_x, draw_y = _screen_xy(
            point, offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max
        )
        move_to(draw_x, draw_y)
        pressure = 1.0 if envelope is None else float(envelope[min(i, len(envelope) - 1)])
        human_delay(draw_delay * (1.55 - 0.75 * pressure))


def _draw_pressure(path_points, bounds, draw_delay, lift_pause, _pressure_width, pressure_taper):
    """
    压感绘画只跟随红线。粗细已在提取阶段用重叠路径表达，这里不再另造偏移。
    """
    strokes = split_strokes_at_corners(path_points)
    for i, stroke in enumerate(strokes):
        env = pressure_envelope(len(stroke), taper=pressure_taper)
        _draw_poly_variable_speed(stroke, bounds, draw_delay, env)
        last = i == len(strokes) - 1
        finish_stroke(lift_pause if last else MIN_PEN_UP_SETTLE)


def draw_paths(
    app,
    contours,
    calib_data,
    method,
    *,
    stroke_len=15,
    min_drag_dist=5,
    draw_delay=0.005,
    lift_pause=5.0,
    speed_mult=1.0,
    hand_shake=0,
    think_pause=3,
    corner_sharpness=5,
    pressure_width=2.0,
    pressure_taper=0.22,
):
    """
    统一绘画循环。
    短行程 / 智能拖动 / 仿真人 / 压感。
    速度倍率只应由调用方除到 draw_delay 上，lift_pause 不乘速度。
    """
    try:
        start_hotkey_listener()
        if calib_data is None or calib_data[0] is None:
            _user_log(app, "未完成标定，已取消")
            return

        _sx, _sy, scale_factor, offset_x, offset_y, safe_x_min, safe_x_max, safe_y_min, safe_y_max = calib_data
        bounds = (offset_x, offset_y, scale_factor, safe_x_min, safe_x_max, safe_y_min, safe_y_max)

        contours, n_old, n_new = resample_contours_for_canvas(contours, scale_factor)
        if n_old > 0:
            log_info(f"画布精简 {n_old} → {n_new} 点 (scale={scale_factor:.3f})")
        if n_old > 20 and n_new < n_old * 0.7:
            _user_log(app, "已按画布精度精简路径")

        from modules.path_planner import estimate_path_stats, plan_draw_paths

        cell_size = None
        if hasattr(app, "bbox_cell_size"):
            try:
                raw = float(app.bbox_cell_size.get())
                cell_size = raw if raw > 0 else None
            except Exception:
                cell_size = None
        paths = plan_draw_paths(contours, strategy="bbox_chunks", cell_size=cell_size)
        stats = estimate_path_stats(paths)
        cell_note = f"{cell_size:.0f}px" if cell_size else "自动"
        log_info(
            f"路径规划 bbox 分块 cell={cell_note} → "
            f"{stats['paths']} 条 / {stats['points']} 点 "
            f"(均 {stats['avg_points']:.1f})"
        )
        _user_log(
            app,
            f"路径规划：{stats['paths']} 条 / {stats['points']} 点（分块={cell_note}）",
        )
        if method == "仿真人":
            log_info(
                f"仿真人 抖动={hand_shake}px 思考={think_pause}x 锐利={corner_sharpness} "
                f"换线={lift_pause:.2f}s 速度={speed_mult:.1f}x"
            )
        elif method == "压感":
            log_info(
                f"压感 跟随红线 {len(paths)} 条 换线={lift_pause:.2f}s 速度={speed_mult:.1f}x"
            )
        elif method == "智能拖动":
            log_info(
                f"智能拖动 最小距离={min_drag_dist}px 延迟={draw_delay:.4f}s "
                f"换线={lift_pause:.2f}s 速度={speed_mult:.1f}x"
            )
        else:
            log_info(
                f"短行程 笔画={stroke_len} 延迟={draw_delay:.4f}s "
                f"换线={lift_pause:.2f}s 速度={speed_mult:.1f}x"
            )

        _user_log(app, f"开始绘画（{method}，{len(paths)} 条）")
        last_mark = 0

        for path_idx, path in enumerate(paths):
            _raise_if_abort()
            path_points = np.asarray(path).reshape(-1, 2)
            if method == "短行程":
                _draw_short_chunks(path_points, bounds, stroke_len, draw_delay, lift_pause)
            elif method == "智能拖动":
                _draw_smart_drag(path_points, bounds, min_drag_dist, draw_delay, lift_pause)
            elif method == "压感":
                _draw_pressure(
                    path_points, bounds, draw_delay, lift_pause, pressure_width, pressure_taper
                )
            else:
                _draw_human_like(
                    path_points, bounds, draw_delay, lift_pause, hand_shake, think_pause, corner_sharpness
                )
            last_mark = _progress(app, path_idx + 1, len(paths), last_mark)

        _user_log(app, "绘画完成")

    except KeyboardInterrupt:
        _user_log(app, "已中止")
    except Exception as e:
        _user_log(app, "绘画出错，已停止")
        log_error(f"绘画异常 ({method})", e)
    finally:
        time.sleep(0.05)
        mouse_up()
        stop_hotkey_listener()
        on_done = getattr(app, "on_drawing_complete", None)
        if callable(on_done):
            on_done()


def start_drawing_method_1(
    app, contours, img_w, img_h, stroke_len, draw_delay, lift_pause=5.0, speed_mult=1.0, calib_data=None
):
    """方法1: 短行程绘画"""
    draw_paths(
        app,
        contours,
        calib_data,
        "短行程",
        stroke_len=stroke_len,
        draw_delay=draw_delay,
        lift_pause=lift_pause,
        speed_mult=speed_mult,
    )


def start_drawing_method_2(
    app, contours, img_w, img_h, min_drag_dist, draw_delay, speed_mult=1.0, lift_pause=5.0, calib_data=None
):
    """方法2: 智能拖动"""
    draw_paths(
        app,
        contours,
        calib_data,
        "智能拖动",
        min_drag_dist=min_drag_dist,
        draw_delay=draw_delay,
        lift_pause=lift_pause,
        speed_mult=speed_mult,
    )


def start_drawing_method_3(
    app,
    contours,
    img_w,
    img_h,
    draw_delay,
    lift_pause,
    hand_shake,
    think_pause,
    corner_sharpness=5,
    speed_mult=1.0,
    calib_data=None,
):
    """方法3: 仿真人绘画"""
    draw_paths(
        app,
        contours,
        calib_data,
        "仿真人",
        draw_delay=draw_delay,
        lift_pause=lift_pause,
        hand_shake=hand_shake,
        think_pause=think_pause,
        corner_sharpness=corner_sharpness,
        speed_mult=speed_mult,
    )


def start_drawing_method_4(
    app,
    contours,
    img_w,
    img_h,
    draw_delay,
    lift_pause=5.0,
    pressure_width=2.0,
    pressure_taper=0.22,
    speed_mult=1.0,
    calib_data=None,
):
    """方法4: 压感重绘"""
    draw_paths(
        app,
        contours,
        calib_data,
        "压感",
        draw_delay=draw_delay,
        lift_pause=lift_pause,
        pressure_width=pressure_width,
        pressure_taper=pressure_taper,
        speed_mult=speed_mult,
    )
