# Kage Uninstall Script for Windows
# Usage: .\scripts\uninstall.ps1 [-Yes] [-DryRun] [-SkipPip]

param(
    [switch]$Yes,
    [switch]$DryRun,
    [switch]$SkipPip,
    [switch]$Help
)

if ($Help) {
    Write-Host "Usage: .\scripts\uninstall.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Yes      Non-interactive mode (don't prompt)"
    Write-Host "  -DryRun   Show actions without deleting anything"
    Write-Host "  -SkipPip  Skip pip uninstall"
    Write-Host "  -Help     Show this help message"
    exit 0
}

$targets = @(
    "$env:LOCALAPPDATA\Kage",          # installer-managed dir
    "$env:APPDATA\kage",               # legacy config path
    "$HOME\.kage",                     # new config path
    "$env:LOCALAPPDATA\kage",          # runtime data path
    "$env:LOCALAPPDATA\kage\sessions", # explicit session cache
    "$env:LOCALAPPDATA\kage\audit"
)

Write-Host "[*] Kage uninstall starting..." -ForegroundColor Cyan
Write-Host "[*] This will remove Kage install, config, and data directories." -ForegroundColor Yellow

if (-not $Yes -and -not $DryRun) {
    $confirm = Read-Host "Proceed? [y/N]"
    if ($confirm -notin @("y", "Y")) {
        Write-Host "[*] Cancelled." -ForegroundColor Cyan
        exit 0
    }
}

foreach ($target in $targets) {
    if (-not (Test-Path $target)) {
        Write-Host "[*] Not found: $target" -ForegroundColor Cyan
        continue
    }

    if ($DryRun) {
        Write-Host "[dry-run] Would remove: $target" -ForegroundColor Yellow
        continue
    }

    try {
        Remove-Item -Path $target -Recurse -Force -ErrorAction Stop
        Write-Host "[✓] Removed: $target" -ForegroundColor Green
    }
    catch {
        Write-Host "[!] Failed to remove: $target ($($_.Exception.Message))" -ForegroundColor Yellow
    }
}

# Remove launcher from user PATH if present
$binDir = "$env:LOCALAPPDATA\Kage\bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -and $userPath -like "*$binDir*") {
    if ($DryRun) {
        Write-Host "[dry-run] Would remove PATH entry: $binDir" -ForegroundColor Yellow
    }
    else {
        $segments = $userPath.Split(";") | Where-Object { $_ -and $_ -ne $binDir }
        [Environment]::SetEnvironmentVariable("Path", ($segments -join ";"), "User")
        Write-Host "[✓] Removed PATH entry: $binDir" -ForegroundColor Green
    }
}

if (-not $SkipPip) {
    if ($DryRun) {
        Write-Host "[dry-run] Would run: pip uninstall -y kage" -ForegroundColor Yellow
    }
    else {
        try {
            python -m pip uninstall -y kage | Out-Null
            Write-Host "[✓] pip uninstall attempted" -ForegroundColor Green
        }
        catch {
            Write-Host "[!] pip uninstall skipped: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}
else {
    Write-Host "[*] Skipping pip uninstall (-SkipPip)." -ForegroundColor Cyan
}

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Kage uninstall completed" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "If you used custom paths, also check: KAGE_CONFIG_DIR / KAGE_DATA_DIR" -ForegroundColor Cyan
