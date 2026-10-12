"""Itinerary generator: groups places into days respecting visit time, daily limit and travel time."""
import math
import pandas as pd
from . import config as C


def km_between(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h)) * C.ROAD_FACTOR


def fmt(h: float) -> str:
    m = int(round(h * 60))
    return f"{m // 60:02d}:{m % 60:02d}"


def build_itinerary(places: pd.DataFrame, days: int):
    """Greedy: each day starts with the best-ranked unscheduled place, then keeps adding the
    nearest place that still fits before DAY_END. Lunch is inserted around midday."""
    remaining = places.sort_values("score", ascending=False).to_dict("records")
    plan = []
    for d in range(1, days + 1):
        t, pos, stops, lunch_done, n_sights = C.DAY_START, None, [], False, 0
        while remaining and n_sights < C.MAX_STOPS_PER_DAY:
            if not lunch_done and t >= C.LUNCH_AT:
                stops.append({"start": fmt(t), "end": fmt(t + C.LUNCH_HOURS), "what": "Lunch break", "kind": "meal"})
                t += C.LUNCH_HOURS
                lunch_done = True
            options = []
            for p in remaining:
                travel = 0.0 if pos is None else km_between(pos, p) / C.TRAVEL_SPEED_KMH
                if t + travel + p["visit_hours"] <= C.DAY_END:
                    options.append((travel, p))
            if not options:
                break
            if pos is None:
                travel, p = options[0]            # best-ranked place starts the day
            else:
                travel, p = min(options, key=lambda x: x[0])   # then nearest that fits
            if pos is not None and travel > 0:
                stops.append({"start": fmt(t), "end": fmt(t + travel), "what": f"Travel to {p['name']}", "kind": "travel"})
                t += travel
            stops.append({"start": fmt(t), "end": fmt(t + p["visit_hours"]), "what": p["name"], "kind": "visit",
                          "cost": p["entry_cost"], "activity": p["activity_type"]})
            t += p["visit_hours"]
            pos = p
            n_sights += 1
            remaining.remove(p)
        plan.append({"day": d, "stops": stops})
    return plan, [p["name"] for p in remaining]
