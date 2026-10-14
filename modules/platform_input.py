"""
跨平台输入与显示信息。
Windows 继续走 pydirectinput / Win32 DPI；macOS / Linux 使用 pynput。
"""

import sys
import time
import threading

from modules.app_logger import log_error, log_info

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

_abort_event = threading.Event()
_hotkey_listener = None
_hotkey_lock = threading.Lock()

_mouse_controller = None
_use_pydirectinput = False

try:
    from pynput import mouse as pynput_mouse
    from pynput import keyboard as pynput_keyboard
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    pynput_mouse = None
    pynput_keyboard = None

if IS_WINDOWS:
    try:
        import pydirectinput
        pydirectinput.PAUSE = 0.005
        _use_pydirectinput = True
    except ImportError:
        _use_pydirectinput = False


def _get_mouse_controller():
    global _mouse_controller
    if _mouse_controller is None and PYNPUT_AVAILABLE:
        _mouse_controller = pynput_mouse.Controller()
    return _mouse_controller


def warmup_backends():
    """在主线程预热 Quartz/AppKit，避免后台线程首次调用时 SIGTRAP。"""
    if not PYNPUT_AVAILABLE:
        return
    try:
        controller = _get_mouse_controller()
        if controller is not None:
            _ = controller.position
    except Exception as exc:
        log_error("输入后端预热失败", exc)


def set_dpi_awareness():
    """Windows 上检测 DPI 感知；其他平台直接返回原生缩放信息。"""
    if not IS_WINDOWS:
        return {
            "method": "native",
            "success": True,
            "level": "Retina-aware" if IS_MACOS else "native",
        }

    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return {"method": "SetProcessDpiAwareness", "success": True, "level": "Per-Monitor V1"}
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return {"method": "SetProcessDPIAware", "success": True, "level": "System DPI"}
    except Exception:
        pass

    return {"method": "None", "success": False, "level": "Unaware"}


_dpi_result = set_dpi_awareness()


def _macos_display_info():
    """读取主屏逻辑分辨率和 backing scale（Retina 通常为 2.0）。"""
    try:
        from AppKit import NSScreen

        screen = NSScreen.mainScreen()
        frame = screen.frame()
        scale = float(screen.backingScaleFactor())
        logical_w = int(frame.size.width)
        logical_h = int(frame.size.height)
        return {
            "scale": scale,
            "scale_x": scale,
            "scale_y": scale,
            "dpi": int(72 * scale),
            "screen_size": (int(logical_w * scale), int(logical_h * scale)),
            "logical_size": (logical_w, logical_h),
            "awareness_method": "NSScreen.backingScaleFactor",
            "awareness_level": f"{scale:.1f}x",
        }
    except Exception:
        pass

    try:
        from Quartz import CGDisplayBounds, CGMainDisplayID, CGDisplayPixelsHigh, CGDisplayPixelsWide

        display_id = CGMainDisplayID()
        bounds = CGDisplayBounds(display_id)
        logical_w = int(bounds.size.width)
        logical_h = int(bounds.size.height)
        pixel_w = int(CGDisplayPixelsWide(display_id))
        pixel_h = int(CGDisplayPixelsHigh(display_id))
        scale = pixel_w / logical_w if logical_w else 1.0
        return {
            "scale": scale,
            "scale_x": scale,
            "scale_y": scale,
            "dpi": int(72 * scale),
            "screen_size": (pixel_w, pixel_h),
            "logical_size": (logical_w, logical_h),
            "awareness_method": "Quartz",
            "awareness_level": f"{scale:.1f}x",
        }
    except Exception as exc:
        log_error("获取 macOS 屏幕信息失败", exc)
        return None


def _windows_display_info():
    import ctypes

    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        hdc = user32.GetDC(0)
        dpi_x = gdi32.GetDeviceCaps(hdc, 88)
        dpi_y = gdi32.GetDeviceCaps(hdc, 90)
        user32.ReleaseDC(0, hdc)
        scale_x = dpi_x / 96.0
        scale_y = dpi_y / 96.0
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        try:
            import pyautogui
            logical_w, logical_h = pyautogui.size()
        except Exception:
            logical_w, logical_h = screen_w, screen_h
        return {
            "scale": (scale_x + scale_y) / 2,
            "scale_x": scale_x,
            "scale_y": scale_y,
            "dpi": dpi_x,
            "screen_size": (screen_w, screen_h),
            "logical_size": (logical_w, logical_h),
            "awareness_method": _dpi_result["method"],
            "awareness_level": _dpi_result["level"],
        }
    except Exception as exc:
        log_error("获取 DPI 信息失败", exc)
        return None


def get_dpi_info():
    """获取屏幕缩放与分辨率。pynput 在 macOS 上使用逻辑点，无需再乘 Retina scale。"""
    info = _macos_display_info() if IS_MACOS else _windows_display_info() if IS_WINDOWS else None
    if info:
        return info
    return {
        "scale": 1.0,
        "scale_x": 1.0,
        "scale_y": 1.0,
        "dpi": 72 if IS_MACOS else 96,
        "screen_size": (1920, 1080),
        "logical_size": (1920, 1080),
        "awareness_method": "fallback",
        "awareness_level": "unknown",
    }


def move_to(x, y):
    if _use_pydirectinput:
        import pydirectinput
        pydirectinput.moveTo(int(x), int(y))
        return
    controller = _get_mouse_controller()
    if controller is None:
        raise RuntimeError("没有可用的鼠标控制后端，请安装 pynput")
    controller.position = (int(x), int(y))
    time.sleep(0.005)


def _macos_post_left_button(down):
    """在当前位置发送 Quartz 左键，避免 pynput release 被小程序丢掉后连笔。"""
    from Quartz import (
        CGEventCreate,
        CGEventCreateMouseEvent,
        CGEventGetLocation,
        CGEventPost,
        kCGEventLeftMouseDown,
        kCGEventLeftMouseUp,
        kCGHIDEventTap,
        kCGMouseButtonLeft,
    )

    loc = CGEventGetLocation(CGEventCreate(None))
    event_type = kCGEventLeftMouseDown if down else kCGEventLeftMouseUp
    event = CGEventCreateMouseEvent(None, event_type, (loc.x, loc.y), kCGMouseButtonLeft)
    CGEventPost(kCGHIDEventTap, event)


def mouse_down():
    if _use_pydirectinput:
        import pydirectinput
        pydirectinput.mouseDown()
        return
    controller = _get_mouse_controller()
    controller.press(pynput_mouse.Button.left)


def mouse_up():
    if _use_pydirectinput:
        import pydirectinput
        pydirectinput.mouseUp()
        return
    controller = _get_mouse_controller()
    if controller is not None:
        controller.release(pynput_mouse.Button.left)
    if IS_MACOS:
        try:
            _macos_post_left_button(False)
            time.sleep(0.012)
            _macos_post_left_button(False)
        except Exception:
            pass


def click(x, y):
    if _use_pydirectinput:
        import pydirectinput
        pydirectinput.click(int(x), int(y))
        return
    move_to(x, y)
    controller = _get_mouse_controller()
    controller.click(pynput_mouse.Button.left, 1)


_click_listener = None
_click_lock = threading.Lock()
_ns_key_monitor = None


def _on_hotkey_press(key):
    try:
        if getattr(key, "char", None) and key.char.lower() == "q":
            request_abort()
            return
    except AttributeError:
        pass
    if key == pynput_keyboard.Key.esc:
        request_abort()


def request_abort():
    """由主线程按钮 / 系统级热键调用，立即抬笔并通知绘画循环停止。"""
    _abort_event.set()
    try:
        mouse_up()
    except Exception:
        pass


def _start_macos_key_monitor():
    """用 AppKit 全局监视 Q/Esc，避免 pynput 键盘线程在 macOS 上 SIGSEGV。"""
    global _ns_key_monitor
    if _ns_key_monitor is not None:
        return
    if threading.current_thread() is not threading.main_thread():
        log_info("macOS 热键必须在主线程注册，已跳过")
        return
    from AppKit import NSEvent, NSKeyDownMask

    def handler(event):
        try:
            if event.keyCode() == 53:
                request_abort()
            else:
                chars = event.charactersIgnoringModifiers() or ""
                if chars.lower() == "q":
                    request_abort()
        except Exception:
            pass

    _abort_event.clear()
    _ns_key_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
        NSKeyDownMask, handler
    )
    log_info("热键已就绪（Q / Esc）")


def _hotkey_is_running():
    if IS_MACOS:
        return _ns_key_monitor is not None
    return _hotkey_listener is not None


def start_hotkey_listener():
    """启动全局 Q/Esc。已在运行则为 no-op，不清空中止标志。不要和工作线程 / 鼠标 Listener 重叠。"""
    global _hotkey_listener
    stop_one_click_listener()
    if _hotkey_is_running():
        return
    if threading.current_thread() is not threading.main_thread():
        log_info("热键必须在主线程注册，工作线程已跳过")
        return
    if IS_MACOS:
        _start_macos_key_monitor()
        return
    if not PYNPUT_AVAILABLE:
        return
    with _hotkey_lock:
        if _hotkey_listener is not None:
            return
        _abort_event.clear()
        try:
            listener = pynput_keyboard.Listener(on_press=_on_hotkey_press)
            listener.daemon = True
            listener.start()
            _hotkey_listener = listener
            log_info("热键已就绪（Q / Esc）")
        except Exception as exc:
            log_error("热键监听启动失败", exc)
            _hotkey_listener = None


def stop_hotkey_listener():
    global _hotkey_listener, _ns_key_monitor
    if _ns_key_monitor is not None:
        try:
            from AppKit import NSEvent
            NSEvent.removeMonitor_(_ns_key_monitor)
        except Exception:
            pass
        _ns_key_monitor = None
    with _hotkey_lock:
        if _hotkey_listener is not None:
            try:
                _hotkey_listener.stop()
            except Exception:
                pass
            _hotkey_listener = None


def start_one_click_listener(callback):
    """
    只听下一次左键（用于聚焦小程序）。必须在没有键盘 Listener 时调用。
    callback(x, y) 在 pynput 线程触发。
    """
    global _click_listener
    if not PYNPUT_AVAILABLE:
        raise RuntimeError("pynput 不可用")
    stop_hotkey_listener()
    stop_one_click_listener()

    def on_click(x, y, button, pressed):
        if pressed and button == pynput_mouse.Button.left:
            stop_one_click_listener()
            callback(int(x), int(y))
            return False
        return None

    with _click_lock:
        listener = pynput_mouse.Listener(on_click=on_click)
        listener.daemon = True
        listener.start()
        _click_listener = listener


def stop_one_click_listener():
    global _click_listener
    listener = None
    with _click_lock:
        listener = _click_listener
        _click_listener = None
    if listener is not None:
        try:
            listener.stop()
        except Exception:
            pass
        try:
            listener.join(timeout=1.0)
        except Exception:
            pass


def is_abort_pressed():
    if _abort_event.is_set():
        return True
    if IS_WINDOWS:
        try:
            import keyboard
            return keyboard.is_pressed("q")
        except Exception:
            return False
    return False


def permission_hint():
    if IS_MACOS:
        return (
            "请为终端或 Heytea Painter 开启「辅助功能」和「输入监控」。"
            "自动识别画布还需开启「屏幕录制」。"
        )
    return ""


def focus_terminal():
    if IS_WINDOWS:
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                return True
        except Exception:
            return False
        return False

    return False
