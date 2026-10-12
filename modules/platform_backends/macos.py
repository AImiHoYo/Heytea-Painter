from __future__ import annotations

import time

from .base import PlatformBackend


class MacOSBackend(PlatformBackend):
    name = "macos"

    def __init__(self):
        from pynput import keyboard, mouse

        self.keyboard = keyboard
        self.mouse = mouse
        self._quartz = None
        self._exit_requested = False
        self._kb_listener = None

        try:
            import Quartz

            self._quartz = Quartz
        except Exception:
            self._quartz = None

    def _start_exit_listener(self):
        if self._kb_listener is not None:
            return

        def on_press(key):
            try:
                if getattr(key, "char", "").lower() == "q":
                    self._exit_requested = True
            except Exception:
                return

        self._kb_listener = self.keyboard.Listener(on_press=on_press)
        self._kb_listener.daemon = True
        self._kb_listener.start()

    def _check_accessibility_permission(self) -> tuple[bool, str]:
        if self._quartz is None:
            return False, "缺少 Quartz/PyObjC 依赖，请先安装 pyobjc-framework-Quartz。"

        q = self._quartz
        trusted = False

        if hasattr(q, "AXIsProcessTrusted"):
            trusted = bool(q.AXIsProcessTrusted())

        if not trusted and hasattr(q, "AXIsProcessTrustedWithOptions"):
            options = {q.kAXTrustedCheckOptionPrompt: True}
            trusted = bool(q.AXIsProcessTrustedWithOptions(options))

        if hasattr(q, "CGPreflightListenEventAccess"):
            trusted = trusted and bool(q.CGPreflightListenEventAccess())

        if hasattr(q, "CGPreflightPostEventAccess"):
            trusted = trusted and bool(q.CGPreflightPostEventAccess())

        if trusted:
            return True, ""

        return (
            False,
            "macOS 缺少辅助功能权限。请在“系统设置 > 隐私与安全性 > 辅助功能”中允许终端/Python，"
            "随后重启应用。",
        )

    def ensure_ready_for_drawing(self) -> tuple[bool, str]:
        ok, message = self._check_accessibility_permission()
        if ok:
            self._start_exit_listener()
        return ok, message

    def get_dpi_info(self) -> dict:
        scale = 1.0
        width, height = 1920, 1080
        try:
            if self._quartz is not None:
                display_id = self._quartz.CGMainDisplayID()
                width = int(self._quartz.CGDisplayPixelsWide(display_id))
                height = int(self._quartz.CGDisplayPixelsHigh(display_id))

                if hasattr(self._quartz, "NSScreen"):
                    screen = self._quartz.NSScreen.mainScreen()
                    if screen is not None:
                        scale = float(screen.backingScaleFactor())
        except Exception:
            pass

        dpi = int(96 * scale)
        return {
            "scale": scale,
            "scale_x": scale,
            "scale_y": scale,
            "dpi": dpi,
            "screen_size": (width, height),
            "logical_size": (int(width / max(scale, 1e-6)), int(height / max(scale, 1e-6))),
            "awareness_method": "Quartz",
            "awareness_level": "Retina Aware",
        }

    def capture_single_left_click(self, prompt: str) -> tuple[int, int] | None:
        point = None

        def on_click(x, y, button, pressed):
            nonlocal point
            if pressed and button == self.mouse.Button.left:
                point = (int(x), int(y))
                return False

        with self.mouse.Listener(on_click=on_click) as listener:
            listener.join()
        return point

    def _post_mouse_event(self, event_type, x: int, y: int):
        q = self._quartz
        if q is None:
            raise RuntimeError("Quartz 不可用")
        event = q.CGEventCreateMouseEvent(None, event_type, (float(x), float(y)), q.kCGMouseButtonLeft)
        q.CGEventPost(q.kCGHIDEventTap, event)

    def click(self, x: int, y: int) -> None:
        self.move_to(x, y)
        self.mouse_down()
        time.sleep(0.01)
        self.mouse_up()

    def move_to(self, x: int, y: int) -> None:
        self._post_mouse_event(self._quartz.kCGEventMouseMoved, int(x), int(y))

    def mouse_down(self) -> None:
        pos = self._quartz.NSEvent.mouseLocation()
        self._post_mouse_event(self._quartz.kCGEventLeftMouseDown, int(pos.x), int(pos.y))

    def mouse_up(self) -> None:
        if self._quartz is None:
            return
        pos = self._quartz.NSEvent.mouseLocation()
        self._post_mouse_event(self._quartz.kCGEventLeftMouseUp, int(pos.x), int(pos.y))

    def is_exit_pressed(self) -> bool:
        return self._exit_requested
