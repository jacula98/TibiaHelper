# TibiaHelper

Poradniki questów Tibii w małym oknie obok gry. Szczegóły wkrótce.

## Uruchomienie ze źródeł

Wymaga Pythona 3.12+ (Windows).

```
pip install -r requirements.txt
cd app
python -m tibiahelper
```

Domyślnie aplikacja pokazuje tylko questy ze statusem `reviewed`.
Autor może podejrzeć szkice: `python -m tibiahelper --show-drafts`.

Postęp (odhaczone kroki) zapisuje się w `%APPDATA%\TibiaHelper\progress.json`,
a widoczność (przezroczystość), pozycja i rozmiar okna w `settings.json` w tym samym katalogu.
Widoczność ustawia się trybikiem ⚙ w prawym górnym rogu (10–100%).

Przy starcie aplikacja w tle sprawdza `data/quests.json` na GitHubie. Jeśli jest nowsza wersja
(wyższe `data_version`), pokazuje pasek „Są nowsze poradniki” i dopiero po kliknięciu
„Zaktualizuj” zapisuje ją w `%APPDATA%\TibiaHelper\quests.json`. Bez internetu działa na
kopii lokalnej. Autor może to wyłączyć: `python -m tibiahelper --no-update`
(wtedy używany jest tylko `data/quests.json` z repo).

Przycisk „Zgłoś błąd” (z logo GitHuba) otwiera w przeglądarce nowe zgłoszenie (Issue)
z wypełnioną nazwą questa i wersją danych. Do wysłania potrzebne jest darmowe konto GitHub.

## Generator danych (dla autora)

Generator pobiera strony questów z [TibiaWiki](https://tibia.fandom.com/) przez MediaWiki API
i zapisuje je w `generator/raw/` (cache, nie trafia do repo). Uruchamiaj z katalogu głównego repo:

```
python -m generator add-draft "Katana Quest"     # pobiera stronę + /Spoiler, dodaje quest jako draft
python -m generator review katana-quest          # po uzupełnieniu kroków: status reviewed
python -m generator check-updates                # które questy zmieniły się na wiki
python -m generator fetch "Katana Quest" --refresh   # pobierz ponownie (np. przed ponownym przeglądem)
```

Kroki questa piszemy ręcznie (razem z Claude) na podstawie strony `/Spoiler` z cache.
Jeśli przejrzany quest zmieni się na wiki, `check-updates` ustawia mu `needs_review`.
Wtedy: `fetch --refresh`, poprawka kroków i ponownie `review`.
