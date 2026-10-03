# 🛠 Первая помощь сисадмина — SysAdmin First Response Toolkit v2.0

Локальный инструмент первичной диагностики Windows для системного администратора и Help Desk.

```
ПРОБЛЕМА → DIAGNOSTICS → EVIDENCE → CORRELATION → FINDING → RECOMMENDATION → REMEDIATION → RE-TEST → REPORT
```

Администратор не выбирает «какую команду запустить» — он выбирает **что случилось** («Нет интернета», «Не работает принтер»…).
Программа сама выполняет нужные проверки, сопоставляет результаты, называет **вероятную** причину с уровнем уверенности,
предлагает объяснимые действия с уровнем риска, выполняет их **только после подтверждения**, перепроверяет результат и документирует всё в обращении (CASE) и отчёте.

---

## Возможности

| Область | Что проверяется |
|---|---|
| 🌐 **Сеть** | адаптеры, IPv4/IPv6, DHCP/APIPA, шлюз (ping + ARP), Интернет по IP (ICMP + TCP 443/53), DNS, HTTP-проверка (NCSI, captive portal), прокси (WinINET/PAC), маршруты (default route, конфликт VPN), TCP (retransmits), UDP; **этап отказа** |
| 🌐 **DNS** | служба Dnscache, настроенные серверы, прямые UDP-запросы к каждому серверу (мимо кэша), несколько внешних имён, эталонный DNS, суффикс, кэш; для домена — имя домена, `_ldap._tcp.dc._msdcs`, `_kerberos._tcp`, DNS контроллера, **публичный DNS на доменном ПК** |
| 📡 **Wi-Fi** | WlanSvc, SSID, BSSID, сигнал, канал, тип радио, аутентификация, скорости приёма/передачи, IP, шлюз, автоматическое определение этапа отказа (DHCP → шлюз → Интернет) |
| 🏢 **Домен / AD** | членство, обнаружение DC (`nltest /dsgetdc`), Logon Server (вход по кэшу), Secure Channel (`nltest /sc_query`), порты DC (53/88/389/445 + RPC/LDAPS/GC/kpasswd), время (`w32tm /stripchart`), групповые политики (`gpresult` + журнал GroupPolicy), билеты Kerberos (`klist`), SYSVOL, неудачные входы/блокировки (Security, только admin) |
| 🖥 **RDP** | TermService, разрешение RDP, NLA, порт, прослушивание, правила брандмауэра; проверка доступности цели (ping + TCP). Настройки RDP **не изменяются** |
| 🖨 **Принтеры** | Spooler, установленные принтеры, принтер по умолчанию, ошибки/«автономно», очередь, доступность сетевых принтеров (TCP 9100) |
| 🔄 **Windows Update** | wuauserv/BITS/CryptSvc/TrustedInstaller/msiserver, история и коды ошибок с расшифровкой, дата последнего обновления, журнал WindowsUpdateClient, ожидание перезагрузки, WSUS |
| 💾 **Диски** | заполненность системного и других дисков, временные файлы, состояние физических дисков, активность/очередь/задержка, ошибки disk/Ntfs в журнале |
| 🛠 **Здоровье Windows** | DISM CheckHealth (admin), результаты SFC в CBS.log, ожидание перезагрузки, Kernel-Power 41/BugCheck; по запросу — `sfc /verifyonly`, DISM ScanHealth |
| 🛡 **Безопасность** | Defender (real-time, сигнатуры), сторонние антивирусы (Security Center), брандмауэр по профилям, UAC |
| 🐌 **Производительность** | CPU, RAM, топ процессов, uptime, диск C:, автозагрузка, автоматические службы, время загрузки ОС; **простая сводка** без утверждений о причинности |
| 📋 **Журналы событий** | System / Application / WindowsUpdate / Security (admin) — **группировка** одинаковых ошибок, отметка серьёзных (Kernel-Power, диск, WHEA, падения служб) и типичного «шума» (DCOM 10016) |
| ⚙ **Службы** | важные системные службы, автоматические не запущенные, указанная служба |
| 📦 **Программа** | файл/версия, права доступа, процесс, сбои в журнале (модуль сбоя), сеть, связанные службы; пробный запуск — **только с явного разрешения** |
| 🗂 **Сетевой ресурс** | разбор UNC, служба «Рабочая станция», DNS, ping, SMB 445, доступ к папке |

### Сценарии («Что произошло?»)
Нет интернета · Компьютер тормозит · Не могу войти · RDP · Принтер · Windows Update · Диск · Ошибки Windows · Wi-Fi · DNS · Домен ·
Не работает программа · Сетевой ресурс · Служба · Долго загружается · Безопасность · **🚑 FIRST RESPONSE** (1–3 мин) · **🩺 Полная диагностика**.

**Режим Help Desk**: «Что говорит пользователь?» — 7 больших кнопок; «Другое» запускает общую диагностику.

### Correlation Engine
~45 правил анализируют результаты **вместе**. Примеры:

| Факты | Вывод |
|---|---|
| Шлюз ✓, 8.8.8.8 ✗, DNS ✗ | 🔴 Вероятная проблема с доступом во внешнюю сеть |
| Шлюз ✓, 8.8.8.8 ✓, DNS ✗ | 🔴 Проблема DNS (уверенность высокая, если эталонный DNS отвечает) |
| Диск C: 98 % + ошибки WU (0x80070070) | 🔴 Недостаточно места мешает Windows Update |
| Доменный ПК + DNS 8.8.8.8 + нет SRV | 🔴 Доменный компьютер использует внешний DNS |
| Secure Channel ✗, DC доступен | ⛔ Нарушено доверие с доменом |
| DISM Repairable + 0x80073712 | 🔴 Повреждение хранилища компонентов мешает обновлениям |

Каждая находка: **серьёзность**, **уверенность** (высокая/средняя/низкая — никогда «точно»), **основания** (✓/✗), вероятная причина, рекомендация, действия, нужна ли перезагрузка.
Более общие находки подавляются более конкретными (например, «нет адаптера» скрывает «нет DNS»).

### Remediation Engine
`Finding → Recommendation → Remediation → Confirmation → UAC → Action → Re-test → Feedback`

| Risk | Примеры |
|---|---|
| LOW | очистить кэш DNS, проверки DISM/SFC (только чтение), обновить сигнатуры, открыть инструмент |
| MEDIUM | перезапуск служб, обновить IP, перерегистрировать DNS, очистить очередь печати, удалить temp-файлы старше 7 дней, синхронизация времени, gpupdate, CHKDSK /scan |
| HIGH | DISM RestoreHealth, SFC /scannow, CHKDSK /f, CHKDSK /r, сброс кэша Windows Update (с резервной копией .bak), сброс Winsock |

Перед каждым действием — диалог: что будет сделано, что изменится, команда, обратимость, UAC, перезагрузка. Для HIGH — «⚠ Операция может изменить состояние системы». После выполнения — автоматическая повторная проверка («🟢 Проблема устранена» / «🟡 Проблема сохраняется») и вопрос «Проблема решена? Да / Нет / Не знаю» с записью в CASE.

### CASE, Timeline, отчёты
* **CASE #ГГГГММДД-NNNN** — компьютер, пользователь, проблема, хронология, результаты, исправления, отзывы. Хранится в `%LOCALAPPDATA%\FirstAidAdmin\Cases`.
* **HTML-отчёт**: общие сведения → итог диагностики (🟢/🟡/🔴, критические находки, рекомендации) → состояние системы → сеть → DNS → Wi-Fi → домен → RDP → принтеры → Windows Update → безопасность → хранилище → производительность → журналы → находки → рекомендации → история исправлений → хронология. Самодостаточный, печатается в PDF из браузера.
* **JSON-отчёт** с полной структурой.
* **📦 Пакет диагностики** `Case-ГГГГММДД-NNNN.zip`: `report.html, report.json, system.txt, network.txt, event-errors.txt, services.txt, commands.log, metadata.json` — с маскированием (пользователь/компьютер/домен/IP по настройке, секреты — всегда).
* **PDF** — planned (интерфейс `IPdfExporter`).

---

## Архитектура

```
FirstAidAdmin/
├── FirstAidAdmin.sln
├── source/
│   ├── FirstAidAdmin.Core            модели, интерфейсы, Correlation/Severity engine, сценарии, CASE, KB, плагины, анализ
│   ├── FirstAidAdmin.Logging         структурированный JSON-лог, журнал выполненных команд
│   ├── FirstAidAdmin.Infrastructure  запуск команд/PowerShell, пробы ОС (.NET API, реестр, службы, EventLog), DNS-клиент, UAC
│   ├── FirstAidAdmin.Diagnostics     модули: Network, Dns, WiFi, Domain, ActiveDirectory, Rdp, Printer, WindowsUpdate,
│   │                                 Storage, WindowsHealth, Security, Performance, EventLog, Services, Application, NetworkShare
│   ├── FirstAidAdmin.Remediation     каталог действий, исполнитель allow-list, Remediation Engine
│   ├── FirstAidAdmin.Reporting       HTML/JSON/TXT, Redactor, ZIP-пакет, PDF (planned)
│   ├── FirstAidAdmin.Application     DI-композиция, DiagnosticSession (оркестратор), CLI
│   ├── FirstAidAdmin.App             WPF/MVVM UI → FirstAidAdmin.exe (GUI + CLI)
│   └── FirstAidAdmin.Helper          FirstAidAdmin.Helper.exe — повышенные операции через UAC
├── tests/  FirstAidAdmin.Tests (unit), FirstAidAdmin.IntegrationTests
├── KnowledgeBase/  *.json — локальная база типовых проблем (встроена в exe, папка рядом с exe переопределяет)
├── docs/
└── publish/  FirstAidAdmin.exe, FirstAidAdmin.Helper.exe
```

* C# 12, **.NET 8 LTS**, **WPF + MVVM** (CommunityToolkit.Mvvm), **Dependency Injection**, `async/await`, `CancellationToken`, структурированное логирование.
* Единый интерфейс модуля `IDiagnosticModule { Id; Name; RunAsync(DiagnosticContext, CancellationToken) }` и единая модель `DiagnosticResult`
  (`Id, Name, Category, Status, Severity, Summary, Details, Evidence, Recommendation, Remediation, Duration, RequiresAdmin` + вложенные проверки).
* Статусы `OK / WARNING / ERROR / CRITICAL / INFO / SKIPPED`; Severity `Low / Medium / High / Critical`.
* Весь доступ к ОС — через интерфейсы (`INetworkProbe`, `ICommandRunner`, `IPowerShellRunner`, `IServiceProbe`, `IEventLogProbe`, `IRegistryProbe`, …), поэтому анализаторы тестируются без Windows.
* Языконезависимые источники данных: .NET API, CIM/PowerShell JSON, коды возврата, собственный DNS-клиент; разбор `netsh`/`arp` поддерживает русскую и английскую Windows.
* `IAnalysisProvider`: `LocalRuleEngine` (по умолчанию), `OptionalAIProvider` (заглушка, выключена, сетевых вызовов нет).
* **Плагины**: `Plugins\*.dll`, классы с `[DiagnosticPlugin]`, реализующие `IDiagnosticModule` (включаются в настройках).
* **Remote diagnostics (архитектура)**: `IDiagnosticTarget` — сейчас только `LocalDiagnosticTarget`; будущий агент с аутентификацией подключается без изменения ядра. Подробнее — `docs/ARCHITECTURE.md`.

---

## Требования
* Windows 10 / 11 / Server 2016+ (x64).
* Установка .NET **не требуется** (self-contained single-file).
* Для сборки — .NET 8 SDK.

## Запуск
```powershell
publish\FirstAidAdmin.exe            # GUI
```
При старте выполняется только быстрый сбор: ОС, имя ПК, пользователь, права, базовое состояние сети. Остальное — по запросу.

### CLI (то же диагностическое ядро)
```powershell
FirstAidAdmin.exe /diagnose                      # полная диагностика
FirstAidAdmin.exe /firstresponse                 # быстрая первичная картина
FirstAidAdmin.exe /network                       # нет интернета
FirstAidAdmin.exe /report [/out:C:\Reports]      # сохранить report.html + report.json
FirstAidAdmin.exe /case:"Нет интернета" /network # обращение + диагностика + отчёт + ZIP
FirstAidAdmin.exe /rdp:192.168.1.10 /port:3389
FirstAidAdmin.exe /app:"1C" /exe:"C:\Program Files\1cv8\common\1cestart.exe"
FirstAidAdmin.exe /share:\\fs01\docs
FirstAidAdmin.exe /dns /json                     # JSON в stdout
FirstAidAdmin.exe /help
```
Коды возврата: `0` норма, `1` предупреждения, `2` проблемы, `3` ошибка параметров, `4` внутренняя ошибка.
**CLI ничего не исправляет** — только диагностика и отчёты.

## Права администратора
* `FirstAidAdmin.exe` работает с правами текущего пользователя (`asInvoker`) — **principle of least privilege**.
* Обычные проверки выполняются без повышения. Проверки, которым нужны права (DISM, SFC, журнал Security), помечаются `SKIPPED (admin)` и предлагают запуск через UAC.
* Повышенные операции: `User mode → запрос операции → Windows UAC → FirstAidAdmin.Helper.exe (requireAdministrator) → одна операция из allow-list → результат (JSON) → re-test`.
* Helper принимает только идентификатор операции из каталога и проверенный параметр (службы — из белого списка, диск — `X:`). Произвольные команды/скрипты не принимаются.
* Если программа уже запущена от администратора, операции выполняются без повторного запроса UAC.

## Безопасность
Программа **не содержит и не будет содержать**: извлечение паролей/учётных данных, кражу токенов, обход UAC/ACL/AV, persistence, скрытый удалённый доступ, backdoor, обход доменных политик.
* Никаких исправлений без явного подтверждения; HIGH-действия — с отдельным предупреждением.
* Телеметрия **выключена и не реализована**; данные никуда не отправляются. Работает полностью **offline**.
* Пакет диагностики не содержит паролей, cookies, токенов, документов, почты; перед экспортом выполняется маскирование.
* Логи: `%LOCALAPPDATA%\FirstAidAdmin\Logs\app-YYYYMMDD.log` (JSON lines).

## Сборка
```powershell
cd FirstAidAdmin
dotnet publish -c Release -r win-x64 --self-contained true
# → publish\FirstAidAdmin.exe, publish\FirstAidAdmin.Helper.exe, publish\KnowledgeBase\
```
Сборка также выполняется в GitHub Actions (`.github/workflows/firstaidadmin.yml`, windows-latest); артефакт **FirstAidAdmin-win-x64** содержит готовую папку `publish`.

## Тестирование
```powershell
dotnet test FirstAidAdmin.sln
```
* **Unit (160)**: парсеры (netsh en/ru, nltest, w32tm, route, arp, klist, CBS, DNS wire), анализаторы Network/DNS/Wi-Fi/Disk/Domain/RDP/Performance/Event/Printer/WU/Health/Security/Services/Application/Share, Correlation Engine, Severity Engine, Report Generator (порядок разделов, экранирование, JSON), Redactor, ZIP-пакет, Remediation (риски, allow-list, подтверждение, UAC-путь, re-test), CASE, настройки, KB, сценарии, CLI, плагины, admin detection.
* **Integration (8)**: сквозной сценарий «Нет интернета → находка DNS → flush DNS → re-test → Resolved → timeline → отчёт → ZIP»; полная диагностика; RDP; отмена; CLI; реальные пробы ОС (FirstResponse ≤ 3 мин, все сценарии без исключений).
* **CI на Windows**: тесты на реальной Windows, публикация, запуск EXE без .NET в PATH, CLI-сценарии, ZIP, helper (allow-list), запуск от обычного пользователя, GUI smoke-test (рендер всех экранов в PNG). См. `docs/TESTING.md`.

## Ограничения
* Интерфейс на русском (настройка языка подготовлена, английская локализация — в следующей версии).
* Проверка UAC-диалога вручную: в CI повышение не интерактивно (runner уже администратор), helper проверяется прямым вызовом.
* Wi-Fi разбирается из `netsh wlan` (русская/английская локаль); на других локалях часть полей может быть пустой.
* SFC/DISM ScanHealth длительные (5–40 мин) и не входят в полную диагностику — запускаются отдельно.
* Время загрузки ОС и журнал Security доступны только администратору.
* PDF-экспорт — planned (используйте печать HTML в PDF).
* Удалённая диагностика не реализована (только архитектура).

## Что можно сделать в версии 3.0
* Remote Diagnostic Agent с взаимной аутентификацией (mTLS/Kerberos) и аудитом.
* Опциональный AI-ассистент (локальная модель или корпоративный endpoint) через `IAnalysisProvider`.
* Нативный PDF-экспорт, английская локализация.
* Статистика эффективности remediation по отзывам в CASE.
* Интеграция с ITSM (создание тикета из CASE), подписанные плагины, Intune/SCCM-развёртывание (MSIX).
* Wi-Fi через Native WiFi API, SMART через Storage Reliability Counters, сетевая трассировка (pktmon).
