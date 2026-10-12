"""Budget optimizer: estimate cost, raise overrun alerts, suggest and apply cheaper options."""
import math
from dataclasses import dataclass, replace
import pandas as pd

from . import config as C


@dataclass
class Trip:
    destination: str
    budget: float
    days: int
    people: int
    stay: str = "standard"        # budget | standard | luxury
    transport: str = "train"      # bus | train | car | flight
    local: str = "cab"            # public | cab
    distance_km: float = 300.0    # one-way distance from home
    price_level: float = 0.0      # 0 = look up in config (set for live-added places)


def transport_cost(t: Trip) -> float:
    if t.transport == "car":
        return math.ceil(t.people / 4) * t.distance_km * 2 * C.CAR_RATE_PER_KM
    if t.transport == "flight":
        one_way = C.FLIGHT_BASE_ONE_WAY + max(t.distance_km - 500, 0) * C.FLIGHT_PER_KM_BEYOND
        return t.people * 2 * one_way
    return t.people * t.distance_km * 2 * C.RATE_PER_PERSON_KM[t.transport]


def estimate(t: Trip, places: pd.DataFrame) -> dict:
    nights = max(t.days - 1, 0)
    m = t.price_level or C.COST_MULTIPLIER.get(t.destination, 1.0)
    rooms = math.ceil(t.people / C.PEOPLE_PER_ROOM)
    if t.local == "public":
        local = m * C.LOCAL_PUBLIC_PER_PERSON_DAY * t.people * t.days
    else:
        local = m * math.ceil(t.people / 4) * C.LOCAL_CAB_PER_VEHICLE_DAY * t.days
    parts = {
        "Transport (round trip)": transport_cost(t),
        "Accommodation": m * C.STAY_PER_ROOM_NIGHT[t.stay] * rooms * nights,
        "Food": m * C.FOOD_PER_PERSON_DAY[t.stay] * t.people * t.days,
        "Activities": float(places["entry_cost"].sum()) * t.people,
        "Local travel": local,
    }
    parts["Emergency reserve"] = C.EMERGENCY_PCT * sum(parts.values())
    parts["TOTAL"] = sum(parts.values())
    return parts


def optimise(trip: Trip, selected: pd.DataFrame, pool: pd.DataFrame) -> dict:
    """If over budget: cheaper stay -> public local travel -> cheaper transport ->
    swap/drop the worst value-for-money paid attraction. Recalculate after every change."""
    sel, pool = selected.copy(), pool.copy()
    breakdown = estimate(trip, sel)
    original_total = breakdown["TOTAL"]
    alerts, changes = [], []

    def over():
        return estimate(trip, sel)["TOTAL"] > trip.budget

    if over():
        alerts.append(f"Budget overrun: estimated Rs {original_total:,.0f} vs budget Rs {trip.budget:,.0f}.")

    while over() and trip.stay != "budget":
        new = C.STAY_LEVELS[C.STAY_LEVELS.index(trip.stay) - 1]
        changes.append(f"Switched stay {trip.stay} -> {new} (also lowers food cost).")
        trip = replace(trip, stay=new)

    if over() and trip.local != "public":
        changes.append("Switched local travel from cab to public transport.")
        trip = replace(trip, local="public")

    while over() and trip.transport != "bus":
        i = C.TRANSPORT_DOWNGRADE.index(trip.transport)
        new = C.TRANSPORT_DOWNGRADE[i + 1]
        changes.append(f"Switched long-distance transport {trip.transport} -> {new}.")
        trip = replace(trip, transport=new)

    while over():
        paid = sel[sel["entry_cost"] > 0]
        if paid.empty:
            break
        victim = (paid["score"] / paid["entry_cost"]).idxmin()
        v = sel.loc[victim]
        cheaper = pool[pool["entry_cost"] <= v["entry_cost"] * 0.5]
        sel = sel.drop(victim)
        if not cheaper.empty:
            r = cheaper.iloc[[0]]
            pool = pool.drop(r.index)
            sel = pd.concat([sel, r])
            changes.append(f"Replaced '{v['name']}' (Rs {v['entry_cost']:.0f}) with cheaper '{r.iloc[0]['name']}'.")
        else:
            changes.append(f"Dropped paid activity '{v['name']}' (Rs {v['entry_cost']:.0f}).")

    breakdown = estimate(trip, sel)
    fits = breakdown["TOTAL"] <= trip.budget
    if alerts and not fits:
        alerts.append("Even the cheapest options exceed the budget. Increase the budget or reduce days/people.")
    return {"trip": trip, "places": sel.sort_values("score", ascending=False).reset_index(drop=True),
            "breakdown": breakdown, "alerts": alerts, "changes": changes,
            "fits": fits, "original_total": original_total}
