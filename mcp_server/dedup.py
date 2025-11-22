# mcp_server/dedup.py

import math
from datetime import datetime, UTC
from typing import Optional, Dict, Any

from pymongo.collection import Collection


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Great-circle distance between two points on Earth in kilometers.
    """
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(
        dlambda / 2
    ) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def find_matching_incident(
    incidents_coll: Collection,
    *,
    embedding: list[float],
    region: str,
    lat: float,
    lon: float,
    max_km: float = 1.0,
    min_score: float = 0.7,
) -> Optional[Dict[str, Any]]:
    """
    Use Atlas Vector Search to find semantically similar incidents in the same region,
    then filter in Python by distance.
    Returns the best matching incident doc or None.
    """
    pipeline = [
        {
            "$vectorSearch": {
                "index": "incident_embedding_index",
                "path": "embedding",
                "queryVector": embedding,
                "numCandidates": 50,
                "limit": 20,  # a few more candidates so $match still has enough
            }
        },
        {
            # Apply region filter AFTER vector search, using normal query semantics
            "$match": {
                "region": region,
            }
        },
        {
            "$project": {
                "description": 1,
                "region": 1,
                "location": 1,
                "score": {"$meta": "vectorSearchScore"},
                "category": 1,
                "status": 1,
                "report_count": 1,
                "source_links": 1,
            }
        },
    ]


    candidates = list(incidents_coll.aggregate(pipeline))

    best: Optional[Dict[str, Any]] = None
    best_score = min_score

    for doc in candidates:
        loc = doc.get("location") or {}
        coords = loc.get("coordinates")
        if not coords or len(coords) != 2:
            continue

        lon2, lat2 = coords  # GeoJSON is [lon, lat]
        dist_km = haversine_km(lat, lon, lat2, lon2)

        score = doc.get("score", 0.0)
        if dist_km <= max_km and score >= best_score:
            best = doc
            best_score = score

    return best


def upsert_incident_candidate(
    incidents_coll: Collection,
    *,
    description: str,
    category: str,
    region: str,
    lat: float,
    lon: float,
    embedding: list[float],
    source_link: str,
) -> str:
    """
    Given a new incident candidate, either:
    - updates an existing nearby+similar incident, or
    - inserts a new incident.

    Returns the _id (as string) of the incident that was updated/inserted.
    """
    from bson import ObjectId  # imported here to avoid hard dependency in type hints

    now = datetime.now(UTC)

    # 1) Try to find matching incident
    match = find_matching_incident(
        incidents_coll,
        embedding=embedding,
        region=region,
        lat=lat,
        lon=lon,
    )

    location = {
        "type": "Point",
        "coordinates": [lon, lat],  # GeoJSON: [lon, lat]
    }

    if match:
        _id = match["_id"]
        incidents_coll.update_one(
            {"_id": _id},
            {
                "$inc": {"report_count": 1},
                "$set": {"updated_at": now, "last_seen_at": now},
                "$addToSet": {"source_links": source_link},
            },
        )
        return str(_id)

    # 2) Insert new incident
    doc = {
        "description": description,
        "category": category,
        "status": "UNVERIFIED",
        "region": region,
        "location": location,
        "embedding": embedding,
        "report_count": 1,
        "source_links": [source_link] if source_link else [],
        "created_at": now,
        "updated_at": now,
        "last_seen_at": now,
        "last_verified_at": None,
    }

    result = incidents_coll.insert_one(doc)
    return str(result.inserted_id)
