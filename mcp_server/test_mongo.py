# mcp_server/test_mongo.py

import os
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient

def get_db():
    # Load environment variables from .env
    load_dotenv()

    mongo_uri = os.getenv("MONGO_URI")
    db_name = os.getenv("MONGO_DB_NAME", "disaster_db")

    if not mongo_uri:
        raise RuntimeError("MONGO_URI is not set in .env")

    client = MongoClient(mongo_uri)
    return client[db_name]

def main():
    db = get_db()
    incidents = db.incidents  # collection

    # Minimal dummy incident
    doc = {
        "description": "TEST incident from test_mongo.py",
        "category": "INFO",
        "topic": "test",
        "region": "Test Region",
        "status": "UNVERIFIED",
        "report_count": 1,
        "source_links": ["https://example.com/test"],
        "created_at": datetime.utcnow(),
        "last_seen_at": datetime.utcnow(),

        # GeoJSON location (dummy coords)
        "location": {
            "type": "Point",
            "coordinates": [-73.935242, 40.73061]  # [lon, lat]
        },

        # Dummy embedding, short for now – we’ll replace with real one later
        "embedding": [0.01, 0.02, 0.03]
    }

    # Insert doc
    result = incidents.insert_one(doc)
    print(f"Inserted incident with _id={result.inserted_id}")

    # Read back the last 5 incidents
    print("Last 5 incidents:")
    for inc in incidents.find().sort("created_at", -1).limit(5):
        print(f"- {_id_str(inc)} | {inc.get('description')} | {inc.get('region')}")

def _id_str(doc):
    return str(doc.get("_id"))

if __name__ == "__main__":
    main()
