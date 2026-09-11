@echo off
title Silent Angel Bremen SL1P - Studio Controller
cd /d "%~dp0"

echo ========================================================
echo   Silent Angel Bremen SL1P Controller Launcher
echo ========================================================
echo.
echo Checking environment and starting controller...
python bremen_controller.py 8090

pause
