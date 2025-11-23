# utils/geocode.py
from geopy.geocoders import Nominatim
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
geolocator = Nominatim(user_agent="disasterscout")

def refine_place(text: str) -> str | None:
    """Normalize+refine place names using OpenAI."""
    try:
        prompt = f"""
Extract the MOST specific location from this text.
Examples:
"near Shore Parkway Promenade in Brooklyn" → "Shore Parkway Promenade, Brooklyn, NY"
If none, return null.
Text: "{text}"
"""
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )
        place = r.choices[0].message.content.strip()
        if place.lower() in ["none", "null"]:
            return None
        return place
    except Exception as e:
        print("[refine_place] error:", e)
        return None


def geocode_place(place: str, region: str):
    """
    Geocode a refined place. If it fails, fallback to region-only.
    """
    try:
        query = f"{place}, {region}"
        location = geolocator.geocode(query, exactly_one=True, timeout=5)

        if location:
            return (location.longitude, location.latitude)
        else:
            print(f"[geocode_place] no result for '{query}'")
            return None
    except Exception as e:
        print("[geocode_place] error:", e)
        return None
