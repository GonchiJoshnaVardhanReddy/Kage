# Kage Update Script for Windows
# Usage: .\scripts\update.ps1 [-Dev]

param(
    [switch]$Dev,
    [switch]$Help
)

if ($Help) {
    Write-Host "Usage: .\scripts\update.ps1 [-Dev]"
    exit 0
}

Write-Host "[*] Updating Kage..." -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$KageRoot = Split-Path -Parent $ScriptDir
$InstalledPython = "$env:LOCALAPPDATA\Kage\venv\Scripts\python.exe"

if (Test-Path $InstalledPython) {
    $PythonCmd = $InstalledPython
} else {
    $PythonCmd = "python"
}

if ($Dev) {
    & $PythonCmd -m pip install -e "$KageRoot[dev]"
} else {
    & $PythonCmd -m pip install -e "$KageRoot"
}

Write-Host "[✓] Kage update complete" -ForegroundColor Green
Write-Host "Run 'kage --version' to verify." -ForegroundColor Cyan
