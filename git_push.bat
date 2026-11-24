@echo off
chcp 65001 > nul
title DeskPilot GitHub 동기화 및 푸시 관리자
echo ========================================================
echo           DeskPilot - GitHub 원클릭 코드 푸시
echo ========================================================
echo.

set "GIT_EXE=C:\Program Files\Git\cmd\git.exe"
if not exist "%GIT_EXE%" (
    set "GIT_EXE=git"
)

echo [1/3] 변경된 파일 확인 및 스테이징 중...
"%GIT_EXE%" status -s
echo.
"%GIT_EXE%" add .

set /p COMMIT_MSG="커밋 메시지를 입력하세요 (엔터 시 기본 메시지 적용): "
if "%COMMIT_MSG%"=="" (
    set "COMMIT_MSG=Update: DeskPilot 코드 및 문서 최신화"
)

echo.
echo [2/3] 커밋 생성 중: "%COMMIT_MSG%"
"%GIT_EXE%" commit -m "%COMMIT_MSG%"

echo.
echo [3/3] GitHub(https://github.com/Aone-102/DeskPilot)으로 푸시 중...
"%GIT_EXE%" push origin main

if errorlevel 1 (
    echo.
    echo [오류] GitHub 푸시 중 문제가 발생했습니다.
) else (
    echo.
    echo ========================================================
    echo      ✨ GitHub(https://github.com/Aone-102/DeskPilot)
    echo                  업로드 성공 완료!
    echo ========================================================
)
echo.
pause
