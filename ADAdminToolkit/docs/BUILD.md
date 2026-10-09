# Запуск из исходников и сборка EXE

## Запуск из исходников (Windows 10/11)

```bat
cd ADAdminToolkit
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python main.py            :: обычный запуск
.venv\Scripts\python main.py --demo     :: тестовый режим без контроллера домена
.venv\Scripts\python -m pytest -q tests :: автоматические тесты
```

На Linux/macOS исходники также запускаются (для разработки и тестов); функции, требующие Windows (Kerberos через
SSPI, Credential Manager, журналы событий через wevtutil), сообщают о недоступности.

## Сборка EXE

```bat
build_exe.bat            :: onedir (рекомендуется): dist\ADAdminToolkit\ADAdminToolkit.exe
build_exe.bat onefile    :: один файл: dist\ADAdminToolkit.exe
build_exe.bat onedir notests
```

Скрипт выполняет:

1. Поиск Python 3.11–3.13 x64 (предпочтительно 3.12, через `py`-launcher или `python` в PATH).
2. Создание виртуального окружения `.venv`.
3. Установку зависимостей (`requirements-dev.txt`).
4. Запуск автоматических тестов (`build\test-results.xml`); при ошибке сборка останавливается.
5. Сборку PyInstaller по `ADAdminToolkit.spec` (иконка, ресурсы, сведения о версии, исключение неиспользуемых модулей Qt).
6. Копирование документации и `config\settings.example.json` рядом с EXE.
7. Самопроверку собранного EXE (`--selftest`: импорт всех модулей и прогон демо-каталога) — результат в `build\selftest.txt`.

Результат — в папке `dist`. Конечному пользователю не нужны Python и библиотеки: копируется вся папка
`dist\ADAdminToolkit` (onedir) или один файл (onefile; запускается медленнее из-за распаковки во временную папку).

## Конфигурация организации

Скопируйте `config\settings.example.json` в `config\settings.json` рядом с EXE и задайте профили подключения и
политику (периоды неактивности, стандартные группы и т.д.). Пароли в файле не указываются (и игнорируются).
Альтернатива — переменная окружения `ADTOOLKIT_CONFIG=<путь>`.

## Системные компоненты Windows

| Компонент | Для чего | Наличие |
|---|---|---|
| `wevtutil.exe` | журналы безопасности DC | входит в Windows 10/11 |
| `ping.exe` | ICMP-проверка | входит в Windows |
| Windows Credential Manager | хранение пароля (по согласию) | входит в Windows |
| SSPI / Kerberos | вход с текущими учётными данными | входит в Windows (ПК в домене) |
| RSAT / модуль ActiveDirectory для PowerShell | **не требуется** | — |
| PowerShell / WinRM | **не используются** | — |

Сетевые требования: TCP 636 (LDAPS) или 389 (StartTLS/Kerberos) до DC; для журналов — TCP 135 и динамические
RPC-порты, правило «Удалённое управление журналом событий (RPC)» и группа Event Log Readers на DC.
