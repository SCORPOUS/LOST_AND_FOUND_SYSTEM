from main import db, initialize_db
from datetime import datetime, timezone
import sys


SEED_ITEMS = [
    ("lost", "Blue Hydro Flask bottle", "Blue 750ml steel bottle with a mountain sticker", "Water bottle", "Blue", "Hydro Flask", "Science Hall", "2026-10-10", "maya@campus.edu"),
    ("found", "Blue steel water bottle", "Hydro Flask bottle, small mountain sticker on side", "Water bottle", "Blue", "Hydro Flask", "Science Hall", "2026-10-11", "sam@campus.edu"),
    ("lost", "Silver Lenovo laptop", "ThinkPad laptop in a black sleeve, asset sticker on base", "Electronics", "Silver", "Lenovo", "Library", "2026-10-12", "alex@campus.edu"),
    ("found", "Lenovo ThinkPad computer", "Silver laptop inside black fabric sleeve found by study tables", "Electronics", "Silver", "Lenovo", "Main Library", "2026-10-13", "lee@campus.edu"),
    ("lost", "Brass keys with red tag", "Three brass keys and a red CAMPUS tag on a ring", "Keys", "Brass", "", "North Quad", "2026-10-08", "jordan@campus.edu"),
    ("found", "Key ring with red tag", "Brass keys on a ring with red campus fob", "Keys", "Brass", "", "North Quad Cafe", "2026-10-09", "taylor@campus.edu"),
    ("lost", "Green canvas backpack", "Olive green backpack with a white patch and two zipper pulls", "Bags", "Green", "JanSport", "Arts Building", "2026-10-15", "riley@campus.edu"),
    ("found", "Green backpack", "Green bag with a small white patch, left in studio", "Bags", "Green", "JanSport", "Arts Building", "2026-10-15", "casey@campus.edu"),
    ("lost", "Calculus textbook", "Stewart calculus book with handwritten name inside cover", "Books", "Red", "Cengage", "Math Center", "2026-10-14", "dev@campus.edu"),
    ("found", "Red math textbook", "Red calculus textbook found near the tutoring desk", "Books", "Red", "", "Math Center", "2026-10-16", "pat@campus.edu"),
    ("lost", "Black wireless earbuds", "Small black earbuds in a charging case", "Electronics", "Black", "Sony", "Student Union", "2026-10-18", "erin@campus.edu"),
    ("found", "Dark earbuds case", "Black wireless earbud case found by food court", "Electronics", "Black", "", "Student Union", "2026-10-18", "kim@campus.edu"),
    ("lost", "Student ID card", "Campus card with a cracked corner in clear holder", "ID cards", "White", "", "Gym", "2026-10-19", "noah@campus.edu"),
    ("found", "White ID badge", "Unmarked white campus ID card near the front desk", "ID cards", "White", "", "Gym lobby", "2026-10-20", "sky@campus.edu"),
    ("lost", "Yellow rain jacket", "Lightweight yellow rain jacket, size medium", "Clothing", "Yellow", "Columbia", "East Quad", "2026-10-05", "aria@campus.edu"),
    ("found", "Navy umbrella", "Compact navy umbrella with wooden handle", "Clothing", "Navy", "", "West Quad", "2026-10-07", "max@campus.edu"),
    ("lost", "White ceramic mug", "White mug with a blue star design", "Other", "White", "", "Cafeteria", "2026-10-17", "ivy@campus.edu"),
    ("found", "Black wallet", "Black leather wallet found outside the auditorium", "Other", "Black", "", "Auditorium", "2026-10-18", "leo@campus.edu"),
]


def seed():
    initialize_db()
    with db() as connection:
        existing = connection.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        if existing and "--reset" not in sys.argv:
            print(f"Database already contains {existing} reports; leaving existing data unchanged.")
            return
        connection.execute("DELETE FROM matches")
        connection.execute("DELETE FROM claims")
        connection.execute("DELETE FROM items")
        now = datetime.now(timezone.utc).isoformat()
        connection.executemany(
            """INSERT INTO items(type,title,description,category,color,brand,location,date_event,
            contact_email,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [(*item, item[-1], now) for item in SEED_ITEMS],
        )
    print(f"Seeded {len(SEED_ITEMS)} campus reports (four clear pairs and two ambiguous candidates).")


if __name__ == "__main__":
    seed()
