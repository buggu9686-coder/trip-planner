"""Quick terminal demo:  python cli.py --destination Goa --budget 20000 --days 3 --people 2 --interests beaches adventure nature"""
import argparse
from tripwise.db import load_attractions
from tripwise.planner import plan_trip

ap = argparse.ArgumentParser()
ap.add_argument("--destination", default="Goa")
ap.add_argument("--budget", type=float, default=25000)
ap.add_argument("--days", type=int, default=3)
ap.add_argument("--people", type=int, default=2)
ap.add_argument("--interests", nargs="*", default=["beaches", "adventure", "nature"])
ap.add_argument("--stay", default="standard")
ap.add_argument("--transport", default="train")
ap.add_argument("--local", default="cab")
ap.add_argument("--distance", type=float, default=300)
a = ap.parse_args()

r = plan_trip(load_attractions(), a.destination, a.budget, a.days, a.people, a.interests,
              a.stay, a.transport, a.local, a.distance)
print("\nTop recommendations:")
for _, p in r["ranked"].head(6).iterrows():
    print(f"  {p['score']:.3f}  {p['name']}")
for x in r["alerts"] + r["changes"]:
    print(" !", x)
print("\nBudget:")
for k, v in r["breakdown"].items():
    print(f"  {k:<24}Rs {v:>10,.0f}")
print("  Fits budget:", r["fits"])
for d in r["itinerary"]:
    print(f"\nDay {d['day']}")
    for s in d["stops"]:
        print(f"  {s['start']}-{s['end']}  {s['what']}")
