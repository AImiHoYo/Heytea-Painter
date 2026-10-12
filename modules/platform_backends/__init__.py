from __future__ import annotations

import platform

from .base import PlatformBackend
from .unsupported import UnsupportedBackend


def get_platform_backend() -> PlatformBackend:
    system = platform.system()
    if system == "Windows":
        try:
            from .windows import WindowsBackend

            return WindowsBackend()
        except Exception as e:
            return UnsupportedBackend()

    if system == "Darwin":
        try:
            from .macos import MacOSBackend

            return MacOSBackend()
        except Exception:
            return UnsupportedBackend()

    return UnsupportedBackend()
