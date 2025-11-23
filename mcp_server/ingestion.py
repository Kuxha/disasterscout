# mcp_server/ingestion.py

from typing import Dict, Any, List

from mcp_server.dedup import upsert_incident_candidate
from utils.embeddings import embed_text
from utils.tavily_client import search_disaster
from utils.mongo import incidents
from utils.geocode import geocode_place, refine_place
from utils.place_extraction import extract_place_from_text


def classify_category(description: str) -> str:
    text = (description or "").lower()

    if "shelter" in text or "evacuation center" in text:
        return "SHELTER"
    if any(word in text for word in ["trapped", "stranded", "help", "rescue", "sos"]):
        return "SOS"

    return "INFO"


def scan_region_once(region: str, topic: str) -> Dict[str, Any]:
    """
    Fetch Tavily results → extract → refine place → geocode →
    embed → hybrid dedup → insert/update incidents.
    """

    tavily_resp = search_disaster(region, topic)
    results: List[Dict[str, Any]] = tavily_resp.get("results", [])

    processed = 0
    upserts = 0

    for r in results:
        title = r.get("title") or ""
        content = r.get("content") or ""
        url = r.get("url") or ""

        # Build description
        description = title.strip() or content[:200]
        if not description:
            continue

        category = classify_category(description)
        full_text = title + " " + content

        # 1) Extract place from news text
        llm_place = extract_place_from_text(full_text)

        # 2) Refine the extracted place (adds “NY” and fixes formatting)
        refined = refine_place(llm_place or full_text)

        # 3) Geocode the refined place
        geo = None
        if refined:
            geo = geocode_place(refined, region)

        # 4) Fallback → borough centroid
        if not geo:
            print(f"[ingestion] fallback for '{refined}', region='{region}'")
            geo = geocode_place(region, region)

        if not geo:
            continue

        lon, lat = geo

        # 5) Embedding
        embedding = embed_text(description)
        if not embedding:
            continue

        # 6) Hybrid semantic+geo dedup
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
        upserts += 1

    # ← CORRECT: return AFTER the loop
    return {
        "processed": processed,
        "upserts": upserts,
    }


if __name__ == "__main__":
    result = scan_region_once("Brooklyn, NY", "flood")
    print(result)
