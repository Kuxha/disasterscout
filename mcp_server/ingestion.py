# mcp_server/ingestion.py

from typing import Dict, Any, List
import os
import json

from openai import OpenAI

from mcp_server.dedup import upsert_incident_candidate
from utils.embeddings import embed_text
from utils.tavily_client import search_disaster
from utils.mongo import incidents
from utils.geocode import geocode_place, refine_place
from utils.place_extraction import extract_place_from_text

# OpenAI client for relevance + classification
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# -------------------------------------------------------------------------
# Category classification (SOS / SHELTER / INFO)
# -------------------------------------------------------------------------

def classify_category_keyword(description: str, full_text: str) -> str:
    """
    Simple fallback classifier using keywords
    in case the LLM call fails or is ambiguous.
    """
    text = ((description or "") + " " + (full_text or "")).lower()

    # Shelter-like language
    if any(
        kw in text
        for kw in [
            "shelter",
            "evacuation center",
            "evacuation centre",
            "evacuees",
            "temporary housing",
            "relief camp",
            "relief center",
            "relief centre",
            "emergency shelter",
            "displacement site",
            "safe shelter",
        ]
    ):
        return "SHELTER"

    # SOS / people in danger
    if any(
        kw in text
        for kw in [
            "trapped",
            "stranded",
            "missing",
            "rescued",
            "in need of help",
            "urgent help",
            "sos",
            "call for help",
            "people cut off",
            "plea for help",
            "rescue operation",
            "evacuated from",
            "swept away",
        ]
    ):
        return "SOS"

    return "INFO"

def classify_category(description: str, full_text: str, region: str) -> str:
    """
    Use OpenAI to classify an incident into:
      - SOS     (people in danger, needing help)
      - SHELTER (places/resources where people can go)
      - INFO    (general situation / damage / updates)
    """
    try:
        system_msg = """
You classify disaster-related news into categories:

- "SOS": people in danger or needing help.
  Examples: stranded residents, missing people, rescue operations,
  urgent medical needs, calls for urgent assistance.

- "SHELTER": locations or services where people can go for safety or aid.
  Examples: shelters, evacuation centers, relief camps, places distributing
  food/water, temporary housing.

- "INFO": general information about the disaster, damage, closures,
  forecasts, government announcements, etc., that is not a direct SOS
  or a specific shelter location.

Return ONLY a JSON object like:
{
  "category": "SOS" | "SHELTER" | "INFO"
}
        """.strip()

        user_msg = f"""
Region: {region}

Title/summary:
{description}

Full text:
{full_text}
        """.strip()

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            max_tokens=50,
        )

        raw = (resp.choices[0].message.content or "").strip()
        data = json.loads(raw)

        cat = (data.get("category") or "INFO").upper()
        if cat not in {"SOS", "SHELTER", "INFO"}:
            return classify_category_keyword(description, full_text)
        return cat

    except Exception as e:
        print("[classify_category] error, falling back to keyword rules:", e)
        return classify_category_keyword(description, full_text)


# -------------------------------------------------------------------------
# Relevance filter (keep only disaster-ish items for this region)
# -------------------------------------------------------------------------

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
        """.strip()

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


# -------------------------------------------------------------------------
# Main ingestion pipeline
# -------------------------------------------------------------------------

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

        description = title.strip() or content[:200]
        if not description:
            continue

        # Full text (usually Tavily Extract article body)
        full_text = (title + "\n\n" + content).strip()

        # ---- 1) Relevance filter using OpenAI ----
        if not is_relevant_incident(full_text, region):
            continue

        # ---- 1b) Category classification (SOS / SHELTER / INFO) ----
        category = classify_category(description, full_text, region)

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


# -------------------------------------------------------------------------
# CLI entrypoint
# -------------------------------------------------------------------------

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

    print(
        f"[ingestion] running scan_region_once(region={region_arg!r}, "
        f"topic={topic_arg!r})"
    )
    result = scan_region_once(region_arg, topic_arg)
    print(
        f"scan_region_once(region={region_arg!r}, topic={topic_arg!r}) "
        f"-> processed={result['processed']} upserts={result['upserts']}"
    )
