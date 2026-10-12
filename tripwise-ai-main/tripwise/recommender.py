"""Content-based recommender using cosine similarity.

Item vector  = [multi-hot interest tags | rating/5 | affordability]
User vector  = [interest tags | 1.0 (wants good ratings) | budget tightness]
Every block is weighted (config.py) so cost/rating can't drown out interests.
"""
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from .config import INTERESTS, W_TAG, W_RATING, W_AFFORD


def item_matrix(df: pd.DataFrame) -> np.ndarray:
    tags = (df["tags"].str.get_dummies("|")
            .reindex(columns=INTERESTS, fill_value=0).to_numpy(float))
    rating = (df["rating"].to_numpy(float) / 5.0)[:, None]
    max_cost = max(float(df["entry_cost"].max()), 1.0)
    afford = (1.0 - df["entry_cost"].to_numpy(float) / max_cost)[:, None]
    return np.hstack([tags * W_TAG, rating * W_RATING, afford * W_AFFORD])


def user_vector(interests, tightness: float) -> np.ndarray:
    chosen = set(interests) if interests else set(INTERESTS)
    tags = np.array([[1.0 if i in chosen else 0.0 for i in INTERESTS]])
    return np.hstack([tags * W_TAG, [[W_RATING]], [[tightness * W_AFFORD]]])


def budget_tightness(budget, days, people) -> float:
    """0 = lots of money per person per day, 1 = very tight."""
    per_person_day = budget / max(people * days, 1)
    return float(np.clip(1.0 - per_person_day / 6000.0, 0.0, 1.0))


def rank_attractions(df, destination, interests, budget, days, people) -> pd.DataFrame:
    sub = df[df["destination"] == destination].reset_index(drop=True)
    if sub.empty:
        return sub.assign(score=[])
    u = user_vector(interests, budget_tightness(budget, days, people))
    sub = sub.copy()
    sub["score"] = cosine_similarity(u, item_matrix(sub))[0]
    return sub.sort_values("score", ascending=False).reset_index(drop=True)
