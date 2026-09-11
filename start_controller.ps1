# Silent Angel Bremen SL1P — PowerShell Launcher
# UK English Standard
Set-Location -Path $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Silent Angel Bremen SL1P Controller Launcher" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Checking environment and starting controller..." -ForegroundColor Green

python bremen_controller.py 8090
