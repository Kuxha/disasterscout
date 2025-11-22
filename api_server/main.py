# api_server/main.py

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from utils.mongo import incidents  # reuse your existing Mongo client


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

    return {
        "type": "Feature",
        "geometry": geometry,
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


# Mount static map assets from ./map (relative to project root)
app.mount("/map", StaticFiles(directory="map", html=True), name="map")


@app.get("/")
def root() -> RedirectResponse:
    """Redirect / -> /map/"""
    return RedirectResponse(url="/map/")
