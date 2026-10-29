# TibiaHelper

Małe okno obok gry z poradnikami do Tibii. Zawsze jest na wierzchu, więc nie trzeba przełączać się
do przeglądarki.

## Co potrafi

- **Questy krok po kroku.** Odhaczasz kroki, a aktualny krok sam przewija się na górę.
  Postęp zapisuje się na Twoim komputerze.
- **Mapa przy krokach.** Kliknij kafelek z pinezką albo postacią NPC obok kroku, a na dole okna wysunie się
  mapa z zaznaczonym miejscem.
- **Potwory w poradnikach.** Przy nazwie potwora jest jego obrazek. Po najechaniu myszką widać HP, exp
  i słabości, a po kliknięciu otwiera się pełna strona potwora.
- **Zakładka „Potwory”.** Ponad 2000 potworów z wyszukiwarką. Każdy ma HP, exp, obrażenia od żywiołów,
  umiejętności, loot i mapę miejsc (expowisk), w których występuje. Listę można sortować po HP i expie.
  Przycisk „Filtry” pokazuje też bossy, potwory eventowe, niedostępne w grze, bez HP i bez expa (domyślnie ukryte).
- **Zakładka „Hunt/Bestiary zones”.** Ponad 400 miejsc huntów z TibiaWiki. Wpisz swój level i wybierz profesję,
  a zobaczysz miejsca, na które już możesz iść. Wyszukasz też po potworze (np. „dragon”); do tego filtr miasta i sortowanie po poziomie, expie i loocie.
  Każde miejsce ma gwiazdki exp/loot, potwory z Bestiary (ile killi i charm pointów), części miejsca (piętra),
  najlepszy loot i mapę z wejściem albo trasą od autora.
- **Zakładka „Bossy”.** Bossy opisane przez autora: wymagania (z linkiem do questa), jak dojść (z trasą na mapie) i jak bić.
  Do tego klasa w Bosstiary, ile killi trzeba do Prowess, Expertise i Mastery, cooldown oraz czym bić.
  Loot i mapa są na karcie potwora. Lista ma wyszukiwarkę i filtr klasy (Bane, Archfoe, Nemesis).
- **Powiadomienia o bossach.** Wpisz swój świat w ustawieniach (⚙). Raz na dobę program sprawdza statystyki
  zabójstw z tibia.com (przez darmowe TibiaData) i, jeśli boss ze spawnem na świecie (np. Tyrn) kogoś zabił
  albo zginął, pokazuje powiadomienie z dźwiękiem. Klik otwiera bossa. Tam ustawisz timer „Zabity” z oknem
  respawnu (np. 3–7 dni); godzinę przed początkiem okna dostaniesz drugie powiadomienie.
- **Zakładka „Przedmioty”.** Wyszukasz dowolny przedmiot i zobaczysz, któremu NPC go sprzedać i za ile
  (z miejscem na mapie), gdzie go kupić i z jakich potworów wypada. Quest itemy, soul core, pojemniki i przedmioty
  bez handlu z NPC są domyślnie ukryte (do pokazania przyciskiem „Filtry”). Przedmiotów z fansite'ów nie ma wcale.
- **Zakładka „Narzędzia”.** Kalkulatory: „Cena ze Store” (wpisujesz cenę 1 Tibia Coina, a program liczy
  cenę w gp i gp za sztukę dla potionów, kegów, casków, run i exercise weapons oraz porównuje z ceną u NPC), „Podział lootu” (wklejasz Party Hunt Analyzer, program mówi, kto komu ile przelewa,
  i kopiuje komendę `transfer` dla bankiera), „Stamina” (ile być offline do wybranej staminy i o której będzie gotowa)
  oraz „Skille” (ile exercise weapons i za ile do wybranego poziomu skilla).
- **Zakładka „Quality of life”.** „TibiaMaps”: zaznaczasz, czy chcesz markery i siatkę (grid overlay),
  i klikasz „Wgraj mapę”. Program sam pobiera pełną minimapę z [tibiamaps.io](https://tibiamaps.io/) i wgrywa ją
  do Tibii (`%LOCALAPPDATA%\Tibia\packages\Tibia\minimap`, stara minimapa trafia raz do `minimap.tibiahelper-backup`).
  Oraz „Loot filter & market”:
  jednym kliknięciem „Wgraj” każda postać na koncie dostaje listę pomijanych śmieci w loocie i ceny z Marketu
  dla itemów do delivery tasków i imbu (ustawienia od Yuukiciu). Przed wgraniem zamknij Tibię. Twoje listy
  zostają, a oryginalne pliki mają kopię z końcówką `.tibiahelper-backup` w folderze postaci
  (`%LOCALAPPDATA%\Tibia\packages\Tibia\characterdata`).
  „UI + Hotkeys”: „Wgraj” ustawia oczyszczone UI (mniej animacji i komunikatów), podstawowe hotkeye dla każdej
  profesji i action bary. Twoje logowanie, dźwięk, grafika i okno zostają, a stary `conf\clientoptions.json`
  ma kopię `.tibiahelper-backup`. Przed wgraniem zamknij Tibię.
- **Zgłoś błąd** przy queście, potworze i przedmiocie otwiera gotowe zgłoszenie na GitHubie.
- **Przezroczystość okna** (10–100%) ustawiasz trybikiem ⚙ w prawym górnym rogu.
- **Język programu** też zmienisz trybikiem ⚙: polski, English, Português (Brasil), Deutsch, Svenska.
  Działa po ponownym uruchomieniu. Tłumaczony jest interfejs; treść poradników questów jest po polsku.
- **Aktualizacje.** Gdy pojawią się nowe poradniki, program sam to sprawdzi i zapyta, czy je pobrać.
  Gdy na GitHubie pojawi się nowa wersja programu (Release), pokaże pasek z przyciskiem „Pobierz”.


## Jak uruchomić

Pobierz `TibiaHelper.exe` z [najnowszego wydania](https://github.com/jacula98/TibiaHelper/releases/latest)
i uruchom go. Instalacja nie jest potrzebna. Windows może przy pierwszym uruchomieniu pokazać ostrzeżenie
„System Windows ochronił ten komputer”, bo plik nie ma płatnego podpisu. Kliknij wtedy „Więcej informacji” →
„Uruchom mimo to”. Nowe poradniki program pobiera sam, a o nowej wersji programu informuje paskiem u góry.

Ze źródeł (Python 3.12+):

```
pip install -r requirements.txt
cd app
python -m tibiahelper
```

## Znalazłeś błąd w poradniku?

Kliknij „Zgłoś błąd” (z logo GitHuba) pod questem. Otworzy się zgłoszenie z nazwą questa
i wersją danych, wystarczy dopisać, co jest nie tak. Potrzebne jest darmowe konto GitHub.

## Raporty z lootu i Hunt Analyzer

Pod bossem jest przycisk „📨 Wyślij loot z bossa”, a pod miejscem huntu „📨 Wyślij Hunt Analyzer”. Otwiera
formularz Google z wpisaną nazwą; wklejasz loot albo analyzer i klikasz „Prześlij”. Konto nie jest potrzebne.
Ostatnie raporty innych graczy widać na tej samej stronie (5 najnowszych, „Pokaż więcej” rozwija kolejne).
Nowe raporty dochodzą razem z aktualizacją poradników, więc twój pojawi się po kolejnej aktualizacji.
Raportów nikt nie sprawdza.

## Gdzie program zapisuje dane

Wszystko jest w `%APPDATA%\TibiaHelper`: postęp questów, ustawienia okna, pobrane poradniki,
mapy pięter i obrazki potworów. Usunięcie tego folderu przywraca program do stanu początkowego.

## Źródła danych

- Questy i potwory: [TibiaWiki](https://tibia.fandom.com/), licencja CC BY-SA 4.0.
- Mapy: [tibiamaps](https://github.com/tibiamaps/tibia-map-data).
- Miejsca występowania potworów: Źródło danych: [tibiaroute.com](https://tibiaroute.com/) (za zgodą TibiaRoute).
- Ustawienia loot filtra i cen (`data/qol/`): [Yuukiciu](https://www.youtube.com/watch?v=4fIlbgTtXMg).
- Tibia, obrazki potworów i nazwy z gry: © CipSoft GmbH. Projekt nie jest powiązany z CipSoft ani z Fandom.

Kod programu jest na licencji MIT, a dane w `data/` na CC BY-SA 4.0 (poza `data/qol/`, których autorem jest Yuukiciu).
Szczegóły: [docs/zrodla-danych.md](docs/zrodla-danych.md).

---

Przygotowujesz poradniki? Instrukcje są w [docs/AUTOR.md](docs/AUTOR.md).
