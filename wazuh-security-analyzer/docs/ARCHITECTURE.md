# Архитектура Wazuh Security Analyzer

## Конвейер анализа

```text
Files / folders / ZIP / GZ
        │  SourceDiscovery: лимиты размера, коэффициента сжатия, Zip Slip, без распаковки на диск
        ▼
Format detection (по содержимому)  →  Parser (stream)  →  raw dict (форма Wazuh-алерта)
        ▼
Normalizer → NormalizedAlert (rule, agent, src/dst, user, process, command line, hashes, CVE, IOC…)
        ▼
Classifier (Rule KB → rule.groups → Windows/Sysmon IDs → keywords; эскалация по командной строке)
        ▼
GroupBuilder (повторы → AlertGroup)        ──►  SQLite workspace (alerts пакетами по 5000)
        ▼
Correlation: success-after-failures, attack chains (kill-chain stages, sliding window), campaigns
        ▼
MITRE mapping (wazuh_rule=high, rule_kb=medium, heuristic=medium/low, всегда с evidence)
        ▼
Threat Intelligence: local IOC list, CISA KEV (кэш), NVD, VirusTotal, AbuseIPDB, OTX (ONLINE)
        ▼
False-positive analysis  →  Risk engine (настраиваемые веса)  →  Explainer (факты vs выводы)
        ▼
Recommendations (playbooks с плейсхолдерами)  →  Incidents  →  Dashboard / Reports
        ▼
AI Analysis (по запросу): normalized context → Sanitizer → Provider → Pydantic → guardrails
```

## Ключевые решения

| Решение | Причина |
|---|---|
| PySide6 + QThreadPool | нативный Windows UI, анализ в фоне, GUI не зависает |
| SQLite workspace на каждый анализ | 1M алертов не держатся в памяти; GUI читает страницами (LIMIT/OFFSET, индексы) |
| SQLAlchemy | Core для быстрых пакетных вставок; state DB может быть PostgreSQL |
| Группы как единица анализа | скоринг/объяснения/рекомендации считаются для групп, а не для каждого из 1M событий |
| Потоковый JSON (`raw_decode`) | многогигабайтные JSON-массивы без загрузки целиком |
| Pydantic | конфигурация, ответы TI API, ответы AI — всё валидируется |
| keyring | Windows Credential Manager для API-ключей |
| httpx (async для TI, sync для AI) | таймауты, TLS, прокси, MockTransport для тестов |
| reportlab / python-docx / openpyxl / Jinja2 | отчёты без внешних программ (Word/Excel не требуются) |
| Без QtWebEngine/QtCharts | меньший размер exe; графики нарисованы QPainter |

## Корреляция атакующих цепочек

Категории алертов отображаются на стадии: Reconnaissance → Credential attack → Initial Access → Execution →
Persistence / Privilege Escalation / Defense Evasion → Credential Access → Lateral Movement / C2 → Impact.

Цепочка создаётся только если:
* есть **якорь** (brute-force burst, malware, credential dumping, encoded PowerShell, C2, деструктивные команды), и
* стадии идут в правильном порядке (наибольшая возрастающая подпоследовательность ≥ `min_chain_stages`),
  либо успешный вход после серии неудач сопровождается post-compromise активностью.

Неудачные логины считаются в скользящем окне — редкие периодические попытки (сканер раз в час) не становятся brute force.

## Принцип «факт vs вывод»

* `evidence` — только наблюдения из логов (кол-во событий, IP, аккаунты, командные строки, вердикты TI).
* `what_happened` — описание наблюдаемого; `why_it_matters` / `possible_attack` / `assessment` — аналитический вывод
  с осторожными формулировками: *Possible attack, Suspicious activity, Potential compromise, Likely brute-force activity,
  Insufficient evidence, Confirmed malicious indicator*. Фраза «система взломана» не используется.
* `confidence` — насколько данные подтверждают оценку; `fp_probability` — с причинами «за» и «против».

## AI

* `AIProvider` → `OpenAIProvider`, `AnthropicProvider`, `OllamaProvider`, `GenericOpenAICompatibleProvider`.
* В AI отправляется только нормализованный контекст: главная группа, связанные группы, контекст актива, IOC, MITRE-кандидаты, CVE.
* Облачные провайдеры → всегда санитизация. Локальные (Ollama/localhost) → по настройке `ai.anonymize_local`.
* Ответ: строгая Pydantic-схема, одна попытка «починки», затем guardrails: удаляются IOC/CVE, которых нет в контексте,
  неизвестные MITRE ID, MITRE без evidence; AI-only маппинги понижаются до `low`.
* Если AI недоступен — локальный анализ остаётся полным.

## Расширение

```python
from app.parsers.base import BaseParser, ParseContext
from app.parsers.registry import register_parser

class FortiGateParser(BaseParser):
    name = "fortigate"
    vendor = "fortigate"
    extensions = (".log",)

    @classmethod
    def sniff(cls, head, filename):
        return 0.9 if "devname=" in head and "logid=" in head else 0.0

    def parse(self, stream, ctx: ParseContext):
        for line in stream:
            ...  # yield {"rule": {...}, "agent": {...}, "data": {...}, "full_log": line}

register_parser(FortiGateParser)
```

Знания расширяются без кода: `rule_knowledge.yaml` и `local_ioc.csv` в каталоге данных пользователя,
веса риска и правила критичности активов — в `config.yaml`.
