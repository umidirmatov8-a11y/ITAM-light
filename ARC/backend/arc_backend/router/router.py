"""Command Router: Russian phrase → Plan. Pure logic, no side effects.

The router never produces anything except catalog actions with typed parameters, a clarifying
question, a reply or a meta command (undo / repeat / cancel / confirm / emergency stop).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Literal, Optional

from ..apps.matcher import match_app
from ..apps.registry import AppEntry, AppKind
from ..models import ActionRequest
from ..storage.scenarios import Scenario
from .numbers import extract_number
from .text import normalize, similarity

PlanKind = Literal["actions", "clarify", "reply", "meta", "unknown", "ignored", "unavailable"]
Meta = Literal["undo", "repeat", "cancel", "confirm_yes", "confirm_no", "emergency_stop", "help"]

DIALOG_TTL_S = 45.0
WAKE_WORDS = ("арк", "arc", "ark", "a.r.c", "а.р.к", "эй арк", "окей арк", "привет арк")


@dataclass
class DialogState:
    """A question A.R.C. asked and is waiting an answer for."""
    intent: Literal["launch", "create_folder", "close"]
    question: str
    options: dict[str, str] = field(default_factory=dict)  # option label -> app id
    kind: Optional[AppKind] = None
    admin: bool = False
    parent: str = "desktop"
    expires_at: float = 0.0


@dataclass
class RouterContext:
    apps: list[AppEntry] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)
    folders: dict[str, str] = field(default_factory=dict)
    wake_word: str = "арк"
    require_wake_word: bool = False
    dialog: Optional[DialogState] = None
    has_pending_confirmation: bool = False
    now: float = field(default_factory=time.time)
    raw: str = ""


@dataclass
class Plan:
    kind: PlanKind
    intent: str
    message: str = ""
    actions: list[ActionRequest] = field(default_factory=list)
    options: list[str] = field(default_factory=list)
    dialog: Optional[DialogState] = None
    meta: Optional[Meta] = None
    keep_dialog: bool = False
    labels: dict[str, str] = field(default_factory=dict)  # human-readable names for descriptions


# ----------------------------------------------------------------------------- vocabularies
_LAUNCH = r"(?:открой|открыть|запусти|запустить|включи|включить|стартуй|загрузи|давай|хочу поиграть в|поиграем в|запуск)"
_CLOSE = r"(?:закрой|закрыть|заверши|завершить|выключи|выруби|останови|убей)"
_FOLDER_WORDS = {
    "desktop": r"рабоч\w* стол\w*",
    "documents": r"(?:мои[хм]? )?документ\w*",
    "downloads": r"загрузк\w*",
    "pictures": r"(?:изображени\w*|картинк\w*)",
    "music": r"музык\w*",
    "videos": r"видео",
}
_SITES = {
    "ютуб": "https://www.youtube.com", "youtube": "https://www.youtube.com", "гугл": "https://www.google.com",
    "google": "https://www.google.com", "яндекс": "https://ya.ru", "вк": "https://vk.com",
    "вконтакте": "https://vk.com", "гитхаб": "https://github.com", "github": "https://github.com",
    "википедия": "https://ru.wikipedia.org", "википедию": "https://ru.wikipedia.org",
    "почту": "https://mail.google.com", "гмейл": "https://mail.google.com",
}
_DOMAIN = re.compile(r"\b((?:https?://)?(?:[a-z0-9а-я\-]+\.)+(?:ru|com|org|net|io|рф|su|dev|info|me|tv|ai|edu|gov|uk|de|by|kz|ua)(?:/[^\s]*)?)\b")


def _folder_key(text: str) -> Optional[str]:
    for key, pattern in _FOLDER_WORDS.items():
        if re.search(pattern, text):
            return key
    return None


def _strip_folder_phrase(text: str) -> str:
    for pattern in _FOLDER_WORDS.values():
        text = re.sub(r"\b(?:на|в|во|из|с|со)?\s*" + pattern, " ", text)
    return " ".join(text.split())


def _original_case(raw: str, fragment: str) -> str:
    """Finds `fragment` (normalized) in the raw phrase and returns it with the user's capitalization."""
    tokens = [re.escape(t) for t in fragment.split()]
    if not tokens:
        return fragment
    pattern = r"[\W_]+".join(t.replace("е", "[её]") for t in tokens)
    match = re.search(pattern, raw, re.IGNORECASE)
    return match.group(0) if match else fragment


def strip_wake_word(text: str, wake_word: str) -> tuple[bool, str]:
    words = {normalize(w) for w in (*WAKE_WORDS, wake_word) if w}
    for candidate in sorted(words, key=len, reverse=True):
        if text == candidate:
            return True, ""
        if text.startswith(candidate + " "):
            return True, text[len(candidate) + 1:].strip()
    return False, text


class CommandRouter:
    def route(self, raw: str, ctx: RouterContext) -> Plan:
        text = normalize(raw)
        ctx.raw = raw
        if not text:
            return Plan("ignored", "empty")
        woke, text = strip_wake_word(text, ctx.wake_word)
        dialog = ctx.dialog if ctx.dialog and ctx.dialog.expires_at > ctx.now else None
        if ctx.require_wake_word and not woke and dialog is None and not ctx.has_pending_confirmation:
            return Plan("ignored", "no_wake_word", "Команда без слова активации проигнорирована")
        if not text:
            return Plan("reply", "wake", "Слушаю.", keep_dialog=True)

        meta = self._meta(text, ctx, dialog)
        if meta:
            return meta
        if dialog:
            answered = self._answer_dialog(text, raw, dialog, ctx)
            if answered:
                return answered
        for handler in (self._power, self._mode, self._volume, self._windows, self._system_info, self._documents,
                        self._web, self._files, self._scenario, self._close, self._launch):
            plan = handler(text, ctx)
            if plan:
                return plan
        return Plan("unknown", "unknown", "Не понял команду. Скажите «что ты умеешь», чтобы услышать примеры.")

    # ------------------------------------------------------------------ meta commands
    def _meta(self, text: str, ctx: RouterContext, dialog: Optional[DialogState]) -> Optional[Plan]:
        if re.fullmatch(r"(?:аварийная остановка|экстренная остановка|стоп автоматизац\w*|останови все|остановить все)",
                        text):
            return Plan("meta", "emergency_stop", meta="emergency_stop")
        if re.fullmatch(r"(?:что ты умеешь|помощь|справка|какие (?:есть )?команды|help)", text):
            return Plan("meta", "help", meta="help")
        if ctx.has_pending_confirmation:
            if re.fullmatch(r"(?:да|подтверждаю|выполняй|выполнить|давай|ок|окей|да подтверждаю|согласен)", text):
                return Plan("meta", "confirm", meta="confirm_yes")
            if re.fullmatch(r"(?:нет|не надо|отмена|отмени|стоп|не нужно|отказ)", text):
                return Plan("meta", "confirm", meta="confirm_no")
        if re.fullmatch(r"(?:отмени|отменить|верни как было|отмени (?:последнее )?(?:действие|команду|это))", text):
            if dialog and text in ("отмени", "отменить"):
                return Plan("meta", "cancel", meta="cancel")
            return Plan("meta", "undo", meta="undo")
        if re.fullmatch(r"(?:отмена|не надо|стоп|забудь|никакую|ничего|не нужно)", text):
            return Plan("meta", "cancel", meta="cancel")
        if re.fullmatch(r"(?:повтори|повтори (?:последнюю )?команду|еще раз|сделай (?:это )?еще раз|повторить)", text):
            return Plan("meta", "repeat", meta="repeat")
        return None

    # ------------------------------------------------------------------ dialog follow-ups
    def _answer_dialog(self, text: str, raw: str, dialog: DialogState, ctx: RouterContext) -> Optional[Plan]:
        if dialog.intent == "create_folder":
            name = " ".join(re.sub(r"^(?:назови|назовем|название|пусть будет|имя)\s+", "", raw.strip(), flags=re.I)
                            .strip(" .,!?\"'«»").split())
            if not name:
                return None
            return Plan("actions", "files.create_folder",
                        actions=[ActionRequest(action="files.create_folder",
                                               params={"name": name, "parent": dialog.parent})])
        if dialog.intent in ("launch", "close"):
            if dialog.options:
                best_label, best_score = None, 0.0
                for label in dialog.options:
                    score = similarity(text, label)
                    if text.isdigit() and int(text) == list(dialog.options).index(label) + 1:
                        score = 1.0
                    if score > best_score:
                        best_label, best_score = label, score
                if best_label and best_score >= 0.7:
                    entry = next((a for a in ctx.apps if a.id == dialog.options[best_label]), None)
                    if entry:
                        return self._app_plan(entry, dialog.intent, dialog.admin)
            # a fresh command ("открой проводник") abandons the question
            if re.match(_LAUNCH + r"\b|" + _CLOSE + r"\b", text):
                return None
            query = re.sub(r"^(?:игру|игра|программу|приложение)\s+", "", text)
            result = match_app(query, ctx.apps, dialog.kind)
            if result.best:
                return self._app_plan(result.best, dialog.intent, dialog.admin)
            if result.ambiguous:
                return self._ambiguous(result.candidates, dialog.intent, dialog.kind, dialog.admin, ctx)
            what = "игру" if dialog.kind == AppKind.GAME else "программу"
            return Plan("clarify", dialog.intent, f"Не нашёл {what} «{query}». Назовите ещё раз или скажите «отмена».",
                        options=list(dialog.options), dialog=DialogState(**{**dialog.__dict__,
                                                                            "expires_at": ctx.now + DIALOG_TTL_S}))
        return None

    # ------------------------------------------------------------------ power
    def _power(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        if re.search(r"отмени\w* (?:выключени|перезагрузк)", text):
            return Plan("actions", "power.abort", actions=[ActionRequest(action="power.abort")])
        target = r"(?:компьютер|комп|пк|систему|windows|виндовс)"
        delay = self._delay(text)
        if re.search(r"(?:перезагрузи|перезапусти|перезагрузка|перезагрузить)\s*" + target + r"?\b", text) and \
                re.search(r"перезагруз|перезапусти " + target, text):
            return Plan("actions", "power.restart",
                        actions=[ActionRequest(action="power.restart", params={"delay_s": delay})])
        if re.search(r"(?:выключи|выключить|отключи|заверши работу|завершение работы)\s*" + target, text) or \
                re.fullmatch(r"заверши(?:ть)? работу(?: windows| компьютера)?", text):
            return Plan("actions", "power.shutdown",
                        actions=[ActionRequest(action="power.shutdown", params={"delay_s": delay})])
        return None

    @staticmethod
    def _delay(text: str) -> int:
        match = re.search(r"через (.+?) (секунд|минут)", text)
        if match:
            number = extract_number(match.group(1)) or 1
            return min(3600, number * (60 if match.group(2) == "минут" else 1))
        if re.search(r"через минуту", text):
            return 60
        if re.search(r"сейчас|немедленно|сразу", text):
            return 5
        return 60

    # ------------------------------------------------------------------ modes
    def _mode(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        if re.search(r"(?:режим\w* тишин\w*|тих\w* режим|не беспокоить)", text):
            off = re.search(r"(?:выйди|выключи|отключи|отмени|заверши|выход)", text)
            enabled = not off
            return Plan("actions", "profile.silent",
                        actions=[ActionRequest(action="profile.silent", params={"enabled": enabled})])
        if re.search(r"(?:режим|переключись|перейди|включи|работай)", text):
            if re.search(r"\b(?:онлайн|online|интернет\w*|сетев\w*)\b", text):
                return Plan("actions", "mode.set", actions=[ActionRequest(action="mode.set", params={"mode": "ONLINE"})])
            if re.search(r"\b(?:офлайн|оффлайн|offline|локальн\w*|local|автономн\w*|без интернета)\b", text):
                return Plan("actions", "mode.set", actions=[ActionRequest(action="mode.set", params={"mode": "LOCAL"})])
        return None

    # ------------------------------------------------------------------ volume
    def _volume(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        about_sound = re.search(r"(?:громкост\w*|звук\w*|громче|тише|mute|мьют)", text)
        if not about_sound:
            return None
        if re.search(r"(?:выключи|отключи|убери|заглуши|без|вырубай|выруби|замьють)\w* ?(?:весь )?звук|^mute$|^тишина$",
                     text):
            return Plan("actions", "volume.mute", actions=[ActionRequest(action="volume.mute", params={"muted": True})])
        if re.search(r"(?:включи|верни|вруби)\w* ?звук", text):
            return Plan("actions", "volume.mute", actions=[ActionRequest(action="volume.mute", params={"muted": False})])
        number = extract_number(text)
        up = re.search(r"(?:увелич|прибав|подними|повыс|громче|добав|больше)", text)
        down = re.search(r"(?:уменьш|убав|понизь|сниз|тише|меньше|опусти)", text)
        if up or down:
            delta = number if number is not None else 10
            delta = max(1, min(100, delta)) * (1 if up and not down else -1)
            return Plan("actions", "volume.change",
                        actions=[ActionRequest(action="volume.change", params={"delta": delta})])
        if number is not None and re.search(r"громкост", text):
            return Plan("actions", "volume.set",
                        actions=[ActionRequest(action="volume.set", params={"level": max(0, min(100, number))})])
        return None

    # ------------------------------------------------------------------ windows
    def _windows(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        if re.fullmatch(r"(?:сверни|свернуть|спрячь)(?: все)?(?: окна| программы)?|покажи рабочий стол", text):
            return Plan("actions", "window.minimize_all", actions=[ActionRequest(action="window.minimize_all")])
        if re.search(r"(?:разверни|верни|восстанови)(?: все)? окна", text):
            return Plan("actions", "window.restore_all", actions=[ActionRequest(action="window.restore_all")])
        return None

    # ------------------------------------------------------------------ system information
    def _system_info(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        topic = None
        if re.search(r"(?:свободно\w* мест\w*|мест\w* на диск\w*|сколько места|заполнен\w* диск)", text):
            topic = "disk"
        elif re.search(r"(?:как\w* (?:программы|приложения|процессы)|что (?:сейчас )?(?:запущено|открыто|работает))", text) \
                and re.search(r"(?:запущен|открыт|работа|сейчас|процесс)", text):
            topic = "processes"
        elif re.search(r"(?:оперативн\w*|памят\w*|озу|ram)\b", text) and re.search(r"(?:сколько|загруз|занят|свобод|памят)",
                                                                               text):
            topic = "memory"
        elif re.search(r"(?:процессор\w*|цп|cpu)", text) and re.search(r"(?:загруз|нагрузк|сколько|как)", text):
            topic = "cpu"
        elif re.search(r"(?:видеокарт\w*|gpu|графическ\w* процессор)", text):
            topic = "gpu"
        elif re.search(r"(?:который час|сколько (?:сейчас )?времени|какое (?:сейчас )?время|^время$)", text):
            topic = "time"
        elif re.search(r"(?:какое (?:сегодня )?число|какая (?:сегодня )?дата|какой (?:сегодня )?день|^дата$)", text):
            topic = "date"
        elif re.search(r"(?:состояние|статус|нагрузка|показатели) (?:системы|компьютера|пк)", text):
            topic = "stats"
        if topic is None:
            return None
        return Plan("actions", "system.info", actions=[ActionRequest(action="system.info", params={"topic": topic})])

    # ------------------------------------------------------------------ documents (stage 5)
    def _documents(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        if re.search(r"(?:подготовь|создай|сделай|напиши|сгенерируй)\s+(?:\w+\s+)?(?:презентаци\w*|документ|доклад|отчет|"
                     r"таблиц\w*|pdf|ворд)", text) and not re.search(r"папк", text):
            return Plan("unavailable", "documents.create",
                        "Создание документов и презентаций появится в модуле документов (этап 5). "
                        "Сейчас я могу открыть Word или PowerPoint, если они есть в реестре.")
        return None

    # ------------------------------------------------------------------ web / browser
    def _web(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        match = re.search(r"(?:найди|поищи|ищи|загугли|погугли|узнай|посмотри)\s+(?:мне\s+)?(?:в интернете|в сети|в гугле|"
                          r"в яндексе|актуальн\w* информаци\w*|информаци\w*|новости)\s*(?:(?:на тему|по теме|об|о|про|по)\s+)?(.*)",
                          text)
        if not match:
            match = re.search(r"(?:загугли|погугли)\s+(.*)", text)
        if match:
            query = match.group(1).strip()
            if not query:
                return Plan("reply", "web.search", "Что найти в интернете?")
            return Plan("actions", "web.search", actions=[ActionRequest(action="web.search", params={"query": query})])
        nav = re.search(r"(?:перейди|зайди|открой|откройте)\s+(?:браузер\s+и\s+(?:перейди|зайди|открой)\s+)?"
                        r"(?:на\s+)?(?:сайт|страницу|адрес)?\s*(.+)", text)
        if nav:
            target = nav.group(1).strip()
            url = self._url(target)
            if url:
                return Plan("actions", "browser.open_url",
                            actions=[ActionRequest(action="browser.open_url", params={"url": url})])
        return None

    @staticmethod
    def _url(target: str) -> Optional[str]:
        domain = _DOMAIN.search(target)
        if domain:
            url = domain.group(1)
            return url if url.startswith(("http://", "https://")) else "https://" + url
        word = target.split()[0] if target.split() else ""
        if word in _SITES and len(target.split()) <= 2:
            return _SITES[word]
        return None

    # ------------------------------------------------------------------ files and folders
    def _files(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        create = re.search(r"(?:создай|создать|сделай)\s+(?:нов\w+\s+)?(?:папк\w*|каталог\w*|директори\w*)\s*(.*)", text)
        if create:
            rest = create.group(1)
            parent = _folder_key(rest) or "desktop"
            rest = _strip_folder_phrase(rest)
            named = re.search(r"(?:с названием|под названием|с именем|названием|именем|назови(?:те)?)\s+(.+)", rest)
            if named:
                name = _original_case(ctx.raw, named.group(1).strip(" .\"'«»"))
                return Plan("actions", "files.create_folder",
                            actions=[ActionRequest(action="files.create_folder", params={"name": name, "parent": parent})])
            hint = re.sub(r"^(?:для|под)\s+", "", rest).strip()
            options = [hint.capitalize()] if hint else []
            return Plan("clarify", "files.create_folder", "Как назвать папку?", options=options,
                        dialog=DialogState("create_folder", "Как назвать папку?", parent=parent,
                                           expires_at=ctx.now + DIALOG_TTL_S))
        search = re.search(r"(?:найди|поищи|ищи|где лежит|где находится|отыщи)\s+(?:мне\s+)?(?:файл\w*|документ\w*|папк\w*)?"
                           r"\s*(.*)", text)
        if search and (re.search(r"файл|документ|папк", text) or _folder_key(text)):
            rest = search.group(1)
            scope = _folder_key(rest)
            query = _strip_folder_phrase(rest)
            query = re.sub(r"^(?:(?:с|со|по|под)\s+)?(?:названи\w*|имен\w*)\s+|^(?:с|со|по|про)\s+", "", query)
            query = re.sub(r"\b(?:на|в|во)\s*$", "", query).strip(" .\"'«»")
            if not query:
                return Plan("reply", "files.search", "Какой файл найти? Назовите часть имени.")
            params = {"query": query}
            if scope:
                params["scope"] = scope
            return Plan("actions", "files.search", actions=[ActionRequest(action="files.search", params=params)])
        if re.search(r"(?:открой|запусти|покажи)\s+(?:мне\s+)?проводник", text):
            folder = _folder_key(text)
            return Plan("actions", "explorer.open",
                        actions=[ActionRequest(action="explorer.open", params={"folder": folder} if folder else {})])
        folder_open = re.fullmatch(r"(?:открой|покажи)\s+(?:папку\s+)?(.+)", text)
        if folder_open:
            key = _folder_key(folder_open.group(1))
            if key and not _strip_folder_phrase(folder_open.group(1)).replace("папку", "").strip():
                return Plan("actions", "explorer.open",
                            actions=[ActionRequest(action="explorer.open", params={"folder": key})])
        return None

    # ------------------------------------------------------------------ scenarios
    def _scenario(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        stripped = re.sub(r"^(?:включи|запусти|активируй|перейди в|переключись в|режим)\s+", "", text)
        best, best_score = None, 0.0
        for scenario in ctx.scenarios:
            if not scenario.enabled:
                continue
            for name in (scenario.name, *scenario.aliases):
                n = normalize(name)
                score = 1.0 if n in (text, stripped) else similarity(stripped, n)
                if score > best_score:
                    best, best_score = scenario, score
        if best and best_score >= 0.86:
            return Plan("actions", "scenario.run",
                        actions=[ActionRequest(action="scenario.run", params={"scenario_id": best.id})],
                        labels={best.id: best.name})
        return None

    # ------------------------------------------------------------------ close application
    def _close(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        match = re.match(_CLOSE + r"\s+(?:программу|приложение|игру)?\s*(.+)", text)
        if not match:
            return None
        query = match.group(1).strip()
        result = match_app(query, ctx.apps)
        if result.best:
            return self._app_plan(result.best, "close")
        if result.ambiguous:
            return self._ambiguous(result.candidates, "close", None, False, ctx)
        return None

    # ------------------------------------------------------------------ launch
    def _launch(self, text: str, ctx: RouterContext) -> Optional[Plan]:
        match = re.match(_LAUNCH + r"(?:\s+(.*))?$", text)
        if not match:
            return None
        rest = (match.group(1) or "").strip()
        admin = bool(re.search(r"(?:от имени|с правами) администратора|как администратор\w*", rest))
        rest = re.sub(r"\s*(?:от имени|с правами) администратора|\s*как администратор\w*", "", rest).strip()
        kind: Optional[AppKind] = None
        game = re.match(r"(?:мне\s+)?(?:игру|игрушку|игра)\b\s*(.*)", rest)
        if game:
            kind, rest = AppKind.GAME, game.group(1).strip()
        else:
            rest = re.sub(r"^(?:мне\s+)?(?:программу|приложение)\s+", "", rest)
        if not rest or rest in ("программу", "приложение", "что-нибудь", "что нибудь"):
            return self._ask_which(kind, admin, ctx)
        if rest == "браузер":
            result = match_app("браузер", ctx.apps)
            if result.best:
                return self._app_plan(result.best, "launch", admin)
            return Plan("actions", "browser.open_url",
                        actions=[ActionRequest(action="browser.open_url", params={"url": "https://duckduckgo.com/"})])
        result = match_app(rest, ctx.apps, kind)
        if result.best:
            return self._app_plan(result.best, "launch", admin)
        if result.ambiguous:
            return self._ambiguous(result.candidates, "launch", kind, admin, ctx)
        what = "игру" if kind == AppKind.GAME else "программу"
        return Plan("reply", "app.not_found",
                    f"Не нашёл {what} «{rest}» в реестре. Добавьте её в разделе «Приложения» "
                    f"или запустите поиск установленных программ.")

    def _ask_which(self, kind: Optional[AppKind], admin: bool, ctx: RouterContext) -> Plan:
        pool = [a for a in ctx.apps if a.enabled and (kind is None or a.kind == kind)]
        pool.sort(key=lambda a: (not a.pinned, -(a.last_launched or 0)))
        options = {a.name: a.id for a in pool[:6]}
        question = "Какую игру запустить?" if kind == AppKind.GAME else "Что запустить?"
        if kind == AppKind.GAME and not pool:
            return Plan("reply", "launch", "В реестре нет игр. Найдите их в разделе «Приложения» → «Найти установленные».")
        return Plan("clarify", "launch", question, options=list(options),
                    dialog=DialogState("launch", question, options=options, kind=kind, admin=admin,
                                       expires_at=ctx.now + DIALOG_TTL_S))

    def _ambiguous(self, candidates, intent, kind, admin, ctx: RouterContext) -> Plan:
        options = {m.entry.name: m.entry.id for m in candidates}
        question = "Нашёл несколько вариантов: " + ", ".join(options) + ". Какой именно?"
        return Plan("clarify", intent, question, options=list(options),
                    dialog=DialogState(intent, question, options=options, kind=kind, admin=admin,
                                       expires_at=ctx.now + DIALOG_TTL_S))

    @staticmethod
    def _app_plan(entry: AppEntry, intent: str, admin: bool = False) -> Plan:
        if intent == "close":
            action = "app.close"
        else:
            action = "app.launch_admin" if admin or entry.run_as_admin else "app.launch"
        return Plan("actions", action, actions=[ActionRequest(action=action, params={"app_id": entry.id})],
                    labels={entry.id: entry.name})
