@echo off
REM ==========================================================================================================
REM  AD Admin Toolkit — build script (Windows 10/11)
REM    build_exe.bat              -> onedir build (dist\ADAdminToolkit\ADAdminToolkit.exe), recommended
REM    build_exe.bat onefile      -> single-file build (dist\ADAdminToolkit.exe)
REM    build_exe.bat onedir notests / onefile notests -> skip automated tests (not recommended)
REM  Steps: Python check -> venv -> dependencies -> tests -> PyInstaller -> self-test of the EXE -> dist\
REM ==========================================================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul

set "MODE=onedir"
if /I "%~1"=="onefile" set "MODE=onefile"
if /I "%~1"=="--onefile" set "MODE=onefile"
set "RUNTESTS=1"
if /I "%~2"=="notests" set "RUNTESTS=0"
if /I "%~1"=="notests" set "RUNTESTS=0"

echo.
echo [1/7] Поиск совместимого Python (3.11 - 3.13, 64-bit; рекомендуется 3.12)...
set "PY="
for %%V in (3.12 3.13 3.11) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [ОШИБКА] Не найден Python 3.11-3.13. Установите Python 3.12 x64 с https://www.python.org/downloads/windows/
    echo          ^(отметьте "Add python.exe to PATH" и "py launcher"^). Python нужен только для сборки, не для работы EXE.
    exit /b 1
)
%PY% -c "import struct, sys; sys.exit(0 if struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
    echo [ОШИБКА] Требуется 64-битный Python.
    exit /b 1
)
for /f "delims=" %%i in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set "PYVER=%%i"
echo       Используется Python %PYVER% (%PY%)

echo.
echo [2/7] Виртуальное окружение .venv ...
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 ( echo [ОШИБКА] Не удалось создать виртуальное окружение & exit /b 1 )
)
set "VPY=%CD%\.venv\Scripts\python.exe"

echo.
echo [3/7] Установка зависимостей...
"%VPY%" -m pip install --disable-pip-version-check --upgrade pip >nul
"%VPY%" -m pip install --disable-pip-version-check -r requirements-dev.txt
if errorlevel 1 ( echo [ОШИБКА] Не удалось установить зависимости & exit /b 1 )

if not exist build mkdir build
if "%RUNTESTS%"=="1" (
    echo.
    echo [4/7] Автоматические тесты ^(демо-каталог и mock LDAP, реальный домен не используется^)...
    set "QT_QPA_PLATFORM=offscreen"
    "%VPY%" -m pytest -q tests --junitxml=build\test-results.xml
    if errorlevel 1 ( echo [ОШИБКА] Тесты не пройдены — сборка остановлена. Отчёт: build\test-results.xml & exit /b 1 )
    set "QT_QPA_PLATFORM="
) else (
    echo.
    echo [4/7] Тесты пропущены по параметру notests
)

echo.
echo [5/7] Сборка PyInstaller ^(%MODE%^)...
if "%MODE%"=="onefile" ( set "ADTK_ONEFILE=1" ) else ( set "ADTK_ONEFILE=" )
"%VPY%" -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller ADAdminToolkit.spec
if errorlevel 1 ( echo [ОШИБКА] Сборка PyInstaller завершилась с ошибкой & exit /b 1 )

if "%MODE%"=="onefile" (
    set "EXE=dist\ADAdminToolkit.exe"
    set "OUTDIR=dist"
) else (
    set "EXE=dist\ADAdminToolkit\ADAdminToolkit.exe"
    set "OUTDIR=dist\ADAdminToolkit"
)
if not exist "%EXE%" ( echo [ОШИБКА] Не найден %EXE% & exit /b 1 )
if "%MODE%"=="onedir" if not exist "dist\ADAdminToolkit\_internal\shiboken6" ( echo [ОШИБКА] В сборке нет _internal\shiboken6 ^(PySide6 не запустится^) & exit /b 1 )

echo.
echo [6/7] Копирование документации и примера конфигурации...
if not exist "%OUTDIR%\config" mkdir "%OUTDIR%\config"
copy /Y config\settings.example.json "%OUTDIR%\config\settings.example.json" >nul
if not exist "%OUTDIR%\docs" mkdir "%OUTDIR%\docs"
copy /Y docs\*.md "%OUTDIR%\docs\" >nul
copy /Y README.md "%OUTDIR%\README.md" >nul

echo.
echo [7/7] Самопроверка собранного EXE ^(без Python и без контроллера домена^)...
if exist build\selftest.txt del /q build\selftest.txt
start "" /wait "%EXE%" --selftest --selftest-out="%CD%\build\selftest.txt"
if errorlevel 1 ( echo [ОШИБКА] Самопроверка EXE не пройдена & type build\selftest.txt 2>nul & exit /b 1 )
type build\selftest.txt

echo.
echo ============================================================================================
echo  Готово: %EXE%
echo  Запуск в тестовом режиме без домена: "%EXE%" --demo
if "%MODE%"=="onedir" echo  Установщик для передачи пользователям: build_installer.bat
echo ============================================================================================
endlocal
exit /b 0
