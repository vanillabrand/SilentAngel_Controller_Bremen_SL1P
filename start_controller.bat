@echo off
title Silent Angel Streamer - Studio Controller
cd /d "%~dp0"

echo ========================================================
echo   Silent Angel Streamer Controller Launcher
echo ========================================================
echo.
echo Checking environment and starting controller...
python silent_angel_controller.py 8090

pause
