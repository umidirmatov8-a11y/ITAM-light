# ITAM Platform — учёт IT-активов

Корпоративная система учёта IT-оборудования, сотрудников, лицензий, доступов и документов. Устанавливается на Windows
Server одним файлом `ITAM-Setup.exe`, работает как служба Windows, пользователи открывают веб-интерфейс
`http://IP-СЕРВЕРА:8080` в браузере.

## Возможности

| Модуль | Что умеет |
|---|---|
| Сотрудники | карточка, статусы, история переводов по оргструктуре (с датами), увольнение с проверкой незакрытых позиций, архив, массовые операции |
| Оргструктура | регионы → города → филиалы → офисы → кабинеты/склады, иерархия подразделений, должности; переименование не ломает историю |
| Активы | настраиваемые типы/категории/статусы, дополнительные поля, авто-инвентарные номера, QR и штрихкоды, печать этикеток, комплектующие, амортизация |
| Операции | выдача, возврат, передача, смена статуса, ремонт; акты с номерами; **операции задним числом** с полной проверкой хронологии; отмена с сохранением истории |
| История | для каждого актива: фактическая дата события и дата внесения, кто внёс; состояние актива на любую дату |
| Документы | DOCX-шаблоны с плейсхолдерами и версиями, генерация DOCX + PDF, статус подписи, скан подписанного документа |
| Лицензии и ПО | места, назначение на сотрудника/устройство, контроль превышения и сроков, зашифрованные ключи |
| Доступы | системы, уровни, выдача/отзыв, пересмотр, доступы уволенных |
| Онбординг / оффбординг | шаблоны чек-листов, автоматические проверки (вся техника возвращена, доступы отозваны…) |
| Инвентаризация | кампании, сканирование QR камерой телефона или сканером, акт инвентаризации |
| Склад расходников | остатки по складам, движения, минимальные остатки |
| Договоры | реестр договоров, связи с активами и лицензиями, предупреждения об окончании |
| Отчёты | 14 отчётов (в т.ч. «состояние активов на дату», амортизация), экспорт XLSX / CSV / PDF |
| Импорт | XLSX/CSV: загрузка → просмотр → сопоставление колонок → проверка → подтверждение |
| Администрирование | пользователи, роли и права (RBAC), ограничение по регионам, журнал аудита (неизменяемый), настройки, резервные копии |
| Интерфейс | русский (по умолчанию), английский, узбекский; светлая и тёмная тема; адаптивная вёрстка |

Полный список, включая 24 дополнительные функции, — в [ADMIN_GUIDE.md](Documentation/ADMIN_GUIDE.md#дополнительные-функции).

## Быстрый старт

**Windows Server (рекомендуется):** запустите `ITAM-Setup.exe`, выберите «Установить встроенный PostgreSQL», задайте пароли и
откройте адрес, показанный в конце установки. Подробно — [INSTALLATION.md](Documentation/INSTALLATION.md).

**Docker (Linux):**

```bash
cd ITAM
ITAM_DB_PASSWORD='сложный-пароль' docker compose -f deploy/docker/docker-compose.yml up -d
# http://localhost:8080 → мастер первоначальной настройки
```

**Разработка:**

```bash
# backend (нужен PostgreSQL 14+)
cd ITAM/Backend
dotnet run --project ITAM.Api -- setup --db-host localhost --db-user postgres --db-password postgres \
    --admin-password 'Admin12345!' --org "Тест" --demo --data-root ./data
dotnet run --project ITAM.Api -- --Itam:DataRoot=./data          # http://localhost:8080
# frontend с горячей перезагрузкой (проксирует /api на :8080)
cd ../Frontend && npm ci && npm run dev                          # http://localhost:5173
```

## Состав репозитория

```
ITAM/
├── Backend/            ASP.NET Core 10 (Clean Architecture): Domain, Application, Infrastructure, Api (ITAM.Server)
│   └── Tests/          ITAM.UnitTests, ITAM.IntegrationTests (реальный PostgreSQL)
├── Frontend/           React 18 + TypeScript + Ant Design (сборка в Backend/ITAM.Api/wwwroot)
├── Database/           migrations.sql — идемпотентный SQL-скрипт всех миграций
├── Installer/          Inno Setup (ITAM.iss) и build-installer.ps1
├── deploy/docker/      Dockerfile, docker-compose.yml
└── Documentation/      документация
```

## Документация

| Документ | Содержание |
|---|---|
| [ARCHITECTURE.md](Documentation/ARCHITECTURE.md) | архитектура, ERD, модель прав, временная модель данных, точки расширения |
| [INSTALLATION.md](Documentation/INSTALLATION.md) | установка, обновление, тихая установка, удаление, Docker |
| [ADMIN_GUIDE.md](Documentation/ADMIN_GUIDE.md) | руководство администратора и пользователя, дополнительные функции |
| [DATABASE.md](Documentation/DATABASE.md) | структура БД, миграции, обслуживание |
| [API.md](Documentation/API.md) | REST API, аутентификация, примеры |
| [SECURITY.md](Documentation/SECURITY.md) | меры безопасности и рекомендации по эксплуатации |
| [BACKUP.md](Documentation/BACKUP.md) | резервное копирование, восстановление, перенос на другой сервер |
| [TROUBLESHOOTING.md](Documentation/TROUBLESHOOTING.md) | диагностика и решение проблем |

## Сборка и тесты

```bash
cd ITAM
(cd Frontend && npm ci && npm run build)
dotnet test ITAM.slnx                       # интеграционным тестам нужен PostgreSQL: ITAM_TEST_PG="Host=...;Username=...;Password=..."
pwsh Installer/build-installer.ps1           # Windows: ITAM-Setup.exe в Installer/Output
```

CI (`.github/workflows/itam.yml`): сборка фронтенда, юнит- и интеграционные тесты на PostgreSQL 16, проверка актуальности
`migrations.sql`, сборка установщика на Windows, тихая установка со встроенным PostgreSQL, проверка службы, веб-интерфейса,
входа и резервного копирования. Готовый `ITAM-Setup.exe` — в артефактах сборки.
