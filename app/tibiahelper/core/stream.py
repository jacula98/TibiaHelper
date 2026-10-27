"""Czy autor właśnie streamuje na Kick (przycisk „Stream” w nagłówku okna).

Kick ma publiczne API bez klucza: /api/v2/channels/<kanał> zwraca dane kanału,
a pole "livestream" jest puste (null), gdy kanał nie nadaje. Oficjalne API Kick
wymaga zarejestrowanej aplikacji z sekretem, a sekretu nie da się schować w .exe.
"""

import http.client
import json
import logging
import urllib.request

log = logging.getLogger(__name__)

CHANNEL = "jackyykick"
CHANNEL_URL = f"https://kick.com/{CHANNEL}"
API_URL = f"https://kick.com/api/v2/channels/{CHANNEL}"
TIMEOUT_SECONDS = 10
MAX_BYTES = 1_000_000  # odpowiedź ma kilkanaście KB; limit chroni przed ogromnym plikiem
# Co ile program pyta Kick. Rzadko, żeby nie obciążać ich serwera ani sieci gracza.
CHECK_EVERY_MS = 3 * 60 * 1000


def fetch(url: str = API_URL) -> bytes:
    # Kick (Cloudflare) odrzuca część zapytań bez nagłówków przeglądarki.
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TibiaHelper", "Accept": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # stały adres https
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Odpowiedź Kick jest za duża")
    return data


def is_live(get=fetch) -> bool | None:
    """True = nadaje, False = offline, None = nie udało się sprawdzić (brak sieci, blokada, zmiana API)."""
    try:
        raw = json.loads(get(API_URL).decode("utf-8"))
    except (OSError, http.client.HTTPException, ValueError) as exc:
        log.info("Sprawdzanie streamu pominięte: %s", exc)
        return None
    if not isinstance(raw, dict) or "livestream" not in raw:
        # Inny format odpowiedzi: nie zgadujemy, tylko pokazujemy „nie wiadomo”.
        return None
    return bool(raw["livestream"])
