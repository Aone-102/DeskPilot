@echo off
chcp 65001 > nul
title DeskPilot v2 Standalone App Packager
echo ========================================================
echo          DeskPilot v2 - 독립 실행 파일(exe) 빌드
echo ========================================================
echo.
echo DeskPilot v2를 배포용 독립 실행 파일(exe)로 빌드합니다...
echo.

set "PYTHON_EXE=C:\Users\cheon\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo [1/2] PyInstaller 컴파일 실행 중...
"%PYTHON_EXE%" -m PyInstaller -y --noconsole --onedir --name "DeskPilot" --add-data "static;static" --clean app.py

if errorlevel 1 (
    echo.
    echo [오류] 빌드 중 문제가 발생했습니다.
    pause
    exit /b 1
)

echo.
echo [2/2] 빌드 완료!
echo ========================================================
echo [배포 파일 위치] dist\DeskPilot\DeskPilot.exe
echo.
echo 이 'dist\DeskPilot' 폴더 전체를 다른 컴퓨터에 복사하거나
echo zip으로 압축하여 다른 사람에게 바로 배포할 수 있습니다!
echo ========================================================
echo.
pause
