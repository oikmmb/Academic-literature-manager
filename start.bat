@echo off
chcp 65001 >nul
cd /d %~dp0
if not exist server\venv\Scripts\python.exe (
    echo [ERROR] venv not found. Run:  python -m venv server\venv
    echo         then:  server\venv\Scripts\pip install -r server\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)
server\venv\Scripts\python.exe start.py %*
