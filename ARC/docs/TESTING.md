# Тесты

```powershell
cd backend; .venv\Scripts\python -m pytest -q        # ядро: ~340 тестов, без сети и устройств
cd app; npm test                                      # интерфейс: vitest + jsdom
powershell -ExecutionPolicy Bypass -File scripts\build.ps1   # всё + PyInstaller + самопроверка EXE + установщик
```

Тесты ядра по умолчанию не ходят в интернет и не требуют микрофона, камеры и Ollama: устройства и модели
подменяются, сеть — `httpx.MockTransport`, а фикстура `no_network` роняет тест при любом соединении не на
127.0.0.1. Тесты с настоящими моделями и интернетом включаются переменными и выполняются в Windows CI:

| Переменная | Тесты | Что нужно |
|---|---|---|
| `ARC_TEST_MODELS` | `test_voice_real.py`, `test_vision_real.py` | Whisper, Piper, модель рук MediaPipe |
| `ARC_TEST_OLLAMA=qwen2.5:3b` | `test_ai_real.py` | Ollama с моделью |
| `ARC_TEST_ONLINE=1` | `test_online_real.py`, часть `test_ai_real.py` | интернет |

## 15 обязательных проверок из задания

| # | Проверка | Автотест | Где выполняется |
|---|---|---|---|
| 1 | Запуск без интернета | `test_process.py::test_starts_offline_and_shuts_down`, `test_offline.py` (целая сессия без внешних соединений) | локально, CI |
| 2 | Запуск программы голосом | `test_voice_real.py::test_spoken_command_is_executed` (Piper произносит «открой блокнот» → Whisper → действие), `test_voice.py::test_push_to_talk_executes_command_and_speaks` | CI (реальные модели), локально |
| 3 | Неизвестная команда | `test_assistant.py::test_unknown_command`, `test_ai_planner.py::test_unknown_program_falls_back_when_model_cannot_help` | локально |
| 4 | Нет микрофона | `test_voice.py::test_no_microphone_keeps_text_commands_working`, `test_microphone_disabled_is_never_opened` | локально |
| 5 | Нет камеры | `test_vision.py::test_no_camera_reports_error_and_rest_works`, `test_camera_disabled_is_never_opened` | локально |
| 6 | Ollama не запущена | `test_api.py::test_ollama_not_running`, `test_ai_planner.py::test_model_failures_are_graceful`, `test_documents.py::test_without_local_model_a_marked_template_is_created` | локально |
| 7 | Переключение LOCAL/ONLINE | `test_assistant.py::test_mode_switch_enables_web_search`, `test_online_master_switch` | локально |
| 8 | Отказ онлайн-функций в офлайне | `test_online.py::test_local_mode_makes_no_requests`, `test_client_rechecks_mode_on_every_request`, `test_documents.py::test_web_facts_need_online_mode` | локально |
| 9 | Подтверждение критического действия | `test_assistant.py::test_critical_operation_requires_confirmation`, `test_api.py::test_command_and_confirm`, `test_ai_planner.py::test_critical_action_from_model_needs_ui_confirmation` | локально |
| 10 | Защита жестов от повторов | `test_vision.py::test_hold_then_fire_once_while_held`, `test_release_and_cooldown`, `test_min_interval_between_different_gestures` | локально |
| 11 | Сохранение настроек | `test_storage.py::test_settings_persist_across_restart`, `test_plugins.py::test_modules_survive_restart` | локально |
| 12 | Создание PPTX | `test_documents.py::test_presentation_by_voice_command_with_local_model`, `test_ai_real.py::test_presentation_written_by_the_model` (реальная qwen2.5:3b) | локально, CI |
| 13 | Завершение фоновых процессов | `test_process.py::test_exits_when_parent_dies`, CI: «arc-backend.exe still running after exit» в smoke-тесте | локально, CI |
| 14 | Нет выполнения произвольного кода | `test_code_safety.py`, `test_ai_real.py::test_prompt_injection_cannot_do_anything_dangerous`, `test_plugins.py::test_dangerous_or_malformed_manifests_are_rejected` | локально, CI |
| 15 | Сборка установщика | CI `build-test`: `build.ps1`, тихая установка, ярлык в «Пуск», smoke-тест установленной копии, удаление; `signing`: подпись и SHA-256 | CI (Windows) |

Регрессии аудита безопасности — `test_security_review.py` (см. [SECURITY_REVIEW.md](SECURITY_REVIEW.md)).
