# ============================================================
# Claw Code - Windows Node Deployment Script
# PowerShell: .\deploy_windows.ps1 -PortalIP "192.168.1.xxx"
# ============================================================

param(
    [string]$PortalIP = "",
    [int]$Port = 8081,
    [string]$NodeName = $env:COMPUTERNAME
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "    Tudou Claws - Windows Node Deployment" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan

# ---------- 1. Check / Install Python ----------
Write-Host "`n[1/4] Checking Python..." -ForegroundColor Yellow

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.1[0-9]|Python 3\.[2-9]") {
            $pythonCmd = $cmd
            Write-Host "  Found: $ver" -ForegroundColor Green
            break
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "  Python 3.10+ not found. Installing..." -ForegroundColor Yellow

    $installerUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
    $installerPath = "$env:TEMP\python-installer.exe"

    Write-Host "  Downloading Python 3.12.8..." -ForegroundColor Cyan
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing

    Write-Host "  Installing Python (this may take a minute)..." -ForegroundColor Cyan
    Start-Process -FilePath $installerPath -ArgumentList "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_pip=1" -Wait -NoNewWindow

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

    foreach ($cmd in @("python", "python3", "py")) {
        try {
            $ver = & $cmd --version 2>&1
            if ($ver -match "Python 3") {
                $pythonCmd = $cmd
                Write-Host "  Installed: $ver" -ForegroundColor Green
                break
            }
        } catch {}
    }

    if (-not $pythonCmd) {
        Write-Host "  ERROR: Python install failed. Download from https://python.org/downloads/" -ForegroundColor Red
        exit 1
    }
}

# ---------- 2. Install dependencies ----------
Write-Host "`n[2/4] Installing dependencies..." -ForegroundColor Yellow
& $pythonCmd -m pip install --upgrade pip --quiet 2>$null
& $pythonCmd -m pip install requests pyyaml --quiet
Write-Host "  Dependencies OK" -ForegroundColor Green

# ---------- 3. Detect network ----------
Write-Host "`n[3/4] Detecting network..." -ForegroundColor Yellow
$lanIP = & $pythonCmd -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0]);s.close()"
Write-Host "  LAN IP: $lanIP  Port: $Port" -ForegroundColor Green

# ---------- 4. Start node ----------
Write-Host "`n[4/4] Starting Claw Code Node..." -ForegroundColor Yellow
Write-Host "  Node: $NodeName" -ForegroundColor Cyan
Write-Host "  URL:  http://${lanIP}:${Port}" -ForegroundColor Cyan

if ($PortalIP) {
    Write-Host "  Hub:  http://${PortalIP}:9090" -ForegroundColor Cyan
}

Write-Host "`n  Starting..." -ForegroundColor Green

& $pythonCmd -c @"
import sys, os, threading, time
sys.path.insert(0, r'C:\claw-code')
os.chdir(r'C:\claw-code')
os.environ['CLAW_NODE_NAME'] = '$NodeName'

# Auto-register with Portal after a short delay
portal_ip = '$PortalIP'
if portal_ip:
    def _register():
        import requests
        time.sleep(3)
        node_url = 'http://${lanIP}:${Port}'
        hub_url = f'http://{portal_ip}:9090'
        for attempt in range(5):
            try:
                resp = requests.post(
                    f'{hub_url}/api/hub/register',
                    json={'node_id': 'win-${NodeName}'.lower().replace(' ','-'),
                          'name': '$NodeName', 'url': node_url},
                    timeout=10)
                if resp.status_code == 200:
                    print(f'\n  Registered with Hub: {resp.json()}')
                    # Also sync our agents
                    try:
                        requests.post(f'{hub_url}/api/hub/sync',
                            json={'node_id': 'win-${NodeName}'.lower().replace(' ','-'),
                                  'agents': []}, timeout=5)
                    except: pass
                    break
            except Exception as e:
                print(f'  Register attempt {attempt+1}: {e}')
                time.sleep(3)
    threading.Thread(target=_register, daemon=True).start()

from app.portal import run_portal
run_portal(port=${Port}, node_name='$NodeName')
"@
