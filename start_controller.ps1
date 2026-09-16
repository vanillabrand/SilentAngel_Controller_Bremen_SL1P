# Silent Angel Streamer — PowerShell Launcher
# UK English Standard
Set-Location -Path $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Silent Angel Streamer Controller Launcher" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Checking environment and starting controller..." -ForegroundColor Green

python silent_angel_controller.py 8090
