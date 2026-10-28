import os


MATCH_WEIGHTS = {
    "text": 35,
    "color": 15,
    "brand": 10,
    "location": 20,
    "date": 20,
}

DATE_WINDOW_DAYS = 30
TOP_MATCHES = 5
DATABASE_PATH = os.getenv("DATABASE_PATH", "campus_portal.db")
CAMPUS_SAFETY_CONTACT = "campus-safety@campus.edu"
