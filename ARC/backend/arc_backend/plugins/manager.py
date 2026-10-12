"""Plugin Manager: import, verify, enable and grant permissions to declarative modules."""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from ..apps.matcher import match_app
from ..apps.registry import AppRegistry
from ..models import ActionRequest, Source
from ..permissions.catalog import CATALOG
from ..router.text import normalize, similarity
from ..storage.settings import PluginGrant, Settings, SettingsStore
from .manifest import MAX_FILE_BYTES, PluginCommand, PluginManifest
from .signing import verify

log = logging.getLogger(__name__)


class PluginError(ValueError):
    """User-facing reason why a module was refused."""


@dataclass
class Plugin:
    manifest: PluginManifest
    raw: dict[str, Any]          # manifest exactly as signed
    signature: Optional[dict[str, str]]
    trust: str                   # trusted | unsigned | untrusted_key | invalid
    signer: str = ""             # name of the trusted key

    @property
    def id(self) -> str:
        return self.manifest.id


@dataclass
class PluginMatch:
    plugin: Plugin
    command: PluginCommand
    requests: list[ActionRequest]
    labels: dict[str, str]
    error: str = ""


def parse_file(data: bytes) -> tuple[dict[str, Any], Optional[dict[str, str]]]:
    if len(data) > MAX_FILE_BYTES:
        raise PluginError("Файл модуля слишком большой (больше 256 КБ)")
    try:
        doc = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PluginError("Файл модуля повреждён: это не JSON")
    if not isinstance(doc, dict) or not isinstance(doc.get("manifest"), dict):
        raise PluginError("В файле нет описания модуля (manifest)")
    signature = doc.get("signature")
    if signature is not None and not (isinstance(signature, dict) and isinstance(signature.get("key_id"), str)
                                      and isinstance(signature.get("ed25519"), str)):
        raise PluginError("Подпись модуля в неверном формате")
    return doc["manifest"], signature


class PluginManager:
    def __init__(self, directory: Path, settings: SettingsStore, registry: AppRegistry):
        self.directory = directory
        self.settings = settings
        self.registry = registry
        self._lock = threading.RLock()
        self._plugins: dict[str, Plugin] = {}
        self.load_errors: list[str] = []
        self.reload()

    # ------------------------------------------------------------------ trust
    def _trust(self, raw: dict[str, Any], signature: Optional[dict[str, str]], settings: Settings) -> tuple[str, str]:
        if signature is None:
            return "unsigned", ""
        for key in settings.plugins.trusted_keys:
            if key.id == signature["key_id"]:
                return ("trusted", key.name) if verify(raw, signature["ed25519"], key.public_key) else ("invalid", "")
        return "untrusted_key", ""

    def _build(self, raw: dict[str, Any], signature: Optional[dict[str, str]]) -> Plugin:
        try:
            manifest = PluginManifest.model_validate(raw)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(map(str, first["loc"]))
            raise PluginError(f"Описание модуля некорректно: {where} — {first['msg']}")
        trust, signer = self._trust(raw, signature, self.settings.get())
        return Plugin(manifest, raw, signature, trust, signer)

    @staticmethod
    def _refusal(plugin: Plugin, settings: Settings) -> str:
        if plugin.trust == "invalid":
            return "Подпись модуля не сходится: файл изменён после подписания"
        if plugin.trust == "untrusted_key":
            return f"Модуль подписан неизвестным ключом {plugin.signature['key_id'] if plugin.signature else ''}. " \
                   "Добавьте ключ автора в доверенные, если доверяете ему"
        if plugin.trust == "unsigned" and not settings.plugins.allow_unsigned:
            return "Модуль не подписан. Неподписанные модули запрещены (можно разрешить в «Модули»)"
        return ""

    # ------------------------------------------------------------------ storage
    def reload(self) -> None:
        with self._lock:
            self._plugins.clear()
            self.load_errors = []
            if not self.directory.is_dir():
                return
            for path in sorted(self.directory.glob("*.arcplugin")):
                try:
                    raw, signature = parse_file(path.read_bytes())
                    plugin = self._build(raw, signature)
                    if plugin.id + ".arcplugin" != path.name:
                        raise PluginError("имя файла не совпадает с id модуля")
                    self._plugins[plugin.id] = plugin
                except (PluginError, OSError) as exc:
                    self.load_errors.append(f"{path.name}: {exc}")
                    log.warning("plugin %s not loaded: %s", path.name, exc)

    def list(self) -> list[Plugin]:
        with self._lock:
            return sorted(self._plugins.values(), key=lambda p: p.manifest.name.lower())

    def get(self, plugin_id: str) -> Optional[Plugin]:
        with self._lock:
            return self._plugins.get(plugin_id)

    def import_file(self, path: str) -> Plugin:
        if not path.lower().endswith(".arcplugin"):
            raise PluginError("Нужен файл модуля .arcplugin")
        try:
            with open(path, "rb") as fh:
                data = fh.read(MAX_FILE_BYTES + 1)
        except OSError as exc:
            raise PluginError(f"Не удалось прочитать файл: {exc.strerror or exc}")
        return self.import_bytes(data)

    def import_bytes(self, data: bytes) -> Plugin:
        raw, signature = parse_file(data)
        plugin = self._build(raw, signature)
        settings = self.settings.get()
        refusal = self._refusal(plugin, settings)
        if refusal:
            raise PluginError(refusal)
        with self._lock:
            existing = self._plugins.get(plugin.id)
            if existing is not None:
                if plugin.manifest.version_tuple() <= existing.manifest.version_tuple():
                    raise PluginError(f"Модуль «{existing.manifest.name}» версии {existing.manifest.version} "
                                      "уже установлен; можно установить только более новую версию")
                old_key = existing.signature["key_id"] if existing.signature else None
                new_key = plugin.signature["key_id"] if plugin.signature else None
                if old_key and old_key != new_key:
                    raise PluginError("Новая версия подписана другим ключом — обновление отклонено")
            self.directory.mkdir(parents=True, exist_ok=True)
            target = self.directory / f"{plugin.id}.arcplugin"
            tmp = target.with_suffix(".tmp")
            tmp.write_text(json.dumps({"manifest": raw, "signature": signature}, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, target)
            self._plugins[plugin.id] = plugin
            grants = dict(settings.plugins.grants)
            old = grants.get(plugin.id, PluginGrant())
            # an update keeps only permissions that are still requested; new ones start switched off
            grants[plugin.id] = PluginGrant(enabled=old.enabled if existing else False,
                                            modules=[m for m in old.modules if m in plugin.manifest.permissions])
            self._save_grants(grants)
        return plugin

    def remove(self, plugin_id: str) -> bool:
        with self._lock:
            plugin = self._plugins.pop(plugin_id, None)
            path = self.directory / f"{plugin_id}.arcplugin"
            if path.is_file():
                path.unlink()
            grants = dict(self.settings.get().plugins.grants)
            if grants.pop(plugin_id, None) is not None:
                self._save_grants(grants)
            return plugin is not None

    def _save_grants(self, grants: dict[str, PluginGrant]) -> None:
        self.settings.update({"plugins": {"grants": {k: v.model_dump() for k, v in grants.items()}}})

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        plugin = self._require(plugin_id)
        if enabled:
            refusal = self._refusal(plugin, self.settings.get())
            if refusal:
                raise PluginError(refusal)
        grants = dict(self.settings.get().plugins.grants)
        grant = grants.get(plugin_id, PluginGrant())
        grants[plugin_id] = PluginGrant(enabled=enabled, modules=grant.modules)
        self._save_grants(grants)

    def set_modules(self, plugin_id: str, modules: list[str]) -> None:
        plugin = self._require(plugin_id)
        extra = set(modules) - set(plugin.manifest.permissions)
        if extra:
            raise PluginError(f"Модуль не запрашивал: {', '.join(sorted(extra))}")
        grants = dict(self.settings.get().plugins.grants)
        grant = grants.get(plugin_id, PluginGrant())
        grants[plugin_id] = PluginGrant(enabled=grant.enabled, modules=sorted(set(modules)))
        self._save_grants(grants)

    def _require(self, plugin_id: str) -> Plugin:
        plugin = self.get(plugin_id)
        if plugin is None:
            raise KeyError("Модуль не найден")
        return plugin

    def refresh_trust(self) -> None:
        """After the list of trusted keys changed."""
        self.reload()

    # ------------------------------------------------------------------ view
    def view(self, plugin: Plugin, settings: Optional[Settings] = None) -> dict[str, Any]:
        settings = settings or self.settings.get()
        grant = settings.plugins.grants.get(plugin.id, PluginGrant())
        refusal = self._refusal(plugin, settings)
        m = plugin.manifest
        return {"id": m.id, "name": m.name, "version": m.version, "author": m.author, "description": m.description,
                "homepage": m.homepage, "permissions": m.permissions, "granted": grant.modules,
                "enabled": grant.enabled and not refusal, "trust": plugin.trust, "signer": plugin.signer,
                "key_id": plugin.signature["key_id"] if plugin.signature else None, "blocked": refusal,
                "commands": [{"phrases": c.phrases, "actions": [a.action for a in c.actions], "reply": c.reply}
                             for c in m.commands]}

    # ------------------------------------------------------------------ matching
    def match(self, text: str, source: Source) -> Optional[PluginMatch]:
        """Finds a phrase of an enabled module. Built-in commands always win: this is called only
        for phrases the router did not understand."""
        norm = normalize(text)
        if not norm:
            return None
        settings = self.settings.get()
        best: Optional[tuple[float, Plugin, PluginCommand]] = None
        for plugin in self.list():
            grant = settings.plugins.grants.get(plugin.id)
            if grant is None or not grant.enabled or self._refusal(plugin, settings):
                continue
            for command in plugin.manifest.commands:
                for phrase in command.phrases:
                    score = 1.0 if phrase == norm else similarity(norm, phrase) if len(phrase) >= 6 else 0.0
                    if score >= 0.9 and (best is None or score > best[0]):
                        best = (score, plugin, command)
        if best is None:
            return None
        _, plugin, command = best
        grant = settings.plugins.grants[plugin.id]
        result = PluginMatch(plugin, command, [], {})
        for item in command.actions:
            spec = CATALOG[item.action]
            if spec.module not in grant.modules:
                result.error = (f"Модулю «{plugin.manifest.name}» не выдано разрешение «{spec.module}». "
                                "Включите его в разделе «Модули».")
                return result
            params = dict(item.params)
            if item.app:
                entry = match_app(item.app, self.registry.list(include_disabled=False)).best
                if entry is None:
                    result.error = f"Программа «{item.app}» не найдена в реестре A.R.C."
                    return result
                params["app_id"] = entry.id
                result.labels[entry.id] = entry.name
            result.requests.append(ActionRequest(action=item.action, params=params, source=Source.PLUGIN))
        return result
