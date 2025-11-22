# mcp_server/ingestion.py

from datetime import datetime, UTC
from typing import List, Dict, Any

from utils.tavily_client import search_disaster
from utils.mongo import incidents, now_utc
from utils.embeddings import embed_text
from utils.geocode import geocode_place

def classify_category(description: str) -> str:
    """
    Very naive rule-based classifier for now.
    We can swap this for LLM classification later.
    """
    text = description.lower()
    if "shelter" in text or "evacuation center" in text:
        return "SHELTER"
    if "trapped" in text or "stranded" in text or "help" in text or "rescue" in text:
        return "SOS"
    return "INFO"

def scan_region_once(region: str, topic: str) -> int:
    """
    One shot: fetch Tavily results, extract minimal info, geocode, embed, insert.
    (Dedup will be added in the next step.)
    Returns: number of incidents inserted.
    """
    tavily_resp = search_disaster(region, topic)
    results = tavily_resp.get("results", [])

    inserted_count = 0

    for r in results:
        # Tavily's shape is usually {title, content, url, ...}
        title = r.get("title") or ""
        content = r.get("content") or ""
        url = r.get("url") or ""

        # For now, description = title or first part of content
        description = title.strip() or content[:200]

        if not description:
            continue

        category = classify_category(description)

        # Simple place extraction hack:
        # later we can use LLM, but for now assume region itself
        place_string = region  # TODO: use smarter extraction

        geo = geocode_place(place_string, region=region)
        if not geo:
            # Skip if we can't geocode
            continue

        lon, lat = geo

        embedding = embed_text(description)
        if not embedding:
            continue

        now = now_utc()
        doc = {
            "description": description,
            "category": category,
            "topic": topic,
            "region": region,
            "status": "UNVERIFIED",
            "report_count": 1,
            "source_links": [url] if url else [],
            "created_at": now,
            "last_seen_at": now,
            "last_verified_at": None,
            "location": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "embedding": embedding,
        }

        incidents.insert_one(doc)
        inserted_count += 1

    return inserted_count

if __name__ == "__main__":
    # quick manual test
    n = scan_region_once("Brooklyn, NY", "flood")
    print(f"Inserted {n} incidents")
