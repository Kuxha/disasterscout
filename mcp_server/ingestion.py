# mcp_server/ingestion.py

from typing import Dict, Any, List

from mcp_server.dedup import upsert_incident_candidate
from utils.embeddings import embed_text  # <-- use utils, not mcp_server.utils

from utils.tavily_client import search_disaster
from utils.mongo import incidents, now_utc
from utils.geocode import geocode_place



def classify_category(description: str) -> str:
    """
    Very naive rule-based classifier for now.
    We can swap this for LLM classification later.
    """
    text = (description or "").lower()
    if "shelter" in text or "evacuation center" in text:
        return "SHELTER"
    if (
        "trapped" in text
        or "stranded" in text
        or "help" in text
        or "rescue" in text
        or "sos" in text
    ):
        return "SOS"
    return "INFO"


def scan_region_once(region: str, topic: str) -> Dict[str, Any]:
    """
    One shot: fetch Tavily results, extract minimal info, geocode, embed, and
    upsert into Mongo with hybrid dedup (semantic + geo).

    Returns a summary dict:
      {
        "processed": <number of Tavily results considered>,
        "upserts": <number of successful upserts>,
      }
    """
    tavily_resp = search_disaster(region, topic)
    results: List[Dict[str, Any]] = tavily_resp.get("results", [])

    processed = 0
    upserts = 0

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

        # Hybrid dedup: either updates an existing incident or inserts a new one
        _id = upsert_incident_candidate(
            incidents,
            description=description,
            category=category,
            region=region,
            lat=lat,
            lon=lon,
            embedding=embedding,
            source_link=url,
        )

        processed += 1
        upserts += 1  # every successful upsert is a write (insert or update)

    return {
        "processed": processed,
        "upserts": upserts,
    }


if __name__ == "__main__":
    # quick manual test
    summary = scan_region_once("Brooklyn, NY", "flood")
    print(
        f"scan_region_once -> processed={summary['processed']} upserts={summary['upserts']}"
    )
