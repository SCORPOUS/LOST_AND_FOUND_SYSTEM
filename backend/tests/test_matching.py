from matching import score_pair
from seed import SEED_ITEMS


def item(kind, **values):
    return {
        "type": kind, "title": "blue hydro flask bottle", "description": "blue steel water bottle",
        "category": "Water bottle", "color": "Blue", "brand": "Hydro Flask",
        "location": "Science Hall", "date_event": "2026-10-10", **values,
    }


def test_obvious_pair_uses_weighted_components():
    result = score_pair(item("lost"), item("found", date_event="2026-10-11"))
    assert result is not None
    score, explanation = result
    assert score == 97
    assert "category 100%" in explanation
    assert "color 100%" in explanation
    assert "1 day(s) apart" in explanation


def test_category_mismatch_loses_only_category_points():
    score, _ = score_pair(item("lost"), item("found", category="Keys"))
    assert score == 70


def test_date_points_decrease_over_seven_days_in_either_direction():
    score, explanation = score_pair(item("lost"), item("found", date_event="2026-10-01"))
    assert score == 80
    assert "9 day(s) apart" in explanation
    score, _ = score_pair(item("lost"), item("found", date_event="2026-10-17"))
    assert score == 80


def test_date_proximity_is_full_same_day_and_zero_after_seven_days():
    same_day, _ = score_pair(item("lost"), item("found"))
    seven_days, _ = score_pair(item("lost"), item("found", date_event="2026-10-17"))
    eight_days, _ = score_pair(item("lost"), item("found", date_event="2026-10-18"))
    assert same_day == 100
    assert seven_days == 80
    assert eight_days == 80


def test_seed_data_pair_scores_with_requested_weights():
    keys = ("type", "title", "description", "category", "color", "brand", "location", "date_event", "contact_email")
    seeded = [dict(zip(keys, row)) for row in SEED_ITEMS]
    strong_pairs = ((0, 1), (2, 3), (4, 5), (6, 7))
    ambiguous_pairs = ((8, 9), (12, 13))

    assert all(score_pair(seeded[lost], seeded[found])[0] >= 70 for lost, found in strong_pairs)
    assert all(score_pair(seeded[lost], seeded[found])[0] > 0 for lost, found in ambiguous_pairs)
    assert score_pair(seeded[0], seeded[4]) is None
    assert score_pair(item("found"), item("lost")) is None
