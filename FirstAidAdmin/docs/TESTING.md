# Тестирование

## Автоматические тесты
```powershell
cd FirstAidAdmin
dotnet test FirstAidAdmin.sln
```
* `tests/FirstAidAdmin.Tests` — 160 unit-тестов (fake-пробы ОС, работают на любой ОС).
* `tests/FirstAidAdmin.IntegrationTests` — 8 тестов: сквозной workflow с реальным DI-графом и реальные пробы текущей ОС.

## CI на Windows (`.github/workflows/firstaidadmin.yml`)
| Шаг | Что проверяет |
|---|---|
| Build / Unit / Integration | сборка Release, все тесты на реальной Windows (integration — с реальными probes, правами администратора runner) |
| Publish | `dotnet publish -c Release -r win-x64 --self-contained true` → `publish\FirstAidAdmin.exe`, `FirstAidAdmin.Helper.exe` |
| Run EXE without .NET | запуск с удалённым из PATH dotnet и несуществующим `DOTNET_ROOT` |
| CLI | `/list`, `/firstresponse /report`, `/case /diagnose` (+ состав ZIP), `/dns /json` (валидный JSON), `/rdp`, `/app`, `/share`, `/health /sfc /dismscan` (SFC, DISM от администратора) |
| Helper | `--op flushdns` успешно; неизвестная операция отклоняется |
| Standard user | `/firstresponse /report` от созданной локальной учётной записи без прав администратора |
| GUI smoke | `--smoke-test`: открывает главную, Help Desk, RDP-сценарий (с запуском), CASE, настройки, тёмную тему; рендерит PNG |

Артефакты: `FirstAidAdmin-win-x64` (папка publish), `test-evidence` (trx, отчёты, ZIP, скриншоты, логи).

## Ручная проверка (чек-лист)
- [ ] Запуск EXE двойным щелчком без установленного .NET
- [ ] Обычный пользователь: проверки admin помечены SKIPPED (admin), DISM/SFC через кнопку → появляется UAC
- [ ] Отмена UAC → «Отменено пользователем в окне UAC», ничего не изменено
- [ ] Администратор: DISM CheckHealth выполняется без повторного UAC
- [ ] Нет интернета (отключить адаптер / указать неверный DNS) → корректный этап отказа и находка
- [ ] Flush DNS → re-test → вопрос «Проблема решена?» → запись в CASE
- [ ] Принтер: остановить Spooler → находка → «Перезапустить Print Spooler» (MEDIUM, подтверждение)
- [ ] HIGH-действие показывает «⚠ Операция может изменить состояние системы»
- [ ] Отчёт HTML открывается, разделы в правильном порядке; ZIP содержит 8 файлов, имя пользователя замаскировано
