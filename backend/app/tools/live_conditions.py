from __future__ import annotations

import json
import time

import httpx
import structlog
from cachetools import TTLCache
from pydantic import BaseModel, Field

from app.config import get_settings
from app.utils.retry import async_retry_on_network_error

log = structlog.get_logger()

# Keyed by (city.lower(), country.lower()); TTL=600s matches settings default
_weather_cache: TTLCache = TTLCache(maxsize=256, ttl=600)

_WMO_CONDITIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


class LiveConditionsInput(BaseModel):
    city: str
    country: str
    travel_date: str | None = Field(default=None, description="ISO date (YYYY-MM-DD) for flight search")


class WeatherData(BaseModel):
    temp_c: float
    conditions: str
    humidity: int
    wind_kph: float


class FlightData(BaseModel):
    cheapest_price: float | None
    currency: str | None
    airline: str | None
    departure_date: str | None


class LiveConditionsOutput(BaseModel):
    weather: WeatherData | None
    flights: FlightData | None
    errors: list[str]


@async_retry_on_network_error(attempts=3)
async def _geocode(city: str, country: str, client: httpx.AsyncClient) -> tuple[float, float] | None:
    """
    Look up coordinates for a city using Open-Meteo's geocoding API.
    
    The API expects ONLY the city name in `name`. We then filter results
    by matching the country (case-insensitive substring) to disambiguate
    cities that share names across countries (e.g. Cambridge UK vs MA).
    """
    resp = await client.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 5, "language": "en"},
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    
    # Prefer a result whose country matches; fall back to the first hit.
    country_lower = country.lower()
    for r in results:
        if country_lower in (r.get("country", "").lower()):
            return r["latitude"], r["longitude"]
    return results[0]["latitude"], results[0]["longitude"]


@async_retry_on_network_error(attempts=3)
async def _fetch_weather(lat: float, lon: float, client: httpx.AsyncClient) -> dict:
    resp = await client.get(
        get_settings().weather_url,
        params={
            "latitude": lat,
            "longitude": lon,
            # Use the newer `current=` form which includes humidity in one call
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
        },
    )
    resp.raise_for_status()
    return resp.json()


async def live_conditions(inp: LiveConditionsInput) -> LiveConditionsOutput:
    errors: list[str] = []
    weather: WeatherData | None = None
    flights: FlightData | None = None

    cache_key = (inp.city.lower(), inp.country.lower())
    cached = _weather_cache.get(cache_key)
    if cached is not None:
        weather = cached
        log.debug("tool.live_conditions.cache_hit", city=inp.city)
    else:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                coords = await _geocode(inp.city, inp.country, client)
                if coords is None:
                    errors.append(f"Could not geocode '{inp.city}, {inp.country}'")
                else:
                    lat, lon = coords
                    raw = await _fetch_weather(lat, lon, client)
                    cur = raw.get("current", {})
                    wmo = int(cur.get("weather_code", 0))
                    weather = WeatherData(
                        temp_c=float(cur.get("temperature_2m", 0.0)),
                        conditions=_WMO_CONDITIONS.get(wmo, f"Code {wmo}"),
                        humidity=int(cur.get("relative_humidity_2m", 0)),
                        wind_kph=float(cur.get("wind_speed_10m", 0.0)),
                    )
                    _weather_cache[cache_key] = weather
            duration_ms = int((time.perf_counter() - t0) * 1000)
            if weather is not None:
                log.info("tool.live_conditions.weather_fetched", city=inp.city, duration_ms=duration_ms)
            else:
                log.warning("tool.live_conditions.geocode_failed", city=inp.city, country=inp.country, duration_ms=duration_ms)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            log.error("tool.live_conditions.error", city=inp.city, error=str(exc), duration_ms=duration_ms)
            errors.append(f"Weather fetch failed: {exc}")

    # Flight stub — structure ready for Amadeus/Skyscanner integration
    if inp.travel_date:
        flights = FlightData(
            cheapest_price=None,
            currency=None,
            airline=None,
            departure_date=inp.travel_date,
        )

    return LiveConditionsOutput(weather=weather, flights=flights, errors=errors)
