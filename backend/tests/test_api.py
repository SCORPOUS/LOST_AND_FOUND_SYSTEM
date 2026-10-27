import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATABASE_PATH", str(tmp_path / "test.db"))
    main.initialize_db()
    with TestClient(main.app) as test_client:
        yield test_client


def headers(email="maya@campus.edu", role="student"):
    return {"X-User-Email": email, "X-User-Role": role}


def report(kind, title, date_event):
    return {
        "type": kind, "title": title, "description": "Blue bottle with a mountain sticker",
        "category": "Water bottle", "color": "Blue", "brand": "Hydro Flask",
        "location": "Science Hall", "date_event": date_event,
        "contact_email": "maya@campus.edu",
    }


def test_report_match_claim_review_and_return_flow(client):
    lost = client.post("/items", json=report("lost", "Blue Hydro Flask", "2026-10-10"), headers=headers())
    assert lost.status_code == 201
    assert "contact_email" not in lost.json()["item"]
    assert "created_by" not in lost.json()["item"]

    found_payload = report("found", "Blue steel Hydro Flask", "2026-10-11")
    found_payload["contact_email"] = "sam@campus.edu"
    found = client.post("/items", json=found_payload, headers=headers("sam@campus.edu"))
    assert found.status_code == 201
    assert found.json()["matches"][0]["score"] >= 80
    assert "same category" in found.json()["matches"][0]["explanation"]

    found_id = found.json()["item"]["id"]
    assert client.get(f"/admin/items/{found_id}", headers=headers()).status_code == 403
    admin_item = client.get(
        f"/admin/items/{found_id}", headers=headers("admin@campus.edu", "admin")
    )
    assert admin_item.json()["contact_email"] == "sam@campus.edu"
    claim = client.post(
        "/claims", json={"item_id": found_id, "proof_description": "Crescent scratch below sticker"},
        headers=headers(),
    )
    assert claim.status_code == 201
    claim_id = claim.json()["id"]

    own_claim = client.get("/claims", headers=headers()).json()[0]
    assert own_claim["status"] == "pending"
    assert "proof_description" not in own_claim
    assert "reporter_contact_email" not in own_claim
    assert client.patch(
        f"/claims/{claim_id}", json={"status": "approved"}, headers=headers()
    ).status_code == 403

    approved = client.patch(
        f"/claims/{claim_id}",
        json={"status": "approved", "admin_notes": "Proof verified"},
        headers=headers("admin@campus.edu", "admin"),
    )
    assert approved.status_code == 200
    assert approved.json()["proof_description"] == "Crescent scratch below sticker"
    assert approved.json()["reporter_contact_email"] == "sam@campus.edu"
    assert client.get(f"/items/{found_id}").json()["status"] == "claimed"

    returned = client.patch(
        f"/items/{found_id}/return", headers=headers("admin@campus.edu", "admin")
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "returned"


def test_listing_filters_and_claim_conflicts(client):
    item = client.post("/items", json=report("found", "Blue bottle", "2026-10-11"), headers=headers())
    assert item.status_code == 201
    found_id = item.json()["item"]["id"]
    assert len(client.get("/items?type=found&category=Water%20bottle").json()) == 1
    assert client.post(
        "/claims", json={"item_id": found_id, "proof_description": "Distinctive scratch mark"},
        headers=headers(),
    ).status_code == 201
    assert client.post(
        "/claims", json={"item_id": found_id, "proof_description": "Another identifying mark"},
        headers=headers("alex@campus.edu"),
    ).status_code == 201
    client.patch(
        "/claims/1", json={"status": "approved"}, headers=headers("admin@campus.edu", "admin")
    )
    assert client.post(
        "/claims", json={"item_id": found_id, "proof_description": "Yet another identifying mark"},
        headers=headers("lee@campus.edu"),
    ).status_code == 409


def test_public_demo_mode_blocks_writes_and_all_admin_claim_data(client, monkeypatch):
    monkeypatch.setenv("PUBLIC_DEMO_READ_ONLY", "true")
    response = client.post(
        "/items", json=report("lost", "Private test report", "2026-10-10"), headers=headers()
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "This public demo is read-only."
    assert client.get("/config").json() == {"read_only": True}
    assert client.get("/claims", headers=headers()).status_code == 403
    assert client.get(
        "/admin/items/1", headers=headers("admin@campus.edu", "admin")
    ).status_code == 403
    assert client.post(
        "/claims", json={"item_id": 1, "proof_description": "Private identifying detail"},
        headers=headers(),
    ).status_code == 403
