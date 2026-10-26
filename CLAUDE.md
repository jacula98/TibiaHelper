# TibiaHelper

Małe okno „zawsze na wierzchu” (Windows) z uproszczonymi poradnikami questów Tibii.

- **Stack:** Python 3.12, PySide6, pydantic. Testy: pytest.
- **Kod:** `app/tibiahelper/` (aplikacja), `generator/` (narzędzie autora, pobiera dane z TibiaWiki), `tests/`.
- **Dane:** `data/quests.json` (licencja CC BY-SA 4.0, kod na MIT). Aplikacja pokazuje tylko questy ze statusem `reviewed`.

## Zasady pracy

- Praca etapami. Jeden etap to jeden PR. Następny etap zaczynamy dopiero po akceptacji autora.
- Komunikacja po polsku, krótko. Przy kodzie krótko wyjaśniamy, dlaczego coś jest zrobione w dany sposób.
- Małe zmiany: łatwiej je przejrzeć i cofnąć.
- Bez płatnych usług i narzędzi (także bez GitHub Actions). Wszystkie sprawdzenia działają lokalnie.

## Nazewnictwo w danych i UI

- „Gate of Expertise” zawsze nazywamy „bramka lvl-owa” (odmieniamy: „przez bramkę lvl-ową”, „do bramki lvl-owej”).
  Słownik zamian jest w `generator/terminology.py`, a test pilnuje, żeby angielska nazwa nie trafiła do `data/quests.json`.

## Czego nie robimy

- Aplikacja nie łączy się z TibiaWiki. Robi to tylko generator, uruchamiany przez autora.
- Brak automatyzacji gry i czytania jej pamięci: to tylko poradnik.

## Sprawdzenie przed PR

```
python scripts/check.py
```

Skrypt uruchamia ruff (jeśli jest zainstalowany), pytest i walidację `data/quests.json`.
Następnie `/code-review` i `/security-review` w Claude Code, a wynik krótko w opisie PR.
Zasady review są w [REVIEW.md](REVIEW.md).
