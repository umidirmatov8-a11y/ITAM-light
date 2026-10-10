"""Password generation and client-side pre-validation against the domain password policy.

The final decision always belongs to the domain controller (history, minimum age and fine-grained password policies
cannot be fully evaluated on the client). Generated passwords are never logged or persisted.
"""
from __future__ import annotations

import math
import re
import secrets
import string
from dataclasses import dataclass

from ..models.connection import DomainPolicy

AMBIGUOUS = set("Il1O0o|`'\";:,.")
DEFAULT_SYMBOLS = "!@#$%^&*()-_=+[]{}?"


@dataclass
class PasswordOptions:
    length: int = 16
    lower: bool = True
    upper: bool = True
    digits: bool = True
    symbols: bool = True
    exclude_ambiguous: bool = True
    symbol_set: str = DEFAULT_SYMBOLS

    def pools(self) -> list[str]:
        pools = []
        if self.lower:
            pools.append(string.ascii_lowercase)
        if self.upper:
            pools.append(string.ascii_uppercase)
        if self.digits:
            pools.append(string.digits)
        if self.symbols:
            pools.append(self.symbol_set or DEFAULT_SYMBOLS)
        if self.exclude_ambiguous:
            pools = ["".join(c for c in p if c not in AMBIGUOUS) for p in pools]
        return [p for p in pools if p]


def generate_password(options: PasswordOptions | None = None) -> str:
    opts = options or PasswordOptions()
    pools = opts.pools()
    if not pools:
        raise ValueError("Выберите хотя бы один набор символов")
    if opts.length < len(pools) or opts.length < 4:
        raise ValueError(f"Минимальная длина пароля — {max(4, len(pools))}")
    if opts.length > 256:
        raise ValueError("Максимальная длина пароля — 256")
    alphabet = "".join(sorted(set("".join(pools))))
    chars = [secrets.choice(p) for p in pools]
    chars += [secrets.choice(alphabet) for _ in range(opts.length - len(chars))]
    rnd = secrets.SystemRandom()
    rnd.shuffle(chars)
    return "".join(chars)


def entropy_bits(options: PasswordOptions) -> float:
    alphabet = set("".join(options.pools()))
    if not alphabet:
        return 0.0
    return round(options.length * math.log2(len(alphabet)), 1)


def _categories(password: str) -> int:
    cats = 0
    if any(c.isupper() for c in password):
        cats += 1
    if any(c.islower() for c in password):
        cats += 1
    if any(c.isdigit() for c in password):
        cats += 1
    if any(not c.isalnum() for c in password):
        cats += 1
    if any(c.isalpha() and not c.isupper() and not c.islower() for c in password):
        cats += 1
    return cats


def check_complexity(password: str, sam_account_name: str = "", display_name: str = "") -> list[str]:
    """Windows 'Password must meet complexity requirements' rules. Returns a list of problems."""
    problems = []
    lowered = password.casefold()
    if sam_account_name and len(sam_account_name) >= 3 and sam_account_name.casefold() in lowered:
        problems.append("Пароль содержит имя входа пользователя")
    for token in re.split(r"[,.\-_#\s\t]+", display_name or ""):
        if len(token) >= 3 and token.casefold() in lowered:
            problems.append(f"Пароль содержит часть полного имени («{token}»)")
            break
    if _categories(password) < 3:
        problems.append("Пароль должен содержать символы минимум трёх категорий: прописные, строчные, цифры, спецсимволы")
    return problems


def validate_against_policy(password: str, policy: DomainPolicy | None, sam_account_name: str = "",
                            display_name: str = "") -> list[str]:
    problems = []
    if not password:
        return ["Пароль не задан"]
    min_len = (policy.min_pwd_length if policy else 0) or 0
    if len(password) < min_len:
        problems.append(f"Минимальная длина по политике домена — {min_len} символов")
    if policy is None or policy.complexity:
        problems.extend(check_complexity(password, sam_account_name, display_name))
    return problems


def policy_summary(policy: DomainPolicy | None) -> str:
    if policy is None:
        return "Политика паролей домена не прочитана"
    parts = [f"мин. длина {policy.min_pwd_length}", "сложность " + ("включена" if policy.complexity else "выключена"),
             f"история {policy.pwd_history_length}"]
    if policy.max_pwd_age_days:
        parts.append(f"макс. срок {policy.max_pwd_age_days:.0f} дн.")
    return "Политика домена: " + ", ".join(parts) + ". История паролей и PSO проверяются контроллером домена."
