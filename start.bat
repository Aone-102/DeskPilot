@echo off
chcp 65001 > nul
title DeskPilot Launcher
echo ========================================================
echo             DeskPilot - 스마트 데스크탑 비서
echo ========================================================
echo.
echo DeskPilot 서버 및 대시보드를 시작합니다...
set "PYTHON_EXE=C:\Users\cheon\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" "%~dp0app.py" %*
pause
