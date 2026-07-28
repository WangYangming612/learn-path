@echo off
echo Setting VPN proxy for LLM API...
set HTTP_PROXY=http://127.0.0.1:7890
set HTTPS_PROXY=http://127.0.0.1:7890
cd /d "%~dp0backend"
echo Starting LearnPath backend server...
call .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
