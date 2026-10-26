"""Nazewnictwo używane w aplikacji zamiast angielskich nazw z TibiaWiki.

Reguła autora: "Gate of Expertise" zawsze nazywamy "bramka lvl-owa".
Zamiana działa na tekst z infoboxu (mianownik). Kroki piszemy ręcznie,
więc tam trzeba odmienić słowo (np. "przez bramkę lvl-ową"); pilnuje tego
test w tests/test_generator.py, który nie przepuści angielskiej nazwy w danych.
"""

import re

# Liczba mnoga przed pojedynczą, żeby "Gates" nie zamieniło się w "bramka" + "s".
TERMS = {
    "Gates of Expertise": "bramki lvl-owe",
    "Gate of Expertise": "bramka lvl-owa",
}

# Bez względu na wielkość liter.
_PATTERNS = [(re.compile(re.escape(en), re.IGNORECASE), pl) for en, pl in TERMS.items()]


def apply_terms(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def find_forbidden(text: str) -> list[str]:
    """Angielskie nazwy (tak, jak wystąpiły w tekście), które nie powinny trafić do danych."""
    return [m.group(0) for pattern, _ in _PATTERNS for m in pattern.finditer(text)]
