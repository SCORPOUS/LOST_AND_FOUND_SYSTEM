from datetime import date
from difflib import SequenceMatcher

from config import DATE_WINDOW_DAYS, MATCH_WEIGHTS


def _text_similarity(left: str, right: str) -> float:
    left = " ".join((left or "").lower().split())
    right = " ".join((right or "").lower().split())
    if not left or not right:
        return 0.0
    sequence = SequenceMatcher(None, left, right).ratio()
    left_words, right_words = set(left.split()), set(right.split())
    overlap = len(left_words & right_words) / max(len(left_words | right_words), 1)
    return max(sequence, overlap)


def _location_score(left: str, right: str) -> tuple[float, str | None]:
    left, right = (left or "").lower(), (right or "").lower()
    if left == right and left:
        return 1.0, "same location"
    if not left or not right:
        return 0.0, None
    left_parts = [part.strip() for part in left.replace(",", " ").split() if part.strip()]
    right_parts = [part.strip() for part in right.replace(",", " ").split() if part.strip()]
    if left_parts and right_parts and left_parts[0] == right_parts[0]:
        return 0.65, "same campus zone"
    if set(left_parts) & set(right_parts):
        return 0.45, "nearby location"
    return 0.0, None


def score_pair(lost: dict, found: dict) -> tuple[int, str] | None:
    if lost["type"] != "lost" or found["type"] != "found":
        return None
    if (lost.get("category") or "").lower() != (found.get("category") or "").lower():
        return None

    components: dict[str, float] = {}
    reasons = ["same category"]

    text_score = _text_similarity(
        f'{lost.get("title", "")} {lost.get("description", "")}',
        f'{found.get("title", "")} {found.get("description", "")}',
    )
    components["text"] = text_score
    if text_score >= 0.25:
        reasons.append("item descriptions are similar")

    color_match = bool(lost.get("color") and found.get("color")) and (
        lost["color"].strip().lower() == found["color"].strip().lower()
    )
    components["color"] = float(color_match)
    if color_match:
        reasons.append("color matches")

    brand_match = bool(lost.get("brand") and found.get("brand")) and (
        lost["brand"].strip().lower() == found["brand"].strip().lower()
    )
    components["brand"] = float(brand_match)
    if brand_match:
        reasons.append("brand matches")

    location, location_reason = _location_score(
        lost.get("location", ""), found.get("location", "")
    )
    components["location"] = location
    if location_reason:
        reasons.append(location_reason)

    try:
        lost_date = date.fromisoformat(lost["date_event"])
        found_date = date.fromisoformat(found["date_event"])
        days_apart = (found_date - lost_date).days
        date_score = (
            max(0.0, 1 - days_apart / DATE_WINDOW_DAYS)
            if 0 <= days_apart <= DATE_WINDOW_DAYS
            else 0.0
        )
    except (TypeError, ValueError):
        date_score, days_apart = 0.0, None
    components["date"] = date_score
    if date_score:
        reasons.append(f"{days_apart} day(s) apart")

    score = round(sum(MATCH_WEIGHTS[key] * value for key, value in components.items()))
    return score, ", ".join(reasons)
