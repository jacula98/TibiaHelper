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
- **Zakładka „Przedmioty”.** Wyszukasz dowolny przedmiot i zobaczysz, któremu NPC go sprzedać i za ile
  (z miejscem na mapie), gdzie go kupić i z jakich potworów wypada.
- **Zgłoś błąd** przy queście, potworze i przedmiocie otwiera gotowe zgłoszenie na GitHubie.
- **Przezroczystość okna** (10–100%) ustawiasz trybikiem ⚙ w prawym górnym rogu.
- **Aktualizacje.** Gdy pojawią się nowe poradniki, program sam to sprawdzi i zapyta, czy je pobrać.

Wkrótce: expowiska i bossy.

## Jak uruchomić

Gotowy plik `.exe` pojawi się przy pierwszym wydaniu. Na razie potrzebny jest Python 3.12+ (Windows):

```
pip install -r requirements.txt
cd app
python -m tibiahelper
```

## Znalazłeś błąd w poradniku?

Kliknij „Zgłoś błąd” (z logo GitHuba) pod questem. Otworzy się zgłoszenie z nazwą questa
i wersją danych, wystarczy dopisać, co jest nie tak. Potrzebne jest darmowe konto GitHub.

## Gdzie program zapisuje dane

Wszystko jest w `%APPDATA%\TibiaHelper`: postęp questów, ustawienia okna, pobrane poradniki,
mapy pięter i obrazki potworów. Usunięcie tego folderu przywraca program do stanu początkowego.

## Źródła danych

- Questy i potwory: [TibiaWiki](https://tibia.fandom.com/), licencja CC BY-SA 4.0.
- Mapy: [tibiamaps](https://github.com/tibiamaps/tibia-map-data).
- Miejsca występowania potworów: Źródło danych: [tibiaroute.com](https://tibiaroute.com/) (za zgodą TibiaRoute).
- Tibia, obrazki potworów i nazwy z gry: © CipSoft GmbH. Projekt nie jest powiązany z CipSoft ani z Fandom.

Kod programu jest na licencji MIT, a dane w `data/` na CC BY-SA 4.0.
Szczegóły: [docs/zrodla-danych.md](docs/zrodla-danych.md).

---

Przygotowujesz poradniki? Instrukcje są w [docs/AUTOR.md](docs/AUTOR.md).
