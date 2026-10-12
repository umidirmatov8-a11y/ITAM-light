"""Russian number words → int ("двадцать пять", "на пятьдесят процентов", "до сорока")."""
from __future__ import annotations

import re
from typing import Optional

_UNITS = {
    "ноль": 0, "нуля": 0, "один": 1, "одна": 1, "одну": 1, "одного": 1, "два": 2, "две": 2, "двух": 2,
    "три": 3, "трех": 3, "четыре": 4, "четырех": 4, "пять": 5, "пяти": 5, "шесть": 6, "шести": 6,
    "семь": 7, "семи": 7, "восемь": 8, "восьми": 8, "девять": 9, "девяти": 9,
}
_TEENS = {
    "десять": 10, "десяти": 10, "одиннадцать": 11, "одиннадцати": 11, "двенадцать": 12, "двенадцати": 12,
    "тринадцать": 13, "тринадцати": 13, "четырнадцать": 14, "четырнадцати": 14, "пятнадцать": 15,
    "пятнадцати": 15, "шестнадцать": 16, "шестнадцати": 16, "семнадцать": 17, "семнадцати": 17,
    "восемнадцать": 18, "восемнадцати": 18, "девятнадцать": 19, "девятнадцати": 19,
}
_TENS = {
    "двадцать": 20, "двадцати": 20, "тридцать": 30, "тридцати": 30, "сорок": 40, "сорока": 40,
    "пятьдесят": 50, "пятидесяти": 50, "шестьдесят": 60, "шестидесяти": 60, "семьдесят": 70,
    "семидесяти": 70, "восемьдесят": 80, "восьмидесяти": 80, "девяносто": 90, "девяноста": 90,
}
_HUNDREDS = {"сто": 100, "ста": 100, "двести": 200, "триста": 300, "четыреста": 400, "пятьсот": 500}
_SPECIAL = {"половину": 50, "половина": 50, "наполовину": 50, "максимум": 100, "максимальную": 100,
            "минимум": 0, "минимальную": 0}

_DIGITS = re.compile(r"(?<![\w.])(\d{1,4})(?:\s*%|\s*процент\w*)?")


def parse_number_words(tokens: list[str]) -> Optional[int]:
    total, found, last_order = 0, False, 1000
    for token in tokens:
        for table, order in ((_HUNDREDS, 100), (_TENS, 10), (_TEENS, 1), (_UNITS, 1)):
            if token in table:
                if order >= last_order and found:
                    return total  # "двадцать тридцать" — stop at the first complete number
                total += table[token]
                found = True
                last_order = order if table is not _TEENS else 0
                break
        else:
            if found:
                return total
    return total if found else None


def extract_number(text: str) -> Optional[int]:
    """First number in the phrase, digits or words."""
    match = _DIGITS.search(text)
    if match:
        return int(match.group(1))
    tokens = text.split()
    for index, token in enumerate(tokens):
        if token in _SPECIAL:
            return _SPECIAL[token]
        if token in _UNITS or token in _TEENS or token in _TENS or token in _HUNDREDS:
            return parse_number_words(tokens[index:])
    return None
