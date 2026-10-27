import os
import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from config import CAMPUS_SAFETY_CONTACT, DATABASE_PATH, TOP_MATCHES
from matching import score_pair

app = FastAPI(title="Lost & Found Campus Portal", version="1.0.0")


def public_read_only():
    return os.getenv("PUBLIC_DEMO_READ_ONLY", "false").strip().lower() in {"1", "true", "yes"}


def ensure_writes_enabled():
    if public_read_only():
        raise HTTPException(status_code=403, detail="This public demo is read-only.")

@contextmanager
def db():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_db():
    with db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL CHECK(type IN ('lost','found')),
                title TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
                color TEXT NOT NULL, brand TEXT NOT NULL DEFAULT '', location TEXT NOT NULL,
                date_event TEXT NOT NULL, contact_email TEXT NOT NULL, image_path TEXT,
                status TEXT NOT NULL DEFAULT 'open', created_by TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT, lost_item_id INTEGER NOT NULL,
                found_item_id INTEGER NOT NULL, score INTEGER NOT NULL, explanation TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(lost_item_id, found_item_id)
            );
            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER NOT NULL,
                claimant_email TEXT NOT NULL, proof_description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                admin_notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'student', created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310_000)
    return f"{salt.hex()}${password_hash.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    salt_hex, expected_hash = encoded_hash.split("$", 1)
    actual_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 310_000)
    return hmac.compare_digest(actual_hash.hex(), expected_hash)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    with db() as connection:
        connection.execute(
            "INSERT INTO sessions(token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
    return token


def current_user(authorization: str | None = Header(default=None)):
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    now = datetime.now(timezone.utc).isoformat()
    with db() as connection:
        user = connection.execute(
            """SELECT u.id, u.name, u.email, u.role FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token = ? AND s.expires_at > ?""",
            (token, now),
        ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    return dict(user)


def require_admin(user=Depends(current_user)):
    ensure_writes_enabled()
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def public_item(row):
    data = dict(row)
    data.pop("contact_email", None)
    data.pop("created_by", None)
    return data


class ItemCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    type: Literal["lost", "found"]
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=4, max_length=2000)
    category: str = Field(min_length=2, max_length=60)
    color: str = Field(min_length=2, max_length=40)
    brand: str = Field(default="", max_length=80)
    location: str = Field(min_length=2, max_length=120)
    date_event: str
    contact_email: EmailStr
    image_path: str | None = None


class AuthRegister(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=256)


class AuthLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ClaimCreate(BaseModel):
    item_id: int
    proof_description: str = Field(min_length=8, max_length=2000)


class ClaimDecision(BaseModel):
    status: Literal["approved", "rejected"]
    admin_notes: str = Field(default="", max_length=1000)


def _all_matches_for(item_id: int):
    with db() as connection:
        item = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        opposite_type = "found" if item["type"] == "lost" else "lost"
        candidates = connection.execute(
            "SELECT * FROM items WHERE type = ? AND status = 'open'", (opposite_type,)
        ).fetchall()
        results = []
        for candidate in candidates:
            lost, found = (item, candidate) if item["type"] == "lost" else (candidate, item)
            scored = score_pair(dict(lost), dict(found))
            if scored and scored[0] > 0:
                results.append({
                    "item": public_item(candidate), "score": scored[0], "explanation": scored[1]
                })
        results.sort(key=lambda result: result["score"], reverse=True)
        return results[:TOP_MATCHES]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/config")
def public_config():
    return {"read_only": public_read_only(), "campus_safety_contact": CAMPUS_SAFETY_CONTACT}


@app.post("/auth/register", status_code=201)
def register(payload: AuthRegister):
    now = datetime.now(timezone.utc).isoformat()
    email = str(payload.email).strip().lower()
    try:
        with db() as connection:
            cursor = connection.execute(
                """INSERT INTO users(name, email, password_hash, role, created_at)
                   VALUES (?, ?, ?, 'student', ?)""",
                (payload.name.strip(), email, hash_password(payload.password), now),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    return {"token": create_session(user_id), "user": {"id": user_id, "name": payload.name.strip(), "email": email, "role": "student"}}


@app.post("/auth/login")
def login(payload: AuthLogin):
    with db() as connection:
        user = connection.execute(
            "SELECT id, name, email, role, password_hash FROM users WHERE email = ?",
            (str(payload.email).strip().lower(),),
        ).fetchone()
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return {
        "token": create_session(user["id"]),
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]},
    }


@app.post("/auth/logout")
def logout(user=Depends(current_user), authorization: str = Header()):
    token = authorization.partition(" ")[2]
    with db() as connection:
        connection.execute("DELETE FROM sessions WHERE token = ?", (token,))
    return {"status": "ok"}


@app.get("/auth/me")
def auth_me(user=Depends(current_user)):
    return user


@app.post("/items", status_code=201)
def create_item(payload: ItemCreate, user=Depends(current_user), _=Depends(ensure_writes_enabled)):
    try:
        datetime.strptime(payload.date_event, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="date_event must use YYYY-MM-DD format")
    created_at = datetime.now(timezone.utc).isoformat()
    fields = payload.model_dump()
    with db() as connection:
        cursor = connection.execute(
            """INSERT INTO items
            (type,title,description,category,color,brand,location,date_event,contact_email,image_path,created_by,created_at)
            VALUES (:type,:title,:description,:category,:color,:brand,:location,:date_event,:contact_email,:image_path,:created_by,:created_at)""",
            {**fields, "contact_email": user["email"], "created_by": user["email"], "created_at": created_at},
        )
        item_id = cursor.lastrowid
    return {"item": get_item_row(item_id), "matches": _all_matches_for(item_id)}


def get_item_row(item_id):
    with db() as connection:
        row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return public_item(row)


def optional_current_user(authorization: str | None = Header(default=None)):
    if not authorization:
        return None
    return current_user(authorization)


@app.get("/items")
def list_items(
    type: Literal["lost", "found"] | None = None,
    category: str | None = None,
    location: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = Query(default=None, max_length=120),
):
    clauses, values = [], []
    for column, value in (("type", type), ("category", category), ("status", status)):
        if value:
            clauses.append(f"{column} = ?")
            values.append(value)
    if location:
        clauses.append("location LIKE ?")
        values.append(f"%{location}%")
    if date_from:
        clauses.append("date_event >= ?")
        values.append(date_from)
    if date_to:
        clauses.append("date_event <= ?")
        values.append(date_to)
    if q:
        clauses.append("(title LIKE ? OR description LIKE ? OR category LIKE ? OR color LIKE ? OR brand LIKE ?)")
        values.extend([f"%{q}%"] * 5)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db() as connection:
        rows = connection.execute(
            f"SELECT * FROM items {where} ORDER BY created_at DESC", values
        ).fetchall()
    return [public_item(row) for row in rows]


@app.get("/items/{item_id}")
def get_item(item_id: int, user=Depends(optional_current_user)):
    with db() as connection:
        row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    item = public_item(row)
    item["is_owner"] = bool(user and row["created_by"] == user["email"])
    return item


@app.get("/admin/items/{item_id}")
def get_admin_item(item_id: int, user=Depends(require_admin)):
    with db() as connection:
        row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return dict(row)


@app.get("/items/{item_id}/matches")
def item_matches(item_id: int):
    return _all_matches_for(item_id)


@app.get("/my/items")
def my_items(user=Depends(current_user)):
    with db() as connection:
        rows = connection.execute(
            "SELECT * FROM items WHERE created_by = ? ORDER BY created_at DESC", (user["email"],)
        ).fetchall()
    return [public_item(row) for row in rows]


@app.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, user=Depends(current_user), _=Depends(ensure_writes_enabled)):
    with db() as connection:
        item = connection.execute(
            "SELECT created_by, status FROM items WHERE id = ?", (item_id,)
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        if item["created_by"] != user["email"] and user["role"] != "admin":
            raise HTTPException(status_code=403, detail="You can only delete your own reports")
        if item["status"] != "open":
            raise HTTPException(status_code=409, detail="Only open reports can be deleted")
        connection.execute(
            "DELETE FROM matches WHERE lost_item_id = ? OR found_item_id = ?",
            (item_id, item_id),
        )
        connection.execute("DELETE FROM claims WHERE item_id = ?", (item_id,))
        connection.execute("DELETE FROM items WHERE id = ?", (item_id,))


@app.patch("/my/items/{item_id}/recover")
def recover_lost_item(item_id: int, user=Depends(current_user), _=Depends(ensure_writes_enabled)):
    with db() as connection:
        cursor = connection.execute(
            """UPDATE items SET status = 'recovered'
               WHERE id = ? AND created_by = ? AND type = 'lost' AND status = 'open'""",
            (item_id, user["email"]),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=409, detail="Only your open lost reports can be marked recovered")
    return get_item_row(item_id)


@app.delete("/my/items/{item_id}", status_code=204)
def delete_my_item(item_id: int, user=Depends(current_user), _=Depends(ensure_writes_enabled)):
    with db() as connection:
        item = connection.execute(
            "SELECT id FROM items WHERE id = ? AND created_by = ? AND status = 'open'",
            (item_id, user["email"]),
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Open report not found")
        connection.execute("DELETE FROM claims WHERE item_id = ?", (item_id,))
        connection.execute("DELETE FROM matches WHERE lost_item_id = ? OR found_item_id = ?", (item_id, item_id))
        connection.execute("DELETE FROM items WHERE id = ?", (item_id,))


@app.post("/claims", status_code=201)
def create_claim(payload: ClaimCreate, user=Depends(current_user), _=Depends(ensure_writes_enabled)):
    with db() as connection:
        item = connection.execute("SELECT * FROM items WHERE id = ?", (payload.item_id,)).fetchone()
        if not item or item["type"] != "found":
            raise HTTPException(status_code=404, detail="Found item not found")
        if item["status"] != "open":
            raise HTTPException(status_code=409, detail="This item is no longer available to claim")
        if item["created_by"] == user["email"]:
            raise HTTPException(status_code=409, detail="You cannot claim your own found item")
        pending_claim = connection.execute(
            "SELECT 1 FROM claims WHERE item_id = ? AND claimant_email = ? AND status = 'pending'",
            (payload.item_id, user["email"]),
        ).fetchone()
        if pending_claim:
            raise HTTPException(status_code=409, detail="You already have a pending claim for this item")
        cursor = connection.execute(
            "INSERT INTO claims(item_id, claimant_email, proof_description, created_at) VALUES (?,?,?,?)",
            (payload.item_id, user["email"], payload.proof_description,
             datetime.now(timezone.utc).isoformat()),
        )
        return {"id": cursor.lastrowid, "item_id": payload.item_id, "status": "pending"}


def claim_record(row, admin: bool):
    result = {
        "id": row["id"], "item_id": row["item_id"], "item_title": row["item_title"],
        "status": row["status"], "admin_notes": row["admin_notes"], "created_at": row["created_at"],
        "collect_location": row["collect_location"],
    }
    if admin:
        result.update(
            claimant_email=row["claimant_email"],
            reporter_contact_email=row["reporter_contact_email"],
            proof_description=row["proof_description"],
        )
    return result


@app.get("/claims")
def list_claims(user=Depends(current_user), _=Depends(ensure_writes_enabled)):
    with db() as connection:
        query = """SELECT c.*, i.title AS item_title, i.location AS collect_location,
                          i.contact_email AS reporter_contact_email FROM claims c
                   JOIN items i ON i.id = c.item_id"""
        values = ()
        if user["role"] != "admin":
            query += " WHERE c.claimant_email = ?"
            values = (user["email"],)
        query += " ORDER BY c.created_at DESC"
        rows = connection.execute(query, values).fetchall()
    return [claim_record(row, user["role"] == "admin") for row in rows]


@app.patch("/claims/{claim_id}")
def decide_claim(claim_id: int, decision: ClaimDecision, user=Depends(require_admin)):
    with db() as connection:
        claim = connection.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        if claim["status"] != "pending":
            raise HTTPException(status_code=409, detail="Claim has already been reviewed")
        if decision.status == "approved":
            item = connection.execute("SELECT status FROM items WHERE id = ?", (claim["item_id"],)).fetchone()
            if item["status"] != "open":
                raise HTTPException(status_code=409, detail="Item is no longer open")
            connection.execute("UPDATE items SET status = 'claimed' WHERE id = ?", (claim["item_id"],))
            connection.execute(
                "UPDATE claims SET status = 'rejected' WHERE item_id = ? AND id != ? AND status = 'pending'",
                (claim["item_id"], claim_id),
            )
        connection.execute(
            "UPDATE claims SET status = ?, admin_notes = ? WHERE id = ?",
            (decision.status, decision.admin_notes, claim_id),
        )
        row = connection.execute(
            """SELECT c.*, i.title AS item_title, i.location AS collect_location,
                      i.contact_email AS reporter_contact_email
               FROM claims c JOIN items i ON i.id = c.item_id WHERE c.id = ?""",
            (claim_id,),
        ).fetchone()
    return claim_record(row, True)


@app.patch("/claims/{claim_id}/collect")
def confirm_collected(claim_id: int, user=Depends(current_user), _=Depends(ensure_writes_enabled)):
    with db() as connection:
        claim = connection.execute(
            "SELECT item_id FROM claims WHERE id = ? AND claimant_email = ? AND status = 'approved'",
            (claim_id, user["email"]),
        ).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Approved claim not found")
        cursor = connection.execute(
            "UPDATE items SET status = 'returned' WHERE id = ? AND status = 'claimed'",
            (claim["item_id"],),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=409, detail="This item is no longer awaiting collection")
    return get_item_row(claim["item_id"])


@app.get("/my/events")
def my_events(user=Depends(current_user), _=Depends(ensure_writes_enabled)):
    events = []
    with db() as connection:
        decisions = connection.execute(
            """SELECT c.status, c.admin_notes, c.created_at, i.title AS item_title
               FROM claims c JOIN items i ON i.id = c.item_id
               WHERE c.claimant_email = ? AND c.status != 'pending'
               ORDER BY c.created_at DESC LIMIT 10""",
            (user["email"],),
        ).fetchall()
        owned_items = connection.execute(
            "SELECT id, title FROM items WHERE created_by = ? ORDER BY created_at DESC LIMIT 20",
            (user["email"],),
        ).fetchall()
    for decision in decisions:
        events.append({
            "type": "claim_decision", "created_at": decision["created_at"],
            "message": f'Your claim for "{decision["item_title"]}" was {decision["status"]}.',
            "admin_notes": decision["admin_notes"],
        })
    for owned_item in owned_items:
        try:
            match_list = _all_matches_for(owned_item["id"])
        except HTTPException:
            raise
        for match in match_list:
            events.append({
                "type": "new_match", "created_at": match["item"].get("created_at", ""),
                "message": f'Possible match for "{owned_item["title"]}": {match["item"]["title"]}.',
            })
    events.sort(key=lambda event: event["created_at"], reverse=True)
    return events[:10]


@app.patch("/items/{item_id}/return")
def return_item(item_id: int, user=Depends(require_admin)):
    with db() as connection:
        cursor = connection.execute(
            "UPDATE items SET status = 'returned' WHERE id = ? AND status = 'claimed'", (item_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=409, detail="Only a claimed item can be marked returned")
    return get_item_row(item_id)


@app.get("/stats")
def stats():
    with db() as connection:
        rows = connection.execute("SELECT status, COUNT(*) AS count FROM items GROUP BY status").fetchall()
    return {row["status"]: row["count"] for row in rows}


initialize_db()

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_app(full_path: str):
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Not found")
