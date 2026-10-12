"""Glue: input -> recommend -> budget optimise -> itinerary."""
from .config import PLACES_PER_DAY
from .recommender import rank_attractions
from .budget import Trip, optimise
from .itinerary import build_itinerary
from .db import get_multiplier


def plan_trip(df, destination, budget, days, people, interests,
              stay="standard", transport="train", local="cab", distance_km=300.0):
    ranked = rank_attractions(df, destination, interests, budget, days, people)
    n = min(len(ranked), days * PLACES_PER_DAY)
    trip = Trip(destination, budget, days, people, stay, transport, local, distance_km,
                price_level=get_multiplier(destination) or 0.0)
    result = optimise(trip, ranked.head(n), ranked.iloc[n:])
    itinerary, unscheduled = build_itinerary(result["places"], days)
    return {**result, "ranked": ranked, "itinerary": itinerary, "unscheduled": unscheduled}
