# mcp_server/ingestion.py

from typing import Dict, Any, List
import os

from openai import OpenAI

from mcp_server.dedup import upsert_incident_candidate
from utils.embeddings import embed_text
from utils.tavily_client import search_disaster
from utils.mongo import incidents
from utils.geocode import geocode_place, refine_place
from utils.place_extraction import extract_place_from_text

# OpenAI client for relevance filtering
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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


def is_relevant_incident(text: str, region: str) -> bool:
    """
    Use OpenAI to keep only disaster / emergency / disruption items
    that are actually about this region.
    """
    try:
        prompt = f"""
You are filtering articles for a crisis-intelligence map.

Text:
{text}

Region of interest: {region}

Does this text describe a disaster, hazard, weather event,
emergency, or critical infrastructure disruption that affects this region?

Answer strictly with "YES" or "NO".
"""
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=3,
        )
        answer = (resp.choices[0].message.content or "").strip().upper()
        return answer.startswith("Y")
    except Exception as e:
        print("[is_relevant_incident] error:", e)
        # On error, be conservative and keep it, so ingestion doesn't silently die
        return True


def scan_region_once(region: str, topic: str) -> Dict[str, Any]:
    """
    One shot: fetch Tavily results, extract minimal info, filter with OpenAI,
    geocode, embed, and upsert into Mongo with hybrid dedup (semantic + geo).

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
        title = r.get("title") or ""
        content = r.get("content") or ""
        url = r.get("url") or ""

        # For now, description = title or first part of content
        description = title.strip() or content[:200]
        if not description:
            continue

        category = classify_category(description)

        # Full text (usually Tavily Extract article body)
        full_text = (title + "\n\n" + content).strip()

        # ---- 1) Relevance filter using OpenAI ----
        if not is_relevant_incident(full_text, region):
            continue

        # ---- 2) Place extraction + refinement ----
        llm_place = extract_place_from_text(full_text)
        refined = refine_place(llm_place, region)

        # ---- 3) Geocoding ----
        geo = geocode_place(refined, region)

        # Fallback: region-level center only (no duplicated region string)
        if not geo:
            print(
                f"[ingestion] fallback geocode for region='{region}' (place='{refined}')"
            )
            geo = geocode_place(region, None)

        if not geo:
            # If we still can't geocode, skip this incident
            continue


        lon, lat = geo

        # ---- 4) Embedding ----
        embedding = embed_text(description)
        if not embedding:
            continue

        # ---- 5) Hybrid dedup upsert ----
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

    return {
        "processed": processed,
        "upserts": upserts,
    }


# if __name__ == "__main__":
#     # quick manual test
#     result = scan_region_once("Brooklyn, NY", "flood")
#     print(
#         f"scan_region_once -> processed={result['processed']} upserts={result['upserts']}"
#     )


if __name__ == "__main__":
    import sys

    # Usage:
    #   python -m mcp_server.ingestion "Brooklyn, NY" flood
    #   python -m mcp_server.ingestion "Qui Nhon, Vietnam" flood
    #
    # If no args, default to Brooklyn flood for quick testing.

    if len(sys.argv) >= 3:
        region_arg = sys.argv[1]
        topic_arg = sys.argv[2]
    else:
        region_arg = "Brooklyn, NY"
        topic_arg = "flood"

    print(f"[ingestion] running scan_region_once(region={region_arg!r}, topic={topic_arg!r})")
    result = scan_region_once(region_arg, topic_arg)
    print(
        f"scan_region_once(region={region_arg!r}, topic={topic_arg!r}) "
        f"-> processed={result['processed']} upserts={result['upserts']}"
    )
