# TibiaHelper

Małe okno „zawsze na wierzchu” (Windows) z uproszczonymi poradnikami questów Tibii.

- **Stack:** Python 3.12, PySide6, pydantic. Testy: pytest.
- **Kod:** `app/tibiahelper/` (aplikacja), `generator/` (narzędzie autora, pobiera dane z TibiaWiki), `tests/`.
- **Dane:** `data/quests.json` (questy i potwory z TibiaWiki, CC BY-SA 4.0, kod na MIT) i `data/spawns.json`
  (miejsca potworów z TibiaRoute, za zgodą). Aplikacja pokazuje tylko questy ze statusem `reviewed`.
  Źródła i zgody: `docs/zrodla-danych.md`. Instrukcje dla autora: `docs/AUTOR.md` (README jest dla graczy).

## Zasady pracy

- Praca etapami. Jeden etap to jeden PR. Następny etap zaczynamy dopiero po akceptacji autora.
- Komunikacja po polsku, krótko. Przy kodzie krótko wyjaśniamy, dlaczego coś jest zrobione w dany sposób.
- Małe zmiany: łatwiej je przejrzeć i cofnąć.
- Bez płatnych usług i narzędzi (także bez GitHub Actions). Wszystkie sprawdzenia działają lokalnie.

## Nazewnictwo w danych i UI

- „Gate of Expertise” zawsze nazywamy „bramka lvl-owa” (odmieniamy: „przez bramkę lvl-ową”, „do bramki lvl-owej”).
  Słownik zamian jest w `app/tibiahelper/core/terminology.py`, a test i edytor (tryb autora) pilnują, żeby angielska nazwa nie trafiła do `data/quests.json`.

## Czego nie robimy

- Aplikacja nie łączy się z TibiaWiki ani TibiaRoute. Robi to tylko generator, uruchamiany przez autora.
  Jedyny wyjątek: obrazki potworów (© CipSoft, nie trzymamy ich w repo). Aplikacja pobiera je
  przy pierwszym użyciu z `static.wikia.nocookie.net/tibia/images/`, pod adresami zapisanymi w danych.
  Drugi wyjątek: dzisiejszy boosted potwór i boss (`core/boosted.py`). Jedno zapytanie do API
  TibiaWiki, najwyżej raz na dzień Tibii (wynik w `boosted.json`), plus ponowne próby co godzinę,
  dopóki wiki nie pokaże nowego dnia.
- Przycisk „Stream” co kilka minut pyta publiczne API Kick (`kick.com/api/v2/channels/jackyykick`),
  czy autor nadaje. Tylko odczyt, bez klucza i bez danych gracza.
- Raporty graczy (loot, Hunt Analyzer) idą przez formularz Google: program tylko otwiera go w przeglądarce.
  Ostatnie raporty czyta z publicznego eksportu CSV arkusza odpowiedzi (`core/reports.py`), najwyżej co 15 minut,
  przy otwarciu bossa albo miejsca. Teksty wpisują obcy ludzie: zawsze escape i ucinanie długości.
- Brak automatyzacji gry i czytania jej pamięci: to tylko poradnik.

## Sprawdzenie przed PR

```
python scripts/check.py
```

Skrypt uruchamia ruff (jeśli jest zainstalowany), pytest i walidację `data/quests.json`.
Następnie `/code-review` i `/security-review` w Claude Code, a wynik krótko w opisie PR.
Zasady review są w [REVIEW.md](REVIEW.md).
