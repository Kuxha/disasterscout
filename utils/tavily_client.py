# utils/tavily_client.py

import os
from typing import Dict, Any, List

from dotenv import load_dotenv
from tavily import TavilyClient

_tavily_client: TavilyClient | None = None


def get_tavily_client() -> TavilyClient:
    """Singleton Tavily client with .env loading."""
    global _tavily_client
    if _tavily_client is None:
        load_dotenv()
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError("TAVILY_API_KEY not set in .env")
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


def search_disaster(
    region: str,
    topic: str,
    days: int = 3,
    use_extract: bool = True,
) -> Dict[str, Any]:
    """
    High-level helper: fetch news/web results for a disaster in a region.

    Uses Tavily Search first, then (optionally) Tavily Extract to upgrade
    each result's `content` field with full article text. This makes our
    LLM filtering, place extraction, and embeddings much better, and is
    a strong story for the Tavily track.
    """
    client = get_tavily_client()

    # Slightly richer prompt so Tavily focuses on local disruptions
    query = (
        f"{topic} in {region}. "
        f"Focus on local impacts, flooding, shelters, closures, SOS, "
        f"emergency response, and public safety updates."
    )

    resp: Dict[str, Any] = client.search(
        query=query,
        topic="news",
        days=days,
        search_depth="advanced",
        include_answer=False,
        max_results=8,
    )

    results: List[Dict[str, Any]] = resp.get("results", [])
    if not use_extract or not results:
        return resp

    # Collect URLs to send to Extract
    urls = [r.get("url") for r in results if r.get("url")]
    if not urls:
        return resp

    try:
        # Tavily Extract – pull full article content for each URL
        extracted_docs = client.extract(
            urls=urls,
            extract_depth="advanced",   # deeper parsing for disaster context
            format="markdown",          # nice for LLM + embeddings
        )

        url_to_text: Dict[str, str] = {}

        for doc in extracted_docs:
            # Handle dict or object-style docs safely
            if isinstance(doc, dict):
                url = doc.get("url") or doc.get("source")
                text = (
                    doc.get("content")
                    or doc.get("raw_content")
                    or doc.get("page_content")
                )
            else:
                url = getattr(doc, "url", None) or getattr(
                    getattr(doc, "metadata", {}), "get", lambda k, d=None: None
                )("source")
                text = (
                    getattr(doc, "content", None)
                    or getattr(doc, "page_content", None)
                )

            if url and text:
                url_to_text[url] = text

        # Overwrite search snippets with extracted content when available
        for r in results:
            u = r.get("url")
            if u in url_to_text:
                r["content"] = url_to_text[u]
                r["extracted"] = True  # optional flag for debugging / logging

    except Exception as e:
        print("[tavily_client] extract failed, falling back to search snippet:", e)

    return resp
