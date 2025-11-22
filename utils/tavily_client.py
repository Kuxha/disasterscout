# utils/tavily_client.py

import os
from dotenv import load_dotenv
from tavily import TavilyClient

_tavily_client = None

def get_tavily_client() -> TavilyClient:
    global _tavily_client
    if _tavily_client is None:
        load_dotenv()
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY not set in .env")
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client

def search_disaster(region: str, topic: str, days: int = 3) -> dict:
    """
    High-level helper: fetch news/web results for a disaster in a region.
    """
    client = get_tavily_client()

    query = f"{region} {topic} shelters SOS situation"
    response = client.search(
        query=query,
        topic="news",
        days=days,
        search_depth="advanced"
    )
    return response
