# utils/geocode.py

from geopy.geocoders import Nominatim
from typing import Optional

geolocator = Nominatim(user_agent="disasterscout")


def refine_place(place: Optional[str], region: str) -> str:
    """
    Normalize a place name:

    - if place is None -> fall back to region
    - strip stray quotes
    - avoid duplicating region
    - don't keep appending region when the place is already country-scoped
    """
    if not place:
        return region

    cleaned = place.strip().strip('"').strip("'")

    # If it already contains the region name, just use it
    if region.lower() in cleaned.lower():
        return cleaned

    # If it already contains a country (e.g. 'Vietnam'), don't append region again
    if any(word in cleaned.lower() for word in ["vietnam", "philippines", "japan", "usa", "united states"]):
        return cleaned

    # Otherwise bias it with the region
    return f"{cleaned}, {region}"


def geocode_place(place: str, region: Optional[str] = None):
    """
    Geocode a place, optionally biased by region.

    - Strip stray quotes.
    - If region is empty/None, query with just the place.
    - If region is already part of the place string, don't append it again.
    """
    try:
        cleaned_place = place.strip().strip('"').strip("'")
        region = (region or "").strip()

        if region and region.lower() not in cleaned_place.lower():
            query = f"{cleaned_place}, {region}"
        else:
            query = cleaned_place

        location = geolocator.geocode(query, exactly_one=True, timeout=5)

        if location:
            return (location.longitude, location.latitude)
        else:
            print(f"[geocode_place] no result for '{query}'")
            return None
    except Exception as e:
        print("[geocode_place] error:", e)
        return None
