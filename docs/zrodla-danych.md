# Źródła danych i zgody

| Źródło | Co bierzemy | Na jakich zasadach |
|---|---|---|
| [TibiaWiki](https://tibia.fandom.com/) | questy, potwory (HP, exp, żywioły, umiejętności, loot, miejsca), przedmioty (ceny, NPC kupujący i sprzedający), NPC z pozycjami | CC BY-SA 4.0: link do źródła przy danych |
| TibiaWiki, pliki obrazków | obrazki potworów, przedmiotów i NPC | grafiki © CipSoft GmbH; nie są w repo, aplikacja pobiera je przy pierwszym użyciu |
| [tibiamaps](https://github.com/tibiamaps/tibia-map-data) | mapy pięter | „Feel free to use”, kod MIT |
| [tibiaroute.com](https://tibiaroute.com/) | miejsca występowania potworów | pisemna zgoda (niżej) |
| [Yuukiciu](https://www.youtube.com/watch?v=4fIlbgTtXMg) | `data/qol/`: loot filter (pomijane śmieci) i ceny z Marketu dla itemów do delivery tasków i imbu | pliki dostarczył autor projektu; w aplikacji podpis „Źródło: Yuukiciu” z linkiem |

Nie korzystamy z Tibiopedii (brak licencji pozwalającej na użycie).

## Zgoda TibiaRoute (2026-10-26)

Otrzymana mailowo przez autora projektu. Treść:

> niniejszym, jako TibiaRoute, wyrażamy zgodę na pobieranie i wykorzystywanie danych udostępnionych
> na naszej stronie internetowej tibiaroute.com, w tym w Państwa oprogramowaniu TibiaHelper, zarówno
> w celach niekomercyjnych, jak i komercyjnych.
>
> Jedynym warunkiem jest umieszczenie w programie, w widocznym miejscu (np. w sekcji „O programie”
> lub przy wyświetlanych danych), informacji o źródle, np.: „Źródło danych: tibiaroute.com”
>
> Zgoda nie obejmuje danych osobowych ani treści, do których prawa należą podmiotom trzecim.
> Zastrzegamy sobie prawo do jej odwołania z zachowaniem rozsądnego terminu.

Co z tego wynika dla kodu:
- przy danych z TibiaRoute i w ustawieniach (⚙) jest napis „Źródło danych: tibiaroute.com”,
- grafik CipSoft z TibiaRoute nie bierzemy (to treści podmiotu trzeciego),
- dane z TibiaRoute trzymamy w osobnych polach, żeby po ewentualnym odwołaniu zgody dało się je łatwo usunąć.
