@echo off
chcp 65001 >nul
rem Резервная копия ARA: дамп базы данных + исходные выгрузки и отчёты -> %ProgramData%\ARA\data\backups
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" & exit /b)
set "ARA_ENV_FILE=%ProgramData%\ARA\config\ara.env"
"%~dp0..\node\node.exe" "%~dp0..\app\server\dist\cli\backup.js" manual
echo.
pause
