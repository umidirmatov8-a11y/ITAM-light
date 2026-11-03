@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if not exist server\dist\main.js (echo Приложение не собрано. Запустите scripts\install.bat & pause & exit /b 1)
set PORT_NUM=3000
for /f "tokens=2 delims==" %%a in ('findstr /b "ARA_PORT=" .env 2^>nul') do set PORT_NUM=%%a
start "" "http://localhost:%PORT_NUM%"
node server\dist\main.js
pause
