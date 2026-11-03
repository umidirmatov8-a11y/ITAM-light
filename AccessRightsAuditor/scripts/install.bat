@echo off
chcp 65001 >nul
cd /d "%~dp0.."
where node >nul 2>nul || (echo Не найден Node.js. Установите Node.js 22 LTS: https://nodejs.org & pause & exit /b 1)
if not exist .env (
  copy .env.example .env >nul
  echo Создан файл .env — укажите параметры подключения к PostgreSQL и запустите install.bat снова.
  notepad .env
  pause
  exit /b 1
)
echo Установка зависимостей...
call npm ci || goto :err
echo Сборка интерфейса и сервера...
call npm run build || goto :err
echo Применение миграций БД...
call npm run migrate || goto :err
echo.
echo Установка завершена. Запуск: scripts\start.bat
echo Демонстрационные данные (необязательно): npm run seed:demo
pause
exit /b 0
:err
echo Ошибка установки.
pause
exit /b 1
