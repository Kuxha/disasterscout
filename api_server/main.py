# api_server/main.py

from typing import Any, Dict, List, Optional
import os

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from openai import OpenAI

from utils.mongo import incidents  # reuse your existing Mongo client

app = FastAPI(title="DisasterScout API")

# OpenAI client for summary generation
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
    radius_km: float = Query(20.0, ge=0.1, le=500.0, description="Search radius in km"),
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


def build_incident_bullets(docs: List[Dict[str, Any]]) -> str:
    """
    Turn Mongo docs into a simple bullet list string for the LLM.
    """
    lines: List[str] = []
    for doc in docs:
        cat = doc.get("category") or "INFO"
        desc = (doc.get("description") or "").strip()
        region = doc.get("region") or ""
        status = doc.get("status") or ""
        report_count = doc.get("report_count", 1)

        line = f"- [{cat}] {desc}"
        extras: List[str] = []
        if status:
            extras.append(f"status: {status}")
        if report_count:
            extras.append(f"reports: {report_count}")
        if region:
            extras.append(f"region: {region}")
        if extras:
            line += f" ({', '.join(extras)})"

        lines.append(line)

    return "\n".join(lines)


def summarize_incidents(region: str, topic: str, docs: List[Dict[str, Any]]) -> str:
    """
    Ask OpenAI for a short situation report based on incidents.
    """
    if not docs:
        return (
            f"For region '{region}' and topic '{topic}', there are currently no "
            "incidents in the DisasterScout database."
        )

    bullets = build_incident_bullets(docs)

    system_msg = """
You are an emergency intelligence assistant.
You receive structured incident bullets from a crisis map.

Your job is to write a SHORT, clear situation report for a human in the affected area.

Structure your answer with these sections (as plain text, no markdown headings needed):
1) Situation overview
2) SOS / people at risk
3) Shelters & resources
4) Key info & advisories
5) Suggested next steps for someone on the ground

Be concise, practical, and avoid panic language.
If there are no SOS or shelters, say that explicitly and focus on information / preparedness.
"""

    user_msg = f"""
Region: {region}
Topic: {topic}

Here are recent incidents:

{bullets}
"""

    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=400,
    )

    summary = (resp.choices[0].message.content or "").strip()
    return summary


@app.get("/api/brief")
def get_brief(
    region: str = Query(..., description="Region name, e.g. 'Brooklyn, NY'"),
    topic: str = Query("flood", description="Disaster topic, e.g. 'flood', 'storm'"),
    limit: int = Query(30, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Return a situation report for a region + topic, based on incidents in Mongo.
    This is the "explain it to me" endpoint for the agent / judges.
    """
    query: Dict[str, Any] = {"region": region}
    # (If you later store topic per incident, you can add: query["topic"] = topic)

    docs = list(
        incidents.find(query)
        .sort("last_seen_at", -1)
        .limit(limit)
    )

    summary = summarize_incidents(region, topic, docs)

    return {
        "region": region,
        "topic": topic,
        "incident_count": len(docs),
        "summary": summary,
    }


# Mount static map assets from ./map (relative to project root)
app.mount("/map", StaticFiles(directory="map", html=True), name="map")


@app.get("/")
def root() -> RedirectResponse:
    """Redirect / -> /map/"""
    return RedirectResponse(url="/map/")
