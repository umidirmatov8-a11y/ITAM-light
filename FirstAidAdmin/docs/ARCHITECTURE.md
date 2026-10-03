# Архитектура FirstAidAdmin 2.0

## Поток данных

```
UI (WPF/MVVM) ─┐                         ┌─ IConfirmationService (диалоги / CLI: всегда «нет»)
CLI ───────────┴─> DiagnosticSession ────┤
                     │                    └─ ICaseStore (CASE + Timeline, JSON)
                     ├─> DiagnosticRunner ──> IDiagnosticTarget ──> IDiagnosticModule × N
                     │         (таймауты, отмена, изоляция исключений, прогресс)
                     ├─> CorrelationEngine (ICorrelationRule × ~45) ──> Finding[]
                     ├─> RemediationEngine ──> confirm ──> IElevationService (UAC → Helper) / IOperationExecutor ──> re-test
                     └─> IAnalysisProvider (LocalRuleEngine) ──> DiagnosticReport ──> HTML / JSON / ZIP (Redactor)
```

## Слои
| Проект | Ответственность | Зависимости |
|---|---|---|
| Core | модели, интерфейсы, правила корреляции, сценарии, CASE, KB, плагины | только Logging.Abstractions |
| Logging | JSON-лог, CommandLog | Core |
| Infrastructure | процессы, PowerShell (`-EncodedCommand`), .NET-пробы, реестр, службы, EventLog, DNS wire, UAC | Core |
| Diagnostics | модули и парсеры (чистые функции) | Core |
| Remediation | каталог действий, allow-list executor, engine | Core |
| Reporting | генераторы отчётов, Redactor, пакет | Core, Remediation |
| Application | DI, DiagnosticSession, CLI | все выше |
| App | WPF | Application |
| Helper | повышенные операции | Remediation, Infrastructure |

## Добавление модуля
1. Класс `: DiagnosticModuleBase` (или `IDiagnosticModule`) в `Diagnostics/<Area>`.
2. Константы проверок в `CheckIds`.
3. Регистрация в `ServiceRegistration` и добавление в нужные сценарии `ScenarioCatalog`.
4. Правила в `CorrelationRules`, статья в `KnowledgeBase/*.json` (тест `EveryCorrelationRule_HasKnowledgeBaseEntry` проверяет это).

## Плагины
`Settings → Diagnostics → LoadPlugins = true`. DLL из `Plugins\` загружаются в отдельный `AssemblyLoadContext`; контракт (`FirstAidAdmin.Core`) разделяется с хостом.
Активируются только типы с `[DiagnosticPlugin]`. Плагин с тем же `Id` заменяет встроенный модуль. Загружайте только доверенные DLL.

## Remote diagnostics (подготовлено, не реализовано)
```
Admin PC → FirstAidAdmin → IDiagnosticTarget (RemoteAgentTarget) ⇄ Remote Diagnostic Agent → Target PC
```
Требования к будущей реализации: явная установка агента (без скрытой установки), взаимная аутентификация (mTLS или Kerberos),
авторизация по группе AD, выполнение **только** модулей и allow-list операций (никаких произвольных команд), журнал аудита на обеих сторонах.
Ядро (DiagnosticRunner) уже работает через `IDiagnosticTarget`, поэтому изменений модулей не потребуется.

## Optional AI
`IAnalysisProvider.AnalyzeAsync(DiagnosticReport)`. По умолчанию `LocalRuleEngine`. `OptionalAIProvider` — заглушка (IsAvailable=false),
сетевых вызовов не делает. Будущая реализация должна получать **уже замаскированный** отчёт и быть отключаемой; основная диагностика от неё не зависит.

## Телеметрия
Отсутствует. `AppSettings.Telemetry` всегда сохраняется как `false`.
