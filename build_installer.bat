@echo off
chcp 65001 > nul
title DeskPilot v2.0 Setup Installer Packager
echo ========================================================
echo        DeskPilot v2.0 - 원클릭 자동 설치 파일(.exe) 빌드
echo ========================================================
echo.

set "PYTHON_EXE=C:\Users\cheon\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYTHON_EXE%" (
    set "PYTHON_EXE=python"
)

echo [1/3] DeskPilot 본체 최신 바이너리 컴파일 중...
"%PYTHON_EXE%" -m PyInstaller -y --noconsole --onedir --name "DeskPilot" --add-data "static;static" --clean app.py
if errorlevel 1 (
    echo [오류] 본체 빌드 실패!
    pause
    exit /b 1
)

echo.
echo [2/3] 설치 패키지 압축(payload.zip 생성) 중...
"%PYTHON_EXE%" -c "import shutil, os; shutil.make_archive('payload', 'zip', 'dist/DeskPilot'); print('    생성 완료: payload.zip (크기: ' + str(round(os.path.getsize('payload.zip')/(1024*1024), 2)) + ' MB)')"
if errorlevel 1 (
    echo [오류] payload.zip 생성 실패!
    pause
    exit /b 1
)

echo.
echo [3/3] 원클릭 자동 설치 파일(DeskPilot-Setup.exe) 컴파일 중...
"%PYTHON_EXE%" -m PyInstaller -y --noconsole --onefile --name "DeskPilot-Setup" --add-data "payload.zip;." --clean installer.py
if errorlevel 1 (
    echo [오류] 인스톨러 빌드 실패!
    pause
    exit /b 1
)

echo.
echo 임시 파일 정리 중...
del /f /q payload.zip 2>nul

echo.
echo ========================================================
echo              ✨ 자동 설치 파일 생성 완료!
echo ========================================================
echo.
echo 생성된 설치 파일:
echo   ▶ dist\DeskPilot-Setup.exe
echo.
echo 이 'DeskPilot-Setup.exe' 파일만 다른 컴퓨터로 옮기거나
echo GitHub Releases 탭에 업로드하여 다른 사람에게 공유하시면 됩니다!
echo.
echo 사용자가 이 exe 파일을 열면(더블클릭):
echo   1) 프로그램이 PC에 자동으로 설치됩니다.
echo   2) 바탕화면 및 시작메뉴에 바로가기 아이콘이 등록됩니다.
echo   3) 윈도우 부팅 시 자동 실행이 등록됩니다.
echo   4) 설치 즉시 DeskPilot이 자동 실행됩니다!
echo ========================================================
echo.
pause
