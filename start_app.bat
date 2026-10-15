@echo off
REM 퀀트 시그널 앱 서버 시작 (자동 실행 스케줄러 포함). 이 창을 닫으면 서버가 꺼집니다.
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
call venv\Scripts\activate.bat
python web_app.py
pause
