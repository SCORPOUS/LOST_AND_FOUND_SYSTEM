from matching import score_pair
from seed import SEED_ITEMS


def item(kind, **values):
    return {
        "type": kind, "title": "blue hydro flask bottle", "description": "blue steel water bottle",
        "category": "Water bottle", "color": "Blue", "brand": "Hydro Flask",
        "location": "Science Hall", "date_event": "2026-10-10", **values,
    }


def test_obvious_pair_scores_high_with_explanation():
    result = score_pair(item("lost"), item("found", date_event="2026-10-11"))
    assert result is not None
    score, explanation = result
    assert score >= 80
    assert "same category" in explanation
    assert "color matches" in explanation
    assert "1 day(s) apart" in explanation


def test_category_mismatch_is_excluded():
    assert score_pair(item("lost"), item("found", category="Keys")) is None


def test_found_before_lost_gets_no_date_points():
    score, explanation = score_pair(item("lost"), item("found", date_event="2026-10-01"))
    assert score == 80
    assert "day(s) apart" not in explanation


def test_seed_data_has_four_strong_and_two_ambiguous_pairs():
    keys = ("type", "title", "description", "category", "color", "brand", "location", "date_event", "contact_email")
    seeded = [dict(zip(keys, row)) for row in SEED_ITEMS]
    strong_pairs = ((0, 1), (2, 3), (4, 5), (6, 7))
    ambiguous_pairs = ((8, 9), (12, 13))

    assert all(score_pair(seeded[lost], seeded[found])[0] >= 70 for lost, found in strong_pairs)
    assert all(score_pair(seeded[lost], seeded[found])[0] > 0 for lost, found in ambiguous_pairs)
    assert score_pair(seeded[0], seeded[4]) is None
