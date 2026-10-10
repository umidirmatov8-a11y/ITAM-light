@echo off
REM ==========================================================================================================
REM  AD Admin Toolkit — сборка установщика (Windows 10/11)
REM    build_installer.bat           -> собирает EXE (build_exe.bat, если нужно) и dist\ADAdminToolkit-Setup-<версия>.exe
REM    build_installer.bat rebuild   -> всегда пересобирает EXE перед упаковкой
REM  Требуется Inno Setup 6: https://jrsoftware.org/isdl.php  (или: winget install JRSoftware.InnoSetup)
REM ==========================================================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul

set "APPDIR=dist\ADAdminToolkit"
if /I "%~1"=="rebuild" if exist "%APPDIR%" rmdir /s /q "%APPDIR%"
if not exist "%APPDIR%\ADAdminToolkit.exe" (
    echo [1/3] Сборка EXE ^(build_exe.bat^)...
    call build_exe.bat onedir
    if errorlevel 1 ( echo [ОШИБКА] Сборка EXE не удалась & exit /b 1 )
) else (
    echo [1/3] Используется готовая сборка %APPDIR% ^(для пересборки: build_installer.bat rebuild^)
)
if not exist "%APPDIR%\_internal\shiboken6" (
    echo [ОШИБКА] В сборке нет %APPDIR%\_internal\shiboken6 — пересоберите: build_installer.bat rebuild
    exit /b 1
)

echo.
echo [2/3] Поиск Inno Setup 6...
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
    if not defined ISCC if exist "%%~P" set "ISCC=%%~P"
)
if not defined ISCC for /f "delims=" %%i in ('where iscc 2^>nul') do if not defined ISCC set "ISCC=%%i"
if not defined ISCC (
    echo [ОШИБКА] Не найден Inno Setup 6 ^(ISCC.exe^). Установите: https://jrsoftware.org/isdl.php или winget install JRSoftware.InnoSetup
    exit /b 1
)
echo       %ISCC%

set "VERSION="
for /f "tokens=2 delims==" %%v in ('findstr /b /c:"__version__" adtoolkit\__init__.py') do set "VERSION=%%~v"
if not defined VERSION set "VERSION=1.0.0"
set "VERSION=%VERSION: =%"
set "VERSION=%VERSION:"=%"

echo.
echo [3/3] Сборка установщика версии %VERSION%...
"%ISCC%" /Qp "/DAppVersion=%VERSION%" installer\ADAdminToolkit.iss
if errorlevel 1 ( echo [ОШИБКА] Inno Setup завершился с ошибкой & exit /b 1 )

echo.
echo ============================================================================================
echo  Готово: dist\ADAdminToolkit-Setup-%VERSION%.exe
echo  Передавайте пользователям только этот файл.
echo ============================================================================================
endlocal
exit /b 0
