# Dla autora: tryb autora i generator danych

Instrukcje dla osoby, która przygotowuje poradniki. Gracze nie muszą tego czytać.

## Tryb autora (edycja questów)

```
cd app
python -m tibiahelper --author
```

W trybie autora widać też szkice (`draft`), a w widoku questa jest przycisk „✎ Edytuj”.
W edytorze można zmieniać nazwę, level, przedmioty, nagrody i kroki (dodawać, usuwać, przesuwać).

- **Pinezka:** zaznacz w tekście kroku fragment, za którym ma stać, kliknij „📍 Dodaj pinezkę” i wskaż miejsce na mapie.
- **Potwór:** zaznacz np. „2 szkielety”, kliknij „🐾 Oznacz potwora”, wpisz kawałek nazwy (np. „skel”) i wybierz z listy, podaj liczbę.
- **„Oznacz jako przejrzany”** zmienia szkic w quest widoczny dla graczy.
- **„Zapisz”** sprawdza dane (także nazewnictwo, np. „bramka lvl-owa”) i zapisuje `data/quests.json`.

Publikacja: wyślij ten plik Claude w czacie projektu.

Inne opcje: `--show-drafts` (podgląd szkiców bez edycji), `--no-update` (tylko pliki z repo, bez kopii z GitHuba).

## Generator danych

Generator pobiera dane z [TibiaWiki](https://tibia.fandom.com/) przez MediaWiki API (strony trafiają
do cache `generator/raw/`, który nie jest w repo) oraz miejsca potworów z TibiaRoute.
Uruchamiaj z katalogu głównego repo:

```
python -m generator import-all                   # wszystkie potwory + brakujące questy jako szkice
python -m generator spawns                       # miejsca występowania potworów (TibiaRoute)
python -m generator items                        # przedmioty: ceny, kto kupuje/sprzedaje, obrazki (po import-all)
python -m generator npcs                         # NPC z pozycjami i obrazkami (pinezki, „komu sprzedać”)
python -m generator monster "Skeleton"           # dodaj/odśwież jednego potwora
python -m generator add-draft "Katana Quest"     # pobiera stronę + /Spoiler, dodaje quest jako draft
python -m generator fetch "Katana Quest" --refresh   # pobierz ponownie stronę i /Spoiler
python -m generator review katana-quest          # po uzupełnieniu kroków: status reviewed
python -m generator check-updates                # które questy zmieniły się na wiki
python -m generator coords "Tom"                 # współrzędne NPC/miejsca do pinezek (pole "markers")
```

Kroki questa piszemy ręcznie (razem z Claude) na podstawie strony `/Spoiler` z cache.
Jeśli przejrzany quest zmieni się na wiki, `check-updates` ustawia mu `needs_review`.
Wtedy: `fetch --refresh`, poprawka kroków i ponownie `review`.

## Pliki danych

- `data/quests.json`: questy i potwory (TibiaWiki, CC BY-SA 4.0). `data_version` rośnie przy każdym zapisie;
  po tym aplikacja graczy poznaje, że na GitHubie są nowsze poradniki.
- `data/spawns.json`: miejsca występowania potworów (TibiaRoute, za zgodą, patrz [zrodla-danych.md](zrodla-danych.md)).
- `data/qol/`: gotowe ustawienia „Loot filter & market” (Yuukiciu). Aplikacja dopisuje je do `lootBlackWhitelist.json` i `itemprices.json` każdej postaci. Przy wydaniu .exe ten folder musi być dołączony obok `quests.json`. `data/qol/clientoptions.json` to ustawienia UI i hotkeyów autora (z jego `conf\clientoptions.json`), bez logowania, dźwięku, grafiki i okna; aplikacja podmienia nimi tylko te części pliku gracza.
- Listy `items` (przedmioty) i `npcs` (NPC z pozycjami) są w `data/quests.json`. W edytorze zaznacz imię
  NPC w tekście kroku i kliknij „👤 NPC”: pinezka stanie tam, gdzie stoi ten NPC.

## Tłumaczenia interfejsu

Każdy tekst widoczny dla gracza piszemy w kodzie po polsku w `tr("...")` (z `core/i18n.py`).
Polski tekst jest kluczem, a tłumaczenia są w `app/tibiahelper/i18n/<język>.json`
(`en`, `pt_BR`, `de`, `sv`). Zmienne: `tr("Wersja: {n}", n=3)`, w tłumaczeniu też `{n}`.
Stałe modułu (np. nazwy sortowania) oznaczamy `N_("...")` i tłumaczymy przy pokazaniu: `tr(stała)`.
Test `tests/test_i18n.py` nie przepuści nowego tekstu bez tłumaczenia we wszystkich językach.
Tryb autora (edytor) zostaje po polsku. Przy budowaniu .exe trzeba dołączyć folder `i18n/`.

## Nowa wersja programu (Release)

Aktualizacja w programie pobiera tylko dane (`data/quests.json`, `data/spawns.json`). Nowy kod
(nowe zakładki, `data/qol/`, nowy schemat danych) dociera do graczy tylko z nowym .exe:

1. Podbij `__version__` w `app/tibiahelper/__init__.py` (i `version` w `pyproject.toml`), np. na `0.2.0`.
2. Zbuduj .exe i na GitHubie utwórz Release z tagiem `v0.2.0`, z plikiem .exe w załączniku.
3. Programy graczy przy starcie zobaczą nowszy tag i pokażą pasek „Jest nowa wersja programu” z przyciskiem
   „Pobierz” (otwiera stronę Release). Program niczego sam nie podmienia.

## Sprawdzenie przed PR

```
python scripts/check.py
```
