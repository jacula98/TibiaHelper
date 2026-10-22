# Zasady review

## Jak tu wygląda błąd

- `data/quests.json` nie przechodzi walidacji albo quest bez przeglądu (`draft`) trafia do użytkownika.
- Aplikacja się wywraca przez złe dane, zamiast pominąć błędny quest.
- Zapis postępu gracza ginie lub się miesza (np. zmiana `id` questa).
- Generator zasypuje TibiaWiki zapytaniami (brak cache albo przerw między zapytaniami).
- Brak informacji o licencji CC BY-SA przy danych z wiki.
- Coś działa tylko na Linuksie, a nie na Windows (ścieżki, kodowanie plików, PySide6).

## Zasady

- Każda uwaga musi wskazać plik i linię. Bez zgadywania po samej nazwie.
- Najwyżej 3 drobne uwagi (styl, nazewnictwo) na PR.
- Oznaczenia: **Ważne** (do poprawy przed merge), **Drobne**, **Istniało wcześniej** (błąd, którego ten PR nie wprowadził).
- Każdą uwagę trzeba zamknąć: poprawką albo krótkim powodem, czemu nie.
- Po 3 rundach poprawek: zastanów się nad innym podejściem, zamiast dalej łatać.

## Pomijaj

- `generator/raw/` (cache z wiki)
- `build/`, `dist/`

## Podsumowanie

Zacznij od liczby uwag. Jeśli nie ma nic do poprawy, napisz wprost: „Brak uwag”.
