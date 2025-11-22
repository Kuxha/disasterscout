# mcp_server/db_client.py

import os
from pymongo import MongoClient

MONGO_URI = os.getenv("MONGODB_URI")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "disaster_db")

_client = MongoClient(MONGO_URI)
_db = _client[MONGO_DB_NAME]

incidents = _db["incidents"]
