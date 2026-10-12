import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from tripwise.db import CSV_PATH
from tripwise.recommender import rank_attractions
from tripwise.planner import plan_trip
from tripwise.config import DAY_END

DF = pd.read_csv(CSV_PATH)

def test_dataset_loads():
    assert {"name", "tags", "entry_cost", "rating", "visit_hours"} <= set(DF.columns)
    assert len(DF) > 30

def test_similarity_ranking():
    r = rank_attractions(DF, "Goa", ["history"], 20000, 3, 2)
    assert r["score"].between(0, 1.0001).all()
    assert "history" in r.iloc[0]["tags"]
    assert r["score"].is_monotonic_decreasing

def test_within_budget_no_alert():
    r = plan_trip(DF, "Goa", 90000, 3, 2, ["beaches", "nature"])
    assert r["fits"] and not r["alerts"]

def test_overrun_triggers_alert_and_fix():
    r = plan_trip(DF, "Goa", 12000, 3, 2, ["adventure", "beaches"], stay="luxury", transport="flight")
    assert r["alerts"] and r["changes"]
    assert r["fits"] and r["breakdown"]["TOTAL"] <= 12000

def test_impossible_budget_is_reported():
    r = plan_trip(DF, "Goa", 1000, 3, 4, ["nature"])
    assert not r["fits"] and any("Even the cheapest" in a for a in r["alerts"])

def test_itinerary_respects_time_limit():
    r = plan_trip(DF, "Hampi", 40000, 3, 2, ["history", "culture"])
    for d in r["itinerary"]:
        for s in d["stops"]:
            h, m = map(int, s["end"].split(":"))
            assert h + m / 60 <= DAY_END + 1e-6


def test_user_upload_and_save(tmp_path):
    from tripwise import db
    path = tmp_path / "t.db"
    db.init_db(db_path=path)
    new = pd.DataFrame([{"destination": "Testville", "name": "Test Beach", "tags": "Beaches | nature",
                         "activity_type": "leisure", "entry_cost": 0, "rating": 4.5,
                         "visit_hours": 2, "lat": 14.52, "lon": 74.32}])
    n, _ = db.import_attractions(new, "merge", path)
    assert n == len(DF) + 1
    assert "Testville" in db.load_attractions(path)["destination"].values
    r = plan_trip(db.load_attractions(path), "Testville", 20000, 2, 2, ["beaches"])
    tid = db.save_trip({"destination": "Testville", "budget": 20000, "days": 2, "people": 2,
                        "interests": ["beaches"]}, r, path)
    assert tid == 1 and len(db.list_trips(path)) == 1

def test_bad_upload_rejected():
    import pytest
    from tripwise.db import validate_attractions
    with pytest.raises(ValueError):
        validate_attractions(pd.DataFrame({"name": ["x"]}))


def test_big_dataset_is_valid():
    big = pd.read_csv(CSV_PATH)
    assert big["destination"].nunique() >= 40
    assert big.groupby("destination").size().min() >= 3
    assert big["lat"].between(-90, 90).all() and big["lon"].between(-180, 180).all()
    for t in big["tags"]:
        assert set(t.split("|")) <= {"nature", "adventure", "history", "beaches", "shopping", "food", "culture"}

def test_international_costs_more_than_domestic():
    a = plan_trip(DF, "Goa", 500000, 4, 2, ["culture"], transport="flight", distance_km=500)
    b = plan_trip(DF, "Paris", 500000, 4, 2, ["culture"], transport="flight", distance_km=7000)
    assert b["breakdown"]["TOTAL"] > 2 * a["breakdown"]["TOTAL"]


def _fake_overpass():
    el = lambda n, tags, lat, lon: {"type": "node", "lat": lat, "lon": lon, "tags": {"name": n, **tags}}
    return {"elements": [
        el("Old Fort", {"historic": "fort", "wikidata": "Q1"}, 14.50, 74.30),
        el("Calm Beach", {"natural": "beach", "wikipedia": "en:Calm"}, 14.51, 74.31),
        el("Big Museum", {"tourism": "museum", "fee": "yes"}, 14.52, 74.32),
        el("Hill Peak", {"natural": "peak"}, 14.53, 74.33),
        el("Old Fort", {"historic": "fort"}, 14.50, 74.30),            # duplicate name
        {"type": "node", "lat": 1, "lon": 1, "tags": {"tourism": "attraction"}},  # no name -> skipped
    ]}

def test_live_lookup_pipeline(tmp_path, monkeypatch):
    from tripwise import fetcher, db
    calls = []
    def fake_get(url, data=None, timeout=45):
        calls.append(url)
        if "nominatim" in url:
            return [{"lat": "14.5", "lon": "74.3", "address": {"country_code": "fr"}}]
        return _fake_overpass()
    monkeypatch.setattr(fetcher, "_get", fake_get)
    info = fetcher.fetch_destination("newville")
    assert info["name"] == "Newville" and len(info["df"]) == 4       # duplicate + unnamed removed
    assert info["multiplier"] == 4.0                                  # France price level
    assert info["df"].iloc[0]["name"] == "Old Fort"                   # notable place ranked first
    path = tmp_path / "t.db"
    db.init_db(db_path=path)
    n, warns = db.import_attractions(info["df"], "merge", path)
    assert not warns and "Newville" in db.load_attractions(path)["destination"].values
    db.set_meta("Newville", info["country"], info["multiplier"], path)
    assert db.get_multiplier("Newville", path) == 4.0
    r = plan_trip(db.load_attractions(path), "Newville", 300000, 2, 2, ["history", "beaches"])
    assert r["itinerary"] and r["breakdown"]["TOTAL"] > 0

def test_live_lookup_errors(monkeypatch):
    import pytest
    from tripwise import fetcher
    monkeypatch.setattr(fetcher, "_get", lambda *a, **k: [])
    with pytest.raises(fetcher.FetchError):
        fetcher.fetch_destination("zzzzqqq")
    monkeypatch.setattr(fetcher, "_get", lambda *a, **k: (_ for _ in ()).throw(fetcher.FetchError("offline")))
    with pytest.raises(fetcher.FetchError):
        fetcher.fetch_destination("Paris")


def test_old_database_gets_missing_bundled_places(tmp_path):
    import sqlite3
    from tripwise import db
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as con:                      # simulate an old DB: only Goa, no hash
        pd.read_csv(CSV_PATH).query("destination == 'Goa'").to_sql("attractions", con, index=False)
    got = db.load_attractions(path)
    assert {"Goa", "Bali", "Paris", "Pune"} <= set(got["destination"])
    n_before = len(got)
    assert len(db.load_attractions(path)) == n_before        # idempotent

def test_replace_all_is_not_undone_by_sync(tmp_path):
    from tripwise import db
    path = tmp_path / "r.db"
    db.init_db(db_path=path)
    mine = pd.DataFrame([{"destination": "Mine", "name": "Spot", "tags": "nature", "activity_type": "x",
                          "entry_cost": 0, "rating": 4, "visit_hours": 1, "lat": 1, "lon": 1}])
    db.import_attractions(mine, "replace", path)
    assert list(db.load_attractions(path)["destination"].unique()) == ["Mine"]

def test_radius_scales_with_place_size():
    from tripwise.fetcher import radius_from_bbox
    assert radius_from_bbox(["-9.1", "-8.0", "114.4", "115.7"], -8.4) == 60000     # island
    assert 8000 <= radius_from_bbox(["15.40", "15.46", "73.78", "73.86"], 15.4) < 15000   # town

def test_live_lookup_widens_search_when_few_results(monkeypatch):
    from tripwise import fetcher
    n = {"over": 0}
    def fake_get(url, data=None, timeout=45):
        if "nominatim" in url:
            return [{"lat": "-8.4", "lon": "115.2", "boundingbox": ["-9.1", "-8.0", "114.4", "115.7"],
                     "address": {"country_code": "id"}}]
        n["over"] += 1
        els = [{"lat": 1, "lon": 1, "tags": {"name": f"P{i}", "natural": "beach", "wikidata": "Q"}}
               for i in range(5 if n["over"] == 2 else 1)]
        return {"elements": els}
    monkeypatch.setattr(fetcher, "_get", fake_get)
    info = fetcher.fetch_destination("bali")
    assert n["over"] == 2 and len(info["df"]) == 5 and info["multiplier"] == 1.4
