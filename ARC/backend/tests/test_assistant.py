import os
import time

import pytest

from arc_backend.models import ActionRequest, Source, Status
from arc_backend.storage.scenarios import ScenarioInput, ScenarioStep


def test_launch_allowed_program_by_voice(services, controller, apps, no_network):
    response = services.assistant.handle_text("АРК, открой Telegram", Source.VOICE, confidence=0.93)
    assert response.status == Status.DONE
    assert response.action == "app.launch"
    assert controller.called("launch_exe") == [
        (r"C:\Users\u\AppData\Roaming\Telegram Desktop\Telegram.exe", (), None)]
    assert services.registry.get(apps["Telegram"]).last_launched is not None
    audit = services.journal.audit_entries(1)[0]
    assert audit["action"] == "app.launch" and audit["status"] == "done" and audit["source"] == "voice"


def test_launch_types(services, controller, apps):
    services.assistant.handle_text("запусти киберпанк")
    services.assistant.handle_text("открой хром")
    services.assistant.handle_text("открой калькулятор магазина")
    assert controller.called("shell_open") == [
        ("steam://rungameid/1091500",),
        (r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Google Chrome.lnk",),
        ("shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App",),
    ]


def test_already_running_switches_to_window(services, controller, apps):
    controller.running["telegram.exe"] = [4242]
    response = services.assistant.handle_text("открой телеграм")
    assert response.status == Status.DONE
    assert response.data["state"] == "already_running"
    assert controller.called("launch_exe") == []
    assert controller.called("activate_window") == [((4242,),)]


def test_missing_executable_reported(services, controller, apps):
    controller.assume_paths_exist = False
    response = services.assistant.handle_text("открой телеграм")
    assert response.status == Status.NOT_FOUND
    assert "не найден" in response.message
    assert controller.called("launch_exe") == []


def test_disabled_entry_is_not_launched(services, controller, apps):
    services.registry.update(apps["Telegram"], {"enabled": False})
    response = services.assistant.handle_text("открой телеграм")
    assert response.status == Status.NOT_FOUND
    assert controller.called("launch_exe") == []


def test_unknown_command(services, controller):
    response = services.assistant.handle_text("сделай мне бутерброд с икрой")
    assert response.status == Status.UNKNOWN
    assert controller.calls == []
    assert services.journal.history(1)[0]["status"] == "unknown"


def test_dialog_flow_game(services, controller, apps):
    first = services.assistant.handle_text("Запусти игру")
    assert first.status == Status.CLARIFY and first.clarify.question == "Какую игру запустить?"
    second = services.assistant.handle_text("Cyberpunk")
    assert second.status == Status.DONE
    assert controller.called("shell_open") == [("steam://rungameid/1091500",)]
    # the question is answered: a new "cyberpunk" is no longer a follow-up
    assert services.assistant.handle_text("Cyberpunk").status == Status.UNKNOWN


def test_dialog_cancel(services, apps):
    services.assistant.handle_text("запусти игру")
    response = services.assistant.handle_text("отмена")
    assert response.status == Status.CANCELLED
    assert services.assistant.state()["dialog"] is None


def test_low_confidence_voice_is_ignored(services, controller, apps):
    response = services.assistant.handle_text("арк открой телеграм", Source.VOICE, confidence=0.3)
    assert response.status == Status.IGNORED
    assert controller.calls == []


def test_background_speech_without_wake_word_is_ignored(services, controller, apps):
    response = services.assistant.handle_text("открой телеграм", Source.VOICE, confidence=0.95)
    assert response.status == Status.IGNORED
    assert controller.calls == []
    # typed text does not need the wake word
    assert services.assistant.handle_text("открой телеграм", Source.TEXT).status == Status.DONE


def test_critical_operation_requires_confirmation(services, controller):
    response = services.assistant.handle_text("выключи компьютер")
    assert response.status == Status.NEEDS_CONFIRMATION
    assert response.confirmation.requires_acknowledge
    assert controller.called("power") == []
    # voice "да" is not enough for category C
    denied = services.assistant.handle_text("да", Source.VOICE)
    assert controller.called("power") == []
    assert denied.status == Status.DENIED
    # UI without acknowledge — denied, still pending
    assert services.assistant.confirm(response.confirmation.id, True, Source.UI, acknowledge=False).status == Status.DENIED
    # UI with acknowledge — executed, but dry-run is on by default
    result = services.assistant.confirm(response.confirmation.id, True, Source.UI, acknowledge=True)
    assert result.status == Status.DRY_RUN and result.dry_run
    assert controller.called("power") == []


def test_critical_operation_executes_when_dry_run_off(services, controller):
    services.settings.update({"safety": {"dry_run": False}})
    response = services.assistant.handle_text("выключи компьютер через 2 минуты")
    result = services.assistant.confirm(response.confirmation.id, True, Source.UI, acknowledge=True)
    assert result.status == Status.DONE
    assert controller.called("power") == [("shutdown", 120)]
    undo = services.assistant.handle_text("отмени выключение")
    assert undo.status == Status.DONE
    assert controller.called("power")[-1] == ("abort", 0)


def test_reject_confirmation(services, controller):
    response = services.assistant.handle_text("создай папку с названием Тест")
    assert response.status == Status.NEEDS_CONFIRMATION
    result = services.assistant.confirm(response.confirmation.id, False)
    assert result.status == Status.CANCELLED
    assert controller.called("make_dir") == []


def test_create_folder_voice_confirmation_and_undo(services, controller, folders):
    services.settings.update({"safety": {"dry_run": False}})
    response = services.assistant.handle_text("создай папку с названием Проект Альфа")
    assert response.status == Status.NEEDS_CONFIRMATION
    result = services.assistant.handle_text("да", Source.VOICE)
    assert result.status == Status.DONE
    target = os.path.join(folders["desktop"], "Проект Альфа")
    assert os.path.isdir(target)
    # undo is a deletion → asks again
    undo = services.assistant.handle_text("отмени последнее действие")
    assert undo.status == Status.NEEDS_CONFIRMATION
    assert services.assistant.confirm(undo.confirmation.id, True).status == Status.DONE
    assert not os.path.exists(target)


def test_folder_outside_allowed_dirs_is_denied(services, controller, tmp_path):
    services.settings.update({"safety": {"dry_run": False}})
    outside = tmp_path / "outside"
    outside.mkdir()
    response = services.assistant.run_action(ActionRequest(action="files.create_folder",
                                                           params={"name": "x", "parent": str(outside)},
                                                           source=Source.UI))
    result = services.assistant.confirm(response.confirmation.id, True)
    assert result.status == Status.DENIED
    assert not (outside / "x").exists()


def test_volume_undo_and_repeat(services, controller):
    controller.volume = 40
    assert services.assistant.handle_text("увеличь громкость на 20 процентов").status == Status.DONE
    assert controller.volume == 60
    assert services.assistant.handle_text("повтори").status == Status.DONE
    assert controller.volume == 80
    assert services.assistant.handle_text("отмени").status == Status.DONE
    assert controller.volume == 60


def test_repeat_without_history(services):
    assert services.assistant.handle_text("повтори").message == "Нечего повторять."


def test_mode_switch_enables_web_search(services, controller, no_network):
    denied = services.assistant.handle_text("найди в интернете курс валют")
    assert denied.status == Status.DENIED
    assert controller.called("shell_open") == []
    assert services.assistant.handle_text("переключись в онлайн режим").status == Status.DONE
    assert services.settings.get().network.mode.value == "ONLINE"
    result = services.assistant.handle_text("найди в интернете курс валют")
    assert result.status == Status.DONE
    assert controller.called("shell_open") == [("https://duckduckgo.com/?q=%D0%BA%D1%83%D1%80%D1%81+%D0%B2%D0%B0%D0%BB%D1%8E%D1%82",)]
    assert services.assistant.handle_text("перейди в локальный режим").status == Status.DONE
    assert services.assistant.handle_text("найди в интернете курс валют").status == Status.DENIED


def test_online_master_switch(services):
    services.settings.update({"network": {"mode": "ONLINE"}})
    services.settings.update({"network": {"online_allowed": False}})
    assert services.settings.get().network.mode.value == "LOCAL"
    assert services.assistant.handle_text("переключись в онлайн режим").status == Status.DENIED


def test_silent_mode(services, controller):
    response = services.assistant.handle_text("переключись в режим тишины")
    assert response.status == Status.DONE
    assert services.settings.get().profile.silent is True
    assert controller.muted is True


def test_scenario_runs_steps_through_permissions(services, controller):
    scenario = services.scenarios.add(ScenarioInput(
        name="Игровой режим", aliases=["игровой режим"],
        steps=[ScenarioStep(action="volume.set", params={"level": 70}), ScenarioStep(action="window.minimize_all")]))
    response = services.assistant.handle_text("включи игровой режим")
    assert response.status == Status.DONE, response.message
    assert controller.volume == 70 and controller.called("minimize_all")
    services.settings.update({"safety": {"modules": {"windows": False}}})
    response = services.assistant.run_action(ActionRequest(action="scenario.run", params={"scenario_id": scenario.id},
                                                           source=Source.UI))
    assert response.status == Status.ERROR and "отключён" in response.message


def test_scenario_rejects_dangerous_steps():
    with pytest.raises(ValueError):
        ScenarioInput(name="x", steps=[ScenarioStep(action="power.shutdown", params={"delay_s": 1})])


def test_emergency_stop(services, controller, apps):
    services.assistant.handle_text("аварийная остановка")
    assert services.assistant.handle_text("открой телеграм").status == Status.DENIED
    assert controller.calls == []
    services.assistant.emergency_stop(False)
    assert services.assistant.handle_text("открой телеграм").status == Status.DONE


def test_action_timeout(services, controller, apps, monkeypatch):
    services.settings.update({"safety": {"action_timeout_s": 0.2}})
    monkeypatch.setattr(controller, "minimize_all", lambda: time.sleep(1))
    started = time.monotonic()
    response = services.assistant.handle_text("сверни все окна")
    assert response.status == Status.ERROR and "не завершилась" in response.message
    assert time.monotonic() - started < 0.9


def test_controller_failure_is_reported(services, controller, apps):
    controller.fail_on.add("launch_exe")
    response = services.assistant.handle_text("открой телеграм")
    assert response.status == Status.ERROR and "Сбой" in response.message


def test_system_info(services, controller):
    for phrase in ("который час", "какое сегодня число", "сколько свободного места на диске", "загрузка процессора",
                   "сколько памяти занято", "какие программы запущены", "состояние системы"):
        response = services.assistant.handle_text(phrase)
        assert response.status == Status.DONE, (phrase, response.message)


def test_file_search(services, folders):
    with open(os.path.join(folders["desktop"], "Отчёт за май.docx"), "w") as fh:
        fh.write("x")
    os.makedirs(os.path.join(folders["documents"], "Архив"))
    with open(os.path.join(folders["documents"], "Архив", "отчет 2023.xlsx"), "w") as fh:
        fh.write("x")
    response = services.assistant.handle_text("найди файл с отчётом на рабочем столе")
    assert response.status == Status.DONE
    assert [f["name"] for f in response.data["files"]] == ["Отчёт за май.docx"]
    response = services.assistant.handle_text("найди файл отчет")
    assert {f["name"] for f in response.data["files"]} == {"Отчёт за май.docx", "отчет 2023.xlsx"}


def test_help(services):
    assert "Telegram" in services.assistant.handle_text("что ты умеешь").message
