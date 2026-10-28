from datetime import date
from difflib import SequenceMatcher

def _similarity(left: str, right: str) -> float:
    left = " ".join((left or "").casefold().split())
    right = " ".join((right or "").casefold().split())
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    left_words, right_words = set(left.split()), set(right.split())
    overlap = len(left_words & right_words) / max(len(left_words | right_words), 1)
    return max(sequence, overlap)


def score_pair(lost: dict, found: dict) -> tuple[int, str] | None:
    if lost["type"] != "lost" or found["type"] != "found":
        return None
    lost_category = " ".join((lost.get("category") or "").casefold().split())
    found_category = " ".join((found.get("category") or "").casefold().split())
    category_score = float(bool(lost_category) and lost_category == found_category)
    color_score = _similarity(lost.get("color", ""), found.get("color", ""))
    location_score = _similarity(lost.get("location", ""), found.get("location", ""))
    try:
        lost_date = date.fromisoformat(lost["date_event"])
        found_date = date.fromisoformat(found["date_event"])
        days_apart = abs((found_date - lost_date).days)
        date_score = max(0.0, 1 - days_apart / 7) if days_apart <= 7 else 0.0
    except (TypeError, ValueError):
        date_score, days_apart = 0.0, None

    score = round(
        30 * category_score + 20 * color_score + 30 * location_score + 20 * date_score
    )
    reasons = [
        f"category {round(category_score * 100)}%",
        f"color {round(color_score * 100)}%",
        f"location {round(location_score * 100)}%",
        f"date {days_apart} day(s) apart" if days_apart is not None else "date unavailable",
    ]
    return score, ", ".join(reasons)
