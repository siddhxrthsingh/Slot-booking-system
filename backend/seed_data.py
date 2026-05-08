"""
Seeds the database with sample slots so you can test immediately.
Usage:  python seed_data.py
Creates slots for the next 3 days for all 5 sports.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings


SPORTS = [
    {"sport": "Football",     "venue": "Main Turf Arena",      "campus": "RR", "capacity": 20},
    {"sport": "Basketball",   "venue": "Indoor Hoop Court",    "campus": "RR", "capacity": 15},
    {"sport": "Cricket",      "venue": "Practice Nets",        "campus": "RR", "capacity": 25},
    {"sport": "Badminton",    "venue": "Li-Ning Indoor Courts","campus": "RR", "capacity": 12},
    {"sport": "Volleyball",   "venue": "Sports Complex Hall",  "campus": "RR", "capacity": 18},
    {"sport": "Squash",       "venue": "Squash Courts Block",  "campus": "RR", "capacity": 8},
    {"sport": "Table Tennis", "venue": "Recreation Hall",      "campus": "RR", "capacity": 10},
    {"sport": "Chess",        "venue": "Indoor Games Room",    "campus": "RR", "capacity": 16},
    # EC Campus
    {"sport": "Football",     "venue": "EC Turf Ground",       "campus": "EC", "capacity": 20},
    {"sport": "Basketball",   "venue": "EC Sports Hall",       "campus": "EC", "capacity": 15},
    {"sport": "Cricket",      "venue": "EC Practice Nets",     "campus": "EC", "capacity": 25},
    {"sport": "Badminton",    "venue": "EC Badminton Courts",  "campus": "EC", "capacity": 12},
]

TIMESLOTS = [
    ("07:00", "08:00"),
    ("15:00", "16:00"),
    ("17:00", "18:00"),
    ("18:30", "19:30"),
]


async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    db = client[settings.mongo_db_name]

    now = datetime.now(timezone.utc)
    created = 0

    for day_offset in range(1, 4):  # next 3 days
        slot_date = (now + timedelta(days=day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for sport in SPORTS:
            for start, end in TIMESLOTS:
                doc = {
                    **sport,
                    "date": slot_date,
                    "start_time": start,
                    "end_time": end,
                    "booked_count": 0,
                    "status": "open",
                    "requires_approval": False,
                    "created_by": None,
                    "created_at": now,
                }
                await db["slots"].insert_one(doc)
                created += 1

    client.close()
    print(f"Seeded {created} slots across the next 3 days.")


if __name__ == "__main__":
    asyncio.run(main())
