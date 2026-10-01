# Wazuh Security Analyzer

Windows desktop-приложение (`WazuhSecurityAnalyzer.exe`) — **Security Analysis Assistant** для алертов Wazuh.
Загружаете файлы с алертами → программа нормализует события, группирует повторы, коррелирует цепочки атак,
считает собственный risk score, объясняет каждое событие простым языком, отделяет факты от выводов,
оценивает вероятность false positive и даёт конкретные рекомендации (Immediate / Investigation / Remediation / Prevention).

* Работает **полностью офлайн** (по умолчанию). ONLINE-режим добавляет NVD, CISA KEV, VirusTotal, AbuseIPDB, OTX.
* AI-аналитик **опционален**: Ollama (локально), OpenAI, Anthropic, любой OpenAI-совместимый сервер.
  Данные для облачных AI всегда проходят Data Sanitization Layer.
* Не требует установленного Python: собирается в один `.exe` через PyInstaller.

Подробная архитектура: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Быстрый старт

```powershell
# Сборка .exe на Windows (Python 3.12 нужен только на машине сборки)
.\build.ps1              # -> dist\WazuhSecurityAnalyzer.exe
.\build.ps1 -OneDir      # -> dist\WazuhSecurityAnalyzer\ (портативная папка, быстрее стартует)

# Запуск из исходников
pip install -r requirements.txt
python main.py
```

При первом запуске появится onboarding: **Offline / Online / Configure AI**. Затем перетащите файлы
в окно (Drag & Drop) или нажмите **Load Demo Dataset**.

### Командная строка

```text
WazuhSecurityAnalyzer.exe                                  GUI
WazuhSecurityAnalyzer.exe alerts.json logs.zip             GUI + сразу анализ файлов
WazuhSecurityAnalyzer.exe --analyze C:\logs --report-dir C:\reports --formats pdf,html,xlsx [--online]
WazuhSecurityAnalyzer.exe --self-test                      проверка собранного exe на демо-данных
python main.py --api --port 8765                           локальный REST API (FastAPI, только 127.0.0.1, токен)
```

## Язык интерфейса (English / Русский)

Язык выбирается при первом запуске и в **Settings › General › Language / Язык**
(`ui.language: auto | en | ru` в `config.yaml`; `auto` — по языку Windows).

* На выбранном языке выводятся интерфейс, объяснения находок, причины ложных срабатываний, факторы риска,
  рекомендации, инциденты, Executive Summary и все отчёты (PDF со встроенным шрифтом DejaVu Sans с кириллицей).
* AI-аналитик получает инструкцию отвечать на выбранном языке.
* Описания правил Wazuh и названия техник MITRE остаются как в первоисточниках.
* Смена языка интерфейса применяется после перезапуска; тексты анализа — со следующего анализа.
* Переводы: `app/i18n/ru.py`, `resources/knowledge/playbooks.ru.yaml`, `resources/knowledge/wazuh_rules.ru.yaml`.
  `python scripts/i18n_keys.py` показывает непереведённые строки (то же проверяет тест).

## Поддерживаемые входные данные

| Формат | Примеры | Парсер |
|---|---|---|
| JSON Lines / NDJSON | `alerts.json` Wazuh, `*.jsonl`, `*.ndjson` | `wazuh_jsonl` |
| JSON | массив, pretty-printed объекты, экспорт OpenSearch/Indexer (`hits.hits[]._source`), Wazuh API (`data.affected_items`) | `wazuh_json` (потоковый) |
| CSV / TSV | экспорт Wazuh Dashboard / Discover (`rule.id`, `_source.agent.name`, …) | `wazuh_csv` |
| XML | XML-экспорт алертов, Windows Event XML | `wazuh_xml` (defusedxml) |
| Текст | классический `alerts.log` | `wazuh_alerts_log` |
| CEF | `*.cef`, syslog с CEF | `cef` |
| Прочие логи | syslog, auth.log | `generic_log` |
| Архивы | `*.zip`, `*.gz` (ротация Wazuh `alerts-01.json.gz`), папки, несколько файлов | безопасный стриминг |

Формат определяется **по содержимому** (первые 64 КБ), расширение — только подсказка.
Новые источники (ESET, Kaspersky, FortiGate, Sysmon, auditd…) добавляются подклассом `BaseParser`
и `register_parser()` — см. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#расширение).

## Что показывает программа

* **Dashboard** — Critical/High/Medium/Low/Info, хосты, пользователи, внешние IP, CVE, MITRE; timeline;
  top rules / hosts / source IPs / users / MITRE / CVE / IOC / повторяющиеся события; Executive Summary.
* **Alerts** — сгруппированные findings (147 попыток = одна карточка) и сырые события с пагинацией.
  Карточка: *What happened / Why is it dangerous / Possible attack / Context / MITRE ATT&CK (с confidence и
  evidence) / Evidence (факты) / Reasoning (факторы риска) / False positive analysis / Recommended actions*.
* **Incidents** — `INC-2026-0017`: цепочки атак, brute-force кампании, malware, уязвимости; статусы
  `NEW / INVESTIGATING / CONFIRMED / FALSE POSITIVE / RESOLVED` сохраняются между запусками.
* **Hosts, Users, IOC, CVE, MITRE ATT&CK (матрица), Rule Intelligence, Reports, Settings**, глобальный поиск
  (IP, user, host, rule ID, CVE, hash, domain, MITRE ID).

### Пример (демо-данные)

```text
INC-2026-0004  CRITICAL  Possible attack chain on web-01   [Potential compromise]
  Credential attack (failed logins)  ↓  Initial Access (successful login)  ↓  Execution
  ↓  Persistence (account change)  ↓  Command and Control
  Possible scenario: Credential Access (brute force) → Initial Access → Execution → Persistence → Command & Control

INC-2026-0001  LOW  Repeated authentication failures from 10.10.5.5   [Likely benign / possible false positive]
  Why this may be a false positive: internal source; repeats every 1h; at most 2 failures per window;
  no successful login; no follow-up activity.
```

## Risk scoring

`Risk = Wazuh level + asset criticality + frequency + external source + brute-force burst + successful auth
after failures + IOC reputation + CVE (CVSS, CISA KEV) + MITRE tactic + correlation + behaviour − FP dampening`

| Score | Severity |
|---|---|
| 0–19 | Informational |
| 20–39 | Low |
| 40–59 | Medium |
| 60–79 | High |
| 80–100 | Critical |

Все веса и пороги — в `config.yaml` (`risk_weights`, `risk_thresholds`) или Settings › Risk model.
Wazuh level 12 сам по себе **не** даёт Critical. Каждый фактор показан в карточке с объяснением.

## Конфигурация и секреты

* Значения по умолчанию: `config/default_config.yaml`; пользовательские: `%LOCALAPPDATA%\WazuhSecurityAnalyzer\config.yaml`.
* API-ключи (VirusTotal, AbuseIPDB, OTX, NVD, OpenAI, Anthropic) хранятся **только** в Windows Credential Manager
  (через `keyring`). Ключи, случайно добавленные в YAML, игнорируются и никогда не записываются.
* Логи: `%LOCALAPPDATA%\WazuhSecurityAnalyzer\logs\application.log, errors.log, analysis.log, audit.log`.
* `WSA_HOME` переопределяет каталог данных (портативный режим).
* `storage.state_database_url` позволяет хранить статусы инцидентов и TI-кэш в PostgreSQL.

## Безопасность

* Нет `eval`/`exec`/`pickle`/shell-вызовов. YAML — только `safe_load`. XML — `defusedxml` (DTD запрещены).
* ZIP/GZ никогда не распаковываются на диск: Zip Slip невозможен, подозрительные пути отклоняются;
  лимиты на размер файла, общий распакованный объём, число записей и коэффициент сжатия (zip-бомбы)
  применяются к **фактически** прочитанным байтам.
* Сетевые запросы: таймауты, TLS verification, лимит размера ответа, без редиректов, Pydantic-валидация ответов.
* Внешним сервисам уходят только публичные индикаторы. Перед отправкой в облачный AI данные проходят
  Data Sanitization Layer (`[USER_001]`, `[INTERNAL_IP_001]`, `[HOST_001]`, `[USER_EMAIL_001]`, секреты → `[REDACTED_SECRET]`).
* Защита экспортов от CSV/Excel formula injection; HTML-отчёты экранируются (Jinja2 autoescape).
* Audit log: запуск анализа, TI-запросы, AI-запросы (провайдер, модель, факт анонимизации — без содержимого), экспорт.

## Тесты

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q            # всё, включая 100k alerts и GUI
python -m pytest -q -m "not slow"                         # быстрый прогон
WSA_TEST_1M=1 python -m pytest -q -k 1m -s                # 1 000 000 алертов
```

## Структура

```text
wazuh-security-analyzer/
  app/
    core/            config, paths, logging, secrets (keyring), severity
    parsers/         JSON/JSONL/CSV/XML/alerts.log/CEF/generic + registry + safe ZIP/GZ sources
    analyzers/       normalizer, classifier, IOC/CVE extraction, risk engine, FP analysis, explainer, rule KB
    correlation/     grouping, attack chains, incidents
    intelligence/    MITRE catalog/mapping, NVD, CISA KEV, VirusTotal, AbuseIPDB, OTX, local IOC, enrichment
    ai/              AIProvider (OpenAI, Anthropic, Ollama, OpenAI-compatible), prompts, schemas, engine
    privacy/         Data Sanitization Layer
    recommendations/ playbook-based recommendations
    reports/         PDF, HTML, DOCX, Excel, CSV, JSON + executive summary
    database/        per-analysis SQLite workspace, state DB (SQLite/PostgreSQL)
    services/        pipeline, session, audit
    ui/              PySide6 GUI (dashboard, alerts, incidents, …)
    api/             optional FastAPI server
  resources/         knowledge bases (MITRE, Wazuh rules, playbooks), templates, icons, local IOC list
  config/            default_config.yaml
  sample_data/       synthetic demo dataset (RFC 5737 IPs, fictitious hosts/users)
  scripts/           demo/large dataset generators, version info
  tests/             unit + integration
  main.py  build.ps1  build.sh  WazuhSecurityAnalyzer.spec  pyproject.toml  requirements.txt
```
