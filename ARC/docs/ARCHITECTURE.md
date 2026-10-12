# A.R.C. — архитектура

A.R.C. (Adaptive Responsive Computer) — настольный голосовой помощник для Windows 10/11 x64.
Принципы: offline-first, local-first, модульность, безопасность по умолчанию.

## 1. Процессы

```
┌──────────────────────────── Electron (arc.exe) ─────────────────────────────┐
│  Renderer (React, sandbox)  ──IPC (allowlist)──►  Main process              │
│   • главный экран, виджет      contextBridge       • окна, трей, хоткеи     │
│   • приложения, журнал,                            • BackendManager         │
│     разрешения, настройки                          • токен API              │
└──────────────────────────────────────────────────────────┬──────────────────┘
                                         HTTP 127.0.0.1:<random port>
                                         X-ARC-Token, без Origin
┌──────────────────────────── Python backend (arc-backend.exe) ───────────────┐
│ API (FastAPI) ─► Assistant (оркестратор)                                   │
│                   ├─ Command Router (разбор русской речи → Intent → Plan)  │
│                   ├─ Permission Manager (каталог действий, риск A/B/C)     │
│                   ├─ Executor ─► SystemController (Windows | Mock)         │
│                   ├─ App Registry + Discovery (ярлыки, Steam, Epic, UWP)  │
│                   └─ Settings & Storage (SQLite: настройки, приложения,   │
│                      сценарии, история, аудит)                             │
│ Voice Engine (этап 2) · Vision Engine (этап 3) · Local AI / Ollama (этап 4)│
│ Online Research, Document Engine (этап 5) · Plugin Manager (этап 6)        │
└─────────────────────────────────────────────────────────────────────────────┘
```

* **Renderer** не имеет доступа к Node.js и к HTTP-API: только `window.arc.*` из preload. Main-процесс
  пропускает запросы по таблице разрешённых маршрутов (`app/electron/routes.ts`).
* **Backend** слушает только `127.0.0.1`, порт выбирается ОС и сообщается строкой
  `{"event":"ready","port":N}` в stdout. Каждый запрос должен содержать случайный токен
  (32 байта, генерируется Electron при каждом запуске и передаётся через переменную окружения).
  Запросы с заголовками `Origin`/`Sec-Fetch-Site` (браузер) и с чужим `Host` (DNS rebinding) отклоняются.
* Backend следит за PID родительского процесса и завершается, если Electron исчез.
  Electron перезапускает упавший backend (до 5 раз с нарастающей задержкой).

## 2. Компоненты и контракты

| Компонент | Код | Контракт |
|---|---|---|
| Desktop UI | `app/src`, `app/electron` | IPC `arc:api` (allowlist), `arc:window`, `arc:dialog`, `arc:system` |
| Command Router | `backend/arc_backend/router` | `CommandRouter.route(text, ctx) -> Plan` — чистая функция без побочных эффектов |
| Permission Manager | `backend/arc_backend/permissions` | `evaluate(ActionRequest) -> Decision`, подтверждения с TTL, аварийная остановка |
| Local Automation | `backend/arc_backend/automation` | `SystemController` (Protocol), `WindowsController`, `MockController`; `Executor.execute(ActionRequest) -> ActionResult` |
| App Registry | `backend/arc_backend/apps` | CRUD, поиск по имени/псевдонимам (транслитерация), discovery |
| Settings & Storage | `backend/arc_backend/storage` | `Database`, `SettingsStore` (типизированные `Settings`), репозитории |
| Voice Engine | этап 2 | `VoiceEngine.transcribe() -> Utterance(text, confidence)` → `Assistant.handle_text` |
| Vision Engine | этап 3 | `GestureEvent(gesture, confidence)` → только действия из списка жестов, риск A |
| Local AI Engine | `backend/arc_backend/ai` | этап 1: проверка Ollama; этап 4: LLM возвращает **только** JSON-план из каталога |
| Online Research | `backend/arc_backend/online` | `OnlineClient.request()` — единственный выход в интернет: проверка ONLINE в момент запроса, https, лимит в минуту, тайм-аут, ≤ 2 МБ, журнал; провайдеры Wikipedia / DuckDuckGo / Brave / SearXNG; `ResearchEngine.search() -> ResearchReport`, сводка локальной моделью |
| Plugin Manager | `backend/arc_backend/plugins` | `.arcplugin` = JSON-описание + подпись Ed25519; `PluginManager.match(text) -> PluginMatch` (только для фраз, не понятых роутером, до локальной модели); действия идут в Permission Manager с источником `plugin` |
| Document Engine | `backend/arc_backend/documents` | `DocumentContent` (pydantic, лимиты) → рендер PPTX/DOCX/XLSX/PDF/TXT → проверка чтением → атомарное сохранение; фоновые задания `DocJob` |

### Поток команды

```
текст/речь ─► normalize ─► wake word? ─► intents ─► Plan
   Plan = Reply | Clarify(вопрос, варианты) | Actions[ActionRequest]
ActionRequest ─► PermissionManager.evaluate
   ├─ deny  (модуль выключен, офлайн, аварийная остановка, жест для B/C, неизвестное действие)
   ├─ confirm (B, C) ─► PendingConfirmation(id, ttl) ─► UI ─► /api/confirm
   └─ allow ─► Executor (dry-run для B/C в тестовом режиме) ─► SystemController
ActionResult ─► журнал аудита + история ─► ответ пользователю (+ undo-действие)
```

Ни один компонент не передаёт текст пользователя или модели в командную оболочку:
выполняются только действия из каталога (`permissions/catalog.py`) с типизированными
параметрами (pydantic). Процессы запускаются `subprocess.Popen([...], shell=False)` либо
`ShellExecute` для ярлыков, UWP (`shell:AppsFolder\…`) и протоколов из белого списка.

## 3. Категории риска

| Категория | Примеры | Политика |
|---|---|---|
| A — безопасные | запуск приложения из реестра, громкость, окна, системная информация, поиск файлов | выполняются сразу |
| B — изменяющие | создание папки, завершение процесса | подтверждение; в тестовом режиме — имитация |
| C — критические | выключение/перезагрузка, запуск от администратора | подтверждение с явной отметкой «понимаю»; жестами и голосом без UI — нельзя |

Настройки разрешений меняются **только** из интерфейса (маршрут `PUT /api/settings`).
Router, LLM, веб-страницы и документы не могут их изменить: в каталоге нет такого действия.

## 4. Хранение

`%LOCALAPPDATA%\ARC\arc.db` (SQLite, WAL): `settings`, `apps`, `scenarios`, `history`, `audit`.
Логи: `%LOCALAPPDATA%\ARC\logs\backend.log` (ротация). Видео и аудио не сохраняются.

## 5. Режимы LOCAL / ONLINE

`settings.network.mode` = `LOCAL` | `ONLINE`, плюс главный выключатель `online_allowed`.
Действия с `requires_online=True` (`web.search`, `web.research`) в LOCAL отклоняются Permission Manager,
а `OnlineClient` повторно проверяет режим перед каждым запросом (защита в глубину: документ «с данными из
интернета» в LOCAL тоже не уйдёт в сеть). Адрес Ollama вне loopback считается внешним сервисом и требует ONLINE.
Интерфейс в ONLINE показывает баннер с кнопкой «Вернуться в LOCAL» и индикатор активного запроса.

### Документы (этап 5)

```
«сделай презентацию про X [с данными из интернета]» ─► documents.create (категория B) ─► подтверждение
   ─► DocJob в фоне: [поиск: ResearchEngine, только ONLINE] ─► текст: Ollama, JSON-схема DocumentContent
      (источники переданы как данные; без них — без конкретных цифр) │ модель недоступна ─► шаблон с пометкой
   ─► рендер во временный файл в целевой папке ─► проверка (слайды/разделы/строки/текст PDF, нет формул)
   ─► os.replace в «Имя.pptx» / «Имя (2).pptx» ─► история + журнал + голосом, если команда была голосовой
```

Папка — `Документы\ARC` или своя, всегда внутри разрешённых каталогов. Аварийная остановка отменяет задания.

## 6. Структура каталогов

```
ARC/
  app/                    Electron + React + Vite (TypeScript)
    electron/             main, preload, BackendManager, трей, IPC
    src/                  интерфейс: экраны, компоненты, дизайн-система (styles/)
    tests/                vitest
  backend/                Python 3.12
    arc_backend/
      api/                FastAPI, защита локального API
      router/             нормализация, числа, транслитерация, интенты, диалог
      permissions/        каталог действий, менеджер разрешений
      automation/         SystemController (Windows/Mock), executor, файлы, sysinfo
      apps/               реестр, сопоставление имён, discovery, .lnk/.vdf парсеры
      storage/            SQLite, настройки
      ai/                 Ollama: статус, вызов /api/chat, планировщик (этап 4)
      online/             клиент сети, провайдеры поиска, ResearchEngine, хранилище ключей
      documents/          модель содержимого, генерация текста, рендеры и проверка, фоновые задания
      plugins/            описание модуля, подпись Ed25519, менеджер модулей, утилита автора
    tests/                pytest
  scripts/                check_env.ps1, dev.ps1, build.ps1
  docs/                   документация
```
