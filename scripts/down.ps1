<#
down.ps1 - ONE command to stop the whole project.

  .\scripts\down.ps1             Shut the VMs down cleanly (keeps everything; start again with up.ps1).
  .\scripts\down.ps1 -Destroy    Delete all project VMs (blank slate).

Run from PowerShell in the repo folder.
#>
param(
    [switch]$Destroy
)

$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)

$vbox = Join-Path "$env:VBOX_MSI_INSTALL_PATH" "VBoxManage.exe"
if (-not (Test-Path $vbox)) { Write-Host "ERROR: VirtualBox is not installed." -ForegroundColor Red; exit 1 }

function Get-ProjectVMs([string]$list = "vms") {
    & $vbox list $list | ForEach-Object { ($_ -split '"')[1] } | Where-Object { $_ -like "alchemy-*" }
}

if ($Destroy) {
    Write-Host "==> Destroying all project VMs" -ForegroundColor Cyan
    $env:ENABLE_BONUS = "true"      # so Vagrant also knows about (and removes) the bonus VM
    vagrant destroy -f
    exit $LASTEXITCODE
}

# Send the "power button" signal, so Ubuntu shuts down properly.
# (Vagrant can't do this after hardening: only 'devops' may log in over SSH.)
$running = @(Get-ProjectVMs "runningvms")
if ($running.Count -eq 0) { Write-Host "No project VMs are running."; exit 0 }

foreach ($vm in $running) {
    Write-Host "    shutting down $vm"
    & $vbox controlvm $vm acpipowerbutton
}

Write-Host "==> Waiting for the VMs to power off" -ForegroundColor Cyan
$deadline = (Get-Date).AddMinutes(2)
while ((Get-Date) -lt $deadline -and @(Get-ProjectVMs "runningvms").Count -gt 0) { Start-Sleep -Seconds 5 }

$still = @(Get-ProjectVMs "runningvms")
if ($still.Count -gt 0) {
    Write-Host "Still running after 2 minutes, forcing power off: $($still -join ', ')" -ForegroundColor Yellow
    foreach ($vm in $still) { & $vbox controlvm $vm poweroff | Out-Null }
}
Write-Host "All project VMs are off." -ForegroundColor Green
