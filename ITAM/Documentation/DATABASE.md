# База данных ITAM

PostgreSQL 14+ (встроенный в установщик — 16). Схема создаётся миграциями EF Core; при запуске сервер применяет новые
миграции автоматически (`Itam:AutoMigrate`, по умолчанию `true`) и синхронизирует справочник прав и встроенные роли.

## Подключение

Строка подключения — `C:\ProgramData\ITAM\config\itam.json` → `ConnectionStrings:Default`, либо переменная окружения
`ITAM_ConnectionStrings__Default`. Установщик создаёт роль `itam` (владелец базы `itam`, без прав суперпользователя);
расширение `pg_trgm` создаётся суперпользователем при установке.

## Общие принципы схемы

* Первичные ключи — UUID v7 (упорядочены по времени, удобны для индексов).
* `OrganizationId` во всех бизнес-таблицах — готовность к нескольким организациям; глобальный фильтр запросов.
* **Мягкое удаление** (`IsDeleted`, `DeletedAt`, `DeletedById`) и **архивирование** (`IsArchived`) вместо физического
  удаления для объектов с историей.
* Поля аудита `CreatedAt/CreatedById/UpdatedAt/UpdatedById`.
* Оптимистичная блокировка: системная колонка PostgreSQL `xmin` как версия строки (`Assets`, `Employees`, `Licenses`,
  `StockBalances`, …) — параллельное изменение одной записи даёт ошибку `CONCURRENT_MODIFICATION`.
* Даты-время в `timestamp with time zone` (UTC); даты без времени — `date`.
* Дополнительные поля и снимки — `jsonb` (`CustomFields`, `EmployeeSnapshot`, `AssetSnapshot`, `Delta`, `Data`).
* Полнотекстовый поиск — индексы GIN `pg_trgm` по ФИО, инвентарному номеру, названию, серийному номеру.

## Таблицы

| Группа | Таблицы |
|---|---|
| Организация | `Organizations`, `Regions`, `Locations` (иерархия, `FullPath`), `Departments` (иерархия), `Positions` |
| Сотрудники | `Employees`, `EmployeeStatuses`, `EmployeeOrgHistory` (периоды работы в подразделениях/должностях) |
| Активы | `AssetCategories`, `AssetTypes`, `AssetStatuses` (с системной категорией `Kind`), `Manufacturers`, `Suppliers`, `Contracts`, `Assets`, `CustomFieldDefinitions`, `NumberSequences` |
| История и операции | `AssetEvents` (поток событий актива), `OperationBatches` (акты), `Assignments`, `AssetReturns`, `AssetTransfers`, `AssetStatusChanges` |
| Ремонты | `RepairStatuses`, `Repairs`, `RepairStatusHistory` |
| ПО и доступы | `Software`, `LicenseTypes`, `Licenses`, `LicenseAssignments`, `AccessSystems`, `AccessLevels`, `EmployeeAccesses` |
| Чек-листы | `ChecklistTemplates`, `ChecklistTemplateItems`, `EmployeeChecklists`, `EmployeeChecklistItems` |
| Документы и файлы | `DocumentTemplates`, `DocumentTemplateVersions`, `GeneratedDocuments`, `StoredFiles` |
| Безопасность | `Users`, `Roles`, `Permissions`, `RolePermissions`, `UserRoles`, `UserRegions`, `UserSessions`, `ApiTokens`, `AuditLogs` |
| Система | `Settings` (jsonb по группам), `Notifications`, `NotificationReads`, `NotificationDeliveries`, `Backups`, `ImportJobs` |
| Инвентаризация, склад | `InventoryCampaigns`, `InventoryCampaignItems`, `StockItems`, `StockBalances`, `StockMovements` |

ER-диаграмма основных сущностей — в [ARCHITECTURE.md](ARCHITECTURE.md#4-database-erd-core).

## Временная модель (история активов)

`AssetEvents` — журнал событий, который только дополняется:

| Колонка | Смысл |
|---|---|
| `EffectiveAt` | фактическая дата события (бизнес-время) |
| `RecordedAt`, `RecordedById` | когда и кем внесено |
| `Sequence` | порядковый номер из последовательности `asset_event_seq` (порядок событий с одинаковой датой) |
| `EventType`, `AffectsState` | тип события; влияет ли на состояние (выдача, возврат, статус…) |
| `Delta` (jsonb) | изменение состояния: статус, сотрудник, подразделение, регион, локация, ожидаемый держатель |
| `StatusId`, `EmployeeId`, `DepartmentId`, `RegionId`, `LocationId` | состояние после события (пересчитывается при вставке задним числом) |
| `Data` (jsonb), `Description` | названия на момент события (откуда/куда, ФИО), описание |
| `IsCancelled`, `CancelledAt`, `CancelledById`, `CancelReason` | отмена события вместе с операцией |
| `OperationType`, `OperationId`, `BatchId` | связь с операцией и актом |

Признак «задним числом» вычисляется сравнением `EffectiveAt` и `RecordedAt` с допуском из настроек безопасности.

Текущее состояние в `Assets` (`StatusId`, `EmployeeId`, `DepartmentId`, `RegionId`, `LocationId`) — проекция последнего
события; при каждой операции цепочка событий проверяется и проекция пересчитывается в одной транзакции.

## Ограничения целостности

| Ограничение | Назначение |
|---|---|
| `UX_Assignments_OneOpenPerAsset` — уникальный частичный индекс `Assignments(AssetId) WHERE EffectiveTo IS NULL AND NOT IsCancelled` | у актива не может быть двух открытых выдач даже при одновременных запросах |
| уникальность `(OrganizationId, InventoryNumber)` для активов, номеров актов, ремонтов, документов, инвентаризаций | номера не повторяются |
| уникальность `(OrganizationId, EmployeeNumber)` среди неудалённых сотрудников, логинов пользователей | |
| `(CampaignId, AssetId)`, `(StockItemId, LocationId)`, `(TemplateId, VersionNumber)` | |
| триггеры `trg_auditlogs_no_update`, `trg_auditlogs_no_truncate` | `AuditLogs` нельзя изменить, удалить или очистить |
| внешние ключи с `RESTRICT` для справочников | справочник, на который есть ссылки, нельзя удалить (только архивировать) |

## Миграции

* Исходники: `Backend/ITAM.Infrastructure/Persistence/Migrations`.
* Идемпотентный SQL всех миграций: `Database/migrations.sql` (CI проверяет, что он актуален) — для применения DBA
  вручную: `psql -U itam -d itam -f migrations.sql`.
* Применить из командной строки: `ITAM.Server.exe migrate`.
* Создать новую миграцию (разработка):
  ```bash
  cd ITAM/Backend
  dotnet ef migrations add <Name> -p ITAM.Infrastructure -s ITAM.Api
  dotnet ef migrations script --idempotent -p ITAM.Infrastructure -s ITAM.Api -o ../Database/migrations.sql
  ```

## Обслуживание

* Autovacuum PostgreSQL достаточно; для больших `AuditLogs` (миллионы строк) периодически выполняйте `VACUUM ANALYZE`.
* Размер базы: `SELECT pg_size_pretty(pg_database_size('itam'));`
* Самые большие таблицы:
  ```sql
  SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) FROM pg_catalog.pg_statio_user_tables
  ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;
  ```
* Резервное копирование — средствами ITAM (база + файлы + ключи шифрования одним архивом), см. [BACKUP.md](BACKUP.md).
  Отдельный `pg_dump` не содержит документов и ключей шифрования лицензий.
* Подключение к встроенному PostgreSQL: `"C:\Program Files\ITAM\pgsql\bin\psql.exe" -h localhost -p 5433 -U postgres -d itam`.

## Отчётность из внешних систем

Для Power BI/Excel рекомендуется REST API с API-токеном (учитывает права и регионы). При прямом подключении к БД создайте
отдельную роль только для чтения:

```sql
CREATE ROLE itam_report LOGIN PASSWORD '***';
GRANT CONNECT ON DATABASE itam TO itam_report;
GRANT USAGE ON SCHEMA public TO itam_report;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO itam_report;
REVOKE SELECT ON "Users", "UserSessions", "ApiTokens", "Settings" FROM itam_report;
```
