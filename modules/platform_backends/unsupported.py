from __future__ import annotations

import platform

from .base import PlatformBackend


class UnsupportedBackend(PlatformBackend):
    name = "unsupported"

    def ensure_ready_for_drawing(self) -> tuple[bool, str]:
        return False, f"当前平台暂不支持自动绘画：{platform.system()}"

    def get_dpi_info(self) -> dict:
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
        return None

    def click(self, x: int, y: int) -> None:
        raise RuntimeError("不支持自动绘画")

    def move_to(self, x: int, y: int) -> None:
        raise RuntimeError("不支持自动绘画")

    def mouse_down(self) -> None:
        raise RuntimeError("不支持自动绘画")

    def mouse_up(self) -> None:
        return

    def is_exit_pressed(self) -> bool:
        return False
