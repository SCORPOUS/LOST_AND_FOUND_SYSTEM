import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATABASE_PATH", str(tmp_path / "test.db"))
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
    assert "same category" in found.json()["matches"][0]["explanation"]

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


def test_listing_filters_and_claim_conflicts(client, tokens):
    item = client.post(
        "/items", json=report("found", "Blue bottle", "2026-10-11"),
        headers=headers(tokens, "sam@campus.edu"),
    )
    assert item.status_code == 201
    found_id = item.json()["item"]["id"]
    assert len(client.get("/items?type=found&category=Water%20bottle").json()) == 1
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
