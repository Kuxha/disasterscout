# api_server/main.py

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from utils.mongo import incidents

app = FastAPI(title="DisasterScout API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def incident_to_feature(doc: Dict[str, Any]) -> Dict[str, Any]:
    loc = doc.get("location") or {}
    coordinates = loc.get("coordinates") or []

    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": coordinates,
        },
        "properties": {
            "id": str(doc["_id"]),
            "description": doc.get("description"),
            "category": doc.get("category"),
            "status": doc.get("status"),
            "region": doc.get("region"),
            "topic": doc.get("topic"),
            "report_count": doc.get("report_count", 1),
            "source_links": doc.get("source_links", []),
            "last_seen_at": doc.get("last_seen_at"),
            "last_verified_at": doc.get("last_verified_at"),
        },
    }


# ─────────────────────────────────────────────
# MAIN ENDPOINT (REGION‑FILTERED)
# Example: /api/incidents?region=Brooklyn, NY
# ─────────────────────────────────────────────
@app.get("/api/incidents")
def get_incidents(
    region: str = Query(..., description="Region name, e.g. 'Brooklyn, NY'"),
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=2000),
):
    query: Dict[str, Any] = {"region": region}
    if category:
        query["category"] = category
    if status:
        query["status"] = status

    cursor = incidents.find(query).sort("last_seen_at", -1).limit(limit)
    features = [incident_to_feature(doc) for doc in cursor]

    return {"type": "FeatureCollection", "features": features}


# ─────────────────────────────────────────────
# OPTIONAL ENDPOINT: RETURN *ALL* INCIDENTS
# This is what your map is calling (/api/incidents_geojson)
# ─────────────────────────────────────────────
@app.get("/api/incidents_geojson")
def get_all_incidents(limit: int = 500):
    cursor = incidents.find({}).sort("last_seen_at", -1).limit(limit)
    features = [incident_to_feature(doc) for doc in cursor]
    return {"type": "FeatureCollection", "features": features}


# ─────────────────────────────────────────────
# STATIC MAP
# ─────────────────────────────────────────────
app.mount("/map", StaticFiles(directory="map", html=True), name="map")


@app.get("/")
def root():
    return RedirectResponse(url="/map/")
