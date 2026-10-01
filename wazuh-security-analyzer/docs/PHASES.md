# Отчёт по этапам разработки

Каждый этап проверен: импорты, синтаксис (Python 3.11 и 3.12), зависимости, тесты, запуск приложения.

## Phase 1–2 — Архитектура и структура проекта
COMPLETED
- **Files:** `app/core/*` (config, paths, logging, secrets, severity, errors), `pyproject.toml`, `requirements*.txt`, `config/default_config.yaml`, [ARCHITECTURE.md](ARCHITECTURE.md)
- **Features:** типизированная конфигурация (Pydantic) с deep-merge defaults+user; секреты только в Windows Credential Manager; 4 лога (application/errors/analysis/audit) с редактированием секретов.
- **Known limitations:** без keyring-бэкенда (headless Linux) ключи хранятся только в памяти сеанса.

## Phase 3 — Wazuh parsers
COMPLETED
- **Files:** `app/parsers/{base,registry,sources,wazuh_json,wazuh_jsonl,wazuh_csv,wazuh_xml,wazuh_text,cef,generic_log}.py`
- **Features:** определение формата по содержимому; потоковый JSON; ZIP/GZ без распаковки на диск (Zip Slip, zip-бомбы, лимиты); устойчивость к битым записям.
- **Tests:** `tests/unit/test_parsers.py`, `tests/unit/test_sources.py` (XXE, billion laughs, Zip Slip, ratio/size/entries limits).
- **Known limitations:** вложенные ZIP и TAR не обрабатываются (сообщается предупреждение).

## Phase 4 — Normalization
COMPLETED
- **Files:** `app/analyzers/normalizer.py`, `ioc_extractor.py`, `classifier.py`, `app/models/*`
- **Features:** sshd/PAM, Windows eventchannel, Sysmon (hashes), syscheck, vulnerability-detector (4.x и 4.8+), VirusTotal, web, CEF, плоские экспорты; дедупликация; IOC (IP/domain/URL/hash, defang).

## Phase 5 — Risk engine
COMPLETED
- **Files:** `app/analyzers/risk_engine.py`, `false_positive.py`, `explainer.py`
- **Features:** 13 настраиваемых факторов, пороги 0–19/20–39/40–59/60–79/80–100, объяснение каждого фактора, FP-анализ (сканеры, периодичность, еженедельность, разреженные попытки), формулировки без утверждений о взломе.

## Phase 6 — Correlation engine
COMPLETED
- **Files:** `app/correlation/{grouping,chains,incidents}.py`
- **Features:** группировка повторов; success-after-failures (скользящее окно); attack chains (kill-chain + LIS, якоря); кампании по source IP; инциденты с сохраняемыми статусами.

## Phase 7 — MITRE / CVE / IOC enrichment
COMPLETED
- **Files:** `app/intelligence/*`, `resources/knowledge/{mitre_techniques,wazuh_rules}.yaml`, `resources/ioc/local_ioc.csv`
- **Features:** маппинг MITRE только с evidence и confidence; NVD 2.0, CISA KEV (кэш для офлайна), VirusTotal, AbuseIPDB, OTX; async, кэш, валидация ответов; «Internet enrichment unavailable. Offline analysis completed.»
- **Known limitations:** NVD без ключа ограничен 5 запросами / 30 с (лимит `max_cve_lookups`).

## Phase 8 — AI engine
COMPLETED
- **Files:** `app/ai/*`, `app/privacy/sanitizer.py`
- **Features:** OpenAI, Anthropic, Ollama, OpenAI-compatible; системный промпт SOC-аналитика; строгая Pydantic-схема; repair-попытка; guardrails против выдуманных IOC/CVE/MITRE; Data Sanitization Layer с восстановлением плейсхолдеров.

## Phase 9 — GUI
COMPLETED
- **Files:** `app/ui/*`
- **Features:** тёмная SOC-тема, sidebar, Drag & Drop, dashboard с графиками, карточки алертов, инциденты с цепочкой, Hosts/Users/IOC/CVE, MITRE-матрица, Rule Intelligence, поиск, отчёты, настройки, onboarding; фоновые задачи с прогрессом «Analyzing… N / ~M» и отменой.

## Phase 10 — Reports
COMPLETED
- **Files:** `app/reports/*`, `resources/templates/report.html.j2`
- **Features:** PDF, HTML, DOCX, Excel, CSV (+events CSV), JSON; выбор разделов; защита от formula injection и XSS.

## Phase 11 — Demo datasets
COMPLETED
- **Files:** `sample_data/sample_{bruteforce,malware,powershell,cve,normal_activity}.json`, `sample_data/formats/*`, `scripts/generate_demo_data.py`
- **Features:** синтетические данные (RFC 5737 IP, вымышленные хосты/пользователи), сценарии: brute force → вход → curl|bash → useradd → C2; RDP brute force → encoded PowerShell → certutil → LSASS → C2 → schtasks; malware; CVE; внутренний сканер (FP); фоновый шум.

## Phase 12 — Tests
COMPLETED
- **Tests:** 183 теста (unit + integration + GUI offscreen + API + CLI). 100k алертов ≈ 60 с, 1M алертов ≈ 250 с (`WSA_TEST_1M=1`).
- Покрыто: parsers, risk scoring, correlation, IOC/CVE, anonymization, AI validation, recommendations, corrupted JSON, invalid CSV, huge ZIP, missing fields, unknown rule, offline mode, API timeout, AI unavailable.

## Phase 13 — PyInstaller build
COMPLETED
- **Files:** `WazuhSecurityAnalyzer.spec`, `build.ps1`, `build.sh`, `scripts/version_info.txt`, `resources/icons/app.ico`
- **Features:** `--onefile` (по умолчанию) или portable folder; без UPX; встроенный `--self-test` проверяется после сборки.
- **Verified:** сборка по тому же spec на Linux, self-test и запуск GUI собранного бинарника — успешно.

## Phase 14 — Audit
COMPLETED
- Нет `eval/exec/pickle/subprocess/shell`; YAML safe_load; defusedxml; TLS по умолчанию, отключение — с подтверждением.
- Исправлено по итогам аудита: одна «патологическая» запись больше не прерывает чтение файла; санитизация AI использует все хосты/пользователи анализа; архив, превысивший лимит, отклоняется целиком; ложное «not in CISA KEV» при незагруженном каталоге заменено на «Unknown»; относительные URL не считаются IOC.
- **Known limitations:** сборка `.exe` должна выполняться на Windows (`build.ps1`); вложенные архивы не распаковываются; онлайн-проверки доменов (DNS/TLS) отключены по умолчанию, т.к. обращаются к инфраструктуре атакующего.
