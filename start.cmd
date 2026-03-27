@echo off
setlocal
cd /d "%~dp0"
echo [code-graph] Launching PowerShell startup wrapper...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
exit /b %errorlevel%