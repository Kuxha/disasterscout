# api_server/main.py

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from utils.mongo import incidents
from mcp_server.ingestion import scan_region_once  # Tavily + Mongo ingestion

app = FastAPI(title="DisasterScout API")

# Allow browser access from localhost / anywhere (fine for hackathon demo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def incident_to_feature(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an incident Mongo doc into a GeoJSON Feature."""
    loc = doc.get("location") or {}
    geometry = {
        "type": "Point",
        "coordinates": loc.get("coordinates", []),
    }

    props: Dict[str, Any] = {
        "id": str(doc.get("_id")),
        "description": doc.get("description"),
        "category": doc.get("category"),
        "status": doc.get("status"),
        "region": doc.get("region"),
        "topic": doc.get("topic"),
        "report_count": doc.get("report_count", 1),
        "source_links": doc.get("source_links", []),
        "last_seen_at": doc.get("last_seen_at"),
        "last_verified_at": doc.get("last_verified_at"),
    }

    # If a geoNear query added distance_m, keep it in properties
    if "distance_m" in doc:
        props["distance_m"] = doc["distance_m"]

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": props,
    }


@app.get("/api/incidents")
def get_incidents(
    region: str = Query(..., description="Region name, e.g. 'Brooklyn, NY'"),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
) -> Dict[str, Any]:
    """
    Return incidents as a GeoJSON FeatureCollection for the given region.
    """
    query: Dict[str, Any] = {"region": region}
    if category:
        query["category"] = category
    if status:
        query["status"] = status

    cursor = incidents.find(query).sort("last_seen_at", -1).limit(limit)
    features: List[Dict[str, Any]] = [incident_to_feature(doc) for doc in cursor]

    return {
        "type": "FeatureCollection",
        "features": features,
    }


@app.get("/api/incidents_near")
def get_incidents_near(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    radius_km: float = Query(
        20.0, ge=0.1, le=500.0, description="Search radius in km"
    ),
    limit: int = Query(200, ge=1, le=2000),
) -> Dict[str, Any]:
    """
    Geo 'near me' endpoint.
    Returns incidents as a GeoJSON FeatureCollection within radius_km of (lat, lon).

    This uses MongoDB's $geoNear on the 'location' field (2dsphere index required).
    """
    max_distance_m = radius_km * 1000.0

    pipeline: List[Dict[str, Any]] = [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": [lon, lat]},
                "distanceField": "distance_m",
                "maxDistance": max_distance_m,
                "spherical": True,
            }
        },
        {"$limit": limit},
    ]

    cursor = incidents.aggregate(pipeline)
    features: List[Dict[str, Any]] = [incident_to_feature(doc) for doc in cursor]

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def _compute_category_stats(region: str, topic: str) -> Dict[str, Dict[str, int]]:
    """
    Aggregate counts by (category, status) for a region.
    Right now this groups by region only; topic is just for labelling in the summary.
    """
    match_stage: Dict[str, Any] = {"region": region}
    # If your docs store topic and you want per-topic stats only, you can later do:
    # match_stage["topic"] = topic

    pipeline: List[Dict[str, Any]] = [
        {"$match": match_stage},
        {
            "$group": {
                "_id": {"category": "$category", "status": "$status"},
                "count": {"$sum": 1},
            }
        },
    ]

    agg = list(incidents.aggregate(pipeline))
    stats: Dict[str, Dict[str, int]] = {}

    for row in agg:
        cat = (row["_id"].get("category") or "UNKNOWN").upper()
        status = (row["_id"].get("status") or "UNKNOWN").upper()
        stats.setdefault(cat, {})
        stats[cat][status] = row["count"]

    return stats


def _build_daily_brief_text(
    region: str, topic: str, stats: Dict[str, Dict[str, int]]
) -> str:
    """
    Turn stats into the 'Daily brief for ...' text.
    """
    lines: List[str] = []
    lines.append(f"Daily brief for {region} on topic '{topic}':")
    lines.append("")

    for cat, statuses in stats.items():
        total_cat = sum(statuses.values())
        parts = [f"{status.lower()}={count}" for status, count in statuses.items()]
        lines.append(f"- {cat}: {total_cat} incidents ({', '.join(parts)})")

    return "\n".join(lines)


def _build_guidance_text(
    region: str, topic: str, stats: Dict[str, Dict[str, int]]
) -> str:
    """
    Simple rule-based guidance so users get concrete advice without another LLM call.
    """
    sos = sum(stats.get("SOS", {}).values())
    shelter = sum(stats.get("SHELTER", {}).values())
    info = sum(stats.get("INFO", {}).values())
    other = sum(
        sum(v.values())
        for k, v in stats.items()
        if k not in {"SOS", "SHELTER", "INFO"}
    )
    total = sos + shelter + info + other

    if total == 0:
        return (
            f"I could not find recent '{topic}' incidents for {region} in the database. "
            "That could mean conditions are currently calm, or that coverage is limited. "
            "Still follow local authorities and official weather channels."
        )

    lines: List[str] = []
    lines.append(f"Based on current reports for {region} on '{topic}':")

    if sos > 0:
        lines.append(
            f"- There are {sos} SOS / distress incidents (red markers). "
            "Avoid these areas if at all possible and follow instructions from local emergency services."
        )

    if shelter > 0:
        lines.append(
            f"- There are {shelter} shelter / resource locations (green markers). "
            "If authorities advise evacuation or relocation, use the map to find the nearest green marker "
            "and move there only if it is safe to do so."
        )

    if info > 0:
        lines.append(
            f"- There are {info} information-only reports (blue markers). "
            "These describe damage, hazard conditions, closures, or forecasts. Use them to understand how the situation is evolving."
        )

    if sos == 0 and shelter == 0:
        lines.append(
            "- I am not seeing specific SOS or shelter locations yet. That does not guarantee safety; "
            "it may simply mean coverage is sparse. Stay alert to local alerts and announcements."
        )

    lines.append(
        "Always prioritise official guidance from local emergency services over any map or automated advice."
    )

    return "\n".join(lines)


class ChatQuery(BaseModel):
    message: str


# Supported hazard keywords (very simple heuristic)
HAZARD_KEYWORDS: Dict[str, List[str]] = {
    "flood": ["flood", "flooding"],
    "earthquake": ["earthquake", "quake"],
    "storm": ["storm", "cyclone", "hurricane", "typhoon"],
    "wildfire": ["wildfire", "bushfire", "forest fire"],
}


def _detect_topic(lower: str) -> Optional[str]:
    """
    Return a canonical topic string ('flood', 'earthquake', etc.)
    if we see any of the known keywords in the message.
    """
    for topic, keywords in HAZARD_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return topic
    return None


def _extract_region(raw: str, lower: str) -> str:
    """
    Very simple heuristic: take whatever comes after the last ' in ' as the region.
    If that fails, fall back to the whole message, and then to 'Brooklyn, NY'.
    """
    region: Optional[str] = None

    idx = lower.rfind(" in ")
    if idx != -1:
        region = raw[idx + 4 :].strip(" ,.!?")

    if not region:
        region = raw.strip()

    # Avoid obviously bad regions
    if not region:
        region = "Brooklyn, NY"

    return region


@app.post("/api/chat_query")
def chat_query(payload: ChatQuery) -> Dict[str, Any]:
    """
    Chat-style endpoint.

    Expected messages like:
    - "Flood in Brooklyn, NY"
    - "Flood in Qui Nhon, Vietnam"
    - "Earthquake in Tokyo"
    - "Storm in Mumbai"
    - "Wildfire in California"

    Behaviour:
    * If the message contains a known hazard keyword:
        - detect topic
        - extract region
        - refresh data with scan_region_once
        - compute stats
        - build brief + guidance
    * If the message is just "hi" / random text with no hazard keyword:
        - return a short help message and no map_url
    """
    raw = payload.message.strip()
    lower = raw.lower()

    topic = _detect_topic(lower)
    if not topic:
        # No recognised hazard keyword: just show usage help.
        help_text = (
            "I can help you understand disaster situations using live news and the map.\n\n"
            "Try messages like:\n"
            "- Flood in Brooklyn, NY\n"
            "- Flood in Bay Ridge, Brooklyn, NY\n"
            "- Flood in Qui Nhon, Vietnam\n"
            "- Earthquake in Tokyo\n"
            "- Storm in Mumbai\n"
            "- Wildfire in California"
        )
        return {
            "ok": True,
            "summary": help_text,
            "region": None,
            "topic": None,
            "scan_summary": None,
            "map_url": None,
        }

    region = _extract_region(raw, lower)

    # 1) Refresh data for this region/topic
    scan_summary = scan_region_once(region, topic)

    # 2) Compute stats and brief
    stats = _compute_category_stats(region, topic)
    brief_text = _build_daily_brief_text(region, topic, stats)

    # 3) Build guidance
    guidance_text = _build_guidance_text(region, topic, stats)

    # 4) Compose final assistant text
    assistant_text = brief_text + "\n\nGuidance:\n" + guidance_text

    return {
        "ok": True,
        "summary": assistant_text,
        "region": region,
        "topic": topic,
        "scan_summary": scan_summary,
        "map_url": f"/map/?region={quote(region)}",
    }


# Mount static map assets from ./map (relative to project root)
app.mount("/map", StaticFiles(directory="map", html=True), name="map")


@app.get("/")
def root() -> RedirectResponse:
    """Redirect / -> /map/"""
    return RedirectResponse(url="/map/")
