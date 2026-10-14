<#
.SYNOPSIS
  Build a Windows portable zip for Heytea Painter.

.DESCRIPTION
  Modes:
    Bootstrap - app sources + start.bat / setup_env.bat (no Python runtime). Small; user runs setup_env.bat once.
    Embed     - downloads Python embeddable into env\, vendors matching Tcl/Tk, pip-installs deps (one-click). Large (~torch).

  Embed profiles:
    Full    - CPU torch + requirements-windows.txt, then zip the one-click archive.
    TkSmoke - customtkinter only, then import tkinter / customtkinter. No fat zip.
              Used by PR CI. The official embeddable zip does not ship tkinter.

  Model weights (netG.pth) are never packaged.

.EXAMPLE
  .\packaging\build_portable_zip.ps1 -Mode Bootstrap
  .\packaging\build_portable_zip.ps1 -Mode Embed
  .\packaging\build_portable_zip.ps1 -Mode Embed -EmbedProfile TkSmoke
#>
[CmdletBinding()]
param(
    [ValidateSet("Bootstrap", "Embed")]
    [string]$Mode = "Bootstrap",

    [ValidateSet("Full", "TkSmoke")]
    [string]$EmbedProfile = "Full",

    [string]$PythonEmbedVersion = "3.10.11",

    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
# Keep native-command failures (msiexec 3010, pip exit codes) inspectable.
$PSNativeCommandUseErrorActionPreference = $false

# windows-latest consoles are cp1252. Child Python inherits that and crashes
# on non-ASCII prints (UnicodeEncodeError). Force UTF-8 before any output.
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
try {
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = $utf8
    [Console]::InputEncoding = $utf8
    $OutputEncoding = $utf8
} catch {
    Write-Host "Warning: could not set console UTF-8 ($($_.Exception.Message))"
}

function Set-EmbedPth {
    param([string]$PthPath)
    # ._pth replaces sys.path. Keep the zip + '.' entries, then add Lib so
    # the vendored tkinter package imports, and site-packages for pip.
    $kept = New-Object System.Collections.Generic.List[string]
    foreach ($line in (Get-Content -Path $PthPath)) {
        $trim = $line.Trim()
        if (-not $trim) { continue }
        if ($trim.StartsWith("#")) { continue }
        if ($trim -eq "import site") { continue }
        if ($trim -eq "Lib" -or $trim -eq "Lib\site-packages") { continue }
        $kept.Add($trim)
    }
    $kept.Add("Lib")
    $kept.Add("Lib\site-packages")
    $kept.Add("import site")
    $text = ($kept -join "`r`n") + "`r`n"
    $enc = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($PthPath, $text, $enc)
}

function Install-OfficialTclTk {
    param(
        [string]$Version,
        [string]$EnvDir,
        [string]$CacheDir
    )
    # Same patch version as the embeddable zip. _tkinter.pyd must match python3xx.dll.
    $Msi = Join-Path $CacheDir "tcltk-$Version-amd64.msi"
    $Url = "https://www.python.org/ftp/python/$Version/amd64/tcltk.msi"
    if (-not (Test-Path $Msi)) {
        Write-Host "==> Downloading official Tcl/Tk MSI for Python $Version"
        Invoke-WebRequest -Uri $Url -OutFile $Msi
    }

    $Extract = Join-Path $CacheDir "tcltk-$Version-amd64"
    if (Test-Path $Extract) { Remove-Item -Recurse -Force $Extract }
    New-Item -ItemType Directory -Force -Path $Extract | Out-Null

    # Administrative extract. Do not leave a trailing backslash before the quote
    # (msiexec treats \" as an escaped quote).
    $Target = (Resolve-Path $Extract).Path.TrimEnd('\')
    Write-Host "==> Extracting official Tcl/Tk ($Version)"
    & cmd.exe /c "msiexec /a `"$Msi`" /qn TARGETDIR=`"$Target`""
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 3010) {
        throw "tcltk.msi extract failed with exit code $LASTEXITCODE"
    }

    $pyd = Get-ChildItem -Path $Extract -Recurse -Filter "_tkinter.pyd" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $pyd) {
        Write-Host "---- tcltk extract listing ----"
        Get-ChildItem -Path $Extract -Recurse -File -ErrorAction SilentlyContinue |
            ForEach-Object { Write-Host $_.FullName }
        throw "tcltk.msi extract did not contain _tkinter.pyd"
    }
    $dllDir = $pyd.Directory.FullName
    foreach ($name in @("_tkinter.pyd", "tcl86t.dll", "tk86t.dll")) {
        $src = Join-Path $dllDir $name
        if (-not (Test-Path $src)) { throw "tcltk.msi extract missing $src" }
        # Embeddable CPython loads extension modules from the directory of python.exe.
        Copy-Item -Path $src -Destination (Join-Path $EnvDir $name) -Force
    }

    $init = Get-ChildItem -Path $Extract -Recurse -Filter "init.tcl" -ErrorAction SilentlyContinue |
        Where-Object { $_.Directory.Name -like "tcl8*" } |
        Select-Object -First 1
    if (-not $init) { throw "tcltk.msi extract did not contain tcl8.6\init.tcl" }
    $tclRoot = $init.Directory.Parent.FullName
    $tkTcl = Join-Path $tclRoot "tk8.6\tk.tcl"
    if (-not (Test-Path $tkTcl)) { throw "tcltk.msi extract did not contain tk8.6\tk.tcl" }
    $tclDst = Join-Path $EnvDir "tcl"
    if (Test-Path $tclDst) { Remove-Item -Recurse -Force $tclDst }
    Copy-Item -Path $tclRoot -Destination $tclDst -Recurse -Force

    $tkInit = Get-ChildItem -Path $Extract -Recurse -Filter "__init__.py" -ErrorAction SilentlyContinue |
        Where-Object { $_.Directory.Name -eq "tkinter" -and $_.Directory.Parent.Name -eq "Lib" } |
        Select-Object -First 1
    if (-not $tkInit) { throw "tcltk.msi extract did not contain Lib\tkinter" }
    $libDir = Join-Path $EnvDir "Lib"
    New-Item -ItemType Directory -Force -Path $libDir | Out-Null
    $tkDst = Join-Path $libDir "tkinter"
    if (Test-Path $tkDst) { Remove-Item -Recurse -Force $tkDst }
    Copy-Item -Path $tkInit.Directory.FullName -Destination $tkDst -Recurse -Force
}

function Invoke-EmbedImportSmoke {
    param(
        [string]$PythonExe,
        [string]$EnvDir,
        [string]$Profile
    )
    # Prefix-relative lookup is prefix\tcl\tcl8.6. Also set the env vars so a
    # ._pth isolated embed still finds init.tcl if sys.prefix is odd.
    $env:TCL_LIBRARY = Join-Path $EnvDir "tcl\tcl8.6"
    $env:TK_LIBRARY = Join-Path $EnvDir "tcl\tk8.6"
    $env:HEYTEA_EMBED_PROFILE = $Profile
    if (-not (Test-Path (Join-Path $env:TCL_LIBRARY "init.tcl"))) {
        throw "TCL_LIBRARY missing init.tcl: $($env:TCL_LIBRARY)"
    }

    $Smoke = Join-Path $EnvDir "_heytea_import_smoke.py"
    @(
        "import os, sys"
        "print('prefix', sys.prefix)"
        "print('tcl_library', os.environ.get('TCL_LIBRARY'))"
        "import tkinter"
        "interp = tkinter.Tcl()"
        "print('tcl', interp.eval('info patchlevel'))"
        "import customtkinter"
        "if os.environ.get('HEYTEA_EMBED_PROFILE') == 'Full':"
        "    import PySide6, cv2, numpy, PIL, torch"
        "print('ok')"
    ) | Set-Content -Path $Smoke -Encoding ascii

    Write-Host "==> Import smoke check ($Profile)"
    & $PythonExe $Smoke
    $code = $LASTEXITCODE
    Remove-Item -Force $Smoke -ErrorAction SilentlyContinue
    if ($code -ne 0) { throw "import smoke failed" }
}

if ($EmbedProfile -eq "TkSmoke" -and $Mode -ne "Embed") {
    throw "-EmbedProfile TkSmoke requires -Mode Embed"
}

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Version = (Get-Content -Path (Join-Path $Root "VERSION") -Raw).Trim()
if (-not $Version) { $Version = "0.0.0" }

if (-not $OutDir) {
    $OutDir = Join-Path $Root "dist"
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$FolderName = "Heytea-Painter-Windows-Portable-$Version"
$Stage = Join-Path $OutDir $FolderName

Write-Host "==> Staging sources ($Mode) -> $Stage"
python (Join-Path $Root "packaging\stage_portable_layout.py") --dest $Stage --version $Version
if ($LASTEXITCODE -ne 0) { throw "stage_portable_layout.py failed" }

# Re-stage into exact folder name (script may nest folder_name under dest parent)
if (-not (Test-Path $Stage)) {
    $alt = Join-Path $OutDir $FolderName
    if (Test-Path $alt) { $Stage = $alt } else { throw "Staging directory missing: $Stage" }
}

Set-Content -Path (Join-Path $Stage "packaging_mode.txt") -Value ($Mode.ToLower()) -Encoding utf8

if ($Mode -eq "Embed") {
    $EmbedZip = Join-Path $OutDir "python-$PythonEmbedVersion-embed-amd64.zip"
    $EmbedUrl = "https://www.python.org/ftp/python/$PythonEmbedVersion/python-$PythonEmbedVersion-embed-amd64.zip"
    $EnvDir = Join-Path $Stage "env"

    if (-not (Test-Path $EmbedZip)) {
        Write-Host "==> Downloading Python embeddable $PythonEmbedVersion"
        Invoke-WebRequest -Uri $EmbedUrl -OutFile $EmbedZip
    }

    if (Test-Path $EnvDir) { Remove-Item -Recurse -Force $EnvDir }
    New-Item -ItemType Directory -Force -Path $EnvDir | Out-Null
    Expand-Archive -Path $EmbedZip -DestinationPath $EnvDir -Force

    $Pth = Get-ChildItem -Path $EnvDir -Filter "python*._pth" | Select-Object -First 1
    if (-not $Pth) { throw "python*._pth not found in embed package" }
    Set-EmbedPth -PthPath $Pth.FullName

    Install-OfficialTclTk -Version $PythonEmbedVersion -EnvDir $EnvDir -CacheDir $OutDir

    $GetPip = Join-Path $OutDir "get-pip.py"
    if (-not (Test-Path $GetPip)) {
        Write-Host "==> Downloading get-pip.py"
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip
    }

    $PythonExe = Join-Path $EnvDir "python.exe"
    Write-Host "==> Installing pip into embeddable env"
    & $PythonExe $GetPip --no-warn-script-location
    if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }

    & $PythonExe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

    if ($EmbedProfile -eq "TkSmoke") {
        Write-Host "==> Installing customtkinter for Tk smoke"
        & $PythonExe -m pip install --no-warn-script-location "customtkinter==5.2.2"
        if ($LASTEXITCODE -ne 0) { throw "customtkinter install failed" }
    } else {
        $Req = Join-Path $Stage "requirements-windows.txt"
        Write-Host "==> Installing runtime dependencies (CPU torch)"
        & $PythonExe -m pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cpu
        if ($LASTEXITCODE -ne 0) { throw "torch install failed" }
        & $PythonExe -m pip install -r $Req
        if ($LASTEXITCODE -ne 0) { throw "requirements install failed" }
    }

    Invoke-EmbedImportSmoke -PythonExe $PythonExe -EnvDir $EnvDir -Profile $EmbedProfile
}

if ($Mode -eq "Embed" -and $EmbedProfile -eq "TkSmoke") {
    Write-Host "==> Tk smoke passed (customtkinter + tkinter). Fat one-click zip is tag-only."
    exit 0
}

$Suffix = if ($Mode -eq "Embed") { "oneclick" } else { "bootstrap" }
$ZipPath = Join-Path $OutDir "$FolderName-$Suffix.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }

Write-Host "==> Creating zip $ZipPath"
Compress-Archive -Path $Stage -DestinationPath $ZipPath -CompressionLevel Optimal

$Hash = Get-FileHash -Algorithm SHA256 -Path $ZipPath
$HashPath = "$ZipPath.sha256"
"$($Hash.Hash.ToLower())  $(Split-Path $ZipPath -Leaf)" | Set-Content -Path $HashPath -Encoding ascii

Write-Host "==> Done"
Write-Host "    Zip:  $ZipPath"
Write-Host "    SHA256: $($Hash.Hash.ToLower())"
Write-Host "    Size: $([math]::Round((Get-Item $ZipPath).Length / 1MB, 1)) MB"
