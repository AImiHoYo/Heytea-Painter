#!/usr/bin/env python3
"""Stage a Windows portable layout (sources + launchers, no model weights).

Works on any OS. Does not bundle a Python runtime; use build_portable_zip.ps1
-Mode Embed on Windows for a one-click env\\ runtime.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Paths relative to repo root to copy into the portable layout.
COPY_FILES = [
    "heytea_qt.py",
    "heytea_modern.py",
    "main.py",
    "heytea_presets.json",
    "VERSION",
    "environment.yml",
    "start.bat",
    "setup_env.bat",
]

COPY_TREES = [
    "modules",
    "fonts",
    "theme",
    "icon",
    "config",
]

SKIP_DIR_NAMES = {"__pycache__", ".git", ".pytest_cache"}
SKIP_FILE_SUFFIXES = {".pyc", ".pyo"}
# Windows portable package: keep ico + small png; drop macOS icns / huge source art.
SKIP_RELATIVE_FILES = {
    Path("icon") / "icon.icns",
    Path("icon") / "icon.png",
    Path("icon") / "build_icons.py",
}


def _should_skip(path: Path, src_root: Path | None = None) -> bool:
    if path.name in SKIP_DIR_NAMES:
        return True
    if path.suffix.lower() in SKIP_FILE_SUFFIXES:
        return True
    # Never ship model weights.
    if path.suffix.lower() == ".pth":
        return True
    if src_root is not None:
        try:
            rel = path.relative_to(src_root)
        except ValueError:
            rel = path.name
        # When copying a tree, src_root is that tree; rebuild repo-relative path.
        tree_name = src_root.name
        repo_rel = Path(tree_name) / rel if rel != Path(".") else Path(tree_name)
        if repo_rel in SKIP_RELATIVE_FILES:
            return True
    return False


def _copy_tree(src: Path, dst: Path) -> None:
    if not src.is_dir():
        raise FileNotFoundError(f"Missing tree: {src}")
    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        rel = root_path.relative_to(src)
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            src_file = root_path / name
            if _should_skip(src_file, src_root=src):
                continue
            shutil.copy2(src_file, target_dir / name)


def stage(dest: Path, version: str | None = None) -> Path:
    dest = dest.resolve()
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    for rel in COPY_FILES:
        src = ROOT / rel
        if not src.is_file():
            raise FileNotFoundError(f"Missing file: {src}")
        shutil.copy2(src, dest / rel)

    for rel in COPY_TREES:
        _copy_tree(ROOT / rel, dest / rel)

    models_dir = dest / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / ".gitkeep").write_text("", encoding="utf-8")
    shutil.copy2(ROOT / "packaging" / "models_README.txt", models_dir / "README.txt")

    logs_dir = dest / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / ".gitkeep").write_text("", encoding="utf-8")

    shutil.copy2(ROOT / "packaging" / "USER_README.md", dest / "README_使用说明.md")
    shutil.copy2(ROOT / "packaging" / "requirements-windows.txt", dest / "requirements-windows.txt")

    ver = version
    if not ver:
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    (dest / "PORTABLE_VERSION.txt").write_text(f"{ver}\n", encoding="utf-8")

    # Marker so start.bat / docs can distinguish bootstrap vs embed packages.
    (dest / "packaging_mode.txt").write_text("bootstrap\n", encoding="utf-8")
    return dest


def make_zip(stage_dir: Path, zip_path: Path) -> Path:
    zip_path = zip_path.resolve()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()
    # zip name without .zip suffix for make_archive
    base = zip_path.with_suffix("")
    archive = shutil.make_archive(str(base), "zip", root_dir=stage_dir.parent, base_dir=stage_dir.name)
    return Path(archive)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        type=Path,
        default=ROOT / "dist" / "portable-stage",
        help="Staging directory (will be replaced)",
    )
    parser.add_argument(
        "--zip",
        type=Path,
        default=None,
        help="Optional output zip path",
    )
    parser.add_argument("--version", default=None, help="Override VERSION for folder/zip naming")
    args = parser.parse_args(argv)

    version = args.version or (ROOT / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    folder_name = f"Heytea-Painter-Windows-Portable-{version}"
    stage_dir = args.dest
    # If --dest is a parent dir (e.g. dist/), create the versioned folder inside it.
    if stage_dir.name != folder_name:
        stage_dir = stage_dir / folder_name

    print(f"Staging portable layout → {stage_dir}")
    stage(stage_dir, version=version)
    print(f"Staged OK ({stage_dir})")

    if args.zip is not None:
        zip_path = args.zip
        if str(zip_path) in ("", "auto"):
            zip_path = ROOT / "dist" / f"{folder_name}-bootstrap.zip"
        out = make_zip(stage_dir, Path(zip_path))
        print(f"Wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
