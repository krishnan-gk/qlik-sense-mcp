# Qlik Sense AI Assistant — Windows Server Deployment Script
# Run this as Administrator on qlik-dev.ispot.tv
# Usage: .\setup\windows_deploy.ps1

param(
    [string]$InstallDir = "C:\qlik-ai",
    [string]$RepoUrl = "https://github.com/ispot-tv/qlik-sense-mcp.git",
    [int]$Port = 8501,
    [string]$PythonVersion = "3.12"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Qlik Sense AI Assistant — Windows Deployment ===" -ForegroundColor Cyan
Write-Host "Install directory: $InstallDir"
Write-Host "Port: $Port"
Write-Host ""

# --- Step 1: Check Python ---
Write-Host "[1/5] Checking Python..." -ForegroundColor Yellow
try {
    $pyVersion = python --version 2>&1
    Write-Host "  Found: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "  Python not found. Download Python $PythonVersion from https://python.org/downloads" -ForegroundColor Red
    Write-Host "  Make sure to check 'Add Python to PATH' during installation."
    exit 1
}

# --- Step 2: Clone or update repo ---
Write-Host "[2/5] Setting up repository at $InstallDir..." -ForegroundColor Yellow
if (Test-Path $InstallDir) {
    Write-Host "  Directory exists — pulling latest changes..."
    Set-Location $InstallDir
    git pull
} else {
    Write-Host "  Cloning from $RepoUrl..."
    git clone $RepoUrl $InstallDir
    Set-Location $InstallDir
}

# --- Step 3: Install dependencies ---
Write-Host "[3/5] Installing Python dependencies..." -ForegroundColor Yellow
pip install -e ".[bedrock-ui]"
Write-Host "  Dependencies installed." -ForegroundColor Green

# --- Step 4: Create .env if missing ---
Write-Host "[4/5] Checking .env configuration..." -ForegroundColor Yellow
if (-not (Test-Path "$InstallDir\.env")) {
    Copy-Item "$InstallDir\.env.example" "$InstallDir\.env"
    Write-Host ""
    Write-Host "  *** ACTION REQUIRED ***" -ForegroundColor Red
    Write-Host "  .env file created from template. Edit it now:" -ForegroundColor Red
    Write-Host "  notepad $InstallDir\.env" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Required fields to fill in:"
    Write-Host "    QLIK_SERVER_URL      = https://qlik-dev.ispot.tv"
    Write-Host "    QLIK_USER_DIRECTORY  = ANALYTICSUSERS"
    Write-Host "    QLIK_USER_ID         = service-account@ispot.tv"
    Write-Host "    QLIK_CLIENT_CERT_PATH= C:\qlik-ai\certs\client.pem"
    Write-Host "    QLIK_CLIENT_KEY_PATH = C:\qlik-ai\certs\client_key.pem"
    Write-Host "    QLIK_CA_CERT_PATH    = C:\qlik-ai\certs\root.pem"
    Write-Host "    ANTHROPIC_API_KEY    = sk-ant-..."
    Write-Host ""
    Read-Host "Press Enter after editing .env to continue"
} else {
    Write-Host "  .env already exists — skipping." -ForegroundColor Green
}

# --- Step 5: Install as Windows Service (NSSM) ---
Write-Host "[5/5] Setting up Windows Service..." -ForegroundColor Yellow

$nssmPath = "C:\nssm\nssm.exe"
if (-not (Test-Path $nssmPath)) {
    Write-Host ""
    Write-Host "  NSSM not found at $nssmPath." -ForegroundColor Yellow
    Write-Host "  Download from: https://nssm.cc/download"
    Write-Host "  Extract nssm.exe to C:\nssm\nssm.exe, then re-run this script."
    Write-Host ""
    Write-Host "  --- Manual start (test mode) ---"
    Write-Host "  python -m streamlit run $InstallDir\web_ui\app.py --server.port $Port --server.address 0.0.0.0"
    Write-Host ""
    Write-Host "  Access at: http://qlik-dev.ispot.tv:$Port"
} else {
    $pythonExe = (Get-Command python).Source
    $serviceName = "QlikAIAssistant"

    # Remove existing service if present
    $existing = & $nssmPath status $serviceName 2>&1
    if ($existing -notmatch "Can't open service") {
        Write-Host "  Removing existing service..."
        & $nssmPath stop $serviceName 2>&1 | Out-Null
        & $nssmPath remove $serviceName confirm 2>&1 | Out-Null
    }

    Write-Host "  Installing service '$serviceName'..."
    & $nssmPath install $serviceName $pythonExe "-m streamlit run $InstallDir\web_ui\app.py --server.port $Port --server.address 0.0.0.0 --server.headless true"
    & $nssmPath set $serviceName AppDirectory $InstallDir
    & $nssmPath set $serviceName AppEnvironmentExtra "PYTHONPATH=$InstallDir"
    & $nssmPath set $serviceName DisplayName "Qlik Sense AI Assistant"
    & $nssmPath set $serviceName Description "Streamlit web UI powered by Claude + Qlik Sense MCP"
    & $nssmPath set $serviceName Start SERVICE_AUTO_START
    & $nssmPath start $serviceName

    Write-Host ""
    Write-Host "  Service '$serviceName' installed and started." -ForegroundColor Green
    Write-Host "  It will auto-start on server reboot."
}

Write-Host ""
Write-Host "=== Deployment complete ===" -ForegroundColor Cyan
Write-Host "Access the app at: http://qlik-dev.ispot.tv:$Port" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps for SRE:"
Write-Host "  1. Open port $Port in Windows Firewall for internal network traffic"
Write-Host "  2. (Optional) Set up IIS reverse proxy for a cleaner URL:"
Write-Host "     https://qlik-dev.ispot.tv/ai/  ->  http://localhost:$Port"
Write-Host "  3. Verify access from another machine on the corporate network"
