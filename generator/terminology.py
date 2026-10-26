"""Słownik nazewnictwa jest w aplikacji (tibiahelper.core.terminology).

Ten moduł zostaje, żeby generator importował go jak dawniej. Słownik musi być
w aplikacji, bo edytor w trybie autora też go używa (a generator nie trafia do .exe).
"""

from tibiahelper.core.terminology import TERMS, apply_terms, find_forbidden

__all__ = ["TERMS", "apply_terms", "find_forbidden"]
