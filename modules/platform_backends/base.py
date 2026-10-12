from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class PlatformBackend(ABC):
    name = "unknown"

    @abstractmethod
    def ensure_ready_for_drawing(self) -> tuple[bool, str]:
        """Validate platform/runtime permissions before drawing."""

    @abstractmethod
    def get_dpi_info(self) -> dict:
        """Return display info with stable keys."""

    @abstractmethod
    def capture_single_left_click(self, prompt: str) -> tuple[int, int] | None:
        """Block until one left click is captured, or return None if unavailable."""

    @abstractmethod
    def click(self, x: int, y: int) -> None:
        ...

    @abstractmethod
    def move_to(self, x: int, y: int) -> None:
        ...

    @abstractmethod
    def mouse_down(self) -> None:
        ...

    @abstractmethod
    def mouse_up(self) -> None:
        ...

    @abstractmethod
    def is_exit_pressed(self) -> bool:
        ...

    def focus_console(self, log_func: Callable[[str], None] | None = None) -> None:
        """Best-effort console focus hook."""
        return
