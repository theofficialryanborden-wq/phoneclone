from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass
class GeoResult:
    latitude: float
    longitude: float
    display_name: str


class GeocodingError(Exception):
    """Address could not be resolved to coordinates."""


def geocode_address(address: str) -> GeoResult:
    """Resolve a street address or place name to lat/lon via OpenStreetMap Nominatim."""
    query = address.strip()
    if not query:
        raise GeocodingError("Address is empty.")

    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "limit": "1",
        }
    )
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "PhoneClone/1.1 (Android emulator; contact: local)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise GeocodingError(f"Geocoding service unreachable: {exc}") from exc

    if not data:
        raise GeocodingError(f"No location found for: {query}")

    entry = data[0]
    return GeoResult(
        latitude=float(entry["lat"]),
        longitude=float(entry["lon"]),
        display_name=entry.get("display_name", query),
    )
