@echo off
chcp 65001 >nul
rem Восстановление доступа: задаёт временный пароль учётной записи администратора ARA (создаёт её, если нет).
net session >nul 2>&1 || (powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs" & exit /b)
set "ARA_ENV_FILE=%ProgramData%\ARA\config\ara.env"
set "LOGIN="
set /p LOGIN=Логин администратора [admin]: 
if "%LOGIN%"=="" set "LOGIN=admin"
"%~dp0..\node\node.exe" "%~dp0..\app\server\dist\cli\create-admin.js" %LOGIN%
echo.
echo Войдите с временным паролем — система попросит сменить его.
pause
