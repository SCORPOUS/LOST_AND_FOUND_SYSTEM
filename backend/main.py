import os
import csv
import hashlib
import hmac
import io
import re
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from config import CAMPUS_SAFETY_CONTACT, DATABASE_PATH, TOP_MATCHES
from matching import score_pair

app = FastAPI(title="Lost & Found Campus Portal", version="1.0.0")
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_LIMIT = 5 * 1024 * 1024
IMAGE_TYPES = {
    "image/jpeg": ("jpg", lambda data: data.startswith(b"\xff\xd8\xff")),
    "image/png": ("png", lambda data: data.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/webp": ("webp", lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"),
}
UPLOAD_NAME = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp)$")


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
                image_url TEXT, image_preview_url TEXT,
                status TEXT NOT NULL DEFAULT 'open', created_by TEXT NOT NULL, created_at TEXT NOT NULL,
                returned_at TEXT
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
                role TEXT NOT NULL DEFAULT 'student', created_at TEXT NOT NULL,
                last_login_at TEXT, total_logins INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                entity_key TEXT NOT NULL UNIQUE,
                actor_email TEXT NOT NULL,
                item_title TEXT NOT NULL,
                related_title TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS return_credits (
                item_id INTEGER PRIMARY KEY,
                finder_email TEXT NOT NULL,
                credited_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS uploaded_images (
                image_url TEXT PRIMARY KEY,
                uploader_email TEXT NOT NULL,
                is_preview INTEGER NOT NULL DEFAULT 0,
                uploaded_at TEXT NOT NULL
            );
            """
        )
        item_columns = {row["name"] for row in connection.execute("PRAGMA table_info(items)")}
        if "returned_at" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN returned_at TEXT")
        if "image_url" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN image_url TEXT")
        if "image_preview_url" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN image_preview_url TEXT")
        connection.execute(
            "UPDATE items SET image_url = image_path WHERE image_url IS NULL AND image_path IS NOT NULL"
        )
        user_columns = {row["name"] for row in connection.execute("PRAGMA table_info(users)")}
        if "last_login_at" not in user_columns:
            connection.execute("ALTER TABLE users ADD COLUMN last_login_at TEXT")
        if "total_logins" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN total_logins INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute(
            """INSERT OR IGNORE INTO return_credits(item_id, finder_email, credited_at)
               SELECT id, created_by, created_at FROM items
               WHERE type = 'found' AND status IN ('claimed', 'returned')"""
        )
        connection.execute(
            """INSERT OR IGNORE INTO activity_log
               (event_type, entity_key, actor_email, item_title, summary, created_at)
               SELECT 'report', 'report:' || id, created_by, title,
                      'Report posted', created_at FROM items"""
        )
        connection.execute(
            """INSERT OR IGNORE INTO activity_log
               (event_type, entity_key, actor_email, item_title, summary, created_at)
               SELECT 'claim', 'claim:' || c.id, c.claimant_email, i.title,
                      'Claim submitted', c.created_at
               FROM claims c JOIN items i ON i.id = c.item_id"""
        )


def add_activity(event_type, entity_key, actor_email, item_title, summary,
                 created_at, related_title=""):
    with db() as connection:
        connection.execute(
            """INSERT OR IGNORE INTO activity_log
               (event_type, entity_key, actor_email, item_title, related_title, summary, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_type, entity_key, actor_email, item_title, related_title, summary, created_at),
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


def optional_current_user(authorization: str | None = Header(default=None)):
    if not authorization:
        return None
    return current_user(authorization)


def public_item(row, allow_sensitive_image=False):
    data = dict(row)
    if "image_url" in data:
        image_url = data.get("image_url") or data.get("image_path")
        is_id_card = (data.get("category") or "").strip().casefold() in {"id card", "id cards"}
        data["image_url"] = (
            image_url if allow_sensitive_image else data.get("image_preview_url")
        ) if is_id_card else image_url
        data.pop("image_path", None)
        data.pop("image_preview_url", None)
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
    image_url: str | None = None
    image_preview_url: str | None = None
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
        if item["status"] in {"returned", "recovered"} or item["returned_at"] is not None:
            return []
        opposite_type = "found" if item["type"] == "lost" else "lost"
        candidates = connection.execute(
            """SELECT * FROM items
               WHERE type = ? AND returned_at IS NULL AND status NOT IN ('returned', 'recovered')""",
            (opposite_type,),
        ).fetchall()
        results = []
        for candidate in candidates:
            lost, found = (item, candidate) if item["type"] == "lost" else (candidate, item)
            scored = score_pair(dict(lost), dict(found))
            if scored and scored[0] >= 40:
                results.append({
                    "item": public_item(candidate), "score": scored[0], "explanation": scored[1]
                })
        results.sort(key=lambda result: result["score"], reverse=True)
        return results[:min(TOP_MATCHES, 5)]


def award_finder_credit(connection, item_id: int, credited_at: str):
    item = connection.execute(
        "SELECT type, created_by FROM items WHERE id = ?", (item_id,)
    ).fetchone()
    if item and item["type"] == "found":
        connection.execute(
            """INSERT OR IGNORE INTO return_credits(item_id, finder_email, credited_at)
               VALUES (?, ?, ?)""",
            (item_id, item["created_by"], credited_at),
        )


def badge_for_returns(returns: int) -> str | None:
    if returns >= 10:
        return "Campus Hero"
    if returns >= 5:
        return "Good Samaritan"
    if returns >= 1:
        return "Helper"
    return None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/uploads", status_code=201)
async def upload_report_image(
    request: Request,
    preview: bool = False,
    user=Depends(current_user),
    _=Depends(ensure_writes_enabled),
):
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    image_type = IMAGE_TYPES.get(content_type)
    if image_type is None:
        raise HTTPException(status_code=415, detail="Upload a JPG, PNG, or WebP image.")

    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > UPLOAD_LIMIT:
            raise HTTPException(status_code=413, detail="Images must be 5 MB or smaller.")
    if not content or not image_type[1](content):
        raise HTTPException(status_code=400, detail="The uploaded file is not a valid image.")

    extension = image_type[0]
    filename = f"{uuid.uuid4().hex}.{extension}"
    destination_dir = UPLOAD_DIR / "preview" if preview else UPLOAD_DIR
    destination_dir.mkdir(parents=True, exist_ok=True)
    (destination_dir / filename).write_bytes(content)
    prefix = "/uploads/preview" if preview else "/uploads"
    image_url = f"{prefix}/{filename}"
    with db() as connection:
        connection.execute(
            """INSERT INTO uploaded_images(image_url, uploader_email, is_preview, uploaded_at)
               VALUES (?, ?, ?, ?)""",
            (image_url, user["email"], int(preview), datetime.now(timezone.utc).isoformat()),
        )
    return {"image_url": image_url}


@app.get("/uploads/preview/{filename}")
def get_image_preview(filename: str):
    if not UPLOAD_NAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="Image not found")
    image_path = UPLOAD_DIR / "preview" / filename
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)


@app.get("/uploads/{filename}")
def get_report_image(filename: str, user=Depends(optional_current_user)):
    if not UPLOAD_NAME.fullmatch(filename):
        raise HTTPException(status_code=404, detail="Image not found")
    image_url = f"/uploads/{filename}"
    with db() as connection:
        row = connection.execute(
            """SELECT category, created_by FROM items
               WHERE image_url = ? OR image_path = ? LIMIT 1""",
            (image_url, image_url),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")
    is_id_card = row["category"].strip().casefold() in {"id card", "id cards"}
    if is_id_card and not (
        user and (user["role"] == "admin" or user["email"] == row["created_by"])
    ):
        raise HTTPException(status_code=403, detail="Only the report owner or an admin can view this image.")
    image_path = UPLOAD_DIR / filename
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)


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
                """INSERT INTO users
                   (name, email, password_hash, role, created_at, last_login_at, total_logins)
                   VALUES (?, ?, ?, 'student', ?, ?, 1)""",
                (payload.name.strip(), email, hash_password(payload.password), now, now),
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
    logged_in_at = datetime.now(timezone.utc).isoformat()
    with db() as connection:
        connection.execute(
            "UPDATE users SET last_login_at = ?, total_logins = total_logins + 1 WHERE id = ?",
            (logged_in_at, user["id"]),
        )
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


@app.get("/account")
def account(user=Depends(current_user)):
    with db() as connection:
        row = connection.execute(
            """SELECT u.name, u.email, u.role, u.created_at, u.last_login_at, u.total_logins,
                      COUNT(rc.item_id) AS returns
               FROM users u LEFT JOIN return_credits rc ON rc.finder_email = u.email
               WHERE u.id = ? GROUP BY u.id""",
            (user["id"],),
        ).fetchone()
    result = dict(row)
    result["badge"] = badge_for_returns(result["returns"])
    return result


@app.get("/leaderboard")
def leaderboard():
    with db() as connection:
        rows = connection.execute(
            """SELECT u.name, COUNT(rc.item_id) AS returns
               FROM users u JOIN return_credits rc ON rc.finder_email = u.email
               WHERE u.role = 'student'
               GROUP BY u.id HAVING COUNT(rc.item_id) > 0
               ORDER BY returns DESC, u.name COLLATE NOCASE LIMIT 10"""
        ).fetchall()
    return [
        {"name": row["name"], "returns": row["returns"],
         "badge": badge_for_returns(row["returns"])}
        for row in rows
    ]


@app.post("/items", status_code=201)
def create_item(payload: ItemCreate, user=Depends(current_user), _=Depends(ensure_writes_enabled)):
    try:
        datetime.strptime(payload.date_event, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=422, detail="date_event must use YYYY-MM-DD format")
    image_url = payload.image_url or payload.image_path
    image_preview_url = payload.image_preview_url
    for image_value, is_preview in ((image_url, False), (image_preview_url, True)):
        if image_value is None:
            continue
        prefix = "/uploads/preview/" if is_preview else "/uploads/"
        filename = image_value.removeprefix(prefix)
        if not image_value.startswith(prefix) or not UPLOAD_NAME.fullmatch(filename):
            raise HTTPException(status_code=422, detail="Report images must come from the upload endpoint.")
        stored_image = (UPLOAD_DIR / "preview" / filename) if is_preview else (UPLOAD_DIR / filename)
        if not stored_image.is_file():
            raise HTTPException(status_code=422, detail="Uploaded report image was not found.")
        with db() as connection:
            upload = connection.execute(
                """SELECT uploader_email, is_preview FROM uploaded_images
                   WHERE image_url = ?""",
                (image_value,),
            ).fetchone()
        if (
            not upload
            or upload["uploader_email"] != user["email"]
            or bool(upload["is_preview"]) != is_preview
        ):
            raise HTTPException(status_code=403, detail="Use an image uploaded from your account.")
    if (
        image_url
        and payload.category.strip().casefold() in {"id card", "id cards"}
        and not image_preview_url
    ):
        raise HTTPException(status_code=422, detail="ID card reports require a blurred image preview.")
    if image_preview_url and (payload.category.strip().casefold() not in {"id card", "id cards"}):
        raise HTTPException(status_code=422, detail="Blurred previews are only supported for ID card reports.")
    created_at = datetime.now(timezone.utc).isoformat()
    fields = payload.model_dump()
    fields["image_url"] = image_url
    fields["image_preview_url"] = image_preview_url
    with db() as connection:
        cursor = connection.execute(
            """INSERT INTO items
            (type,title,description,category,color,brand,location,date_event,contact_email,
             image_url,image_preview_url,image_path,created_by,created_at)
            VALUES (:type,:title,:description,:category,:color,:brand,:location,:date_event,
                    :contact_email,:image_url,:image_preview_url,:image_url,:created_by,:created_at)""",
            {**fields, "contact_email": user["email"], "created_by": user["email"], "created_at": created_at},
        )
        item_id = cursor.lastrowid
    matches = _all_matches_for(item_id)
    add_activity(
        "report", f"report:{item_id}", user["email"], payload.title,
        f'{payload.type.title()} report posted in {payload.location}.', created_at,
    )
    for match in matches:
        lost_id, found_id = (
            (item_id, match["item"]["id"])
            if payload.type == "lost"
            else (match["item"]["id"], item_id)
        )
        add_activity(
            "match", f"match:{lost_id}:{found_id}", user["email"],
            payload.title, f'Possible match found: {match["item"]["title"]}.',
            created_at, match["item"]["title"],
        )
    return {"item": get_item_row(item_id), "matches": matches}


def get_item_row(item_id):
    with db() as connection:
        row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return public_item(row)


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
        clauses.append(
            """(title LIKE ? OR description LIKE ? OR category LIKE ? OR location LIKE ?
               OR color LIKE ? OR brand LIKE ?)"""
        )
        values.extend([f"%{q}%"] * 6)
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
    can_view_sensitive_image = bool(
        user and (user["role"] == "admin" or row["created_by"] == user["email"])
    )
    item = public_item(row, allow_sensitive_image=can_view_sensitive_image)
    item["is_owner"] = bool(user and row["created_by"] == user["email"])
    item["can_view_sensitive_image"] = can_view_sensitive_image
    return item


@app.get("/admin/items/{item_id}")
def get_admin_item(item_id: int, user=Depends(require_admin)):
    with db() as connection:
        row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    return dict(row)


@app.get("/reports/{item_id}/matches")
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


@app.get("/dashboard/analytics")
def dashboard_analytics(user=Depends(current_user)):
    with db() as connection:
        type_rows = connection.execute(
            "SELECT type, COUNT(*) AS count FROM items GROUP BY type"
        ).fetchall()
        timeline_rows = connection.execute(
            """SELECT substr(created_at, 1, 10) AS date, COUNT(*) AS count
               FROM items GROUP BY substr(created_at, 1, 10) ORDER BY date"""
        ).fetchall()
        location_rows = connection.execute(
            """SELECT location, COUNT(*) AS count FROM items
               GROUP BY location ORDER BY count DESC, location COLLATE NOCASE LIMIT 10"""
        ).fetchall()
    counts = {row["type"]: row["count"] for row in type_rows}
    return {
        "lost": counts.get("lost", 0),
        "found": counts.get("found", 0),
        "timeline": [dict(row) for row in timeline_rows],
        "locations": [dict(row) for row in location_rows],
    }


@app.get("/admin/users")
def admin_users(user=Depends(require_admin)):
    with db() as connection:
        rows = connection.execute(
            """SELECT name, email, last_login_at, total_logins
               FROM users WHERE role = 'student'
               ORDER BY name COLLATE NOCASE, email COLLATE NOCASE"""
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/admin/activity")
def admin_activity(
    q: str | None = Query(default=None, max_length=120),
    event_type: Literal["report", "claim", "match"] | None = None,
    user=Depends(require_admin),
):
    clauses, values = [], []
    if event_type:
        clauses.append("a.event_type = ?")
        values.append(event_type)
    if q:
        clauses.append(
            """(a.actor_email LIKE ? OR u.name LIKE ? OR a.item_title LIKE ?
               OR a.related_title LIKE ? OR a.summary LIKE ?)"""
        )
        values.extend([f"%{q}%"] * 5)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db() as connection:
        rows = connection.execute(
            f"""SELECT a.event_type, a.actor_email, COALESCE(u.name, a.actor_email) AS actor_name,
                       a.item_title, a.related_title, a.summary, a.created_at
                FROM activity_log a LEFT JOIN users u ON u.email = a.actor_email
                {where} ORDER BY a.created_at DESC LIMIT 500""",
            values,
        ).fetchall()
    return [dict(row) for row in rows]


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
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = connection.execute(
            "INSERT INTO claims(item_id, claimant_email, proof_description, created_at) VALUES (?,?,?,?)",
            (payload.item_id, user["email"], payload.proof_description, created_at),
        )
        claim_id = cursor.lastrowid
        item_title = item["title"]
    add_activity(
        "claim", f"claim:{claim_id}", user["email"], item_title,
        "Claim submitted", created_at,
    )
    return {"id": claim_id, "item_id": payload.item_id, "status": "pending"}


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
            item = connection.execute(
                "SELECT status FROM items WHERE id = ?", (claim["item_id"],)
            ).fetchone()
            if item["status"] != "open":
                raise HTTPException(status_code=409, detail="Item is no longer open")
            connection.execute("UPDATE items SET status = 'claimed' WHERE id = ?", (claim["item_id"],))
            award_finder_credit(
                connection, claim["item_id"], datetime.now(timezone.utc).isoformat()
            )
            connection.execute(
                "UPDATE claims SET status = 'rejected' WHERE item_id = ? AND id != ? AND status = 'pending'",
                (claim["item_id"], claim_id),
            )
        connection.execute(
            "UPDATE claims SET status = ?, admin_notes = ? WHERE id = ?",
            (decision.status, decision.admin_notes, claim_id),
        )
        item_title = connection.execute(
            "SELECT title FROM items WHERE id = ?", (claim["item_id"],)
        ).fetchone()["title"]
        row = connection.execute(
            """SELECT c.*, i.title AS item_title, i.location AS collect_location,
                      i.contact_email AS reporter_contact_email
               FROM claims c JOIN items i ON i.id = c.item_id WHERE c.id = ?""",
            (claim_id,),
        ).fetchone()
    add_activity(
        "claim", f"claim-decision:{claim_id}", user["email"], item_title,
        f"Claim {decision.status}", datetime.now(timezone.utc).isoformat(),
    )
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
            """UPDATE items SET status = 'returned',
                      returned_at = COALESCE(returned_at, ?)
               WHERE id = ? AND status = 'claimed'""",
            (datetime.now(timezone.utc).isoformat(), claim["item_id"]),
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
        returned_at = datetime.now(timezone.utc).isoformat()
        cursor = connection.execute(
            """UPDATE items SET status = 'returned',
                      returned_at = COALESCE(returned_at, ?)
               WHERE id = ? AND status = 'claimed'""",
            (returned_at, item_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=409, detail="Only a claimed item can be marked returned")
        award_finder_credit(connection, item_id, returned_at)
    return get_item_row(item_id)


@app.get("/admin/stats")
def admin_stats(user=Depends(require_admin)):
    with db() as connection:
        counts = connection.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN status = 'returned' THEN 1 ELSE 0 END) AS returned
               FROM items"""
        ).fetchone()
        recoveries = connection.execute(
            """SELECT created_at, returned_at FROM items
               WHERE status = 'returned' AND returned_at IS NOT NULL"""
        ).fetchall()
    total = counts["total"] or 0
    returned = counts["returned"] or 0
    unclaimed = total - returned
    durations = []
    for row in recoveries:
        created_at = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
        returned_at = datetime.fromisoformat(row["returned_at"].replace("Z", "+00:00"))
        durations.append(max(0.0, (returned_at - created_at).total_seconds()))
    average_hours = sum(durations) / len(durations) / 3600 if durations else 0
    return {
        "total_reports": total,
        "returned_count": returned,
        "unclaimed_count": unclaimed,
        "returned_rate": round(returned * 100 / total, 1) if total else 0,
        "unclaimed_rate": round(unclaimed * 100 / total, 1) if total else 0,
        "average_recovery_hours": round(average_hours, 2),
        "average_recovery_days": round(average_hours / 24, 2),
        "recovered_count": len(durations),
    }


@app.get("/admin/export.csv")
def export_reports_csv(user=Depends(require_admin)):
    with db() as connection:
        rows = connection.execute(
            """SELECT id, type, title, category, color, location, date_event, status,
                      created_by AS reporter, created_at, returned_at
               FROM items ORDER BY id"""
        ).fetchall()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow([
        "id", "type", "title", "category", "color", "location", "date",
        "status", "reporter", "created_at", "returned_at",
    ])
    writer.writerows([tuple(row) for row in rows])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="campfindr-reports.csv"'},
    )


@app.get("/stats")
def stats():
    with db() as connection:
        rows = connection.execute("SELECT status, COUNT(*) AS count FROM items GROUP BY status").fetchall()
    return {row["status"]: row["count"] for row in rows}


def backfill_match_activity():
    with db() as connection:
        lost_items = connection.execute(
            "SELECT * FROM items WHERE type = 'lost' AND status = 'open'"
        ).fetchall()
    for lost_item in lost_items:
        for match in _all_matches_for(lost_item["id"]):
            found_item = match["item"]
            created_at = max(lost_item["created_at"], found_item["created_at"])
            add_activity(
                "match", f"match:{lost_item['id']}:{found_item['id']}",
                lost_item["created_by"], lost_item["title"],
                f"Possible match found: {found_item['title']}.", created_at,
                found_item["title"],
            )


initialize_db()
backfill_match_activity()

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_app(full_path: str):
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Not found")
