# AD Admin Toolkit — архитектура, ограничения LDAP и структура файлов

## 1. Принципы

* **Разделение слоёв.** UI (PySide6) не обращается к ldap3 напрямую: только к сервисам; сервисы — только к
  абстрактному шлюзу каталога `DirectoryGateway`.
* **Единый слой доступа к данным.** `Ldap3Gateway` (реальный AD) и `MemoryGateway` (демо-режим и тесты) реализуют
  один контракт: поиск с постраничной выдачей, чтение, изменение, перемещение, установка пароля.
* **Единая обработка ошибок.** Коды LDAP, расширенные коды AD (`0000052D`, `data 775` и т.п.), исключения ldap3/ssl/socket
  преобразуются в типизированные `ToolkitError` (`adtoolkit/ldap/error_mapping.py`) с русским текстом, рекомендацией и
  маскированными техническими деталями.
* **Безопасность по умолчанию.** Режим «только чтение» включён по умолчанию; запись разрешается явно и проверяется
  в шлюзе (`_guard_write`) — то есть ни один путь UI не может её обойти. Пароли передаются только по TLS.
* **Неблокирующий интерфейс.** Все операции LDAP/сети выполняются в `QThreadPool` (`workers/tasks.py`), результат
  возвращается в GUI через Qt-сигналы; длительные операции поддерживают отмену между страницами/объектами.

```
┌──────────────────────────── UI (PySide6) ─────────────────────────────┐
│ MainWindow · страницы · диалоги · Actions (подтверждения, защита)       │
│ DataTable (сортировка, фильтр, столбцы, экспорт) · Toast · TaskManager  │
└──────────────┬──────────────────────────────────────────┬─────────────┘
               │ ServiceContext                           │ QThreadPool + CancelToken
┌──────────────▼────────────── Сервисы ────────────────────▼─────────────┐
│ user · computer · group · ou · dashboard · audit · bulk · offboarding   │
│ explorer · report · events (wevtutil) · network · compare · password    │
└──────────────┬────────────────────────────────────────────────────────┘
               │ DirectoryGateway (контракт)
┌──────────────▼────────────── Доступ к каталогу ───────────────────────┐
│ Ldap3Gateway: TLS/StartTLS, bind, paged search, reconnect, error map    │
│ MemoryGateway: демо-каталог + вычисление фильтров (803/804/1941)        │
│ filters.py (AST + экранирование) · dn.py · adtypes.py · SD parser       │
└──────────────┬────────────────────────────────────────────────────────┘
┌──────────────▼──────── Безопасность и хранение ───────────────────────┐
│ permissions (allowedAttributesEffective, SID привилегированных групп)  │
│ audit_log (журнал приложения) · masking · credentials (Credential Mgr) │
│ storage/database.py (SQLite: настройки, профили, запросы, шаблоны)     │
└────────────────────────────────────────────────────────────────────────┘
```

## 2. Структура файлов

```
ADAdminToolkit/
├── main.py                      # точка входа: GUI, --demo, --version, --selftest
├── requirements.txt / requirements-dev.txt
├── ADAdminToolkit.spec          # PyInstaller (onedir по умолчанию, onefile через ADTK_ONEFILE=1)
├── build_exe.bat                # сборка EXE: Python → venv → зависимости → тесты → PyInstaller → самопроверка
├── config/settings.example.json # пример конфигурации организации (без секретов)
├── resources/                   # иконки (icon.ico, icon.png) и генератор make_icon.py
├── docs/                        # документация
├── tests/                       # pytest: 149 тестов, mock LDAP и демо-каталог
└── adtoolkit/
    ├── core/        errors.py (типизированные ошибки) · cancel.py · app_config.py (настройки)
    ├── ldap/        gateway.py (контракт, Entry) · ldap3_gateway.py · memory_gateway.py · demo_data.py
    │                filters.py (AST, экранирование RFC 4515, парсер) · dn.py (RFC 4514) · adtypes.py
    │                security_descriptor.py (DACL: «запрет смены пароля», защита от удаления) · error_mapping.py
    ├── models/      connection.py (профиль, DirectoryInfo, политика) · records.py (User/Computer/Group/OU, Finding)
    ├── services/    ldap_service · user_service · computer_service · group_service · ou_service · dashboard_service
    │                audit_service · bulk_service · offboarding_service · explorer_service · report_service
    │                events_service · network_service · compare_service · password_service · attribute_reference
    ├── security/    credentials.py · permissions.py · audit_log.py · masking.py
    ├── storage/     database.py (SQLite)
    ├── reports/     exporters.py (CSV / XLSX / HTML)
    ├── workers/     tasks.py (фоновые задачи, отмена, прогресс)
    └── ui/          app.py · main_window.py · theme.py · actions.py · widgets/ · dialogs/ · pages/
```

## 3. Подключение и шифрование

| Режим | Порт | Аутентификация | Пароль по сети | Комментарий |
|---|---|---|---|---|
| LDAPS | 636 | Simple (UPN/DN), NTLM, Kerberos | только внутри TLS | рекомендуется |
| StartTLS | 389 | Simple, NTLM, Kerberos | только после установки TLS | если 636 закрыт |
| LDAP без TLS | 389 | **только Kerberos**, с явным разрешением | не передаётся | данные каталога открыты; операции с паролями запрещены |

* Проверка сертификата **не отключается**: `ssl.CERT_REQUIRED` + проверка имени узла. Можно указать собственный PEM-файл
  корневого ЦС или ожидаемое имя сертификата (при подключении по IP). По умолчанию используются доверенные корневые
  сертификаты Windows.
* **SASL signing/sealing.** Библиотека ldap3 2.9 реализует Kerberos/NTLM только как аутентификацию — без слоёв
  целостности/конфиденциальности (это видно в `ldap3/protocol/sasl/kerberos.py`). Поэтому конфиденциальность
  обеспечивается TLS; простой LDAP на 389 никогда не считается защищённым.
* Kerberos с текущими учётными данными Windows — через пакет `winkerberos` (поддерживает channel binding для LDAPS).
* NTLM-bind требует MD4 (`pycryptodome`, т.к. OpenSSL 3 исключил MD4); при политике «LDAP channel binding = Always»
  используйте Simple bind поверх TLS или Kerberos.

После подключения определяются: DNS-имя домена, NetBIOS-имя (crossRef), Base DN (defaultNamingContext),
контроллер (dnsHostName), функциональные уровни, список DC, политика паролей и блокировки, интервал
`msDS-LogonTimeSyncInterval`, учётная запись (WhoAmI) и время последнего успешного обмена.

Потеря связи: чтение повторяется после автоматического переподключения (несколько попыток с паузой);
изменения **не повторяются** — пользователь получает сообщение «результат неизвестен, обновите объект».
Постраничный поиск, прерванный обрывом связи, не «склеивается» на новом соединении (cookie привязан к соединению).

## 4. Ограничения LDAP / Active Directory и как они учтены

| Ограничение | Решение в приложении |
|---|---|
| MaxPageSize (1000) и MaxResultSetSize | Paged Results Control (1.2.840.113556.1.4.319), размер страницы настраивается; лимит строк в UI с явной пометкой «результат неполный» |
| Атрибуты >1500 значений (`member`) | ldap3 `auto_range` + объединение `member;range=…` при декодировании |
| Спецсимволы в фильтрах | только AST-построитель с экранированием RFC 4515; ручной фильтр в Explorer проходит синтаксический разбор и перерисовку |
| Спецсимволы в DN | экранирование RFC 4514 (`child_dn`, `escape_dn_value`), сравнение по нормализованному DN |
| Подстрочный поиск по DN не поддерживается AD | при вводе DN выполняется чтение объекта, а не `(distinguishedName=*…*)` |
| `lastLogon` не реплицируется | функция «Точный последний вход» опрашивает каждый DC |
| `lastLogonTimestamp` обновляется с задержкой (14 дн. − до 5 дн.) | все «неактивные» показатели помечены как приблизительные, пустое значение — «нет данных», а не «не входил» |
| Блокировка: `lockoutTime > 0` ≠ «заблокирован сейчас» | состояние берётся из `msDS-User-Account-Control-Computed`; при отсутствии — оценка по `lockoutDuration` с пометкой |
| Истечение пароля с учётом PSO | `msDS-UserPasswordExpiryTimeComputed` |
| «User cannot change password» не хранится в UAC | разбор DACL (`nTSecurityDescriptor`, SD Flags = DACL) — deny ACE «Change Password» для Everyone/SELF |
| `memberOf` не содержит основную группу и вложенность | основная группа по `primaryGroupID`, вложенность — `LDAP_MATCHING_RULE_IN_CHAIN` (1.2.840.113556.1.4.1941) и обход с путями и защитой от циклов |
| «Пустые» группы могут иметь членов через primaryGroupID | проверка `(primaryGroupID=RID)` для каждой группы-кандидата |
| Локализованные имена встроенных групп | привилегированные группы определяются по SID/RID |
| Журнал безопасности DC недоступен через LDAP | отдельный модуль на `wevtutil.exe` (Windows, RPC, Event Log Readers) |
| Права нельзя вычислить по ACL на клиенте надёжно | предварительная проверка через `allowedAttributesEffective` / `allowedChildClassesEffective`, окончательное решение — DC; право Reset Password (extended right) проверяется контроллером |
| Конфликт одновременного изменения | модификация «удалить старое значение + добавить новое» в одной операции → конфликт при изменении другим администратором |

## 5. Хранение данных

`%LOCALAPPDATA%\ADAdminToolkit\toolkit.db` (SQLite, WAL): настройки, профили подключений **без паролей**,
избранные запросы и история, сохранённые фильтры, шаблоны создания пользователей и увольнения, журнал операций
приложения. Журнал программы: `%LOCALAPPDATA%\ADAdminToolkit\logs\adtoolkit.log` (ротация 5×5 МБ, маскирование секретов).
Каталог можно переопределить переменной `ADTOOLKIT_HOME`, конфигурацию организации — `ADTOOLKIT_CONFIG`.
