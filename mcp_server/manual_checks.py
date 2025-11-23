# mcp_server/manual_checks.py

from pprint import pprint

from utils.mongo import incidents
from utils.embeddings import embed_text
from mcp_server.ingestion import scan_region_once
from mcp_server.dedup import upsert_incident_candidate


def check_counts():
    print("=== Incident counts by region ===")
    pipeline = [
        {"$group": {"_id": "$region", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    for row in incidents.aggregate(pipeline):
        print(row)


def check_near_brooklyn():
    print("\n=== Sample $near query around Brooklyn ===")
    pt = {"type": "Point", "coordinates": [-73.95, 40.68]}
    cursor = incidents.find(
        {
            "location": {
                "$near": {
                    "$geometry": pt,
                    "$maxDistance": 5000,
                }
            }
        },
        {
            "description": 1,
            "category": 1,
            "status": 1,
            "region": 1,
            "location.coordinates": 1,
        },
    ).limit(5)

    for doc in cursor:
        pprint(doc)


def main():
    print("Running scan_region_once just to ensure ingestion works...")
    n = scan_region_once("Brooklyn, NY", "flood")
    print(f"scan_region_once inserted/updated: {n} incidents")

    check_counts()
    check_near_brooklyn()


if __name__ == "__main__":
    main()
