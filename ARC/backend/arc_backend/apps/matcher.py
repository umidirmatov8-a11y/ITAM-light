"""Find registry entries by a spoken name ("телеграм", "киберпанк", "стим")."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from ..router.text import normalize, similarity
from .registry import AppEntry, AppKind

ACCEPT = 0.78       # minimal score to consider a match
AMBIGUITY = 0.04    # candidates closer than this to the best one are ambiguous

# Common Russian names for popular programs; used both by discovery (as default aliases)
# and by the matcher, so that "телега" finds "Telegram" even without user aliases.
KNOWN_ALIASES: dict[str, list[str]] = {
    "telegram": ["телеграм", "телеграмм", "телега"],
    "steam": ["стим"],
    "google chrome": ["хром", "гугл хром", "браузер хром"],
    "chrome": ["хром"],
    "mozilla firefox": ["файрфокс", "фаерфокс", "мозилла"],
    "firefox": ["файрфокс", "фаерфокс"],
    "microsoft edge": ["эдж", "edge"],
    "yandex": ["яндекс", "яндекс браузер"],
    "discord": ["дискорд"],
    "word": ["ворд"],
    "excel": ["эксель", "excel"],
    "powerpoint": ["пауэрпоинт", "поверпоинт"],
    "outlook": ["аутлук"],
    "spotify": ["спотифай"],
    "visual studio code": ["вс код", "вскод", "vs code", "код"],
    "obs studio": ["обс"],
    "vlc media player": ["влц", "плеер vlc"],
    "notepad++": ["нотпад", "блокнот плюс плюс"],
    "cyberpunk 2077": ["киберпанк"],
    "the witcher 3": ["ведьмак", "ведьмак 3"],
    "counter-strike 2": ["кс", "контра", "каэс"],
    "dota 2": ["дота"],
    "epic games launcher": ["эпик", "эпик геймс"],
    "zoom": ["зум"],
    "skype": ["скайп"],
    "whatsapp": ["ватсап", "вотсап"],
    "1c": ["1с", "один с"],
}


def default_aliases(name: str) -> list[str]:
    key = normalize(name)
    for known, aliases in KNOWN_ALIASES.items():
        if key == known or key.startswith(known + " ") or key.endswith(" " + known):
            return list(aliases)
    return []


@dataclass
class Match:
    entry: AppEntry
    score: float


@dataclass
class MatchResult:
    best: Optional[AppEntry]
    candidates: list[Match]

    @property
    def ambiguous(self) -> bool:
        return self.best is None and len(self.candidates) > 1


def score_entry(query: str, entry: AppEntry) -> float:
    names = [entry.name, *entry.aliases, *default_aliases(entry.name)]
    q = normalize(query)
    best = 0.0
    for name in names:
        n = normalize(name)
        if not n:
            continue
        if q == n:
            return 1.0
        best = max(best, similarity(q, n))
    return best


def match_app(query: str, entries: Iterable[AppEntry], kind: AppKind | None = None) -> MatchResult:
    pool = [e for e in entries if e.enabled and (kind is None or e.kind == kind)]
    scored = sorted((Match(e, score_entry(query, e)) for e in pool), key=lambda m: m.score, reverse=True)
    scored = [m for m in scored if m.score >= ACCEPT]
    if not scored:
        return MatchResult(None, [])
    top = scored[0]
    close = [m for m in scored if top.score - m.score < AMBIGUITY]
    if len(close) == 1 or top.score == 1.0 and (len(close) == 1 or close[1].score < 1.0):
        return MatchResult(top.entry, scored[:5])
    return MatchResult(None, close[:5])
