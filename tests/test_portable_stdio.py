#!/usr/bin/env python3
"""Packaging logs must survive a Windows cp1252 console.

The v1.1.4 one-click job died on:
    UnicodeEncodeError: 'charmap' codec can't encode character '\\u2192'

This script is dependency-free so the portable bootstrap job can run it
with plain CPython.
"""

from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGE_SCRIPT = ROOT / "packaging" / "stage_portable_layout.py"
PS1_SCRIPT = ROOT / "packaging" / "build_portable_zip.ps1"


def _fail(message: str) -> None:
    raise SystemExit(message)


def _assert_lines_ascii(path: Path, markers: tuple[str, ...]) -> None:
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        if not any(marker in line for marker in markers):
            continue
        try:
            line.encode("ascii")
        except UnicodeEncodeError as exc:
            _fail(f"{path}:{lineno} is not ASCII ({exc}): {line.strip()}")


def _load_stage():
    spec = importlib.util.spec_from_file_location("stage_portable_layout", STAGE_SCRIPT)
    if spec is None or spec.loader is None:
        _fail(f"Cannot load {STAGE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cp1252_stream(buf: io.BytesIO) -> io.TextIOWrapper:
    stream = io.TextIOWrapper(buf, encoding="cp1252", errors="strict", newline="\n")

    def _refuse(**_kwargs: object) -> None:
        raise OSError("console encoding is fixed to cp1252")

    # Windows CI cannot switch the console code page from inside print().
    stream.reconfigure = _refuse  # type: ignore[method-assign]
    return stream


def test_embed_vendors_matching_tcltk() -> None:
    """Embed mode must vendor official Tcl/Tk; embeddable CPython has no tkinter."""
    text = PS1_SCRIPT.read_text(encoding="utf-8")
    for needle in (
        "amd64/tcltk.msi",
        "_tkinter.pyd",
        "tcl86t.dll",
        "tk86t.dll",
        "TCL_LIBRARY",
        "TK_LIBRARY",
        "tkinter.Tcl()",
        "customtkinter",
        "EmbedProfile TkSmoke",
    ):
        if needle not in text:
            _fail(f"{PS1_SCRIPT.name} missing {needle}")
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    if "TCL_LIBRARY" not in bat or "TK_LIBRARY" not in bat:
        _fail("start.bat must set TCL_LIBRARY and TK_LIBRARY for the vendored Tcl/Tk tree")
    if "env\\tcl\\tcl8.6\\init.tcl" not in bat:
        _fail("start.bat must only point TCL_LIBRARY at env\\tcl\\tcl8.6")


def test_log_sources_are_ascii() -> None:
    _assert_lines_ascii(STAGE_SCRIPT, ("print(", "_log("))
    _assert_lines_ascii(PS1_SCRIPT, ("Write-Host",))
    # Windows PowerShell 5.1 reads .ps1 as the ANSI code page unless the
    # file is ASCII (or has a UTF-8 BOM). Keep the script ASCII-only.
    try:
        PS1_SCRIPT.read_text(encoding="utf-8").encode("ascii")
    except UnicodeEncodeError as exc:
        _fail(f"{PS1_SCRIPT} contains non-ASCII: {exc}")


def test_main_survives_fixed_cp1252_stdout() -> None:
    module = _load_stage()
    buf = io.BytesIO()
    stdout = _cp1252_stream(buf)
    stderr = _cp1252_stream(io.BytesIO())
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = stdout, stderr
    try:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dist"
            zip_path = Path(tmp) / "out.zip"
            rc = module.main(
                ["--dest", str(dest), "--version", "9.9.9", "--zip", str(zip_path)]
            )
            stdout.flush()
            if rc != 0:
                _fail(f"stage_portable_layout.main returned {rc}")
            if not zip_path.is_file():
                _fail(f"zip was not written: {zip_path}")
    finally:
        sys.stdout, sys.stderr = old_out, old_err

    text = buf.getvalue().decode("cp1252")
    if "Staging portable layout ->" not in text:
        _fail(f"expected ASCII staging line, got: {text!r}")
    if "\u2192" in text:
        _fail("unicode arrow leaked into cp1252 stdout")


def test_subprocess_cp1252_env() -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252"
    env.pop("PYTHONUTF8", None)
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "dist"
        zip_path = Path(tmp) / "out.zip"
        proc = subprocess.run(
            [
                sys.executable,
                str(STAGE_SCRIPT),
                "--dest",
                str(dest),
                "--version",
                "9.9.9",
                "--zip",
                str(zip_path),
            ],
            env=env,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            _fail(
                "cp1252 subprocess failed:\n"
                + proc.stdout.decode("utf-8", errors="replace")
                + proc.stderr.decode("utf-8", errors="replace")
            )
        if not zip_path.is_file():
            _fail("cp1252 subprocess did not write the zip")
    text = proc.stdout.decode("utf-8", errors="replace")
    if "Staging portable layout ->" not in text:
        _fail(f"subprocess stdout missing ASCII staging line: {text!r}")


def main() -> int:
    test_embed_vendors_matching_tcltk()
    test_log_sources_are_ascii()
    test_main_survives_fixed_cp1252_stdout()
    test_subprocess_cp1252_env()
    print("portable stdio encoding checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
