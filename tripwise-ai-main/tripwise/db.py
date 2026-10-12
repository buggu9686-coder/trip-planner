"""Destination database: data/destinations.csv -> SQLite -> DataFrame."""
import hashlib
import sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "destinations.csv"
DB_PATH = ROOT / "data" / "tripwise.db"


def _csv_hash(csv_path=CSV_PATH):
    return hashlib.md5(Path(csv_path).read_bytes()).hexdigest()


def _kv_get(con, key):
    con.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)")
    row = con.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _kv_set(con, key, value):
    con.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT OR REPLACE INTO app_meta VALUES (?,?)", (key, value))


def init_db(csv_path=CSV_PATH, db_path=DB_PATH):
    df = pd.read_csv(csv_path)
    with sqlite3.connect(db_path) as con:
        df.to_sql("attractions", con, if_exists="replace", index=False)
        _kv_set(con, "bundled_hash", _csv_hash(csv_path))
    return db_path


def _sync_bundled(db_path):
    """If the bundled CSV changed since this DB last saw it, add destinations the DB lacks.
    Never overwrites or removes anything the user stored."""
    h = _csv_hash()
    with sqlite3.connect(db_path) as con:
        if _kv_get(con, "bundled_hash") == h:
            return
        cur = pd.read_sql("SELECT * FROM attractions", con)
        bundled = pd.read_csv(CSV_PATH).drop(columns=["id"], errors="ignore")
        missing = bundled[~bundled["destination"].isin(cur["destination"])]
        if len(missing):
            merged = pd.concat([cur.drop(columns=["id"], errors="ignore"), missing]).reset_index(drop=True)
            merged.insert(0, "id", range(1, len(merged) + 1))
            merged.to_sql("attractions", con, if_exists="replace", index=False)
        _kv_set(con, "bundled_hash", h)


def load_attractions(db_path=DB_PATH):
    if not Path(db_path).exists():
        init_db(db_path=db_path)
    else:
        _sync_bundled(db_path)
    with sqlite3.connect(db_path) as con:
        return pd.read_sql("SELECT * FROM attractions", con)


# ---------------------------------------------------------------------------
# User-supplied data: upload attractions + save planned trips
# ---------------------------------------------------------------------------
import json
from datetime import datetime

from .config import INTERESTS

REQUIRED_COLS = ["destination", "name", "tags", "activity_type", "entry_cost",
                 "rating", "visit_hours", "lat", "lon"]
NUMERIC_COLS = ["entry_cost", "rating", "visit_hours", "lat", "lon"]


def validate_attractions(df: pd.DataFrame):
    """Return (clean_df, warnings). Raises ValueError with a readable message if unusable."""
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))
    df = df[[c for c in df.columns if c in REQUIRED_COLS or c == "id"]]
    for c in NUMERIC_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    bad = df[df[NUMERIC_COLS + ["destination", "name", "tags"]].isna().any(axis=1)]
    if len(bad):
        raise ValueError(f"{len(bad)} row(s) have empty/non-numeric values (first bad row: {bad.index[0] + 2} in the file).")
    if (df["rating"] < 0).any() or (df["rating"] > 5).any():
        raise ValueError("rating must be between 0 and 5.")
    if (df["entry_cost"] < 0).any() or (df["visit_hours"] <= 0).any():
        raise ValueError("entry_cost must be >= 0 and visit_hours must be > 0.")
    for c in ["destination", "name", "tags", "activity_type"]:
        df[c] = df[c].astype(str).str.strip()
    df["tags"] = df["tags"].str.lower().str.replace(r"\s*\|\s*", "|", regex=True)
    unknown = sorted({t for tags in df["tags"] for t in tags.split("|")} - set(INTERESTS))
    warnings = []
    if unknown:
        warnings.append("Ignored by the recommender (not in the interest list): " + ", ".join(unknown))
    return df.drop(columns=["id"], errors="ignore"), warnings


def import_attractions(df: pd.DataFrame, mode="merge", db_path=DB_PATH):
    """Store validated user data. mode='merge' adds new rows and updates same (destination, name);
    mode='replace' wipes the table first. Returns (rows_in_table, warnings)."""
    clean, warnings = validate_attractions(df)
    existing = pd.DataFrame(columns=REQUIRED_COLS) if mode == "replace" else load_attractions(db_path)
    existing = existing.drop(columns=["id"], errors="ignore")
    merged = pd.concat([existing, clean]).drop_duplicates(["destination", "name"], keep="last")
    merged = merged.reset_index(drop=True)
    merged.insert(0, "id", range(1, len(merged) + 1))
    with sqlite3.connect(db_path) as con:
        merged.to_sql("attractions", con, if_exists="replace", index=False)
        _kv_set(con, "bundled_hash", _csv_hash())
    return len(merged), warnings


def reset_attractions(db_path=DB_PATH):
    """Back to the bundled data/destinations.csv."""
    return init_db(db_path=db_path)


def save_trip(inputs: dict, result: dict, db_path=DB_PATH) -> int:
    with sqlite3.connect(db_path) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS saved_trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, destination TEXT,
            budget REAL, days INTEGER, people INTEGER, interests TEXT, stay TEXT,
            transport TEXT, local TEXT, distance_km REAL, estimated_total REAL,
            fits INTEGER, places TEXT, plan_json TEXT)""")
        t = result["trip"]   # final settings after any budget downgrades
        cur = con.execute(
            "INSERT INTO saved_trips (created_at,destination,budget,days,people,interests,stay,transport,"
            "local,distance_km,estimated_total,fits,places,plan_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), inputs["destination"], inputs["budget"],
             inputs["days"], inputs["people"], ",".join(inputs["interests"]), t.stay, t.transport,
             t.local, t.distance_km, result["breakdown"]["TOTAL"], int(result["fits"]),
             ", ".join(result["places"]["name"]),
             json.dumps({"breakdown": result["breakdown"], "itinerary": result["itinerary"],
                         "changes": result["changes"]}, default=float)))
        return cur.lastrowid


def list_trips(db_path=DB_PATH) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        try:
            return pd.read_sql("SELECT id,created_at,destination,budget,days,people,interests,"
                               "estimated_total,fits,places FROM saved_trips ORDER BY id DESC", con)
        except Exception:
            return pd.DataFrame()


def set_meta(destination, country, multiplier, db_path=DB_PATH):
    with sqlite3.connect(db_path) as con:
        con.execute("CREATE TABLE IF NOT EXISTS destination_meta (destination TEXT PRIMARY KEY, country TEXT, multiplier REAL)")
        con.execute("INSERT OR REPLACE INTO destination_meta VALUES (?,?,?)", (destination, country, float(multiplier)))


def get_multiplier(destination, db_path=DB_PATH):
    """Price level saved for a live-added place, else None."""
    if not Path(db_path).exists():
        return None
    with sqlite3.connect(db_path) as con:
        try:
            row = con.execute("SELECT multiplier FROM destination_meta WHERE destination=?", (destination,)).fetchone()
        except sqlite3.OperationalError:
            return None
    return row[0] if row else None
