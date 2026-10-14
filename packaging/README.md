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
2. **oneclick (Embed)** — same layout plus an embeddable CPython under `env\` with pip deps (CPU torch). Matches `start.bat` looking for `env\python.exe`.

## Maintainer: build locally

### Bootstrap (any OS with Python 3)

```bash
python3 packaging/stage_portable_layout.py --dest dist --zip auto
```

### One-click embeddable env (Windows PowerShell)

```powershell
.\packaging\build_portable_zip.ps1 -Mode Bootstrap
.\packaging\build_portable_zip.ps1 -Mode Embed
```

Outputs under `dist/`:

- `Heytea-Painter-Windows-Portable-<VERSION>-bootstrap.zip`
- `Heytea-Painter-Windows-Portable-<VERSION>-oneclick.zip` (+ `.sha256`)

## CI / Releases

Workflow: `.github/workflows/portable-windows.yml`

- On PR / push to `main`: upload zip artifacts.
- On tag `v*` (e.g. `v1.1.4`): attach zip(s) to the GitHub Release. If the one-click job fails, the bootstrap zip is still attached.

Maintainer release checklist:

1. Bump `VERSION` and `RELEASE_NOTES.md`.
2. Merge to `main`.
3. Tag `vX.Y.Z` and push the tag.
4. Confirm the Release assets include the portable zip(s).
5. Point README “Releases” section at the latest Release.

Fat **oneclick** builds need the Windows runner (embeddable Python + torch wheels). Bootstrap can also be produced on Linux via `stage_portable_layout.py`.
