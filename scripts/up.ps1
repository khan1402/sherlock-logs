<#
up.ps1 - ONE command to start the whole project.

  .\scripts\up.ps1               First run: create all VMs and configure everything.
                                 Later runs: boot the existing VMs.
  .\scripts\up.ps1 -Fresh        Destroy everything first, then build from a blank slate.
  .\scripts\up.ps1 -Bonus        Include the bonus features (backup server, Fail2Ban).
  .\scripts\up.ps1 -Fresh -Bonus Blank slate WITH the bonus features.

Run from PowerShell in the repo folder. Needs VirtualBox, Vagrant, and the
.vault_pass file in the repo root (see README).
#>
param(
    [switch]$Fresh,
    [switch]$Bonus
)

# 'Continue' (not 'Stop'): Windows PowerShell treats any text a program writes
# to stderr as an error under 'Stop', even when the program succeeds.
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
$started = Get-Date

function Fail([string]$message) {
    Write-Host "ERROR: $message" -ForegroundColor Red
    exit 1
}

# --- 1. Prerequisites -----------------------------------------------------------
Write-Host "==> Checking prerequisites" -ForegroundColor Cyan
if (-not (Get-Command vagrant -ErrorAction SilentlyContinue))    { Fail "Vagrant is not installed (see README)." }
if (-not (Get-Command ssh-keygen -ErrorAction SilentlyContinue)) { Fail "OpenSSH client is not installed (Windows: Settings > Optional features)." }
$vbox = Join-Path "$env:VBOX_MSI_INSTALL_PATH" "VBoxManage.exe"
if (-not (Test-Path $vbox)) { Fail "VirtualBox is not installed (see README)." }
if (-not (Test-Path ".vault_pass")) { Fail ".vault_pass is missing in the repo root (see README)." }

function Get-ProjectVMs([string]$list = "vms") {
    & $vbox list $list | ForEach-Object { ($_ -split '"')[1] } | Where-Object { $_ -like "alchemy-*" }
}

# --- 2. Optional: start from a blank slate --------------------------------------------
if ($Fresh) {
    Write-Host "==> -Fresh: destroying all project VMs" -ForegroundColor Cyan
    $env:ENABLE_BONUS = "true"      # so Vagrant also knows about (and removes) the bonus VM
    vagrant destroy -f
    if ($LASTEXITCODE -ne 0) { Fail "vagrant destroy failed." }
}

if ($Bonus) { $env:ENABLE_BONUS = "true" } else { Remove-Item Env:ENABLE_BONUS -ErrorAction SilentlyContinue }

# --- 3. Forget old SSH host keys ----------------------------------------------------
# Rebuilt VMs get NEW host keys on the SAME IPs; old entries would make SSH refuse.
10..15 | ForEach-Object { ssh-keygen -R "192.168.56.$_" 2>&1 | Out-Null }

# --- 4. Create or boot ----------------------------------------------------------------
$existing = @(Get-ProjectVMs)

if ($existing.Count -eq 0) {
    Write-Host "==> Creating the VMs and configuring everything (first run: about 45-60 minutes)" -ForegroundColor Cyan
    vagrant up
    if ($LASTEXITCODE -ne 0) { Fail "vagrant up failed - read the first error in the output above." }
}
else {
    # After hardening only 'devops' may log in over SSH, so 'vagrant up' can no
    # longer confirm an existing VM has booted. VirtualBox boots them directly.
    Write-Host "==> VMs already exist - booting them with VirtualBox" -ForegroundColor Cyan
    $running = @(Get-ProjectVMs "runningvms")
    foreach ($vm in $existing) {
        if ($running -contains $vm) { Write-Host "    $vm is already running" }
        else { Write-Host "    starting $vm"; & $vbox startvm $vm --type headless | Out-Null }
    }
    if ($Bonus -and ($existing -notcontains "alchemy-backup-server")) {
        Write-Host "    NOTE: the bonus backup server was never created. Use: .\scripts\up.ps1 -Fresh -Bonus" -ForegroundColor Yellow
    }

    Write-Host "==> Waiting for the app to answer through the load balancer" -ForegroundColor Cyan
    $deadline = (Get-Date).AddMinutes(5)
    $up = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:8080/" -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { $up = $true; break }
        } catch { }
        Start-Sleep -Seconds 10
    }
    if (-not $up) { Fail "The app did not answer within 5 minutes. Check the VMs in VirtualBox." }
}

# --- 5. Summary --------------------------------------------------------------------------
$minutes = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
Write-Host ""
Write-Host "Ready in $minutes minutes." -ForegroundColor Green
Write-Host "  App:       http://localhost:8080   (or http://192.168.56.10)"
Write-Host "  Jenkins:   http://192.168.56.14:8080"
$validateCmd = if ($Bonus) { "bash scripts/validate.sh --bonus" } else { "bash scripts/validate.sh" }
Write-Host "  Validate:  $validateCmd   (in Git Bash)"
