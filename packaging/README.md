# Windows portable packaging

Produces a **portable zip** for GitHub Releases (not an `.exe` installer).

End users: unzip → place `models\netG.pth` → run `start.bat`.

## What gets packaged

| Included | Not included |
|----------|----------------|
| App sources (`heytea_qt.py`, `heytea_modern.py`, `modules/`, …) | `models\*.pth` weights |
| `start.bat`, `setup_env.bat` | Demo `images/` |
| `fonts/`, `theme/`, `icon/`, `config/` | Tests / CI-only files |
| `README_使用说明.md` | |

Two artifact flavors:

1. **bootstrap** — sources + launchers only. User needs Python 3.10+ once to run `setup_env.bat`.
2. **oneclick (Embed)** — same layout plus an embeddable CPython under `env\` with pip deps (CPU torch). The official embeddable zip has no Tcl/Tk; the script extracts the matching `tcltk.msi` from python.org (`_tkinter.pyd`, `tcl86t.dll`, `tk86t.dll`, `tcl\`, `Lib\tkinter`) so `customtkinter` imports. `start.bat` sets `TCL_LIBRARY` / `TK_LIBRARY` when that tree is present. Matches `start.bat` looking for `env\python.exe`.

## Maintainer: build locally

### Bootstrap (any OS with Python 3)

```bash
python3 packaging/stage_portable_layout.py --dest dist --zip auto
```

### One-click embeddable env (Windows PowerShell)

```powershell
.\packaging\build_portable_zip.ps1 -Mode Bootstrap
.\packaging\build_portable_zip.ps1 -Mode Embed
.\packaging\build_portable_zip.ps1 -Mode Embed -EmbedProfile TkSmoke
```

`TkSmoke` installs only `customtkinter` and checks `import tkinter` / `tkinter.Tcl()` / `import customtkinter`. It does not build the fat zip.

Outputs under `dist/`:

- `Heytea-Painter-Windows-Portable-<VERSION>-bootstrap.zip`
- `Heytea-Painter-Windows-Portable-<VERSION>-oneclick.zip` (+ `.sha256`)

## CI / Releases

Workflow: `.github/workflows/portable-windows.yml`

- On PR / push to `main`: upload the bootstrap zip, and on Windows run Embed `TkSmoke` (embeddable Python + official Tcl/Tk + `customtkinter` import).
- On tag `v*` (e.g. `v1.1.4`): build the fat one-click zip (same Tcl/Tk step, plus torch) and attach zip(s) to the GitHub Release. If the one-click job fails, the bootstrap zip is still attached. Re-uploading a tag overwrites existing assets (`overwrite_files`).

Maintainer release checklist:

1. Bump `VERSION` and `RELEASE_NOTES.md`.
2. Merge to `main`.
3. Tag `vX.Y.Z` and push the tag.
4. Confirm the Release assets include the portable zip(s).
5. Point README “Releases” section at the latest Release.

Fat **oneclick** builds need the Windows runner (embeddable Python + torch wheels). Bootstrap can also be produced on Linux via `stage_portable_layout.py`.
