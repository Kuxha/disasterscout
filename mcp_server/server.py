# mcp_server/server.py

from typing import List, Dict, Any, Optional

from bson import ObjectId
from mcp.server.fastmcp import FastMCP

from utils.mongo import incidents, now_utc
from mcp_server.ingestion import scan_region_once

mcp = FastMCP("DisasterScout")


# -------------------------
# Tool: scan_region
# -------------------------
@mcp.tool()
def scan_region(region: str, topic: str) -> Dict[str, Any]:
    """
    Refresh disaster intel for a region+topic using Tavily and hybrid dedup.

    Returns: { region, topic, processed, upserts }
    """
    summary = scan_region_once(region, topic)
    return {
        "region": region,
        "topic": topic,
        **summary,
    }


# -------------------------
# Tool: list_incidents
# -------------------------
@mcp.tool()
def list_incidents(
    region: str,
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    List incidents in a region, optionally filtered by category and status.
    """
    query: Dict[str, Any] = {"region": region}
    if category:
        query["category"] = category
    if status:
        query["status"] = status

    cursor = incidents.find(query).sort("last_seen_at", -1).limit(limit)

    results: List[Dict[str, Any]] = []
    for doc in cursor:
        results.append(
            {
                "id": str(doc["_id"]),
                "description": doc.get("description"),
                "category": doc.get("category"),
                "status": doc.get("status"),
                "region": doc.get("region"),
                "topic": doc.get("topic"),
                "report_count": doc.get("report_count", 1),
                "source_links": doc.get("source_links", []),
                "location": doc.get("location"),
                "last_seen_at": doc.get("last_seen_at"),
                "last_verified_at": doc.get("last_verified_at"),
            }
        )

    return results


# -------------------------
# Tool: find_nearest_resources
# -------------------------
@mcp.tool()
def find_nearest_resources(
    lat: float,
    lon: float,
    category: str,
    max_km: float = 3.0,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Find nearby incidents (e.g. shelters) around a lat/lon.
    Defaults to 3km radius, top 5 results.
    """
    max_distance_m = max_km * 1000.0

    pipeline = [
        {
            "$geoNear": {
                "near": {"type": "Point", "coordinates": [lon, lat]},
                "distanceField": "distance_m",
                "maxDistance": max_distance_m,
                "spherical": True,
                "query": {
                    "category": category,
                },
            }
        },
        {"$limit": limit},
        {
            "$project": {
                "description": 1,
                "category": 1,
                "status": 1,
                "region": 1,
                "topic": 1,
                "location": 1,
                "report_count": 1,
                "source_links": 1,
                "distance_m": 1,
            }
        },
    ]

    docs = list(incidents.aggregate(pipeline))
    results: List[Dict[str, Any]] = []
    for doc in docs:
        results.append(
            {
                "id": str(doc["_id"]),
                "description": doc.get("description"),
                "category": doc.get("category"),
                "status": doc.get("status"),
                "region": doc.get("region"),
                "topic": doc.get("topic"),
                "location": doc.get("location"),
                "report_count": doc.get("report_count", 1),
                "source_links": doc.get("source_links", []),
                "distance_m": doc.get("distance_m"),
            }
        )

    return results


# -------------------------
# Tool: verify_incident
# -------------------------
@mcp.tool()
def verify_incident(incident_id: str) -> Dict[str, Any]:
    """
    Mark an incident as VERIFIED if we have enough signals.

    Hackathon logic:
      - if report_count >= 2 -> VERIFIED
      - else leave status as-is
    """
    try:
        _id = ObjectId(incident_id)
    except Exception:
        return {"ok": False, "reason": "invalid incident_id"}

    doc = incidents.find_one({"_id": _id})
    if not doc:
        return {"ok": False, "reason": "incident not found"}

    report_count = doc.get("report_count", 1)
    now = now_utc()

    new_status = doc.get("status", "UNVERIFIED")
    reason = "Not enough evidence (report_count < 2); left status unchanged."

    if report_count >= 2:
        new_status = "VERIFIED"
        reason = "Auto-verified based on multiple reports (report_count >= 2)."

    incidents.update_one(
        {"_id": _id},
        {
            "$set": {
                "status": new_status,
                "last_verified_at": now,
                "updated_at": now,
            }
        },
    )

    return {
        "ok": True,
        "incident_id": incident_id,
        "new_status": new_status,
        "report_count": report_count,
        "reason": reason,
    }


# -------------------------
# Tool: daily_brief
# -------------------------
@mcp.tool()
def daily_brief(region: str, topic: str) -> Dict[str, Any]:
    """
    High-level situation report for a region and topic.

    For now:
      - Triggers a fresh scan_region_once (Tavily + dedup).
      - Aggregates counts by category and status.
      - Returns a text summary + raw stats.
    """
    # 1) Refresh data
    summary = scan_region_once(region, topic)

    # 2) Aggregate by category/status
    pipeline = [
        {"$match": {"region": region}},
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

    lines: List[str] = []
    lines.append(f"Daily brief for {region} on topic '{topic}':")
    lines.append("")
    for cat, statuses in stats.items():
        total_cat = sum(statuses.values())
        parts = [f"{status.lower()}={count}" for status, count in statuses.items()]
        lines.append(f"- {cat}: {total_cat} incidents ({', '.join(parts)})")

    text_summary = "\n".join(lines)

    return {
        "region": region,
        "topic": topic,
        "scan_summary": summary,
        "stats": stats,
        "summary": text_summary,
    }


if __name__ == "__main__":
    # FastMCP will run over stdio when invoked as a module
    mcp.run()
