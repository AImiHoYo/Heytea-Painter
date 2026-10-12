"""
绘画引擎模块
包含画布校准和三种绘画方法
"""

from __future__ import annotations

import random
import time

import cv2
import numpy as np

from modules.platform_backends import get_platform_backend


def get_dpi_info():
    """获取 DPI 信息（由平台后端提供）"""
    return get_platform_backend().get_dpi_info()


def human_delay(base_delay, randomness=0.3):
    """添加随机性延迟，模拟人类行为"""
    variation = base_delay * randomness
    actual_delay = base_delay + random.uniform(-variation, variation)
    time.sleep(max(0.001, actual_delay))


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


def _is_exit_requested(backend):
    try:
        return backend.is_exit_pressed()
    except Exception:
        return False


def calibrate_and_activate(img_w, img_h, backend=None):
    """
    画布校准 - 使用鼠标点击选择绘画区域
    返回: (screen_x, screen_y, scale_factor, offset_x, offset_y,
            safe_x_min, safe_x_max, safe_y_min, safe_y_max)
    """
    backend = backend or get_platform_backend()

    if img_w <= 0 or img_h <= 0:
        print(f"错误: 无效图像尺寸 img_w={img_w}, img_h={img_h}")
        return (None,) * 9

    ok, reason = backend.ensure_ready_for_drawing()
    if not ok:
        print(f"错误: {reason}")
        return (None,) * 9

    print("\n--- 步骤 A: 校准画布 ---")
    print("请用鼠标左键点击小程序绘画区域的 [左上角]...")
    top_left = backend.capture_single_left_click("top_left")
    if not top_left:
        print("错误: 未捕获到左上角坐标（可能缺少系统权限）")
        return (None,) * 9
    print(f"已记录 [左上角] 坐标: {top_left}")

    print("\n请用鼠标左键点击小程序绘画区域的 [右下角]...")
    bottom_right = backend.capture_single_left_click("bottom_right")
    if not bottom_right:
        print("错误: 未捕获到右下角坐标（可能缺少系统权限）")
        return (None,) * 9
    print(f"已记录 [右下角] 坐标: {bottom_right}")

    dpi_info = backend.get_dpi_info()

    print(f"\n{'=' * 60}")
    print("系统显示信息:")
    print(f"  当前屏幕分辨率: {dpi_info['screen_size'][0]} x {dpi_info['screen_size'][1]} 像素")
    if dpi_info["logical_size"] != dpi_info["screen_size"]:
        print(f"  逻辑分辨率: {dpi_info['logical_size'][0]} x {dpi_info['logical_size'][1]} 像素")
    print(f"  当前 DPI 缩放: {dpi_info['scale'] * 100:.0f}% (DPI: {dpi_info['dpi']})")
    print(f"  DPI 感知方法: {dpi_info['awareness_method']}")
    print(f"  DPI 感知级别: {dpi_info['awareness_level']}")
    print(f"  处理后图像尺寸: {img_w} x {img_h} 像素")
    print(f"{'=' * 60}")

    print("\n等待 3 秒后开始绘画...")
    time.sleep(3)

    screen_x, screen_y = int(top_left[0]), int(top_left[1])
    bottom_x, bottom_y = int(bottom_right[0]), int(bottom_right[1])
    screen_w = bottom_x - screen_x
    screen_h = bottom_y - screen_y

    print("\n画布校准结果:")
    print(f"  画布左上角: ({screen_x}, {screen_y})")
    print(f"  画布右下角: ({bottom_x}, {bottom_y})")
    print(f"  画布尺寸: {screen_w} x {screen_h} 像素")

    if screen_w <= 0 or screen_h <= 0:
        print("错误: 坐标无效。")
        return (None,) * 9

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

    print("\n绘画参数计算:")
    print(f"  图像处理尺寸: {img_w} x {img_h} 像素 (已优化)")
    print(f"  画布可用尺寸: {screen_w} x {screen_h} 像素")
    print(f"  X轴缩放比例: {scale_x:.4f}")
    print(f"  Y轴缩放比例: {scale_y:.4f}")
    print(f"  最终缩放比例: {scale_factor:.4f} (取较小值保持比例)")
    print(f"  缩放后图像: {actual_w:.1f} x {actual_h:.1f} 像素")
    print(f"  居中偏移: X={((screen_w - actual_w) / 2):.1f}, Y={((screen_h - actual_h) / 2):.1f}")
    print(f"  绘制区域: ({safe_x_min}, {safe_y_min}) → ({safe_x_max}, {safe_y_max})")

    canvas_usage = (actual_w * actual_h) / (screen_w * screen_h) * 100
    print(f"  画布利用率: {canvas_usage:.1f}%")

    test_x = int(offset_x + actual_w / 2)
    test_y = int(offset_y + actual_h / 2)
    print(f"\n测试: 点击图像中心 ({test_x}, {test_y})")
    backend.click(test_x, test_y)
    time.sleep(0.5)

    print("\n提示: 按 Q 键可随时退出绘画")
    print("=" * 60)

    return screen_x, screen_y, scale_factor, offset_x, offset_y, safe_x_min, safe_x_max, safe_y_min, safe_y_max


# --- 绘画方法 ---

def start_drawing_method_1(app, contours, img_w, img_h, stroke_len, draw_delay, lift_pause=0.05, speed_mult=1.0):
    """方法1: 短行程绘画"""
    backend = get_platform_backend()
    try:
        calib_data = calibrate_and_activate(img_w, img_h, backend=backend)
        if calib_data[0] is None:
            return
        _, _, scale_factor, offset_x, offset_y, safe_x_min, safe_x_max, safe_y_min, safe_y_max = calib_data

        print("\n--- 步骤 D: 开始模拟绘画 (方法 1: 短行程) ---")
        print(f"   (笔画长度: {stroke_len} 点, 延迟: {draw_delay:.4f}秒, 速度: {speed_mult:.1f}x)")

        for path in contours:
            if _is_exit_requested(backend):
                raise KeyboardInterrupt("用户中止")

            path_points = path.reshape(-1, 2)
            if len(path_points) == 0:
                continue

            for i in range(0, len(path_points), stroke_len):
                if _is_exit_requested(backend):
                    raise KeyboardInterrupt("用户中止")

                sub_path = path_points[i : i + stroke_len + 1]
                if len(sub_path) == 0:
                    continue

                start_x = clamp(int(offset_x + sub_path[0][0] * scale_factor), safe_x_min, safe_x_max)
                start_y = clamp(int(offset_y + sub_path[0][1] * scale_factor), safe_y_min, safe_y_max)

                backend.move_to(start_x, start_y)
                backend.mouse_down()

                try:
                    for point in sub_path[1:]:
                        draw_x = clamp(int(offset_x + point[0] * scale_factor), safe_x_min, safe_x_max)
                        draw_y = clamp(int(offset_y + point[1] * scale_factor), safe_y_min, safe_y_max)
                        backend.move_to(draw_x, draw_y)
                        human_delay(draw_delay)
                finally:
                    backend.mouse_up()

                pause_time = lift_pause + random.uniform(0, lift_pause * 0.3)
                human_delay(pause_time)

        print("\n--- 绘画完成！ ---")

    except KeyboardInterrupt:
        print("\n\n检测到中止信号！")
    except Exception as e:
        print(f"\n发生意外错误: {e}")
    finally:
        time.sleep(0.05)
        backend.mouse_up()
        app.on_drawing_complete()


def start_drawing_method_2(app, contours, img_w, img_h, min_drag_dist, draw_delay, speed_mult=1.0):
    """方法2: 智能拖动"""
    backend = get_platform_backend()
    try:
        calib_data = calibrate_and_activate(img_w, img_h, backend=backend)
        if calib_data[0] is None:
            return
        _, _, scale_factor, offset_x, offset_y, safe_x_min, safe_x_max, safe_y_min, safe_y_max = calib_data

        print("\n--- 步骤 D: 开始模拟绘画 (方法 2: 智能拖动) ---")
        print(f"   (最小距离: {min_drag_dist}px, 延迟: {draw_delay:.4f}秒, 速度: {speed_mult:.1f}x)")

        for path in contours:
            if _is_exit_requested(backend):
                raise KeyboardInterrupt("用户中止")

            path_points = path.reshape(-1, 2)
            if len(path_points) == 0:
                continue

            start_x = clamp(int(offset_x + path_points[0][0] * scale_factor), safe_x_min, safe_x_max)
            start_y = clamp(int(offset_y + path_points[0][1] * scale_factor), safe_y_min, safe_y_max)

            backend.move_to(start_x, start_y)
            backend.mouse_down()
            last_drawn_screen_point = (start_x, start_y)

            try:
                for point in path_points[1:]:
                    if _is_exit_requested(backend):
                        raise KeyboardInterrupt("用户中止")

                    new_draw_x = clamp(int(offset_x + point[0] * scale_factor), safe_x_min, safe_x_max)
                    new_draw_y = clamp(int(offset_y + point[1] * scale_factor), safe_y_min, safe_y_max)

                    dist = abs(new_draw_x - last_drawn_screen_point[0]) + abs(new_draw_y - last_drawn_screen_point[1])

                    if dist >= min_drag_dist:
                        backend.move_to(new_draw_x, new_draw_y)
                        last_drawn_screen_point = (new_draw_x, new_draw_y)
                        human_delay(draw_delay)
            finally:
                backend.mouse_up()

        print("\n--- 绘画完成！ ---")

    except KeyboardInterrupt:
        print("\n\n检测到中止信号！")
    except Exception as e:
        print(f"\n发生意外错误: {e}")
    finally:
        time.sleep(0.05)
        backend.mouse_up()
        app.on_drawing_complete()


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
):
    """方法3: 仿真人绘画 - 快速移动+停顿"""
    backend = get_platform_backend()
    try:
        calib_data = calibrate_and_activate(img_w, img_h, backend=backend)
        if calib_data[0] is None:
            return
        _, _, scale_factor, offset_x, offset_y, safe_x_min, safe_x_max, safe_y_min, safe_y_max = calib_data

        print("\n--- 步骤 D: 开始模拟绘画 (方法 3: 仿真人绘画) ---")
        print(f"   手部抖动: {hand_shake}px | 思考停顿: {think_pause}x | 转角锐利度: {corner_sharpness} | 速度倍率: {speed_mult:.1f}x")

        sorted_contours = sorted(contours, key=lambda c: cv2.contourArea(c), reverse=True)

        for path_idx, path in enumerate(sorted_contours):
            if _is_exit_requested(backend):
                raise KeyboardInterrupt("用户中止")

            path_points = path.reshape(-1, 2)
            if len(path_points) < 2:
                continue

            path_complexity = calculate_path_complexity(path_points)
            _ = path_complexity

            start_point = path_points[0]
            start_x = clamp(int(offset_x + start_point[0] * scale_factor), safe_x_min, safe_x_max)
            start_y = clamp(int(offset_y + start_point[1] * scale_factor), safe_y_min, safe_y_max)

            backend.move_to(start_x + random.randint(-hand_shake, hand_shake), start_y + random.randint(-hand_shake, hand_shake))
            human_delay(draw_delay * 2)

            backend.mouse_down()
            human_delay(draw_delay * 0.5)

            last_point = start_point

            for i, point in enumerate(path_points[1:], 1):
                if _is_exit_requested(backend):
                    raise KeyboardInterrupt("用户中止")

                target_x_raw = offset_x + point[0] * scale_factor
                target_y_raw = offset_y + point[1] * scale_factor

                shake_x = random.randint(-hand_shake, hand_shake)
                shake_y = random.randint(-hand_shake, hand_shake)

                target_x = clamp(int(target_x_raw + shake_x), safe_x_min, safe_x_max)
                target_y = clamp(int(target_y_raw + shake_y), safe_y_min, safe_y_max)

                angle_change = calculate_angle_change(last_point, point, path_points[min(i + 1, len(path_points) - 1)])
                is_corner = angle_change > 30

                backend.move_to(target_x, target_y)

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

                last_point = point

            human_delay(draw_delay * 0.5)
            backend.mouse_up()

            pause_time = lift_pause + random.uniform(0, lift_pause * 0.5)
            human_delay(pause_time)

            if (path_idx + 1) % 10 == 0:
                print(f"  已完成 {path_idx + 1}/{len(sorted_contours)} 条路径...")

        print("\n--- 绘画完成！ ---")

    except KeyboardInterrupt:
        print("\n\n检测到中止信号！")
    except Exception as e:
        print(f"\n发生意外错误: {e}")
    finally:
        time.sleep(0.05)
        backend.mouse_up()
        app.on_drawing_complete()
