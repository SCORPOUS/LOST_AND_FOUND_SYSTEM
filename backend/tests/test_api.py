import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    main.initialize_db()
    with TestClient(main.app) as test_client:
        for name, email, password, role in [
            ("Maya", "maya@campus.edu", "Student123!", "student"),
            ("Sam", "sam@campus.edu", "Student123!", "student"),
            ("Alex", "alex@campus.edu", "Student123!", "student"),
            ("Admin", "admin@campus.edu", "CampusAdmin123!", "admin"),
        ]:
            with main.db() as connection:
                connection.execute(
                    """INSERT INTO users(name, email, password_hash, role, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (name, email, main.hash_password(password), role, "2026-10-01T00:00:00+00:00"),
                )
        yield test_client


@pytest.fixture
def tokens(client):
    def login(email="maya@campus.edu", password="Student123!"):
        if email == "admin@campus.edu":
            password = "CampusAdmin123!"
        response = client.post("/auth/login", json={"email": email, "password": password})
        assert response.status_code == 200
        return {"Authorization": f"Bearer {response.json()['token']}"}
    return login


def headers(tokens, email="maya@campus.edu"):
    return tokens(email)


def report(kind, title, date_event):
    return {
        "type": kind, "title": title, "description": "Blue bottle with a mountain sticker",
        "category": "Water bottle", "color": "Blue", "brand": "Hydro Flask",
        "location": "Science Hall", "date_event": date_event,
        "contact_email": "maya@campus.edu",
    }


def upload_image(client, tokens, body, content_type="image/png", email="maya@campus.edu", preview=False):
    headers = {**headers_for(tokens, email), "Content-Type": content_type}
    path = "/uploads?preview=true" if preview else "/uploads"
    return client.post(path, content=body, headers=headers)


def headers_for(tokens, email):
    return tokens(email)


def test_report_matches_only_open_opposite_reports_and_limits_results(client, tokens):
    lost = client.post(
        "/items", json=report("lost", "Blue Hydro Flask", "2026-10-10"),
        headers=headers(tokens),
    ).json()["item"]
    found_ids = []
    for day in range(7):
        response = client.post(
            "/items",
            json=report("found", f"Found bottle {day}", f"2026-10-{10 + day}"),
            headers=headers(tokens, "sam@campus.edu"),
        )
        found_ids.append(response.json()["item"]["id"])

    returned_id = found_ids[-1]
    with main.db() as connection:
        connection.execute(
            "UPDATE items SET status = 'returned', returned_at = ? WHERE id = ?",
            ("2026-10-20T00:00:00+00:00", returned_id),
        )
    low_score = client.post(
        "/items",
        json={
            **report("found", "Umbrella", "2026-10-30"),
            "category": "Other", "color": "Orange", "location": "West Gym",
        },
        headers=headers(tokens, "sam@campus.edu"),
    ).json()["item"]["id"]
    opposite_type = client.post(
        "/items", json=report("lost", "Another lost bottle", "2026-10-10"),
        headers=headers(tokens),
    ).json()["item"]["id"]

    response = client.get(f"/reports/{lost['id']}/matches")

    assert response.status_code == 200
    matches = response.json()
    assert len(matches) == 5
    assert all(match["score"] >= 40 for match in matches)
    assert [match["score"] for match in matches] == sorted(
        (match["score"] for match in matches), reverse=True
    )
    result_ids = {match["item"]["id"] for match in matches}
    assert returned_id not in result_ids
    assert low_score not in result_ids
    assert opposite_type not in result_ids


def test_report_match_claim_review_and_return_flow(client, tokens):
    lost = client.post("/items", json=report("lost", "Blue Hydro Flask", "2026-10-10"), headers=headers(tokens))
    assert lost.status_code == 201
    assert "contact_email" not in lost.json()["item"]
    assert "created_by" not in lost.json()["item"]

    found = client.post(
        "/items", json=report("found", "Blue steel Hydro Flask", "2026-10-11"),
        headers=headers(tokens, "sam@campus.edu"),
    )
    assert found.status_code == 201
    assert found.json()["matches"][0]["score"] >= 80
    assert "category 100%" in found.json()["matches"][0]["explanation"]

    found_id = found.json()["item"]["id"]
    assert client.get(f"/admin/items/{found_id}", headers=headers(tokens)).status_code == 403
    admin_item = client.get(f"/admin/items/{found_id}", headers=headers(tokens, "admin@campus.edu"))
    assert admin_item.json()["contact_email"] == "sam@campus.edu"
    claim = client.post(
        "/claims", json={"item_id": found_id, "proof_description": "Crescent scratch below sticker"},
        headers=headers(tokens),
    )
    assert claim.status_code == 201
    claim_id = claim.json()["id"]

    own_claim = client.get("/claims", headers=headers(tokens)).json()[0]
    assert own_claim["status"] == "pending"
    assert "proof_description" not in own_claim
    assert "reporter_contact_email" not in own_claim
    assert client.patch(
        f"/claims/{claim_id}", json={"status": "approved"}, headers=headers(tokens)
    ).status_code == 403

    approved = client.patch(
        f"/claims/{claim_id}",
        json={"status": "approved", "admin_notes": "Proof verified"},
        headers=headers(tokens, "admin@campus.edu"),
    )
    assert approved.status_code == 200
    assert approved.json()["proof_description"] == "Crescent scratch below sticker"
    assert approved.json()["reporter_contact_email"] == "sam@campus.edu"
    assert client.get(f"/items/{found_id}").json()["status"] == "claimed"
    claimant_claim = client.get(f"/claims", headers=headers(tokens)).json()[0]
    assert claimant_claim["collect_location"] == "Science Hall"
    assert claimant_claim["admin_notes"] == "Proof verified"
    assert "reporter_contact_email" not in claimant_claim
    assert "proof_description" not in claimant_claim

    returned = client.patch(
        f"/items/{found_id}/return", headers=headers(tokens, "admin@campus.edu")
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "returned"
    assert returned.json()["returned_at"]
    leaderboard = client.get("/leaderboard").json()
    assert {"name": "Sam", "returns": 1, "badge": "Helper"} in leaderboard
    sam_account = client.get("/account", headers=headers(tokens, "sam@campus.edu")).json()
    assert sam_account["returns"] == 1
    assert sam_account["badge"] == "Helper"


def test_report_image_upload_privacy_and_public_blurred_preview(client, tokens):
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
    upload = upload_image(client, tokens, png)
    preview_upload = upload_image(client, tokens, png, preview=True)
    assert upload.status_code == 201
    assert preview_upload.status_code == 201

    payload = report("found", "Campus ID card", "2026-10-10")
    payload.update({
        "category": "ID cards",
        "image_url": upload.json()["image_url"],
        "image_preview_url": preview_upload.json()["image_url"],
    })
    created = client.post("/items", json=payload, headers=headers(tokens))
    assert created.status_code == 201
    item_id = created.json()["item"]["id"]
    public_list_item = client.get("/items").json()[0]
    assert public_list_item["image_url"] == preview_upload.json()["image_url"]

    public_detail = client.get(f"/items/{item_id}").json()
    assert public_detail["image_url"] == preview_upload.json()["image_url"]
    assert public_detail["can_view_sensitive_image"] is False
    assert "image_path" not in public_detail
    assert "image_preview_url" not in public_detail
    assert upload.json()["image_url"] not in str(public_detail)
    assert client.get(upload.json()["image_url"]).status_code == 403
    assert client.get(preview_upload.json()["image_url"]).status_code == 200

    owner_detail = client.get(f"/items/{item_id}", headers=headers(tokens)).json()
    assert owner_detail["image_url"] == upload.json()["image_url"]
    assert owner_detail["can_view_sensitive_image"] is True
    assert client.get(upload.json()["image_url"], headers=headers(tokens)).status_code == 200
    assert client.get(
        upload.json()["image_url"], headers=headers(tokens, "admin@campus.edu")
    ).status_code == 200
    assert client.get(upload.json()["image_url"], headers=headers(tokens, "sam@campus.edu")).status_code == 403


def test_image_upload_validates_type_size_auth_and_report_ownership(client, tokens):
    assert client.post("/uploads", content=b"image", headers={"Content-Type": "image/gif"}).status_code == 401
    assert upload_image(client, tokens, b"image", content_type="image/gif").status_code == 415
    assert upload_image(client, tokens, b"not an image").status_code == 400
    assert upload_image(client, tokens, b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    foreign_upload = upload_image(
        client, tokens, b"\x89PNG\r\n\x1a\n" + b"\x00" * 24, email="sam@campus.edu"
    )
    payload = report("found", "Blue bottle", "2026-10-10")
    payload["image_url"] = foreign_upload.json()["image_url"]
    assert client.post("/items", json=payload, headers=headers(tokens)).status_code == 403


def test_image_upload_accepts_supported_formats(client, tokens):
    samples = [
        ("image/jpeg", b"\xff\xd8\xff" + b"\x00" * 24),
        ("image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 24),
        ("image/webp", b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 16),
    ]
    for content_type, image_data in samples:
        response = upload_image(client, tokens, image_data, content_type=content_type)
        assert response.status_code == 201
        assert response.json()["image_url"].endswith(
            {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
        )


def test_report_matches_only_return_unresolved_opposites_and_top_five(client, tokens):
    lost = client.post(
        "/items", json=report("lost", "Blue bottle", "2026-10-10"), headers=headers(tokens)
    ).json()["item"]
    found_items = []
    for index in range(6):
        found = report("found", f"Blue bottle {index}", "2026-10-10")
        found_items.append(client.post(
            "/items", json=found, headers=headers(tokens, "sam@campus.edu")
        ).json()["item"])

    matches = client.get(f"/reports/{lost['id']}/matches")
    assert matches.status_code == 200
    assert len(matches.json()) == 5
    assert all(match["score"] == 100 for match in matches.json())
    with main.db() as connection:
        connection.execute(
            "UPDATE items SET status = 'returned', returned_at = ? WHERE id = ?",
            ("2026-10-12T00:00:00+00:00", found_items[0]["id"]),
        )
    still_open = client.get(f"/reports/{lost['id']}/matches").json()
    assert all(match["item"]["id"] != found_items[0]["id"] for match in still_open)
    assert client.get(f"/reports/{found_items[0]['id']}/matches").json() == []
    assert client.get("/items/999999/matches").status_code == 404


def test_admin_recovery_stats_export_and_access_control(client, tokens):
    lost = client.post(
        "/items", json=report("lost", "Lost blue bottle", "2026-10-10"), headers=headers(tokens)
    )
    assert lost.status_code == 201
    found = client.post(
        "/items", json=report("found", "Found blue bottle", "2026-10-10"),
        headers=headers(tokens, "sam@campus.edu"),
    ).json()["item"]
    admin_headers = headers(tokens, "admin@campus.edu")
    assert client.get("/admin/stats", headers=headers(tokens)).status_code == 403
    assert client.get("/admin/export.csv", headers=headers(tokens)).status_code == 403
    claim = client.post(
        "/claims", json={"item_id": found["id"], "proof_description": "Distinctive scratch mark"},
        headers=headers(tokens),
    ).json()
    client.patch(
        f"/claims/{claim['id']}", json={"status": "approved"}, headers=admin_headers
    )
    with main.db() as connection:
        connection.execute(
            "UPDATE items SET created_at = ? WHERE id = ?",
            ((datetime.now(timezone.utc) - timedelta(days=2)).isoformat(), found["id"]),
        )
    client.patch(f"/items/{found['id']}/return", headers=admin_headers)

    stats = client.get("/admin/stats", headers=admin_headers)
    assert stats.status_code == 200
    assert stats.json()["total_reports"] == 2
    assert stats.json()["returned_count"] == 1
    assert stats.json()["unclaimed_count"] == 1
    assert stats.json()["returned_rate"] == 50
    assert stats.json()["unclaimed_rate"] == 50
    assert stats.json()["average_recovery_hours"] > 0
    exported = client.get("/admin/export.csv", headers=admin_headers)
    assert exported.status_code == 200
    assert "text/csv" in exported.headers["content-type"]
    assert "returned_at" in exported.text.splitlines()[0]
    assert "sam@campus.edu" in exported.text


def test_badge_thresholds_and_safe_returned_at_migration(tmp_path, monkeypatch):
    assert main.badge_for_returns(0) is None
    assert main.badge_for_returns(1) == "Helper"
    assert main.badge_for_returns(4) == "Helper"
    assert main.badge_for_returns(5) == "Good Samaritan"
    assert main.badge_for_returns(10) == "Campus Hero"

    database_path = tmp_path / "existing.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """CREATE TABLE items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL, title TEXT NOT NULL,
                description TEXT NOT NULL, category TEXT NOT NULL, color TEXT NOT NULL,
                brand TEXT NOT NULL DEFAULT '', location TEXT NOT NULL, date_event TEXT NOT NULL,
                contact_email TEXT NOT NULL, image_path TEXT, status TEXT NOT NULL DEFAULT 'open',
                created_by TEXT NOT NULL, created_at TEXT NOT NULL
            )"""
        )
        connection.execute(
            """INSERT INTO items
               (type, title, description, category, color, location, date_event,
               contact_email, image_path, created_by, created_at, status)
               VALUES ('found', 'Found keys', 'Silver keychain', 'Keys', 'Silver',
                      'Library', '2026-10-01', 'sam@campus.edu', '/legacy/keys.jpg', 'sam@campus.edu',
                       '2026-10-01T00:00:00+00:00', 'returned')"""
        )

    monkeypatch.setattr(main, "DATABASE_PATH", str(database_path))
    main.initialize_db()
    with main.db() as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(items)")}
        preserved = connection.execute(
            "SELECT title, status, image_url FROM items WHERE id = 1"
        ).fetchone()
        credit = connection.execute(
            "SELECT finder_email FROM return_credits WHERE item_id = 1"
        ).fetchone()
    assert "returned_at" in columns
    assert tuple(preserved) == ("Found keys", "returned", "/legacy/keys.jpg")
    assert credit["finder_email"] == "sam@campus.edu"


def test_listing_filters_and_claim_conflicts(client, tokens):
    item = client.post(
        "/items", json=report("found", "Blue bottle", "2026-10-11"),
        headers=headers(tokens, "sam@campus.edu"),
    )
    assert item.status_code == 201
    found_id = item.json()["item"]["id"]
    assert len(client.get("/items?type=found&category=Water%20bottle").json()) == 1
    assert len(client.get("/items?q=Science%20Hall").json()) == 1
    assert len(client.get("/items?q=Blue").json()) == 1
    assert client.post(
        "/claims", json={"item_id": found_id, "proof_description": "Distinctive scratch mark"},
        headers=headers(tokens),
    ).status_code == 201
    assert client.post(
        "/claims", json={"item_id": found_id, "proof_description": "Another identifying mark"},
        headers=headers(tokens, "alex@campus.edu"),
    ).status_code == 201
    client.patch(
        "/claims/1", json={"status": "approved"}, headers=headers(tokens, "admin@campus.edu")
    )
    assert client.post(
        "/claims", json={"item_id": found_id, "proof_description": "Yet another identifying mark"},
        headers=headers(tokens, "maya@campus.edu"),
    ).status_code == 409


def test_public_demo_mode_blocks_writes_and_all_admin_claim_data(client, tokens, monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO_READ_ONLY", "true")
    response = client.post(
        "/items", json=report("lost", "Private test report", "2026-10-10"), headers=headers(tokens)
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "This public demo is read-only."
    assert client.get("/config").json()["read_only"] is True
    assert client.get("/claims", headers=headers(tokens)).status_code == 403
    assert client.get(
        "/admin/items/1", headers=headers(tokens, "admin@campus.edu")
    ).status_code == 403
    assert client.post(
        "/claims", json={"item_id": 1, "proof_description": "Private identifying detail"},
        headers=headers(tokens),
    ).status_code == 403


def test_auth_register_login_and_wrong_password(client):
    registered = client.post(
        "/auth/register",
        json={"name": "New Student", "email": "new@campus.edu", "password": "NewStudent123"},
    )
    assert registered.status_code == 201
    assert registered.json()["user"]["role"] == "student"
    registered_account = client.get(
        "/account", headers={"Authorization": f"Bearer {registered.json()['token']}"}
    ).json()
    assert registered_account["total_logins"] == 1
    assert registered_account["last_login_at"]
    assert client.get(
        "/auth/me", headers={"Authorization": f"Bearer {registered.json()['token']}"}
    ).json()["email"] == "new@campus.edu"
    auth_headers = {"Authorization": f"Bearer {registered.json()['token']}"}
    assert client.post("/auth/logout", headers=auth_headers).status_code == 200
    assert client.get("/auth/me", headers=auth_headers).status_code == 401
    assert client.post(
        "/auth/login", json={"email": "maya@campus.edu", "password": "wrong-password"}
    ).status_code == 401
    assert client.post(
        "/auth/register",
        json={"name": "Short", "email": "short@campus.edu", "password": "short"},
    ).status_code == 422


def test_student_cannot_claim_own_found_item_or_duplicate_pending_claim(client, tokens):
    own_item = client.post(
        "/items", json=report("found", "My blue bottle", "2026-10-11"), headers=headers(tokens)
    ).json()["item"]
    own_claim = client.post(
        "/claims",
        json={"item_id": own_item["id"], "proof_description": "I know every mark on it"},
        headers=headers(tokens),
    )
    assert own_claim.status_code == 409

    found = client.post(
        "/items", json=report("found", "Found blue bottle", "2026-10-11"),
        headers=headers(tokens, "sam@campus.edu"),
    ).json()["item"]
    payload = {"item_id": found["id"], "proof_description": "There is a scratch near the lid"}
    assert client.post("/claims", json=payload, headers=headers(tokens)).status_code == 201
    duplicate = client.post("/claims", json=payload, headers=headers(tokens))
    assert duplicate.status_code == 409


def test_approved_claim_rejects_others_and_claimant_confirms_collection(client, tokens):
    found = client.post(
        "/items", json=report("found", "Found bottle", "2026-10-11"),
        headers=headers(tokens, "sam@campus.edu"),
    ).json()["item"]
    first = client.post(
        "/claims", json={"item_id": found["id"], "proof_description": "A unique mark under it"},
        headers=headers(tokens),
    ).json()
    second = client.post(
        "/claims", json={"item_id": found["id"], "proof_description": "A unique mark on its base"},
        headers=headers(tokens, "alex@campus.edu"),
    ).json()
    client.patch(
        f"/claims/{first['id']}", json={"status": "approved", "admin_notes": "Verified"},
        headers=headers(tokens, "admin@campus.edu"),
    )
    records = client.get("/claims", headers=headers(tokens, "admin@campus.edu")).json()
    assert next(row for row in records if row["id"] == second["id"])["status"] == "rejected"
    assert client.patch(
        f"/claims/{first['id']}/collect", headers=headers(tokens)
    ).json()["status"] == "returned"


def test_student_can_recover_or_delete_only_their_open_reports(client, tokens):
    lost = client.post(
        "/items", json=report("lost", "Lost bottle", "2026-10-10"), headers=headers(tokens)
    ).json()["item"]
    recovered = client.patch(f"/my/items/{lost['id']}/recover", headers=headers(tokens))
    assert recovered.status_code == 200
    assert recovered.json()["status"] == "recovered"

    found = client.post(
        "/items", json=report("found", "Found bottle", "2026-10-11"), headers=headers(tokens)
    ).json()["item"]
    assert client.patch(
        f"/my/items/{found['id']}/recover", headers=headers(tokens)
    ).status_code == 409

    another_lost = client.post(
        "/items", json=report("lost", "Lost keys", "2026-10-12"),
        headers=headers(tokens, "sam@campus.edu"),
    ).json()["item"]
    assert client.delete(
        f"/my/items/{another_lost['id']}", headers=headers(tokens)
    ).status_code == 404
    assert client.delete(f"/my/items/{found['id']}", headers=headers(tokens)).status_code == 204
    assert client.get(f"/items/{found['id']}").status_code == 404


def test_recent_events_include_decisions_and_possible_matches(client, tokens):
    lost = client.post(
        "/items", json=report("lost", "My blue bottle", "2026-10-10"), headers=headers(tokens)
    ).json()["item"]
    client.post(
        "/items", json=report("found", "Found blue bottle", "2026-10-11"),
        headers=headers(tokens, "sam@campus.edu"),
    )
    match_events = client.get("/my/events", headers=headers(tokens)).json()
    assert any(event["type"] == "new_match" and str(lost["title"]) in event["message"] for event in match_events)

    claim = client.post(
        "/claims",
        json={"item_id": 2, "proof_description": "I know a distinctive mark"},
        headers=headers(tokens),
    )
    assert claim.status_code == 201
    client.patch(
        f"/claims/{claim.json()['id']}", json={"status": "approved"},
        headers=headers(tokens, "admin@campus.edu"),
    )
    events = client.get("/my/events", headers=headers(tokens)).json()
    assert any(event["type"] == "claim_decision" and event["admin_notes"] == "" for event in events)


def test_delete_item_allows_owner_and_cleans_claims(client, tokens):
    found = client.post(
        "/items", json=report("found", "Found blue bottle", "2026-10-11"),
        headers=headers(tokens),
    ).json()["item"]
    claim = client.post(
        "/claims",
        json={"item_id": found["id"], "proof_description": "There is a hidden blue mark"},
        headers=headers(tokens, "sam@campus.edu"),
    )
    assert claim.status_code == 201
    lost = client.post(
        "/items", json=report("lost", "Lost blue bottle", "2026-10-10"),
        headers=headers(tokens, "sam@campus.edu"),
    ).json()["item"]
    with main.db() as connection:
        connection.execute(
            """INSERT INTO matches(lost_item_id, found_item_id, score, explanation, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (lost["id"], found["id"], 90, "Test match", "2026-10-27T00:00:00+00:00"),
        )
    own_detail = client.get(f"/items/{found['id']}", headers=headers(tokens)).json()
    assert own_detail["is_owner"] is True
    other_detail = client.get(
        f"/items/{found['id']}", headers=headers(tokens, "sam@campus.edu")
    ).json()
    assert other_detail["is_owner"] is False

    deleted = client.delete(f"/items/{found['id']}", headers=headers(tokens))
    assert deleted.status_code == 204
    assert client.get(f"/items/{found['id']}").status_code == 404
    with main.db() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM claims WHERE item_id = ?", (found["id"],)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM matches WHERE lost_item_id = ? OR found_item_id = ?",
            (found["id"], found["id"]),
        ).fetchone()[0] == 0


def test_delete_item_forbids_other_student_and_claimed_status(client, tokens):
    found = client.post(
        "/items", json=report("found", "Found blue bottle", "2026-10-11"),
        headers=headers(tokens, "maya@campus.edu"),
    ).json()["item"]
    forbidden = client.delete(
        f"/items/{found['id']}", headers=headers(tokens, "sam@campus.edu")
    )
    assert forbidden.status_code == 403
    admin_report = client.post(
        "/items", json=report("lost", "Open report for admin", "2026-10-12"),
        headers=headers(tokens, "sam@campus.edu"),
    ).json()["item"]
    assert client.delete(
        f"/items/{admin_report['id']}", headers=headers(tokens, "admin@campus.edu")
    ).status_code == 204

    claim = client.post(
        "/claims",
        json={"item_id": found["id"], "proof_description": "There is a hidden blue mark"},
        headers=headers(tokens, "sam@campus.edu"),
    ).json()
    approved = client.patch(
        f"/claims/{claim['id']}", json={"status": "approved"},
        headers=headers(tokens, "admin@campus.edu"),
    )
    assert approved.status_code == 200
    conflict = client.delete(
        f"/items/{found['id']}", headers=headers(tokens, "maya@campus.edu")
    )
    assert conflict.status_code == 409
    missing = client.delete("/items/9999", headers=headers(tokens))
    assert missing.status_code == 404


def test_account_analytics_and_admin_dashboard_data(client, tokens):
    lost = client.post(
        "/items", json=report("lost", "My blue bottle", "2026-10-10"),
        headers=headers(tokens, "maya@campus.edu"),
    ).json()["item"]
    found = client.post(
        "/items", json=report("found", "Found blue bottle", "2026-10-11"),
        headers=headers(tokens, "sam@campus.edu"),
    ).json()["item"]
    claim = client.post(
        "/claims",
        json={"item_id": found["id"], "proof_description": "A unique mark below the lid"},
        headers=headers(tokens, "maya@campus.edu"),
    )
    assert claim.status_code == 201

    maya_headers = headers(tokens, "maya@campus.edu")
    account = client.get("/account", headers=maya_headers)
    assert account.status_code == 200
    assert account.json()["email"] == "maya@campus.edu"
    assert account.json()["total_logins"] >= 2
    assert account.json()["last_login_at"]

    analytics = client.get("/dashboard/analytics", headers=maya_headers)
    assert analytics.status_code == 200
    assert analytics.json()["lost"] == 1
    assert analytics.json()["found"] == 1
    assert analytics.json()["locations"] == [{"location": "Science Hall", "count": 2}]
    assert analytics.json()["timeline"][0]["count"] == 2

    admin_headers = headers(tokens, "admin@campus.edu")
    students = client.get("/admin/users", headers=admin_headers)
    assert students.status_code == 200
    maya = next(student for student in students.json() if student["email"] == "maya@campus.edu")
    assert maya["total_logins"] >= 2
    assert maya["last_login_at"]

    activity = client.get("/admin/activity", headers=admin_headers)
    assert activity.status_code == 200
    event_types = {event["event_type"] for event in activity.json()}
    assert {"report", "claim", "match"}.issubset(event_types)
    filtered = client.get(
        "/admin/activity?event_type=match&q=bottle", headers=admin_headers
    )
    assert filtered.status_code == 200
    assert filtered.json()
    assert all(event["event_type"] == "match" for event in filtered.json())
    assert client.get("/admin/users", headers=maya_headers).status_code == 403
