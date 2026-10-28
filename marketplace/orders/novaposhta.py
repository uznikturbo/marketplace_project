"""Small Nova Poshta client with caching and 429 handling.

The checkout city/warehouse lookups are read-only and change rarely, so
responses are cached in Django's cache. This keeps normal typing from
turning into a burst of upstream API calls.
"""

import hashlib
import time

import requests
from django.core.cache import cache

NOVAPOSHTA_API_URL = "https://api.novaposhta.ua/v2.0/json/"
CITY_CACHE_TTL = 60 * 60 * 24
WAREHOUSE_CACHE_TTL = 60 * 60 * 24 * 7
REQUEST_TIMEOUT = 10


class NovaPoshtaError(Exception):
    """Raised when Nova Poshta cannot answer a request."""


class NovaPoshtaRateLimited(NovaPoshtaError):
    """Raised when Nova Poshta keeps returning HTTP 429."""


def _cache_key(kind, value):
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"novaposhta:{kind}:{digest}"


def _call(payload):
    for attempt in range(2):
        try:
            response = requests.post(
                NOVAPOSHTA_API_URL, json=payload, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            raise NovaPoshtaError("Nova Poshta API is unavailable") from exc

        if response.status_code == 429:
            if attempt == 0:
                retry_after = getattr(response, "headers", {}).get("Retry-After")
                try:
                    delay = float(retry_after)
                except (TypeError, ValueError):
                    delay = 0.5
                # Do not hold a web worker for too long; the cache and the
                # browser-side debounce are the main protection.
                time.sleep(min(max(delay, 0.5), 2.0))
                continue
            raise NovaPoshtaRateLimited("Nova Poshta API rate limit exceeded")

        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise NovaPoshtaError("Nova Poshta API is unavailable") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise NovaPoshtaError("Nova Poshta returned invalid JSON") from exc

        if not isinstance(data, dict):
            raise NovaPoshtaError("Nova Poshta returned an unexpected response")
        return data

    raise NovaPoshtaRateLimited("Nova Poshta API rate limit exceeded")


def _cached(key, ttl, loader):
    cached = cache.get(key)
    if cached is not None:
        return cached

    data = loader()
    if data.get("success"):
        cache.set(key, data, ttl)
    return data


def get_cities(query):
    query = (query or "").strip()
    if len(query) < 2:
        return {"success": True, "data": []}

    key = _cache_key("cities", query.casefold())
    payload = {
        "apiKey": _api_key(),
        "modelName": "Address",
        "calledMethod": "getCities",
        "methodProperties": {"FindByString": query, "Limit": "50"},
    }
    return _cached(key, CITY_CACHE_TTL, lambda: _call(payload))


def get_warehouses(city_ref):
    city_ref = (city_ref or "").strip()
    if not city_ref or len(city_ref) > 36:
        return {"success": False, "error": "city_ref is required"}

    key = _cache_key("warehouses", city_ref)
    payload = {
        "apiKey": _api_key(),
        "modelName": "Address",
        "calledMethod": "getWarehouses",
        "methodProperties": {"CityRef": city_ref, "Limit": "500"},
    }
    return _cached(key, WAREHOUSE_CACHE_TTL, lambda: _call(payload))


def _api_key():
    from django.conf import settings

    return settings.NOVAPOST_API
