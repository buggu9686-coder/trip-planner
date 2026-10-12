"""Live lookup for places that are not in the database yet.

Type any place -> geocode it (Nominatim) -> find nearby attractions (Overpass) -> build rows
in the same format as data/destinations.csv. app.py then stores them in SQLite, so the next
time the place is instant and works offline.

Free OpenStreetMap services, no API key. Ratings and entry fees are NOT in OpenStreetMap, so
they are estimated (see build_rows) - treat them as rough values.
"""
import json
import math
import urllib.parse
import urllib.request

import pandas as pd

from . import config as C

UA = "TripWiseAI-student-project/1.0 (educational mini project)"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"

HOURS = {"museum": 2.0, "gallery": 1.5, "zoo": 3.0, "theme_park": 5.0, "aquarium": 2.0, "beach": 2.5,
         "waterfall": 2.0, "peak": 3.0, "park": 1.5, "garden": 1.5, "nature_reserve": 3.0,
         "viewpoint": 1.0, "fort": 2.0, "castle": 2.0, "palace": 2.0, "mall": 2.5, "marketplace": 1.5}


class FetchError(Exception):
    """Readable problem (no internet, place not found, too few attractions)."""


def _get(url, data=None, timeout=45):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # network, timeout, bad JSON
        raise FetchError("Could not reach the online place service. Check your internet "
                         f"connection and try again. ({type(e).__name__})") from e


def geocode(place: str) -> dict:
    qs = urllib.parse.urlencode({"q": place, "format": "json", "limit": 1, "addressdetails": 1})
    res = _get(f"{NOMINATIM}?{qs}")
    if not res:
        raise FetchError(f"Could not find a place called '{place}'. Check the spelling.")
    r = res[0]
    lat, lon = float(r["lat"]), float(r["lon"])
    return {"lat": lat, "lon": lon, "radius": radius_from_bbox(r.get("boundingbox"), lat),
            "country": (r.get("address", {}).get("country_code") or "").lower()}


def radius_from_bbox(bbox, lat):
    """Search radius (m) = half the place's diagonal, kept between 8 km and 60 km.
    A town gets ~8-15 km, an island/region like Bali gets the 60 km maximum."""
    if not bbox:
        return C.LIVE_RADIUS_M
    s_, n_, w_, e_ = map(float, bbox)
    dy = (n_ - s_) * 111.0
    dx = (e_ - w_) * 111.0 * math.cos(math.radians(lat))
    return int(min(max(0.5 * math.hypot(dx, dy) * 1000, 8000), 60000))


def _overpass_query(lat, lon, radius, notable_only=False):
    a = f"(around:{radius},{lat},{lon})"
    w = '["wikidata"]' if notable_only else ""   # big areas: only well-known places
    return f"""[out:json][timeout:30];(
  nwr{a}["tourism"~"^(attraction|museum|viewpoint|zoo|theme_park|gallery|aquarium)$"]["name"]{w};
  nwr{a}["historic"~"^(castle|fort|monument|memorial|ruins|archaeological_site|palace|temple)$"]["name"]{w};
  nwr{a}["natural"~"^(beach|waterfall|peak|cave_entrance|hot_spring)$"]["name"]{w};
  nwr{a}["leisure"~"^(park|garden|nature_reserve)$"]["name"]{w};
  nwr{a}["amenity"="place_of_worship"]["name"]["wikidata"];
  nwr{a}["amenity"="marketplace"]["name"];
  nwr{a}["shop"="mall"]["name"];
);out center 250;"""


def interests_from_tags(tags: dict) -> set:
    s, nat, tour = set(), tags.get("natural"), tags.get("tourism")
    hist, leis = tags.get("historic"), tags.get("leisure")
    if nat == "beach":
        s |= {"beaches", "nature"}
    elif nat:
        s.add("nature")
        if nat in {"peak", "cave_entrance"}:
            s.add("adventure")
    if leis in {"park", "garden", "nature_reserve"}:
        s.add("nature")
    if tour in {"zoo", "aquarium", "viewpoint"}:
        s.add("nature")
    if tour == "theme_park":
        s.add("adventure")
    if tour == "museum":
        s |= {"culture", "history"}
    if tour == "gallery":
        s.add("culture")
    if hist:
        s.add("history")
        if hist in {"temple", "palace", "castle", "fort"}:
            s.add("culture")
    if tags.get("amenity") == "place_of_worship":
        s |= {"culture", "history"}
    if tags.get("shop") == "mall":
        s.add("shopping")
    if tags.get("amenity") == "marketplace":
        s |= {"shopping", "food"}
    return s or {"culture"}


def _kind(tags):
    for k in ("natural", "tourism", "historic", "leisure", "shop", "amenity"):
        if tags.get(k):
            return tags[k]
    return "sightseeing"


def build_rows(elements, destination, multiplier=1.0, limit=C.MAX_LIVE_PLACES):
    """Overpass elements -> list of rows (same columns as destinations.csv), best-known first."""
    cands = {}
    for e in elements:
        tags = e.get("tags", {})
        name = (tags.get("name:en") or tags.get("name") or "").strip()
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        if not name or lat is None or lon is None:
            continue
        notable = bool(tags.get("wikidata") or tags.get("wikipedia"))
        score = 2 * notable + (1 if tags.get("tourism") == "attraction" else 0) + (0.5 if tags.get("website") else 0)
        kind = _kind(tags)
        row = {"destination": destination, "name": name, "tags": "|".join(sorted(interests_from_tags(tags))),
               "activity_type": kind.replace("_", " "),
               "entry_cost": round(200 * multiplier) if tags.get("fee") == "yes" else 0,
               "rating": 4.3 if notable else 4.0,               # ESTIMATE: OSM has no ratings
               "visit_hours": HOURS.get(kind, 1.5), "lat": float(lat), "lon": float(lon)}
        key = name.casefold()
        if key not in cands or score > cands[key][0]:
            cands[key] = (score, row)
    ranked = sorted(cands.values(), key=lambda x: -x[0])
    return [r for _, r in ranked[:limit]]


def fetch_destination(place: str) -> dict:
    """Returns {'name', 'df', 'country', 'multiplier'}; raises FetchError with a readable message."""
    place = place.strip()
    if not place:
        raise FetchError("Type a place name first.")
    g = geocode(place)
    mult = C.COUNTRY_MULTIPLIER.get(g["country"], C.DEFAULT_FOREIGN_MULTIPLIER if g["country"] else 1.0)
    name = place.title()
    r0 = g["radius"]
    rows = []
    # 1st try: area sized to the place; 2nd try: 3x wider but only well-known places
    for radius, notable in [(r0, r0 > 20000), (min(r0 * 3, 100000), True)]:
        q = urllib.parse.urlencode({"data": _overpass_query(g["lat"], g["lon"], radius, notable)}).encode()
        elements = _get(OVERPASS, data=q, timeout=60).get("elements", [])
        rows = build_rows(elements, name, mult)
        if len(rows) >= 4:
            break
    if len(rows) < 2:
        raise FetchError(f"Found too few tourist attractions near '{place}'. Try a bigger city/town "
                         "name, or add it yourself with the CSV upload box.")
    return {"name": name, "df": pd.DataFrame(rows), "country": g["country"], "multiplier": mult}
