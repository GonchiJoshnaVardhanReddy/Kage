# Kage Installation Script for Windows
# Usage: .\scripts\install.ps1 [-Dev]

param(
    [switch]$Dev,
    [switch]$Help
)

# Colors
$Colors = @{
    Red = "Red"
    Green = "Green"
    Yellow = "Yellow"
    Cyan = "Cyan"
}

# Configuration
$InstallDir = "$env:LOCALAPPDATA\Kage"
$VenvDir = "$InstallDir\venv"
$BinDir = "$InstallDir\bin"

function Write-Banner {
    Write-Host @"

    ██╗  ██╗ █████╗  ██████╗ ███████╗
    ██║ ██╔╝██╔══██╗██╔════╝ ██╔════╝
    █████╔╝ ███████║██║  ███╗█████╗  
    ██╔═██╗ ██╔══██║██║   ██║██╔══╝  
    ██║  ██╗██║  ██║╚██████╔╝███████╗
    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
    AI-Powered Penetration Testing Assistant

"@ -ForegroundColor Cyan
}

function Show-Help {
    Write-Host "Usage: .\install.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Dev      Install with development dependencies"
    Write-Host "  -Help     Show this help message"
    exit 0
}

function Test-PythonVersion {
    Write-Host "[1/6] Checking Python version..." -ForegroundColor Yellow
    
    $pythonCmd = $null
    
    # Try python first, then python3
    foreach ($cmd in @("python", "python3")) {
        try {
            $version = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($version) {
                $pythonCmd = $cmd
                break
            }
        } catch {}
    }
    
    if (-not $pythonCmd) {
        Write-Host "[!] Python not found. Please install Python 3.10 or higher." -ForegroundColor Red
        Write-Host "    Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
        exit 1
    }
    
    $versionParts = $version -split '\.'
    $major = [int]$versionParts[0]
    $minor = [int]$versionParts[1]
    
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Host "[!] Python 3.10+ required, found $version" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "[✓] Python $version found" -ForegroundColor Green
    return $pythonCmd
}

function Test-Dependencies {
    param([string]$PythonCmd)
    
    Write-Host "[2/6] Checking dependencies..." -ForegroundColor Yellow
    
    # Check pip
    try {
        & $PythonCmd -m pip --version | Out-Null
    } catch {
        Write-Host "[!] pip not found. Installing..." -ForegroundColor Yellow
        & $PythonCmd -m ensurepip --upgrade
    }
    
    # Check for git
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "[!] Git not found. Please install Git for Windows." -ForegroundColor Yellow
        Write-Host "    Download from: https://git-scm.com/download/win" -ForegroundColor Yellow
    }
    
    Write-Host "[✓] Dependencies satisfied" -ForegroundColor Green
}

function New-VirtualEnvironment {
    param([string]$PythonCmd)
    
    Write-Host "[3/6] Setting up virtual environment..." -ForegroundColor Yellow
    
    # Create directories
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }
    if (-not (Test-Path $BinDir)) {
        New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
    }
    
    # Remove existing venv
    if (Test-Path $VenvDir) {
        Write-Host "[*] Removing existing virtual environment..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force $VenvDir
    }
    
    # Create venv
    & $PythonCmd -m venv $VenvDir
    
    # Activate and upgrade pip
    & "$VenvDir\Scripts\Activate.ps1"
    & "$VenvDir\Scripts\python.exe" -m pip install --upgrade pip wheel setuptools 2>$null | Out-Null
    
    Write-Host "[✓] Virtual environment created" -ForegroundColor Green
}

function Install-Kage {
    Write-Host "[4/6] Installing Kage..." -ForegroundColor Yellow
    
    # Get script directory
    $ScriptDir = Split-Path -Parent $MyInvocation.ScriptName
    if (-not $ScriptDir) {
        $ScriptDir = Split-Path -Parent $PSCommandPath
    }
    $KageRoot = Split-Path -Parent $ScriptDir
    
    # Activate venv
    & "$VenvDir\Scripts\Activate.ps1"
    
    # Install
    if ($Dev) {
        Write-Host "[*] Installing in development mode..." -ForegroundColor Cyan
        & "$VenvDir\Scripts\pip.exe" install -e "$KageRoot[dev]"
    } else {
        & "$VenvDir\Scripts\pip.exe" install -e "$KageRoot"
    }
    
    Write-Host "[✓] Kage installed successfully" -ForegroundColor Green
}

function New-Launcher {
    Write-Host "[5/6] Creating launcher..." -ForegroundColor Yellow
    
    # Create batch launcher
    $BatchContent = @"
@echo off
call "$VenvDir\Scripts\activate.bat"
python -m kage %*
"@
    
    Set-Content -Path "$BinDir\kage.cmd" -Value $BatchContent
    
    # Create PowerShell launcher
    $PsContent = @"
# Kage launcher - auto-generated
& "$VenvDir\Scripts\Activate.ps1"
& python -m kage @args
"@
    
    Set-Content -Path "$BinDir\kage.ps1" -Value $PsContent
    
    Write-Host "[✓] Launchers created" -ForegroundColor Green
}

function Set-PathEnvironment {
    Write-Host "[6/6] Configuring PATH..." -ForegroundColor Yellow
    
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    
    if ($currentPath -notlike "*$BinDir*") {
        $newPath = "$BinDir;$currentPath"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        $env:Path = "$BinDir;$env:Path"
        Write-Host "[*] Added $BinDir to user PATH" -ForegroundColor Yellow
    }
    
    Write-Host "[✓] PATH configured" -ForegroundColor Green
}

function Main {
    if ($Help) {
        Show-Help
    }
    
    Write-Banner
    
    Write-Host "[*] Starting Kage installation..." -ForegroundColor Cyan
    Write-Host ""
    
    $pythonCmd = Test-PythonVersion
    Test-Dependencies -PythonCmd $pythonCmd
    New-VirtualEnvironment -PythonCmd $pythonCmd
    Install-Kage
    New-Launcher
    Set-PathEnvironment
    
    Write-Host ""
    Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host "  Kage installed successfully!" -ForegroundColor Green
    Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host ""
    Write-Host "  To get started:" -ForegroundColor Cyan
    Write-Host "    1. Restart your terminal (required for PATH changes)" -ForegroundColor White
    Write-Host "    2. Run setup wizard: " -NoNewline; Write-Host "kage setup" -ForegroundColor Cyan
    Write-Host "    3. Start hacking: " -NoNewline; Write-Host "kage chat" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  For autonomous mode:" -ForegroundColor Cyan
    Write-Host "    kage hack" -ForegroundColor Cyan -NoNewline; Write-Host " - Full autonomous penetration testing" -ForegroundColor White
    Write-Host ""
    Write-Host "  ⚠ For authorized security testing only." -ForegroundColor Red
    Write-Host ""
}

Main
