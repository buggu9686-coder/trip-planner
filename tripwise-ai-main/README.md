# TripWise AI - Intelligent Personalized Travel Planner

Pipeline (matches the synopsis block diagram):
user input -> destination DB (CSV -> SQLite) -> cosine-similarity recommender -> budget optimizer -> itinerary generator -> dashboard.

## Run
    pip install -r requirements.txt
    streamlit run app.py                # dashboard
    python cli.py --destination Goa --budget 20000 --days 3 --people 2 --interests beaches adventure nature
    python -m pytest tests              # tests

## Files
- data/destinations.csv     attractions (Goa, Hampi, Mysuru). Add rows to add places/destinations.
- tripwise/recommender.py   item/user vectors + cosine similarity ranking
- tripwise/budget.py        cost estimate, overrun alert, cheaper-option suggestions + recalculation
- tripwise/itinerary.py     day-wise schedule (visit time, daily limit, travel time, lunch)
- tripwise/config.py        every price/weight/time constant in one place
- tripwise/planner.py       glue; app.py = Streamlit UI; cli.py = terminal demo

## Your own data
Use the sidebar "Add your own attractions (CSV)" to upload a file (same columns as data/destinations.csv, without id). It is validated and stored in SQLite (data/tripwise.db); "Save this plan" stores each trip in the saved_trips table.

## Typing any place
Type a place name in the sidebar. If it is not in the database, the app looks it up online (OpenStreetMap, no API key), saves its attractions into SQLite and plans the trip. Needs internet the first time only. Ratings and fees for looked-up places are estimates.

## Notes
- Prices and ratings in the CSV and config.py are rough estimates. Verify/replace before presenting as real data.
- Nights = days - 1. Rooms hold 2 people. Cab = 4 seats per vehicle.
- Over-budget order: cheaper stay -> public local travel -> cheaper long-distance transport -> swap/drop worst value paid attraction.
