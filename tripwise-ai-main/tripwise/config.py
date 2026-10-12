"""All tunable numbers live here. Costs are rough INR estimates - edit freely."""

INTERESTS = ["nature", "adventure", "history", "beaches", "shopping", "food", "culture"]

# --- recommender feature weights -------------------------------------------
W_TAG = 1.0       # interest match matters most
W_RATING = 0.35   # prefer well-rated places
W_AFFORD = 0.25   # prefer cheaper places (scaled by how tight the budget is)

# --- cost model (INR) -------------------------------------------------------
STAY_LEVELS = ["budget", "standard", "luxury"]            # cheapest -> costliest
STAY_PER_ROOM_NIGHT = {"budget": 800, "standard": 2000, "luxury": 5000}
PEOPLE_PER_ROOM = 2
FOOD_PER_PERSON_DAY = {"budget": 400, "standard": 800, "luxury": 1500}

TRANSPORT_DOWNGRADE = ["flight", "car", "train", "bus"]   # costliest -> cheapest
RATE_PER_PERSON_KM = {"bus": 1.5, "train": 2.0, "flight": 7.0}
FLIGHT_MIN_ONE_WAY = 3500
CAR_RATE_PER_KM = 11        # per vehicle (4 seats), per km
LOCAL_PUBLIC_PER_PERSON_DAY = 120
LOCAL_CAB_PER_VEHICLE_DAY = 1800
EMERGENCY_PCT = 0.10

# Stay/food/local-travel price level by destination (1.0 = typical Indian town). Unlisted = 1.0.
COST_MULTIPLIER = {
    "Mumbai": 1.4, "Delhi": 1.1, "Bengaluru": 1.2, "Andaman": 1.3, "Leh": 1.3,
    "Dubai": 2.5, "Singapore": 3.0, "Bangkok": 1.5, "Bali": 1.4, "Paris": 4.0,
    "London": 4.5, "Tokyo": 3.0, "Maldives": 4.0, "Kathmandu": 0.8,
    "Kuala Lumpur": 1.3, "Istanbul": 1.6, "New York": 5.0, "Sydney": 4.0, "Rome": 3.5,
}
FLIGHT_BASE_ONE_WAY = 3500   # first 500 km
FLIGHT_PER_KM_BEYOND = 3.0   # long-haul rate per extra km

# --- itinerary --------------------------------------------------------------
DAY_START, DAY_END = 9.0, 19.0     # hours
LUNCH_AT, LUNCH_HOURS = 12.5, 1.0
TRAVEL_SPEED_KMH = 30.0
ROAD_FACTOR = 1.3                  # straight-line -> road distance
MAX_STOPS_PER_DAY = 4
PLACES_PER_DAY = 3                 # initial target before budget check

# --- live lookup of new places (OpenStreetMap: Nominatim + Overpass, no API key) ----
LIVE_RADIUS_M = 15000
MAX_LIVE_PLACES = 12
DEFAULT_FOREIGN_MULTIPLIER = 2.5
COUNTRY_MULTIPLIER = {      # ISO country code -> price level (India = 1.0)
    "in": 1.0, "np": 0.8, "lk": 1.0, "bd": 0.9, "th": 1.5, "id": 1.4, "my": 1.3, "vn": 1.2,
    "tr": 1.6, "ae": 2.5, "sg": 3.0, "jp": 3.0, "kr": 2.8, "fr": 4.0, "gb": 4.5, "us": 5.0,
    "au": 4.0, "it": 3.5, "de": 3.5, "es": 3.0, "ch": 5.5, "mv": 4.0, "cn": 2.0, "eg": 1.5,
}
