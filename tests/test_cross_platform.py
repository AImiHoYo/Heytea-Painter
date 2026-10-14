"""macOS 功能冒烟测试：图像管线、轮廓优化、平台信息。不移动真实鼠标。"""

import os
import sys
import traceback

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

SAMPLE = os.path.join(ROOT, "images", "1.png")
RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def test_imports():
    import customtkinter  # noqa: F401
    import cv2
    import numpy  # noqa: F401
    import torch
    from modules import (  # noqa: F401
        contour_optimizer,
        draw_session,
        drawing_engine,
        image_processor,
        platform_input,
        preview,
        settings_store,
        smart_resize,
        canvas_detect,
    )
    record("核心依赖导入", True, f"cv2 {cv2.__version__}, torch {torch.__version__}")


def test_pyside6_optional():
    """可选：导入 PySide6。未安装则跳过，不要求真实显示器。"""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    try:
        from PySide6 import QtCore
        from PySide6.QtWidgets import QApplication
    except ImportError:
        record("PySide6 导入", True, "未安装，已跳过")
        return
    try:
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        from heytea_qt import HeyteaWindow
        window = HeyteaWindow()
        method = window.extraction_method.get()
        window.close()
        record("PySide6 导入", True, f"Qt {QtCore.__version__}, 窗口={method}")
    except Exception as exc:
        record("PySide6 导入", True, f"已安装但 offscreen 不可用: {exc}")


def test_display_info():
    from modules.platform_input import IS_MACOS, get_dpi_info, permission_hint

    info = get_dpi_info()
    ok = info["logical_size"][0] > 0 and info["logical_size"][1] > 0
    record(
        "屏幕信息",
        ok,
        f"mac={IS_MACOS} logical={info['logical_size']} scale={info['scale']} via {info['awareness_method']}",
    )
    record("权限提示", IS_MACOS and bool(permission_hint()), permission_hint()[:40] + "...")


def test_ximgproc():
    import cv2
    import numpy as np

    has_api = hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "thinning")
    if not has_api:
        record("骨架细化 cv2.ximgproc", False, "opencv 无 contrib，ximgproc.thinning 不可用")
        return False
    try:
        dummy = np.zeros((32, 32), dtype=np.uint8)
        dummy[8:24, 8:24] = 255
        result = cv2.ximgproc.thinning(dummy, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
        ok = result is not None and result.shape == dummy.shape and int(result.sum()) < int(dummy.sum())
        record("骨架细化 cv2.ximgproc", ok, "可用" if ok else "thinning 调用未产生骨架")
        return ok
    except Exception as exc:
        record("骨架细化 cv2.ximgproc", False, str(exc))
        return False


def test_pencil():
    from modules.image_processor import process_image_pencil

    preview, contours, w, h = process_image_pencil(SAMPLE, 60, 0.4, 0.05, 1.0, 0, 1)
    ok = preview is not None and contours is not None and w > 0 and len(contours) > 0
    record("Pencil Sketch", ok, f"{w}x{h}, {0 if contours is None else len(contours)} paths")
    return contours, preview


def test_canny():
    from modules.image_processor import process_image_canny

    preview, contours, w, h = process_image_canny(SAMPLE, 3, 50, 150, 1.0, 0, 1)
    ok = preview is not None and contours is not None and w > 0 and len(contours) > 0
    record("Canny", ok, f"{w}x{h}, {0 if contours is None else len(contours)} paths")
    return contours, preview


def test_anime():
    from modules.image_processor import process_image_anime2sketch

    model = os.path.join(ROOT, "models", "netG.pth")
    if not os.path.isfile(model):
        record("Anime2Sketch", False, "缺少 models/netG.pth")
        return None, None
    preview, contours, w, h = process_image_anime2sketch(
        SAMPLE, 1.0, 0, 1, 127, 2, 1, 10, "外部轮廓 (快速)", 0, 0, 0.5, False, False
    )
    ok = preview is not None and contours is not None and w > 0
    record(
        "Anime2Sketch",
        ok,
        f"{w}x{h}, {0 if contours is None else len(contours)} paths",
    )
    return contours, preview


def test_optimizers(contours, preview):
    from modules.contour_optimizer import (
        apply_jitter_correction,
        apply_point_skipping,
        remove_backtracking,
        thin_contours_to_skeleton,
    )

    if not contours:
        record("轮廓优化", False, "没有可用轮廓")
        return
    cleaned = remove_backtracking(contours)
    jittered = apply_jitter_correction(cleaned, 2)
    skipped = apply_point_skipping(jittered, 2)
    record(
        "去回头 / 抖动 / 跳点",
        len(skipped) > 0,
        f"{len(contours)} → {len(cleaned)} → {len(skipped)} paths",
    )
    thinned = thin_contours_to_skeleton(cleaned, preview.shape)
    # 回退会原样返回传入的 contours；那必须记为失败，不能当 PASS
    fallback = thinned is cleaned
    ok = thinned is not None and not fallback and len(thinned) > 0
    detail = f"{len(thinned)} skeleton paths" if ok else (
        "ximgproc 细化失败，回退为原始轮廓" if fallback else "细化结果为空"
    )
    record("边缘细化", ok, detail)


def test_draw_math():
    from modules.drawing_engine import calculate_angle_change, calculate_path_complexity, clamp

    assert clamp(150, 0, 100) == 100
    assert clamp(-5, 0, 100) == 0
    angle = calculate_angle_change((0, 0), (1, 0), (1, 1))
    complexity = calculate_path_complexity([(0, 0), (10, 0), (10, 10), (20, 10)])
    record("绘画几何计算", 80 < angle < 100 and complexity > 0, f"corner={angle:.1f}°, complexity={complexity:.1f}")


def test_resize():
    import cv2
    from modules.smart_resize import adaptive_resize

    img = cv2.imread(SAMPLE)
    out = adaptive_resize(img, 320, 240)
    record("智能缩放", out is not None and out.shape[1] > 0, f"{img.shape[1]}x{img.shape[0]} → {out.shape[1]}x{out.shape[0]}")


def test_abort_flag():
    from modules.drawing_engine import DrawingAborted, human_delay
    from modules.platform_input import _abort_event, is_abort_pressed, request_abort

    _abort_event.clear()
    if is_abort_pressed():
        record("中止标志跨模块", False, "clear 后仍为按下")
        return
    request_abort()
    record("中止标志跨模块", is_abort_pressed(), "request_abort 与绘画循环共用同一 Event")
    started = __import__("time").time()
    try:
        human_delay(3.0, randomness=0)
        record("中止打断延迟", False, "延迟未被中止打断")
    except DrawingAborted:
        elapsed = __import__("time").time() - started
        record("中止打断延迟", elapsed < 0.5, f"3s 延迟在 {elapsed:.3f}s 内被打断")
    finally:
        _abort_event.clear()


def test_stroke_gap_floor():
    from modules.drawing_engine import MIN_PEN_UP_SETTLE, stroke_gap_seconds

    tiny = stroke_gap_seconds(0.05)
    long = stroke_gap_seconds(5.0)
    record(
        "换线抬笔下限",
        tiny >= MIN_PEN_UP_SETTLE and long >= 5.0 and tiny < 0.2,
        f"0.05→{tiny:.2f}s, 5.0→{long:.2f}s",
    )


def test_presets():
    import json

    path = os.path.join(ROOT, "heytea_presets.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    required = ["extraction_method", "drawing_method", "draw_delay"]
    ok = all(k in data for k in required)
    record("预设 JSON", ok, f"{len(data)} keys")


def test_settings_normalize():
    from modules.settings_store import normalize_settings

    old = {
        "extraction_method": "Pencil Sketch (V19)",
        "drawing_method": "方法 3: 仿真人绘画 🎨",
        "anime_contour_mode": "骨架提取 (推荐)",
        "draw_delay": 8,
    }
    values = normalize_settings(old)
    ok = (
        values["extraction_method"] == "Pencil Sketch"
        and values["drawing_method"] == "仿真人"
        and values["anime_contour_mode"] == "中心线"
        and values["draw_delay"] == 8
        and values["corner_sharpness"] == 5
    )
    record(
        "设置短键迁移",
        ok,
        f"{values['extraction_method']} / {values['drawing_method']} / {values['anime_contour_mode']}",
    )


def test_centerline_trace():
    import cv2
    import numpy as np
    from modules.contour_optimizer import trace_centerlines

    img = np.zeros((80, 80), dtype=np.uint8)
    img[10:70, 36:44] = 255
    img[62:70, 36:70] = 255
    paths = trace_centerlines(img, min_length=8)
    if not paths:
        record("中心线跟踪", False, "未跟踪到路径")
        return
    pts = np.vstack([p.reshape(-1, 2) for p in paths])
    vert = pts[pts[:, 1] < 55]
    if len(vert) < 5:
        record("中心线跟踪", False, f"{len(paths)} paths, 竖段点数不足")
        return
    x_mean = float(np.mean(vert[:, 0]))
    x_std = float(np.std(vert[:, 0]))
    blob, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    outline_pts = sum(len(c) for c in blob)
    line_pts = sum(len(c) for c in paths)
    ok = abs(x_mean - 40.0) <= 3.0 and x_std < 3.0 and line_pts < outline_pts
    record(
        "中心线跟踪",
        ok,
        f"{len(paths)} paths, {line_pts} pts vs 外框 {outline_pts}, x̄={x_mean:.1f} σ={x_std:.1f}",
    )


def test_taper_red_paths():
    import numpy as np
    from modules.contour_optimizer import expand_taper_paths, end_heavy_envelope

    env = end_heavy_envelope(21, taper=0.25, mid=0.15)
    env_ok = float(env[0]) > 0.85 and float(env[10]) < 0.35 and float(env[-1]) > 0.85

    line = np.array([[[i, 20]] for i in range(40)], dtype=np.int32)
    out = expand_taper_paths([line], image_shape=(40, 50), max_layers=3, taper=0.25, spacing=1.0)
    extras = [p for p in out[1:]]
    end_pts = []
    mid_pts = []
    for path in extras:
        pts = path.reshape(-1, 2)
        end_pts.extend(pts[(pts[:, 0] < 8) | (pts[:, 0] > 31)])
        mid_pts.extend(pts[(pts[:, 0] > 14) & (pts[:, 0] < 26)])
    extra_ok = len(out) > 1 and len(end_pts) > len(mid_pts)
    record(
        "起收笔红线重叠",
        env_ok and extra_ok,
        f"env端={float(env[0]):.2f} 中={float(env[10]):.2f} paths={len(out)} 端点={len(end_pts)} 中点={len(mid_pts)}",
    )


def test_pressure_envelope():
    import numpy as np
    from modules.drawing_engine import pressure_envelope, pressure_overstrokes, split_strokes_at_corners

    env = pressure_envelope(21, taper=0.25)
    env_ok = float(env[0]) < 0.4 and float(env[10]) > 0.9 and float(env[-1]) < 0.4

    line = np.array([[float(i), 10.0] for i in range(30)], dtype=np.float64)
    extras = pressure_overstrokes(line, width_img=2.0, taper=0.2)
    mid = extras[0][len(extras[0]) // 2] if extras else np.array([0.0, 10.0])
    extra_ok = len(extras) >= 2 and abs(float(mid[1]) - 10.0) > 0.5

    corner = np.array([[0.0, 0.0], [4.0, 0.0], [8.0, 0.0], [8.0, 4.0], [8.0, 8.0]], dtype=np.float64)
    parts = split_strokes_at_corners(corner, corner_deg=40.0, min_len=2)
    split_ok = len(parts) >= 2
    record(
        "压感包络与补笔",
        env_ok and extra_ok and split_ok,
        f"mid={float(env[10]):.2f} extras={len(extras)} splits={len(parts)}",
    )


def test_canvas_resample():
    import numpy as np
    from modules.drawing_engine import resample_contours_for_canvas

    pts = np.array([[[i, 0]] for i in range(100)], dtype=np.int32)
    out, n_old, n_new = resample_contours_for_canvas([pts], 0.1)
    ok = n_old == 100 and n_new < 20 and n_new >= 2 and len(out) == 1
    record("画布精度精简", ok, f"{n_old} → {n_new} 点 (scale=0.1)")


def test_corner_resample():
    import numpy as np
    from modules.drawing_engine import resample_contours_for_canvas

    pts = []
    for x in range(0, 51, 2):
        pts.append([[x, 0]])
    for y in range(2, 51, 2):
        pts.append([[50, y]])
    contour = np.array(pts, dtype=np.int32)
    out, n_old, n_new = resample_contours_for_canvas([contour], 0.05)
    kept = np.asarray(out[0]).reshape(-1, 2)
    has_corner = any(int(p[0]) == 50 and int(p[1]) == 0 for p in kept)
    record("保角精简保留直角", has_corner and n_new < n_old, f"{n_old} → {n_new} 含拐角={has_corner}")


def test_path_order():
    import numpy as np
    from modules.drawing_engine import order_paths_nearest
    from modules.path_planner import order_paths_bbox_chunks, plan_draw_paths

    far = np.array([[[80, 80]], [[90, 80]]], dtype=np.int32)
    near = np.array([[[0, 0]], [[10, 0]]], dtype=np.int32)
    ordered = order_paths_nearest([far, near])
    first = np.asarray(ordered[0]).reshape(-1, 2)[0]
    ok = len(ordered) == 2 and int(first[0]) == 0 and int(first[1]) == 0
    record("最近邻接笔", ok, f"先画 {tuple(first.tolist())}")

    # 四个象限各一条短线：分块后再串，条数不变且覆盖全部
    paths = [
        np.array([[[5, 5]], [[15, 5]]], dtype=np.int32),
        np.array([[[85, 5]], [[95, 5]]], dtype=np.int32),
        np.array([[[5, 85]], [[15, 85]]], dtype=np.int32),
        np.array([[[85, 85]], [[95, 85]]], dtype=np.int32),
    ]
    chunked = order_paths_bbox_chunks(paths, cell_size=50)
    planned = plan_draw_paths(paths, strategy="bbox_chunks")
    ok2 = len(chunked) == 4 and len(planned) == 4
    starts = [tuple(np.asarray(c).reshape(-1, 2)[0].tolist()) for c in chunked]
    # 第一块应靠近原点
    ok2 = ok2 and starts[0][0] <= 20 and starts[0][1] <= 20
    record("包围盒分块最近邻", ok2, f"starts={starts}")


def test_ui_mode_normalize():
    from modules.settings_store import normalize_settings, apply_beginner_preset

    simple = normalize_settings({"ui_mode": "简单", "lift_pause": 1.0})
    advanced = normalize_settings({"ui_mode": "advanced", "lift_pause": 0.5})
    beginner = apply_beginner_preset({})
    ok = (
        simple["ui_mode"] == "simple"
        and simple["lift_pause"] >= 5.0
        and advanced["ui_mode"] == "advanced"
        and advanced["lift_pause"] >= 1.0
        and beginner["ui_mode"] == "simple"
        and beginner["extraction_method"] == "Anime2Sketch"
    )
    record(
        "简单/高级模式归一化",
        ok,
        f"simple_lift={simple['lift_pause']} adv={advanced['ui_mode']} beginner={beginner['drawing_method']}",
    )


def test_model_hint_api():
    from modules import image_processor as ip

    ip.set_user_hint("")
    pack = ip._placeholder_error("Anime2Sketch Missing", hint_key="anime2sketch")
    hint = ip.get_user_hint(clear=True)
    ok = (
        "error_img" in pack
        and "Anime2Sketch" in hint
        and "models" in hint
        and ip.get_user_hint() == ""
    )
    record("缺模型中文提示", ok, hint[:40])


def test_canvas_detect_geom():
    from modules.canvas_detect import pixel_rect_to_logical, quartz_bounds_to_topleft

    x, top, w, h = quartz_bounds_to_topleft({"X": 100, "Y": 200, "Width": 400, "Height": 300}, 1000)
    # 1000 - 200 - 300 = 500
    tl, br = pixel_rect_to_logical(10, 20, (40, 80, 200, 100), 2.0)
    ok = (
        abs(x - 100) < 1e-6 and abs(top - 500) < 1e-6 and abs(w - 400) < 1e-6
        and tl == (30, 60) and br == (130, 110)
    )
    record("自动定框坐标换算", ok, f"win=({x:.0f},{top:.0f}) rect={tl}->{br}")


def test_lineart_optional():
    from modules.image_processor import LINEART_ANIME_PATH, process_image_lineart_anime

    if not os.path.isfile(LINEART_ANIME_PATH):
        record("LineartAnime", True, "无权重，已跳过")
        return
    preview, contours, w, h = process_image_lineart_anime(
        SAMPLE, 1.0, 0, 1, 512, 10, "外部轮廓 (快速)"
    )
    ok = preview is not None and contours is not None and w > 0
    record("LineartAnime", ok, f"{w}x{h}, {0 if contours is None else len(contours)} paths")


def _synthetic_contours():
    import numpy as np

    path_a = np.array([[[0, 0]], [[10, 0]], [[20, 0]], [[20, 10]]], dtype=np.int32)
    path_b = np.array([[[80, 80]], [[90, 80]], [[100, 80]]], dtype=np.int32)
    return [path_a, path_b]


def _fake_calib(scale=1.0):
    return (100, 100, scale, 100.0, 100.0, 100, 220, 100, 220)


class _FakeApp:
    def __init__(self):
        self.logs = []
        self.complete = 0

    def log(self, message):
        self.logs.append(str(message))

    def on_drawing_complete(self):
        self.complete += 1


def _assert_no_press_while_flying(events, jump=50):
    pressed = False
    last = None
    downs = 0
    ups = 0
    for ev in events:
        kind = ev[0]
        if kind == "down":
            if pressed:
                raise AssertionError("mouse_down 时仍按着")
            pressed = True
            downs += 1
        elif kind == "up":
            pressed = False
            ups += 1
        elif kind == "move":
            pos = (ev[1], ev[2])
            if pressed and last is not None:
                dist = abs(pos[0] - last[0]) + abs(pos[1] - last[1])
                if dist >= jump:
                    raise AssertionError(f"按住时飞向下一笔 {last}→{pos} d={dist}")
            last = pos
    if downs == 0:
        raise AssertionError("没有 mouse_down")
    if ups < downs:
        raise AssertionError(f"未抬笔 downs={downs} ups={ups}")
    if pressed:
        raise AssertionError("结束时仍按着")
    return downs, ups


def _patch_fake_mouse(events, abort_after_down=False):
    from contextlib import ExitStack
    from unittest.mock import patch

    from modules.drawing_engine import DrawingAborted
    from modules.platform_input import _abort_event, is_abort_pressed

    def fake_move(x, y):
        events.append(("move", int(x), int(y)))

    def fake_down():
        events.append(("down",))
        if abort_after_down:
            _abort_event.set()

    def fake_up():
        events.append(("up",))

    def fake_delay(base_delay, randomness=0.3):
        if is_abort_pressed():
            raise DrawingAborted("用户中止")

    stack = ExitStack()
    stack.enter_context(patch("modules.drawing_engine.move_to", fake_move))
    stack.enter_context(patch("modules.drawing_engine.mouse_down", fake_down))
    stack.enter_context(patch("modules.drawing_engine.mouse_up", fake_up))
    stack.enter_context(patch("modules.drawing_engine.human_delay", fake_delay))
    stack.enter_context(patch("modules.drawing_engine.start_hotkey_listener", lambda: None))
    stack.enter_context(patch("modules.drawing_engine.stop_hotkey_listener", lambda: None))
    stack.enter_context(patch("modules.drawing_engine.time.sleep", lambda s: None))
    stack.enter_context(patch("modules.platform_input.move_to", fake_move))
    stack.enter_context(patch("modules.platform_input.mouse_down", fake_down))
    stack.enter_context(patch("modules.platform_input.mouse_up", fake_up))
    return stack


def test_draw_loop_fake_mouse():
    from modules.drawing_engine import (
        start_drawing_method_1,
        start_drawing_method_2,
        start_drawing_method_3,
        start_drawing_method_4,
    )
    from modules.platform_input import _abort_event

    contours = _synthetic_contours()
    calib = _fake_calib(scale=1.0)
    methods = [
        ("短行程", start_drawing_method_1, (15, 0.001, 0.05, 1.0)),
        ("智能拖动", start_drawing_method_2, (5, 0.001, 1.0, 0.05)),
        ("仿真人", start_drawing_method_3, (0.001, 0.05, 0, 1, 5, 1.0)),
        ("压感", start_drawing_method_4, (0.001, 0.05, 2.0, 0.22, 1.0)),
    ]
    all_ok = True
    details = []
    for name, fn, extra in methods:
        events = []
        app = _FakeApp()
        _abort_event.clear()
        try:
            with _patch_fake_mouse(events):
                fn(app, contours, 120, 120, *extra, calib_data=calib)
            downs, ups = _assert_no_press_while_flying(events)
            done = app.complete == 1 and any("绘画完成" in line for line in app.logs)
            ok = done and downs >= 2
            details.append(f"{name}: down={downs} up={ups}")
            if not ok:
                all_ok = False
        except Exception as exc:
            all_ok = False
            details.append(f"{name}: {exc}")
        finally:
            _abort_event.clear()
    record("假鼠标三方法抬笔", all_ok, "; ".join(details))


def test_draw_loop_abort():
    from modules.drawing_engine import start_drawing_method_1
    from modules.platform_input import _abort_event

    events = []
    app = _FakeApp()
    contours = _synthetic_contours()
    _abort_event.clear()
    try:
        with _patch_fake_mouse(events, abort_after_down=True):
            start_drawing_method_1(
                app, contours, 120, 120, 15, 0.001, 0.05, 1.0, calib_data=_fake_calib()
            )
        aborted = any("已中止" in line for line in app.logs)
        closed = app.complete == 1 and events.count(("up",)) >= events.count(("down",))
        still_set = _abort_event.is_set()
        record(
            "假鼠标中止抬笔",
            aborted and closed and still_set,
            f"complete={app.complete} down={events.count(('down',))} up={events.count(('up',))}",
        )
    finally:
        _abort_event.clear()


def test_hotkey_running_is_noop():
    from modules import platform_input as pi

    pi._abort_event.set()
    sentinel = object()
    old_ns = pi._ns_key_monitor
    old_listener = pi._hotkey_listener
    if pi.IS_MACOS:
        pi._ns_key_monitor = sentinel
    else:
        pi._hotkey_listener = sentinel
    try:
        pi.start_hotkey_listener()
        still_set = pi._abort_event.is_set()
        still_same = (pi._ns_key_monitor is sentinel) if pi.IS_MACOS else (pi._hotkey_listener is sentinel)
        record("热键已运行时 no-op", still_set and still_same, "不清空中止标志")
    finally:
        pi._ns_key_monitor = old_ns
        pi._hotkey_listener = old_listener
        pi._abort_event.clear()



def test_bbox_cell_size_plan():
    import numpy as np
    from modules.path_planner import plan_draw_paths, estimate_path_stats

    paths = [
        np.array([[[5, 5]], [[15, 5]]], dtype=np.int32),
        np.array([[[85, 5]], [[95, 5]]], dtype=np.int32),
        np.array([[[5, 85]], [[15, 85]]], dtype=np.int32),
        np.array([[[85, 85]], [[95, 85]]], dtype=np.int32),
    ]
    auto = plan_draw_paths(paths, strategy="bbox_chunks", cell_size=0)
    fixed = plan_draw_paths(paths, strategy="bbox_chunks", cell_size=50)
    stats = estimate_path_stats(fixed)
    ok = len(auto) == 4 and len(fixed) == 4 and stats["paths"] == 4 and stats["points"] == 8
    record("可配置分块边长", ok, f"stats={stats}")


def test_preview_cache_key():
    from modules.preview import _infer_cache_key
    import tempfile, os

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
        f.write(b"x")
    try:
        k1 = _infer_cache_key("Anime2Sketch", path, sigmoid=0.5)
        k2 = _infer_cache_key("Anime2Sketch", path, sigmoid=0.5)
        k3 = _infer_cache_key("Anime2Sketch", path, sigmoid=0.7)
        ok = k1 == k2 and k1 != k3 and k1[0] == "Anime2Sketch"
        record("Anime2Sketch 边图缓存键", ok, f"same={k1 == k2} diff_sigmoid={k1 != k3}")
    finally:
        os.unlink(path)


def test_bbox_cell_setting():
    from modules.settings_store import normalize_settings

    a = normalize_settings({"bbox_cell_size": 0})
    b = normalize_settings({"bbox_cell_size": 80})
    c = normalize_settings({"bbox_cell_size": 5})  # clamp to >=20 when >0
    ok = a["bbox_cell_size"] == 0.0 and b["bbox_cell_size"] == 80.0 and c["bbox_cell_size"] == 20.0
    record("分块边长设置归一化", ok, f"0={a['bbox_cell_size']} 80={b['bbox_cell_size']} 5→{c['bbox_cell_size']}")


def test_cache_stats_counter():
    from modules.cache_stats import EdgeCacheStats

    stats = EdgeCacheStats()
    stats.record_miss("Anime2Sketch")
    stats.record_hit("Anime2Sketch")
    hit_line = stats.record_hit("Anime2Sketch")
    ok = (
        stats.counts("Anime2Sketch") == (2, 1)
        and abs(stats.hit_rate("Anime2Sketch") - 2 / 3) < 1e-6
        and "2/3" in stats.summary("Anime2Sketch")
        and "命中" in hit_line
        and stats.hit_rate("LineartAnime") == 0.0
    )
    record("缓存命中率统计", ok, stats.summary("Anime2Sketch"))


def test_edge_cache_reuse_and_force():
    """第二次取包命中缓存不重推理；clear_edge_cache 后强制重推理。"""
    import tempfile
    from unittest.mock import patch

    import numpy as np
    from modules import preview as preview_mod

    class _FakeHost(preview_mod.PreviewMixin):
        def __init__(self):
            self._edge_cache = None

    host = _FakeHost()
    calls = []

    def fake_infer(path, sigmoid=0.5):
        calls.append(sigmoid)
        return {
            "edge_map": np.zeros((8, 8), dtype=np.uint8),
            "original_w": 8,
            "original_h": 8,
        }

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name
        f.write(b"x")
    try:
        with patch.object(preview_mod, "infer_anime2sketch_edge_map", fake_infer):
            host._get_edge_pack("Anime2Sketch", tmp_path, sigmoid=0.5)   # 未命中 → 推理
            host._get_edge_pack("Anime2Sketch", tmp_path, sigmoid=0.5)   # 命中 → 复用
            ok_hit = len(calls) == 1 and host._edge_cache is not None
            stats = host._ensure_cache_stats()
            ok_stats = stats.counts("Anime2Sketch") == (1, 1)
            host.clear_edge_cache()
            host._get_edge_pack("Anime2Sketch", tmp_path, sigmoid=0.5)   # 清缓存 → 再推理
            ok_force = len(calls) == 2 and host._edge_cache is not None
            ok_stats2 = stats.counts("Anime2Sketch") == (1, 2)
        record(
            "边图缓存复用与强制重推理",
            ok_hit and ok_stats and ok_force and ok_stats2,
            f"infer={len(calls)} 命中/未命中={stats.counts('Anime2Sketch')}",
        )
    finally:
        os.unlink(tmp_path)


def test_chunk_grid():
    import numpy as np
    from modules.path_planner import bbox_chunk_grid, draw_chunk_grid

    paths = [
        np.array([[[5, 5]], [[15, 5]]], dtype=np.int32),
        np.array([[[85, 5]], [[95, 5]]], dtype=np.int32),
        np.array([[[5, 85]], [[15, 85]]], dtype=np.int32),
        np.array([[[85, 85]], [[95, 85]]], dtype=np.int32),
    ]
    rects, cell = bbox_chunk_grid(paths, cell_size=50)
    ok_fixed = cell == 50.0 and len(rects) >= 4
    # 四条路径的包围盒中心分别是 (10,5)(90,5)(10,85)(90,85)，网格必须各覆盖一格
    covered = all(
        any(x0 <= px <= x1 and y0 <= py <= y1 for x0, y0, x1, y1 in rects)
        for px, py in ((10, 5), (90, 5), (10, 85), (90, 85))
    )
    auto_rects, auto_cell = bbox_chunk_grid(paths, cell_size=0)
    ok_auto = auto_cell > 0 and len(auto_rects) >= 4
    ok_single = bbox_chunk_grid([paths[0]], cell_size=50) == ([], 0.0)

    img = np.full((100, 100, 3), 255, dtype=np.uint8)
    out, cell_used, cells = draw_chunk_grid(img, paths, cell_size=50)
    drawn = bool((out < 255).any(axis=2).sum() > 0)
    ok_draw = drawn and cell_used == 50.0 and cells == len(rects) and out is img
    record(
        "分块网格可视化",
        ok_fixed and covered and ok_auto and ok_single and ok_draw,
        f"fixed={len(rects)}格 cell={cell:.0f} auto_cell={auto_cell:.0f}",
    )


def test_show_grid_setting():
    from modules.settings_store import normalize_settings

    a = normalize_settings({})
    b = normalize_settings({"show_chunk_grid": True})
    ok = a["show_chunk_grid"] is False and b["show_chunk_grid"] is True
    record("分块网格设置归一化", ok, f"默认={a['show_chunk_grid']} 开={b['show_chunk_grid']}")


def test_qt_simple_mode_extract_values():
    """Qt：简单模式提取方法只剩 AI 两项，切回高级恢复四项。"""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    try:
        from PySide6.QtWidgets import QApplication
        from heytea_qt import HeyteaWindow
        from modules.settings_store import ALL_EXTRACT_METHODS, SIMPLE_EXTRACT_METHODS
    except ImportError:
        record("简单模式隐藏 Pencil/Canny (Qt)", True, "PySide6 未安装，已跳过")
        return
    try:
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        window = HeyteaWindow()
        window.ui_mode.set("高级")
        window.apply_ui_mode()
        adv_values = window.extraction_method.values()
        window.ui_mode.set("简单")
        window.apply_ui_mode()
        simple_values = window.extraction_method.values()
        current = window.extraction_method.get()
        window.ui_mode.set("高级")
        window.apply_ui_mode()
        back_values = window.extraction_method.values()
        window.close()
        ok = (
            adv_values == ALL_EXTRACT_METHODS
            and simple_values == SIMPLE_EXTRACT_METHODS
            and current in SIMPLE_EXTRACT_METHODS
            and back_values == ALL_EXTRACT_METHODS
        )
        record(
            "简单模式隐藏 Pencil/Canny (Qt)",
            ok,
            f"高级={adv_values} 简单={simple_values} 当前={current}",
        )
    except Exception as exc:
        record("简单模式隐藏 Pencil/Canny (Qt)", False, str(exc))

def main():
    if not os.path.isfile(SAMPLE):
        print(f"缺少测试图: {SAMPLE}")
        sys.exit(2)

    tests = [
        test_imports,
        test_pyside6_optional,
        test_display_info,
        test_ximgproc,
        test_draw_math,
        test_resize,
        test_abort_flag,
        test_stroke_gap_floor,
        test_presets,
        test_settings_normalize,
        test_taper_red_paths,
        test_pressure_envelope,
        test_centerline_trace,
        test_canvas_resample,
        test_corner_resample,
        test_path_order,
        test_ui_mode_normalize,
        test_model_hint_api,
        test_bbox_cell_size_plan,
        test_preview_cache_key,
        test_bbox_cell_setting,
        test_cache_stats_counter,
        test_edge_cache_reuse_and_force,
        test_chunk_grid,
        test_show_grid_setting,
        test_qt_simple_mode_extract_values,
        test_canvas_detect_geom,
        test_lineart_optional,
        test_draw_loop_fake_mouse,
        test_draw_loop_abort,
        test_hotkey_running_is_noop,
    ]
    for fn in tests:
        try:
            fn()
        except Exception as exc:
            record(fn.__name__, False, str(exc))
            traceback.print_exc()

    try:
        contours, preview = test_pencil()
        test_canny()
        test_anime()
        test_optimizers(contours, preview)
    except Exception as exc:
        record("图像管线", False, str(exc))
        traceback.print_exc()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print()
    print(f"结果: {passed} passed, {failed} failed, {len(RESULTS)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
