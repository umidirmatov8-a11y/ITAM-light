"""Data Sanitization Layer.

Replaces sensitive values with stable placeholders before data is sent to an external
AI provider:

==================  ==========================
usernames           ``[USER_001]``
e-mail addresses    ``[USER_EMAIL_001]``
internal IPs        ``[INTERNAL_IP_001]``
external IPs        ``[EXTERNAL_IP_001]`` (optional - they are usually the IOC under analysis)
hostnames           ``[HOST_001]``
internal domains    ``[DOMAIN_001]``
phone / card data   ``[PHONE_001]`` / ``[CARD_NUMBER]``
passwords, tokens,  ``[REDACTED_SECRET]`` (never restored)
cookies, API keys
==================  ==========================

The mapping lives only in memory for the duration of one request so that the AI answer
can be restored (``restore``) for display.  Secrets are irreversibly removed.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from app.core.config import PrivacyConfig
from app.utils.net import NetworkClassifier

_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),  # JWT
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}"),  # OpenAI / Anthropic style keys
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),  # GitHub tokens
    re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"),  # Slack tokens
]
# key=value / key: value forms; the value is replaced, the key is kept for context
_SECRET_KV = re.compile(
    r"(?i)\b(pass(?:word|wd)?|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|auth[_-]?token|session[_-]?id|"
    r"client[_-]?secret|private[_-]?key)(\s*[=:]\s*|\"\s*:\s*\")([^\s\"'&;,]{3,})")
_AUTH_HEADER = re.compile(r"(?i)\b(authorization|proxy-authorization)(\s*:\s*)(?:bearer|basic|digest|negotiate|ntlm)?\s*"
                          r"[A-Za-z0-9._~+/=-]{6,}")
_COOKIE = re.compile(r"(?i)\b(cookie|set-cookie)(\s*:\s*)[^\r\n]+")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IPV4 = re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\w.])")
_IPV6 = re.compile(r"(?<![\w:])(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}(?![\w:])")
_PHONE = re.compile(r"(?<!\w)\+\d{1,3}[\s-]?\(?\d{2,3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_WIN_PROFILE = re.compile(r"(?i)([a-z]:\\users\\)([^\\\s\"']+)")
_NIX_HOME = re.compile(r"(/home/)([^/\s\"']+)")
_DOMAIN_USER = re.compile(r"(?<![\w\\])([A-Za-z][\w.-]{0,30})\\([A-Za-z0-9._$-]{1,64})(?![\w\\])")
_LOG_USER = re.compile(r"(?i)\b(?:user(?:name)?[=:\s]+|for (?:invalid user )?|invalid user |acct=\"?|uid=\w+\(|"
                       r"targetusername[=:\s\"]+|subjectusername[=:\s\"]+)([A-Za-z0-9._$@-]{2,64})")

USER_KEYS = {"user", "users", "username", "dstuser", "srcuser", "source_user", "target_user", "account",
             "affected_users", "targetusername", "subjectusername", "acct"}
HOST_KEYS = {"agent", "agent_name", "host", "hostname", "computer", "affected_hosts", "hosts", "entity",
             "workstationname", "dvchost"}
_SYSTEM_ACCOUNTS = {"root", "system", "administrator", "admin", "-", "nt authority", "local service",
                    "network service", "unknown", "n/a", "none"}


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class Sanitizer:
    def __init__(self, privacy: PrivacyConfig, network: NetworkClassifier | None = None,
                 known_users: Iterable[str] = (), known_hosts: Iterable[str] = ()):
        self.cfg = privacy
        self.network = network or NetworkClassifier()
        self.forward: dict[tuple[str, str], str] = {}
        self.reverse: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        self.redacted_secrets = 0
        self.internal_domains = [d.lower().lstrip(".") for d in privacy.internal_domains if d]
        self.known_users = sorted({u for u in known_users if u and u.lower() not in _SYSTEM_ACCOUNTS},
                                  key=len, reverse=True)
        self.known_hosts = sorted({h for h in known_hosts if h}, key=len, reverse=True)
        self._user_re = self._word_regex(self.known_users) if privacy.mask_usernames else None
        self._host_re = self._word_regex(self.known_hosts) if privacy.mask_hostnames else None
        self._domain_re = (re.compile(r"\b(?:[A-Za-z0-9-]+\.)*(?:" + "|".join(re.escape(d) for d in self.internal_domains)
                                      + r")\b", re.I) if self.internal_domains and privacy.mask_domains else None)

    @staticmethod
    def _word_regex(words: list[str]) -> re.Pattern[str] | None:
        if not words:
            return None
        return re.compile(r"(?<![\w.@-])(" + "|".join(re.escape(w) for w in words[:2000]) + r")(?![\w@-])", re.I)

    # ------------------------------------------------------------------ placeholders
    def _placeholder(self, kind: str, value: str) -> str:
        key = (kind, value.lower())
        existing = self.forward.get(key)
        if existing:
            return existing
        self._counters[kind] = self._counters.get(kind, 0) + 1
        placeholder = f"[{kind}_{self._counters[kind]:03d}]"
        self.forward[key] = placeholder
        self.reverse[placeholder] = value
        return placeholder

    def user(self, value: str) -> str:
        if not value or not self.cfg.mask_usernames or value.lower() in _SYSTEM_ACCOUNTS or value.startswith("["):
            return value
        return self._placeholder("USER", value)

    def host(self, value: str) -> str:
        if not value or not self.cfg.mask_hostnames or value.startswith("["):
            return value
        return self._placeholder("HOST", value)

    def ip(self, value: str) -> str:
        internal = self.network.is_internal(value)
        if internal is None:
            return value
        if internal and self.cfg.mask_internal_ips:
            return self._placeholder("INTERNAL_IP", value)
        if not internal and self.cfg.mask_external_ips:
            return self._placeholder("EXTERNAL_IP", value)
        return value

    # ------------------------------------------------------------------ text
    def sanitize_text(self, text: str) -> str:
        if not text:
            return text
        text = self._redact_secrets(text)
        if self.cfg.mask_emails:
            text = _EMAIL.sub(lambda m: self._placeholder("USER_EMAIL", m.group(0)), text)
        if self.cfg.mask_usernames:
            text = _WIN_PROFILE.sub(lambda m: m.group(1) + self.user(m.group(2)), text)
            text = _NIX_HOME.sub(lambda m: m.group(1) + self.user(m.group(2)), text)
            text = _DOMAIN_USER.sub(lambda m: self._domain_user(m), text)
            text = _LOG_USER.sub(lambda m: m.group(0)[: m.start(1) - m.start(0)] + self.user(m.group(1)), text)
            if self._user_re:
                text = self._user_re.sub(lambda m: self.user(m.group(1)), text)
        if self._domain_re:
            text = self._domain_re.sub(lambda m: self._placeholder("DOMAIN", m.group(0)), text)
        if self._host_re:
            text = self._host_re.sub(lambda m: self.host(m.group(1)), text)
        text = _IPV4.sub(lambda m: self.ip(m.group(0)), text)
        if ":" in text:
            text = _IPV6.sub(lambda m: self.ip(m.group(0)), text)
        if self.cfg.mask_personal_data:
            text = _PHONE.sub(lambda m: self._placeholder("PHONE", m.group(0)), text)
            text = _CARD.sub(self._card, text)
        return text

    def _domain_user(self, match: re.Match[str]) -> str:
        domain, user = match.group(1), match.group(2)
        if domain.upper() in ("NT AUTHORITY", "BUILTIN") or len(domain) == 1:  # drive letters C:\
            return match.group(0)
        masked_domain = self._placeholder("DOMAIN", domain) if self.cfg.mask_domains else domain
        return f"{masked_domain}\\{self.user(user)}"

    def _card(self, match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits) and len(set(digits)) > 1:
            return "[CARD_NUMBER]"
        return match.group(0)

    def _redact_secrets(self, text: str) -> str:
        before = text
        for pattern in _SECRET_PATTERNS:
            text = pattern.sub("[REDACTED_SECRET]", text)
        text = _SECRET_KV.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_SECRET]", text)
        text = _AUTH_HEADER.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_SECRET]", text)
        text = _COOKIE.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED_SECRET]", text)
        if text != before:
            self.redacted_secrets += 1
        return text

    # ------------------------------------------------------------------ structures
    def sanitize(self, obj: Any, key: str = "") -> Any:
        lowered = key.lower()
        if isinstance(obj, dict):
            return {k: self.sanitize(v, str(k)) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.sanitize(v, key) for v in obj]
        if isinstance(obj, str):
            if lowered in USER_KEYS and obj and " " not in obj:
                if "\\" in obj:
                    return self.sanitize_text(obj)
                return self.user(obj)
            if lowered in HOST_KEYS and obj and " " not in obj:
                return self.host(obj)
            return self.sanitize_text(obj)
        return obj

    def restore(self, obj: Any) -> Any:
        if isinstance(obj, str):
            if "[" not in obj:
                return obj
            return re.sub(r"\[[A-Z_]+_\d{3}\]", lambda m: self.reverse.get(m.group(0), m.group(0)), obj)
        if isinstance(obj, list):
            return [self.restore(v) for v in obj]
        if isinstance(obj, dict):
            return {k: self.restore(v) for k, v in obj.items()}
        return obj

    @property
    def replacements(self) -> int:
        return len(self.forward)
