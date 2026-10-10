import pytest

from arc_backend.router.numbers import extract_number
from arc_backend.router.router import CommandRouter, RouterContext, strip_wake_word
from arc_backend.router.text import normalize, similarity


@pytest.fixture
def ctx(services, apps, folders):
    return RouterContext(apps=services.registry.list(), scenarios=services.scenarios.list(), folders=folders)


router = CommandRouter()


def single(plan):
    assert plan.kind == "actions", (plan.kind, plan.message)
    assert len(plan.actions) == 1
    return plan.actions[0]


# ----------------------------------------------------------------------------- text helpers
@pytest.mark.parametrize("text,expected", [
    ("двадцать", 20), ("на двадцать пять процентов", 25), ("на 30%", 30), ("до пятидесяти", 50),
    ("сто", 100), ("на половину", 50), ("десять пять", 10), ("громкость максимум", 100), ("ничего", None),
])
def test_numbers(text, expected):
    assert extract_number(normalize(text)) == expected


def test_normalize_and_similarity():
    assert normalize("АРК, Открой Telegram!") == "арк открой telegram"
    assert normalize("Ёлка") == "елка"
    assert similarity("телеграм", "Telegram") == 1.0
    assert similarity("киберпанк", "Cyberpunk 2077") > 0.8
    assert similarity("стим", "Stellaris") < 0.7


@pytest.mark.parametrize("text,woke,rest", [
    ("арк открой телеграм", True, "открой телеграм"),
    ("эй арк сверни окна", True, "сверни окна"),
    ("arc mute", True, "mute"),
    ("открой телеграм", False, "открой телеграм"),
    ("аркада", False, "аркада"),
])
def test_wake_word(text, woke, rest):
    assert strip_wake_word(text, "арк") == (woke, rest)


# ----------------------------------------------------------------------------- applications
@pytest.mark.parametrize("phrase,name", [
    ("АРК, открой Telegram", "Telegram"),
    ("открой телеграм", "Telegram"),
    ("открой телегу", "Telegram"),
    ("Запусти Steam", "Steam"),
    ("запусти стим", "Steam"),
    ("Запусти Cyberpunk 2077", "Cyberpunk 2077"),
    ("запусти киберпанк", "Cyberpunk 2077"),
    ("запусти игру ведьмак", "The Witcher 3"),
    ("открой хром", "Google Chrome"),
])
def test_launch_app(ctx, apps, phrase, name):
    action = single(router.route(phrase, ctx))
    assert action.action == "app.launch"
    assert action.params == {"app_id": apps[name]}


def test_launch_unknown_app_is_not_guessed(ctx):
    plan = router.route("запусти фотошоп", ctx)
    assert plan.kind == "reply" and plan.intent == "app.not_found"
    assert not plan.actions


def test_launch_game_asks_which_then_resolves(ctx, apps):
    plan = router.route("Запусти игру", ctx)
    assert plan.kind == "clarify"
    assert plan.message == "Какую игру запустить?"
    assert set(plan.options) == {"Cyberpunk 2077", "The Witcher 3"}
    ctx.dialog = plan.dialog
    action = single(router.route("Cyberpunk", ctx))
    assert action.params == {"app_id": apps["Cyberpunk 2077"]}


def test_clarify_by_option_number(ctx, apps):
    plan = router.route("запусти игру", ctx)
    ctx.dialog = plan.dialog
    action = single(router.route("2", ctx))
    assert action.params["app_id"] == apps[plan.options[1]]


def test_new_command_abandons_question(ctx):
    plan = router.route("запусти игру", ctx)
    ctx.dialog = plan.dialog
    action = single(router.route("открой проводник", ctx))
    assert action.action == "explorer.open"


def test_admin_flag_maps_to_critical_action(ctx, apps):
    assert single(router.route("запусти админку", ctx)).action == "app.launch_admin"
    action = single(router.route("запусти steam от имени администратора", ctx))
    assert action.action == "app.launch_admin" and action.params["app_id"] == apps["Steam"]


def test_close_app(ctx, apps):
    action = single(router.route("закрой телеграм", ctx))
    assert action.action == "app.close" and action.params["app_id"] == apps["Telegram"]


# ----------------------------------------------------------------------------- system
@pytest.mark.parametrize("phrase,action,params", [
    ("Увеличь громкость на двадцать процентов", "volume.change", {"delta": 20}),
    ("сделай громче", "volume.change", {"delta": 10}),
    ("убавь звук на 15", "volume.change", {"delta": -15}),
    ("тише", "volume.change", {"delta": -10}),
    ("установи громкость на пятьдесят", "volume.set", {"level": 50}),
    ("громкость 30", "volume.set", {"level": 30}),
    ("Выключи звук", "volume.mute", {"muted": True}),
    ("включи звук", "volume.mute", {"muted": False}),
    ("Сверни все окна", "window.minimize_all", {}),
    ("покажи рабочий стол", "window.minimize_all", {}),
    ("верни окна", "window.restore_all", {}),
    ("Открой проводник", "explorer.open", {}),
    ("открой загрузки", "explorer.open", {"folder": "downloads"}),
    ("Какие программы сейчас запущены?", "system.info", {"topic": "processes"}),
    ("Сколько свободного места на диске?", "system.info", {"topic": "disk"}),
    ("который час", "system.info", {"topic": "time"}),
    ("какое сегодня число", "system.info", {"topic": "date"}),
    ("загрузка процессора", "system.info", {"topic": "cpu"}),
    ("сколько свободной памяти", "system.info", {"topic": "memory"}),
    ("Переключись в режим тишины", "profile.silent", {"enabled": True}),
    ("выйди из режима тишины", "profile.silent", {"enabled": False}),
    ("переключись в онлайн режим", "mode.set", {"mode": "ONLINE"}),
    ("перейди в локальный режим", "mode.set", {"mode": "LOCAL"}),
    ("выключи компьютер", "power.shutdown", {"delay_s": 60}),
    ("перезагрузи компьютер через 5 минут", "power.restart", {"delay_s": 300}),
    ("отмени выключение", "power.abort", {}),
])
def test_system_commands(ctx, phrase, action, params):
    result = single(router.route(phrase, ctx))
    assert result.action == action
    assert result.params == params


# ----------------------------------------------------------------------------- files / web
def test_find_file_on_desktop(ctx):
    action = single(router.route("Найди файл с отчётом на рабочем столе", ctx))
    assert action.action == "files.search"
    assert action.params == {"query": "отчетом", "scope": "desktop"}


def test_find_file_by_name(ctx):
    action = single(router.route("найди файл по названию бюджет 2024", ctx))
    assert action.params == {"query": "бюджет 2024"}


def test_create_folder_with_name(ctx):
    action = single(router.route("создай папку с названием Проект Альфа в документах", ctx))
    assert action.action == "files.create_folder"
    assert action.params == {"name": "Проект Альфа", "parent": "documents"}


def test_create_folder_asks_for_name(ctx):
    plan = router.route("Создай папку для нового проекта", ctx)
    assert plan.kind == "clarify" and plan.message == "Как назвать папку?"
    ctx.dialog = plan.dialog
    action = single(router.route("Новый проект", ctx))
    assert action.params == {"name": "Новый проект", "parent": "desktop"}


def test_web_search_and_sites(ctx):
    action = single(router.route("Найди актуальную информацию по теме квантовые компьютеры", ctx))
    assert action.action == "web.search" and action.params == {"query": "квантовые компьютеры"}
    action = single(router.route("открой браузер и перейди на github.com", ctx))
    assert action.params == {"url": "https://github.com"}
    action = single(router.route("открой ютуб", ctx))
    assert action.params == {"url": "https://www.youtube.com"}


def test_open_browser_uses_registry_alias(ctx, apps):
    action = single(router.route("открой браузер", ctx))
    assert action.action == "app.launch" and action.params["app_id"] == apps["Google Chrome"]


def test_document_requests_are_honestly_unavailable(ctx):
    plan = router.route("Подготовь презентацию на тему информационной безопасности", ctx)
    assert plan.kind == "unavailable"
    assert not plan.actions


# ----------------------------------------------------------------------------- scenarios / meta
def test_scenario_alias(ctx):
    plan = router.route("включи рабочий режим", ctx)
    action = single(plan)
    assert action.action == "scenario.run"


@pytest.mark.parametrize("phrase,meta", [
    ("повтори", "repeat"), ("ещё раз", "repeat"), ("отмени последнее действие", "undo"), ("отмени", "undo"),
    ("отмена", "cancel"), ("аварийная остановка", "emergency_stop"), ("что ты умеешь", "help"),
])
def test_meta(ctx, phrase, meta):
    plan = router.route(phrase, ctx)
    assert plan.kind == "meta" and plan.meta == meta


def test_yes_no_only_with_pending_confirmation(ctx):
    assert router.route("да", ctx).kind == "unknown"
    ctx.has_pending_confirmation = True
    assert router.route("да", ctx).meta == "confirm_yes"
    assert router.route("нет", ctx).meta == "confirm_no"


def test_unknown(ctx):
    plan = router.route("абракадабра шмяк", ctx)
    assert plan.kind == "unknown"


def test_voice_requires_wake_word(ctx, apps):
    ctx.require_wake_word = True
    assert router.route("открой телеграм", ctx).kind == "ignored"
    assert single(router.route("арк открой телеграм", ctx)).params["app_id"] == apps["Telegram"]


def test_injection_text_never_becomes_shell(ctx):
    for phrase in ["открой calc & del /q c:\\*", "запусти cmd /c format c:", "открой powershell -enc AAAA",
                   "выполни rm -rf /", "открой; shutdown /s"]:
        plan = router.route(phrase, ctx)
        for action in plan.actions:
            assert action.action in ("app.launch", "browser.open_url", "explorer.open")
            assert set(action.params) <= {"app_id", "url", "folder"}
