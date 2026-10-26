"""Nazewnictwo używane w aplikacji zamiast angielskich nazw z TibiaWiki.

Reguła autora: "Gate of Expertise" zawsze nazywamy "bramka lvl-owa".
Zamiana działa na tekst z infoboxu (mianownik). Kroki piszemy ręcznie,
więc tam trzeba odmienić słowo (np. "przez bramkę lvl-ową"); pilnuje tego
test w tests/test_generator.py, który nie przepuści angielskiej nazwy w danych.
"""

import re

TERMS = {
    "Gate of Expertise": "bramka lvl-owa",
}

# Bez względu na wielkość liter i z opcjonalnym "s" na końcu (Gates of Expertise).
_PATTERNS = [
    (re.compile(re.escape(en).replace("Gate", "Gates?"), re.IGNORECASE), pl)
    for en, pl in TERMS.items()
]


def apply_terms(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def find_forbidden(text: str) -> list[str]:
    """Angielskie nazwy, które nie powinny trafić do danych aplikacji."""
    return [pattern.pattern for pattern, _ in _PATTERNS if pattern.search(text)]
