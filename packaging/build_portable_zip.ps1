<#
.SYNOPSIS
  Build a Windows portable zip for Heytea Painter.

.DESCRIPTION
  Modes:
    Bootstrap - app sources + start.bat / setup_env.bat (no Python runtime). Small; user runs setup_env.bat once.
    Embed     - downloads Python embeddable into env\, pip-installs deps (one-click). Large (~torch).

  Model weights (netG.pth) are never packaged.

.EXAMPLE
  .\packaging\build_portable_zip.ps1 -Mode Bootstrap
  .\packaging\build_portable_zip.ps1 -Mode Embed
#>
[CmdletBinding()]
param(
    [ValidateSet("Bootstrap", "Embed")]
    [string]$Mode = "Bootstrap",

    [string]$PythonEmbedVersion = "3.10.11",

    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"

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
    $pthText = Get-Content -Path $Pth.FullName -Raw
    # Enable site, add site-packages for pip installs
    $pthText = $pthText -replace "#import site", "import site"
    if ($pthText -notmatch "Lib\\site-packages") {
        $pthText = $pthText.TrimEnd() + "`r`nLib\site-packages`r`n"
    }
    Set-Content -Path $Pth.FullName -Value $pthText -Encoding ascii

    $GetPip = Join-Path $OutDir "get-pip.py"
    if (-not (Test-Path $GetPip)) {
        Write-Host "==> Downloading get-pip.py"
        Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip
    }

    $PythonExe = Join-Path $EnvDir "python.exe"
    Write-Host "==> Installing pip into embeddable env"
    & $PythonExe $GetPip --no-warn-script-location
    if ($LASTEXITCODE -ne 0) { throw "get-pip failed" }

    $Req = Join-Path $Stage "requirements-windows.txt"
    Write-Host "==> Installing runtime dependencies (CPU torch)"
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install torch==2.1.0 torchvision==0.16.0 --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw "torch install failed" }
    & $PythonExe -m pip install -r $Req
    if ($LASTEXITCODE -ne 0) { throw "requirements install failed" }

    # Smoke: imports only (no GUI)
    Write-Host "==> Import smoke check"
    & $PythonExe -c "import PySide6, cv2, numpy, PIL, torch, customtkinter; print('ok')"
    if ($LASTEXITCODE -ne 0) { throw "import smoke failed" }
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
