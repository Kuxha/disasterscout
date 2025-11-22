# utils/geocode.py

from geopy.geocoders import Nominatim
from functools import lru_cache

_geolocator = Nominatim(user_agent="disasterscout")

@lru_cache(maxsize=256)
def geocode_place(place_string: str, region: str | None = None):
    """
    Return (lon, lat) or None if not found.
    """
    if region:
        query = f"{place_string}, {region}"
    else:
        query = place_string

    location = _geolocator.geocode(query)
    if not location:
        return None

    return (location.longitude, location.latitude)
