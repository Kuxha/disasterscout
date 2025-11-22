# utils/mongo.py

import os
from datetime import datetime, UTC

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "disaster_db")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI missing in .env")

_client = MongoClient(MONGO_URI)
_db = _client[MONGO_DB_NAME]
incidents = _db.incidents

def now_utc():
    return datetime.now(UTC)
