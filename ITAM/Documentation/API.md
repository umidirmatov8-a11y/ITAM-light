# REST API ITAM

Базовый адрес: `http://СЕРВЕР:8080/api`. Формат — JSON (`camelCase`, перечисления строками, даты ISO 8601 в UTC,
например `2026-10-01T05:00:00Z`; даты без времени — `2026-10-01`). Интерактивная документация и схема OpenAPI:
`/swagger` и `/swagger/v1/swagger.json` (отключается параметром `Server:EnableSwagger = false` в `itam.json`; сами методы API в любом случае требуют авторизации).

## Аутентификация

### Сессия (браузер)

```
POST /api/auth/login        {"userName":"admin","password":"..."}
```
Ответ устанавливает cookie `itam.sid` (HttpOnly) и `XSRF-TOKEN`. Для всех изменяющих запросов (POST/PUT/DELETE)
передавайте значение cookie `XSRF-TOKEN` в заголовке `X-XSRF-TOKEN`. `POST /api/auth/logout` — выход.

### API-токен (интеграции)

Создайте токен в **Профиль → API-токены** (или `POST /api/auth/tokens {"name":"PowerBI","expiresInDays":365}` — секрет
возвращается один раз в поле `secret`). Затем:

```
Authorization: Bearer itam_XXXXXXXX...
```

Токен действует с правами и регионами владельца; CSRF-заголовок не нужен. Отзыв: `DELETE /api/auth/tokens/{id}`.

## Ошибки

```json
{ "success": false, "error": { "code": "ASSET_ALREADY_ASSIGNED", "message": "Актив уже выдан другому сотруднику", "details": { } } }
```

| HTTP | Коды |
|---|---|
| 400 | `INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`, `CSRF_INVALID`, `BAD_REQUEST` и прочие бизнес-ошибки без отдельного статуса |
| 401 | `UNAUTHORIZED` |
| 403 | `FORBIDDEN` (в т.ч. объект вне регионов пользователя), `PASSWORD_CHANGE_REQUIRED` |
| 404 | `NOT_FOUND` |
| 409 | `ASSET_ALREADY_ASSIGNED`, `ASSET_NOT_ISSUABLE`, `ASSET_NOT_ASSIGNED`, `ASSET_IN_REPAIR`, `TEMPORAL_CONFLICT`, `BACKDATE_NOT_ALLOWED`, `OPERATION_DATE_IN_FUTURE`, `INVALID_STATUS_TRANSITION`, `REACTIVATION_FORBIDDEN`, `CONCURRENT_MODIFICATION`, `ASSET_CONCURRENT_MODIFICATION`, `DUPLICATE`, `HAS_DEPENDENCIES`, `LICENSE_NO_SEATS`, `LICENSE_EXPIRED`, `EMPLOYEE_HAS_OPEN_ITEMS` |
| 422 | `VALIDATION_FAILED` (в `details` — ошибки по полям), `PASSWORD_POLICY` |
| 429 | `RATE_LIMITED` |

## Списки, фильтры, сортировка

`GET /api/employees?page=1&pageSize=25&search=иван&sort=fullName&order=asc&regionId=...&departmentId=...&statusKind=Active`

```json
{ "items": [ ... ], "total": 128, "page": 1, "pageSize": 25 }
```
`pageSize` — до 500. Экспорт: тот же запрос на `/export?format=xlsx|csv` (`/api/employees/export`, `/api/assets/export`,
`/api/licenses/export`, `/api/repairs/export`, `/api/access/export`, `/api/audit/export`).

## Ресурсы

| Ресурс | Методы |
|---|---|
| Авторизация | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `GET /auth/csrf`, `POST /auth/change-password`, `PUT /auth/preferences`, `GET/POST /auth/tokens`, `DELETE /auth/tokens/{id}` |
| Первичная настройка | `GET /setup/status`, `POST /setup/complete` (только до завершения настройки) |
| Публичные | `GET /public/info`, `GET /public/assets/{id}` (краткая карточка для QR) |
| Главная, поиск | `GET /dashboard?regionId=`, `GET /search?q=` |
| Справочники | `GET /lookups` (описания), `GET/POST /lookups/{key}`, `GET /lookups/{key}/options`, `GET/PUT /lookups/{key}/{id}`, `POST /lookups/{key}/{id}/archive`, `.../restore`. Ключи: `regions`, `locations`, `departments`, `positions`, `employee-statuses`, `asset-categories`, `asset-types`, `asset-statuses`, `manufacturers`, `suppliers`, `repair-statuses`, `stock-items`, `software`, `license-types`, `access-systems`, `access-levels` |
| Сотрудники | `GET/POST /employees`, `GET/PUT/DELETE /employees/{id}`, `GET /employees/{id}/open-items`, `POST /employees/{id}/terminate`, `POST /employees/{id}/archive`, `POST /employees/bulk`, `GET /employees/{id}/timeline`, `.../org-history`, `.../assets`, `GET/POST /employees/{id}/checklists` |
| Активы | `GET/POST /assets`, `GET/PUT/DELETE /assets/{id}`, `GET /assets/{id}/history`, `.../timeline`, `.../state-at?at=`, `.../repairs`, `.../licenses`, `.../operations`, `.../audit`, `.../qr` (PNG), `.../barcode` (SVG), `POST /assets/labels` (PDF), `POST /assets/bulk-edit` |
| Операции | `POST /operations/issue`, `/return`, `/transfer`, `/status`; `GET /operations`, `GET /operations/{id}`, `POST /operations/{id}/cancel`, `PUT /operations/{id}/signature` |
| Ремонты | `GET/POST /repairs`, `GET/PUT /repairs/{id}`, `POST /repairs/{id}/status` |
| Лицензии | `GET/POST /licenses`, `GET /licenses/summary`, `GET/PUT /licenses/{id}`, `GET /licenses/{id}/key`, `POST .../archive`, `.../restore`, `GET/POST /licenses/{id}/assignments`, `POST /licenses/assignments/{id}/revoke`, `GET /licenses/by-employee/{id}`, `/by-software/{id}` |
| Доступы | `GET/POST /access`, `GET/PUT /access/{id}`, `POST /access/{id}/revoke`, `POST /access/{id}/review`, `POST /access/employee/{employeeId}/revoke-all` |
| Чек-листы | `GET /checklists`, `GET /checklists/{id}`, `PUT /checklists/{id}/items/{itemId}`, `POST /checklists/{id}/complete?force=`, `.../cancel`, `GET/POST /checklists/templates`, `GET/PUT /checklists/templates/{id}`, `POST .../archive` |
| Документы | `GET /documents`, `GET /documents/{id}`, `POST /documents/generate`, `GET /documents/{id}/download?format=docx|pdf|scan`, `PUT /documents/{id}/signature`, `POST /documents/{id}/scan`, `POST /documents/{id}/void` |
| Шаблоны | `GET/POST /templates`, `GET/PUT /templates/{id}`, `GET /templates/placeholders/{type}`, `POST /templates/{id}/versions` (multipart DOCX), `POST /templates/{id}/versions/{vid}/activate`, `GET .../download`, `POST /templates/{id}/archive` |
| Файлы | `GET/POST /files/{entityType}/{entityId}` (multipart), `GET/DELETE /files/{id}` |
| Дополнительные поля | `GET/POST /custom-fields`, `PUT /custom-fields/{id}`, `POST /custom-fields/{id}/archive` |
| Отчёты | `GET /reports`, `GET /reports/{key}?параметры`, `GET /reports/{key}/export?format=xlsx|csv|pdf` |
| Импорт | `GET /import/fields`, `GET /import/template/{entity}`, `POST /import/{entity}/upload`, `POST /import/{jobId}/validate`, `POST /import/{jobId}/commit` |
| Инвентаризация | `GET/POST /inventory`, `GET /inventory/{id}`, `GET /inventory/{id}/items`, `POST /inventory/{id}/scan`, `PUT /inventory/{id}/items/{itemId}`, `POST /inventory/{id}/complete`, `.../cancel` |
| Склад | `GET /stock/summary`, `GET /stock/balances`, `GET/POST /stock/movements` |
| Договоры | `GET/POST /contracts`, `GET/PUT/DELETE /contracts/{id}` |
| Уведомления | `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/read`, `POST /notifications/run` |
| Аудит | `GET /audit`, `GET /audit/actions`, `GET /audit/entity/{type}/{id}`, `GET /audit/export` |
| Администрирование | `GET/POST /admin/users`, `GET/PUT/DELETE /admin/users/{id}`, `POST .../reset-password`, `.../unlock`, `GET /admin/users/sessions`, `DELETE /admin/users/sessions/{id}`; `GET/POST /admin/roles`, `GET /admin/roles/permissions`, `PUT/DELETE /admin/roles/{id}`; `GET /admin/settings`, `PUT /admin/settings/{group}`, `POST /admin/settings/test-channel`, `POST /admin/settings/logo`; `GET/POST /admin/backups`, `GET .../{id}/download`, `DELETE /admin/backups/{id}`, `POST .../{id}/restore`, `POST /admin/backups/upload-restore`; `GET /admin/system` |
| Агенты | протокол агента `POST /agent/register`, `POST /agent/inventory`, `GET /agent/package`; администрирование `GET /agents`, `/agents/summary`, `/agents/{id}`, `/agents/{id}/software`, `/agents/by-asset/{assetId}`, `POST /agents/{id}/link|unlink|create-asset|ignore`, `DELETE /agents/{id}`, `GET /agents/software`, `GET|PUT /agents/settings`, `POST /agents/settings/regenerate-key`, `GET /agents/package` — подробно в [AGENT.md](AGENT.md) |
| Мониторинг | `GET /health` (без авторизации) |

## Примеры

### Выдача оборудования (в т.ч. задним числом)

```http
POST /api/operations/issue
X-XSRF-TOKEN: ...

{
  "employeeId": "01a1...",
  "assetIds": ["01a2...", "01a3..."],
  "effectiveAt": "2026-10-01T04:00:00Z",
  "locationId": null,
  "condition": "Good",
  "accessories": "Зарядное устройство, сумка",
  "expectedReturnDate": null,
  "comment": "Новый сотрудник",
  "generateDocument": true
}
```
```json
{ "batchId": "01a4...", "number": "ISS-000015", "type": "Issue", "assetCount": 2, "isBackdated": true, "documentId": "01a5..." }
```

Историческая выдача, уже завершившаяся: добавьте `"returnedAt": "2026-10-02T04:00:00Z"`.

### Возврат

```json
POST /api/operations/return
{ "employeeId": "01a1...", "items": [ { "assetId": "01a2...", "condition": "Fair", "damage": "царапина на крышке" } ],
  "locationId": "01a6...", "generateDocument": true }
```

### Состояние актива на дату

```
GET /api/assets/{id}/state-at?at=2026-10-02T12:00:00Z
→ { "at": "...", "statusName": "На складе", "kind": "InStock", "employeeId": null, "employeeName": null, ... }
```

### PowerShell

```powershell
$h = @{ Authorization = "Bearer itam_XXXX" }
Invoke-RestMethod "http://itam:8080/api/assets?pageSize=500&statusKind=Assigned" -Headers $h |
  Select-Object -ExpandProperty items | Export-Csv assigned.csv -Encoding UTF8 -NoTypeInformation
```

### curl с сессией

```bash
curl -c jar -b jar -H 'Content-Type: application/json' -d '{"userName":"admin","password":"..."}' http://itam:8080/api/auth/login
XSRF=$(awk '/XSRF-TOKEN/{print $7}' jar)
curl -c jar -b jar -H "X-XSRF-TOKEN: $XSRF" -H 'Content-Type: application/json' \
     -d '{"lastName":"Иванов","firstName":"Иван","regionId":"..."}' http://itam:8080/api/employees
```

## Ограничения

* Вход: 10 попыток в минуту с одного IP (`Security:LoginRateLimitPerMinute`), API: 1200 запросов в минуту на пользователя
  (`Security:ApiRateLimitPerMinute`).
* Размер загружаемого файла: до 200 МБ (резервные копии), документы и вложения — по белому списку расширений.
