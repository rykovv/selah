# Build the PyInstaller bundle and the Inno Setup installer.
#
# Usage:  .\build.ps1            (version read from config.py)
#         .\build.ps1 -SkipInstaller
param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# --- Read APP_VERSION from config.py ---
$configPy = Get-Content (Join-Path $root "src\vmix-church-service-manager\config.py") -Raw
if ($configPy -notmatch 'APP_VERSION:\s*str\s*=\s*"([^"]+)"') {
    throw "Could not read APP_VERSION from config.py"
}
$version = $Matches[1]
Write-Host "Building vMix Church Service Manager v$version" -ForegroundColor Cyan

# --- PyInstaller ---
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
& $python -m PyInstaller --noconfirm --clean (Join-Path $root "vmix-church-service-manager.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

if ($SkipInstaller) {
    Write-Host "Skipped installer. Bundle: dist\vmix-church-service-manager" -ForegroundColor Green
    exit 0
}

# --- Inno Setup ---
$iscc = @(
    "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php"
}

& $iscc "/DMyAppVersion=$version" (Join-Path $root "installer\setup.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }

Write-Host "Installer: dist\installer\vmix-church-service-manager-setup-$version.exe" -ForegroundColor Green
