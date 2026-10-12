"""Text normalization, transliteration and phonetic keys for Russian/English names."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_PUNCT = re.compile(r"[^\w\s%.:/\-+]", re.UNICODE)
_SPACES = re.compile(r"\s+")

_RU_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

# Applied in order to a latin string to get a rough "how it sounds" key, so that
# "киберпанк" (kiberpank) and "cyberpunk" end up close to each other.
_PHONETIC = [
    (r"ph", "f"), (r"ck", "k"), (r"qu", "kv"), (r"q", "k"), (r"x", "ks"), (r"w", "v"),
    (r"c(?=[ei])", "s"), (r"ch|kh", "h"), (r"c", "k"), (r"th", "t"), (r"ee|ea|ie", "i"), (r"oo", "u"),
    (r"y", "i"), (r"j", "dzh"), (r"zh", "j"), (r"(.)\1+", r"\1"),
]
_VOWELS = re.compile(r"[aeiou]")


def normalize(text: str) -> str:
    """Lowercase, ё→е, drop punctuation (keeps % . : / - + for numbers and URLs), collapse spaces."""
    text = unicodedata.normalize("NFKC", text).lower().replace("ё", "е")
    text = _PUNCT.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    return text.strip(" .")


def to_latin(text: str) -> str:
    return "".join(_RU_LAT.get(ch, ch) for ch in text)


def phonetic(text: str) -> str:
    key = to_latin(normalize(text))
    key = re.sub(r"[^a-z0-9 ]", "", key)
    for pattern, repl in _PHONETIC:
        key = re.sub(pattern, repl, key)
    return _SPACES.sub(" ", key).strip()


def skeleton(text: str) -> str:
    """Consonant skeleton: "steam" and "стим" both become "stm"."""
    return _VOWELS.sub("", phonetic(text)).replace(" ", "")


def similarity(query: str, candidate: str) -> float:
    """0..1 score, robust to script (кириллица/latin) and to a missing tail ("cyberpunk" vs "cyberpunk 2077")."""
    q, c = phonetic(query), phonetic(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    best = SequenceMatcher(None, q, c).ratio()
    q_tokens, c_tokens = q.split(), c.split()
    if len(q_tokens) < len(c_tokens):
        # Compare against windows of the candidate with the same number of tokens.
        n = len(q_tokens)
        for start in range(len(c_tokens) - n + 1):
            window = " ".join(c_tokens[start:start + n])
            ratio = SequenceMatcher(None, q, window).ratio()
            penalty = 0.04 if start == 0 else 0.08
            best = max(best, ratio - penalty)
    qs, cs = skeleton(query), skeleton(candidate)
    if len(qs) >= 3 and len(cs) >= 3:
        best = max(best, SequenceMatcher(None, qs, cs).ratio() * 0.92)
    return min(best, 1.0)
