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

Po starcie widać menu: Questy (Expowiska i Bossy dojdą później). Przy miejscach w krokach jest
pinezka: kliknięcie wysuwa na dole okna mapę Tibii z kropką w tym miejscu (kolejna pinezka tylko przełącza mapę, „✕” ją chowa). Mapy pięter pochodzą
z projektu [tibiamaps](https://github.com/tibiamaps/tibia-map-data) i pobierają się przy pierwszym
użyciu do `%APPDATA%\TibiaHelper\maps`.

## Tryb autora (edycja questów)

```
cd app
python -m tibiahelper --author
```

W widoku questa pojawia się przycisk „✎ Edytuj”. W edytorze można zmieniać nazwę, level,
przedmioty, nagrody i kroki (dodawać, usuwać, przesuwać). Pinezkę dodaje się tak: zaznacz w tekście
kroku fragment, za którym ma stać, kliknij „📍 Dodaj pinezkę” i wskaż miejsce na mapie.
„Oznacz jako przejrzany” zmienia szkic w quest widoczny dla graczy. „Zapisz” sprawdza dane
(także nazewnictwo, np. „bramka lvl-owa”) i zapisuje `data/quests.json`.
Publikacja: wyślij ten plik Claude w czacie projektu.

## Generator danych (dla autora)

Generator pobiera strony questów z [TibiaWiki](https://tibia.fandom.com/) przez MediaWiki API
i zapisuje je w `generator/raw/` (cache, nie trafia do repo). Uruchamiaj z katalogu głównego repo:

```
python -m generator add-draft "Katana Quest"     # pobiera stronę + /Spoiler, dodaje quest jako draft
python -m generator review katana-quest          # po uzupełnieniu kroków: status reviewed
python -m generator check-updates                # które questy zmieniły się na wiki
python -m generator fetch "Katana Quest" --refresh   # pobierz ponownie (np. przed ponownym przeglądem)
python -m generator coords "Tom"                 # współrzędne NPC/miejsca do pinezek (pole "markers")
```

Kroki questa piszemy ręcznie (razem z Claude) na podstawie strony `/Spoiler` z cache.
Jeśli przejrzany quest zmieni się na wiki, `check-updates` ustawia mu `needs_review`.
Wtedy: `fetch --refresh`, poprawka kroków i ponownie `review`.
