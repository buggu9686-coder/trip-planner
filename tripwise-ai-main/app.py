"""TripWise AI dashboard.  Run:  streamlit run app.py"""
import difflib

import pandas as pd
import streamlit as st

from tripwise.config import INTERESTS
from tripwise.db import (load_attractions, import_attractions, reset_attractions,
                         save_trip, list_trips, set_meta, REQUIRED_COLS)
from tripwise.fetcher import fetch_destination, FetchError
from tripwise.planner import plan_trip

st.set_page_config(page_title="TripWise AI", page_icon="🧭", layout="wide")
st.title("🧭 TripWise AI")
st.caption("Intelligent personalized travel planner: recommend, budget-check, schedule.")

with st.sidebar:
    with st.expander("Add your own attractions (CSV)"):
        st.caption("Required columns: " + ", ".join(REQUIRED_COLS) +
                   ". tags = interests separated by | (nature, adventure, history, beaches, shopping, food, culture).")
        up = st.file_uploader("CSV file", type="csv")
        mode = st.radio("Save as", ["Add / update", "Replace all data"])
        if st.button("Store in database") and up is not None:
            try:
                n, warns = import_attractions(pd.read_csv(up), "replace" if mode.startswith("Replace") else "merge")
                st.success(f"Saved. Database now has {n} attractions.")
                for w in warns:
                    st.warning(w)
            except ValueError as e:
                st.error(str(e))
        if st.button("Reset to bundled data"):
            reset_attractions()
            st.success("Restored the original dataset.")

df = load_attractions()

with st.sidebar:
    st.header("Your trip")
    typed = st.text_input("Destination (type a place name)", "Goa")
    budget = st.number_input("Total budget (Rs)", 2000, 1_000_000, 25000, step=1000)
    days = st.slider("Number of days", 1, 7, 3)
    people = st.slider("Number of people", 1, 10, 2)
    stay = st.selectbox("Accommodation", ["budget", "standard", "luxury"], index=1)
    transport = st.selectbox("Travel to destination", ["bus", "train", "car", "flight"], index=1)
    local = st.selectbox("Local travel", ["cab", "public"])
    distance = st.number_input("One-way distance from home (km)", 10, 20000, 300, step=10)
    interests = st.multiselect("Interests", INTERESTS, default=["nature", "adventure", "beaches"])

known = sorted(df["destination"].unique())
lookup = {k.casefold(): k for k in known}
q = typed.strip().casefold()
close = [lookup[q]] if q in lookup else difflib.get_close_matches(q, list(lookup), n=1, cutoff=0.8)
close = close or [k for k in lookup if len(q) >= 4 and (q in k or k in q)][:1]
if close:
    destination = lookup[close[0].casefold()] if close[0].casefold() in lookup else close[0]
    if destination.casefold() != q:
        st.info(f"Showing results for **{destination}**.")
else:
    # Not in the database yet -> look it up online and store it directly.
    try:
        with st.spinner(f"Looking up '{typed}' online and saving it to the database..."):
            info = fetch_destination(typed)
            import_attractions(info["df"], "merge")
            set_meta(info["name"], info["country"], info["multiplier"])
        st.success(f"Added {len(info['df'])} attractions for {info['name']} to the database "
                   "(from OpenStreetMap; ratings and fees are estimates).")
    except FetchError as e:
        st.error(str(e))
        st.stop()
    df = load_attractions()
    destination = info["name"]

r = plan_trip(df, destination, budget, days, people, interests, stay, transport, local, distance)
b = r["breakdown"]

c1, c2, c3 = st.columns(3)
c1.metric("Estimated total", f"Rs {b['TOTAL']:,.0f}")
c2.metric("Budget", f"Rs {budget:,.0f}")
c3.metric("Remaining", f"Rs {budget - b['TOTAL']:,.0f}")

if st.button("💾 Save this plan"):
    tid = save_trip({"destination": destination, "budget": budget, "days": days,
                     "people": people, "interests": interests}, r)
    st.toast(f"Plan #{tid} saved to the database")

if r["alerts"]:
    for a in r["alerts"]:
        st.warning(a)
    for c in r["changes"]:
        st.info(c)
    if r["fits"]:
        st.success("After the changes above, the plan fits your budget.")
else:
    st.success("Plan fits within your budget.")

left, right = st.columns([3, 2])
with left:
    st.subheader("Day-wise itinerary")
    for day in r["itinerary"]:
        with st.expander(f"Day {day['day']}", expanded=True):
            if not day["stops"]:
                st.write("Free day / rest.")
            for s in day["stops"]:
                icon = {"visit": "📍", "travel": "🚗", "meal": "🍽️"}[s["kind"]]
                extra = f" (Rs {s['cost']:.0f} pp)" if s["kind"] == "visit" and s["cost"] else ""
                st.write(f"`{s['start']}-{s['end']}`  {icon} {s['what']}{extra}")
    if r["unscheduled"]:
        st.caption("Could not fit: " + ", ".join(r["unscheduled"]))
with right:
    st.subheader("Budget breakdown")
    parts = pd.Series({k: v for k, v in b.items() if k != "TOTAL"})
    st.bar_chart(parts)
    st.dataframe(parts.rename("Rs").round(0).astype(int))

st.subheader("Recommended attractions (ranked by cosine similarity)")
st.dataframe(r["ranked"][["name", "tags", "activity_type", "entry_cost", "rating", "visit_hours", "score"]]
             .style.format({"score": "{:.3f}"}), width="stretch")

with st.expander("Saved plans"):
    saved = list_trips()
    st.dataframe(saved, width="stretch") if len(saved) else st.write("No saved plans yet.")
