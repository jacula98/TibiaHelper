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

**Bossy.** W trybie autora zakładka „Bossy” pokazuje wszystkie bossy z bazy potworów („Tylko dodane” zawęża
listę). Otwórz bossa i kliknij „✏ Edytuj”: wpisz wymagania, zaznacz questy z wymagań (u graczy są klikalne),
jak dojść i jak bić. Trasę dodajesz przyciskiem „📍 Dodaj punkt”: otwiera się mapa (piętro zmieniasz strzałkami).
Przy zaznaczonym „Szybkie klikanie drogi” każdy klik to kolejny punkt drogi. Między punktami na tym samym piętrze
edytor sam liczy drogę po kratkach, którymi da się przejść (mapa przejść z tibiamaps, pobierana raz na piętro), więc
linia omija ściany. Wystarczy kliknąć start, zakręty w ważnych miejscach i cel. Gdy pod listą pojawi się
„Nie znalazłem przejścia…”, dodaj punkt pośredni (np. przy drzwiach). Zapis czeka, aż droga się policzy. Ważne miejsca (start, schody, sala bossa) dodaj z odznaczoną opcją: wtedy
podajesz podpis i rodzaj (np. „przejście” przy schodach). Gracz widzi listę podpisanych punktów i mapę z linią.
Kolejność zmieniają „↑”/„↓”. HP, exp, loot, żywioły, klasa w Bosstiary i cooldown są z TibiaWiki, więc ich nie wpisujesz.
Gracze widzą bossa dopiero po zaznaczeniu „Gotowy: pokaż graczom”.

**Hunt/Bestiary zones.** Miejsca są z TibiaWiki (`python -m generator hunts`) i gracze widzą je od razu.
Na stronie miejsca „✏ Edytuj” dodaje uwagi i trasę (tak samo jak przy bossie: do miejsca albo po miejscu).
Ponowne pobranie z wiki nie rusza uwag ani trasy.

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
python -m generator hunts                        # miejsca huntów (Hunt/Bestiary zones); trasa i uwagi autora zostają
python -m generator boss-spawns                  # bossy ze spawnem na świecie (powiadomienia o bossach)
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
- `data/boss_spawns.json`: bossy, o których program powiadamia, gdy na świecie gracza kogoś zabiją
  albo zginą (statystyki z TibiaData). Listę robi `python -m generator boss-spawns` (pole `spawntype` z wiki:
  „Raid” albo „Unique” bez „Triggered”). Okno respawnu wpisujesz ręcznie, np. `{"monster": "tyrn", "respawn_days": [3, 7]}`;
  komenda go nie kasuje. Bez okna gracz wpisuje je sam przy timerze. Plik przychodzi do graczy tylko z nową wersją programu.
- Listy `items` (przedmioty) i `npcs` (NPC z pozycjami) są w `data/quests.json`. W edytorze zaznacz imię
  NPC w tekście kroku i kliknij „👤 NPC”: pinezka stanie tam, gdzie stoi ten NPC.

## Raporty graczy (formularz Google)

Przyciski „📨 Wyślij…” otwierają formularz z wpisanym polem „Boss/Hunt place” (dla miejsc: `Hunt: <nazwa>`) i datą.
Numery pól (`entry.*`) i adres arkusza są w `app/tibiahelper/core/reports.py`. Zmiana tytułu pytania ich nie zmienia,
ale usunięcie pytania i dodanie nowego już tak. Wtedy popraw stałe w tym pliku.
Program graczy nie łączy się z arkuszem. Raporty do programu wrzuca komenda:

```
python -m generator reports
```

Pobiera arkusz, zapisuje `data/reports.json` i podbija `data_version`, gdy coś się zmieniło (bez zmian nic nie zapisuje).
Po commicie gracze dostaną raporty razem z aktualizacją poradników. Spam albo testowe wpisy usuń najpierw w arkuszu
(Odpowiedzi w formularzu → usuń), potem uruchom komendę. Przy wydaniu .exe dołącz `data/reports.json` obok `quests.json`.

## Tłumaczenia interfejsu

Każdy tekst widoczny dla gracza piszemy w kodzie po polsku w `tr("...")` (z `core/i18n.py`).
Polski tekst jest kluczem, a tłumaczenia są w `app/tibiahelper/i18n/<język>.json`
(`en`, `pt_BR`, `de`, `sv`). Zmienne: `tr("Wersja: {n}", n=3)`, w tłumaczeniu też `{n}`.
Stałe modułu (np. nazwy sortowania) oznaczamy `N_("...")` i tłumaczymy przy pokazaniu: `tr(stała)`.
Test `tests/test_i18n.py` nie przepuści nowego tekstu bez tłumaczenia we wszystkich językach.
Tryb autora (edytor) zostaje po polsku. Przy budowaniu .exe folder trzeba dołączyć pod tą samą ścieżką
co w kodzie (jak `ui/assets`): `--add-data "app/tibiahelper/i18n;tibiahelper/i18n"`.

## Nowa wersja programu (Release)

Aktualizacja w programie pobiera tylko dane (`data/quests.json`, `data/spawns.json`). Nowy kod
(nowe zakładki, `data/qol/`, nowy schemat danych) dociera do graczy tylko z nowym .exe:

1. Podbij `__version__` w `app/tibiahelper/__init__.py` (i `version` w `pyproject.toml`), np. na `1.1.0`.
2. Na Windowsie zbuduj .exe: `pip install -r requirements-dev.txt`, potem `python scripts/build_exe.py`.
   Wynik to `dist/TibiaHelper.exe` (jeden plik z danymi, tłumaczeniami i ikoną). Tryb `--author` jest w nim wyłączony.
3. Na GitHubie: Releases → „Draft a new release” → tag `v1.1.0` (z „v”), tytuł np. „TibiaHelper 1.1.0”,
   przeciągnij `dist/TibiaHelper.exe` do załączników → „Publish release”.
4. Programy graczy przy starcie zobaczą nowszy tag i pokażą pasek „Jest nowa wersja programu” z przyciskiem
   „Pobierz” (otwiera stronę Release). Program niczego sam nie podmienia.

Ikona .exe to `app/tibiahelper/ui/assets/logo.ico`. Po zmianie `logo.svg` wygeneruj ją ponownie:
`python scripts/make_icon.py`.

## Sprawdzenie przed PR

```
python scripts/check.py
```
