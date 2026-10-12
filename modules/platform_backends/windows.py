from __future__ import annotations

import ctypes

from .base import PlatformBackend


class WindowsBackend(PlatformBackend):
    name = "windows"

    def __init__(self):
        import keyboard
        import pydirectinput
        from pynput import mouse

        self.keyboard = keyboard
        self.pydirectinput = pydirectinput
        self.mouse = mouse
        self.pydirectinput.PAUSE = 0.005
        self._set_process_dpi_awareness()
        self._dpi_result = self._detect_dpi_awareness()

    def _set_process_dpi_awareness(self) -> None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            print("✓ DPI感知已启用 (Per-Monitor V1)")
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
            print("✓ DPI感知已启用 (System DPI)")
        except Exception as e:
            print(f"⚠ DPI设置失败: {e}")

    def _detect_dpi_awareness(self) -> dict:
        try:
            ctypes.windll.shcore
            return {"method": "SetProcessDpiAwareness", "level": "Per-Monitor V1"}
        except Exception:
            pass

        try:
            ctypes.windll.user32
            return {"method": "SetProcessDPIAware", "level": "System DPI"}
        except Exception:
            pass

        return {"method": "None", "level": "Unaware"}

    def ensure_ready_for_drawing(self) -> tuple[bool, str]:
        return True, ""

    def get_dpi_info(self) -> dict:
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
                "awareness_method": self._dpi_result["method"],
                "awareness_level": self._dpi_result["level"],
            }
        except Exception:
            return {
                "scale": 1.0,
                "scale_x": 1.0,
                "scale_y": 1.0,
                "dpi": 96,
                "screen_size": (1920, 1080),
                "logical_size": (1920, 1080),
                "awareness_method": "Unavailable",
                "awareness_level": "Unavailable",
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

    def click(self, x: int, y: int) -> None:
        self.pydirectinput.click(int(x), int(y))

    def move_to(self, x: int, y: int) -> None:
        self.pydirectinput.moveTo(int(x), int(y))

    def mouse_down(self) -> None:
        self.pydirectinput.mouseDown()

    def mouse_up(self) -> None:
        self.pydirectinput.mouseUp()

    def is_exit_pressed(self) -> bool:
        try:
            return self.keyboard.is_pressed("q")
        except Exception:
            return False

    def focus_console(self, log_func=None) -> None:
        try:
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
            console_hwnd = kernel32.GetConsoleWindow()
            if console_hwnd:
                user32.ShowWindow(console_hwnd, 9)
                user32.SetForegroundWindow(console_hwnd)
                if log_func:
                    log_func("已激活终端窗口")
            elif log_func:
                log_func("提示: 请手动切换到终端窗口查看绘画进度")
        except Exception as e:
            if log_func:
                log_func(f"无法激活终端窗口: {e}")
                log_func("提示: 请手动切换到终端窗口查看绘画进度")
