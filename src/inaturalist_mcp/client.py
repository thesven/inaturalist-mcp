from __future__ import annotations

import os
import threading
import time
from typing import Any

import httpx

from . import __version__


class INaturalistError(Exception):
    """Base exception for all iNaturalist MCP client errors."""


class INaturalistAPIError(INaturalistError):
    """Raised when the upstream iNaturalist API returns an HTTP error."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"iNaturalist API error ({status_code}): {message}")
        self.status_code = status_code


class INaturalistNotFoundError(INaturalistAPIError):
    """Raised when an iNaturalist record is not found (HTTP 404)."""


class INaturalistRateLimitError(INaturalistAPIError):
    """Raised when the iNaturalist API rate limits the request (HTTP 429)."""


class SimpleCache:
    """Thread-safe in-memory cache with TTL expiration."""

    def __init__(self, default_ttl_seconds: float = 3600.0) -> None:
        self.default_ttl = default_ttl_seconds
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            if key in self._cache:
                expires_at, val = self._cache[key]
                if now < expires_at:
                    return val
                del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = self.default_ttl if ttl_seconds is None else ttl_seconds
        expires_at = time.monotonic() + ttl
        with self._lock:
            self._cache[key] = (expires_at, value)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


class LeakyBucketLimiter:
    """Thread-safe rate limiter ensuring outbound requests respect upstream limits.

    iNaturalist asks for <= 60 req/min (1 req per second). We space requests with 1.1s intervals.
    """

    def __init__(self, min_interval_seconds: float = 1.1) -> None:
        self.min_interval = min_interval_seconds
        self._last_request_time = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request_time = time.monotonic()


class INaturalistClient:
    """Production-grade client for the iNaturalist REST API v1 with rate limiting and caching."""

    def __init__(
        self,
        base_url: str = "https://api.inaturalist.org/v1",
        api_token: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        enable_rate_limiting: bool = True,
        min_request_interval: float = 1.1,
        enable_caching: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = (
            api_token or os.environ.get("INATURALIST_API_TOKEN") or os.environ.get("INAT_API_TOKEN")
        )
        self.timeout = timeout
        self.max_retries = max_retries
        self.rate_limiter = (
            LeakyBucketLimiter(min_request_interval) if enable_rate_limiting else None
        )
        self.cache = SimpleCache() if enable_caching else None

    @property
    def headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "User-Agent": f"inaturalist-mcp/{__version__} (+https://github.com/thesven/inaturalist-mcp)",
            "Accept": "application/json",
        }
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _request(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        retry_delay: float = 1.0,
        cache_ttl: float | None = None,
    ) -> dict[str, Any]:
        cache_key = None
        if self.cache and cache_ttl is not None:
            sorted_params = tuple(sorted(params.items())) if params else ()
            cache_key = f"{path}:{sorted_params}"
            cached_val = self.cache.get(cache_key)
            if cached_val is not None:
                return cached_val

        url = self.base_url + path
        attempts = 0
        last_exc: Exception | None = None

        while attempts < self.max_retries:
            attempts += 1
            if self.rate_limiter:
                self.rate_limiter.acquire()

            try:
                response = httpx.get(
                    url,
                    params=params,
                    headers=self.headers,
                    timeout=self.timeout,
                )
                if response.status_code == 404:
                    raise INaturalistNotFoundError(404, f"Resource not found at {path}")
                if response.status_code == 429:
                    if attempts < self.max_retries:
                        time.sleep(retry_delay * attempts)
                        continue
                    raise INaturalistRateLimitError(429, "Rate limit exceeded on iNaturalist API")
                if response.status_code >= 500 and attempts < self.max_retries:
                    time.sleep(retry_delay * attempts)
                    continue

                response.raise_for_status()

                try:
                    data = response.json()
                except Exception as exc:
                    raise INaturalistError(f"Failed to decode JSON response from {path}") from exc

                if not isinstance(data, dict):
                    raise INaturalistError(f"Unexpected iNaturalist response shape for {path}")

                if self.cache and cache_key and cache_ttl is not None:
                    self.cache.set(cache_key, data, ttl_seconds=cache_ttl)

                return data

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempts < self.max_retries and not isinstance(
                    exc, (INaturalistNotFoundError, INaturalistRateLimitError)
                ):
                    time.sleep(retry_delay * attempts)
                    continue
                break

        if isinstance(last_exc, INaturalistError):
            raise last_exc
        if isinstance(last_exc, httpx.HTTPStatusError):
            raise INaturalistAPIError(last_exc.response.status_code, str(last_exc)) from last_exc
        raise INaturalistError(
            f"Failed to connect to iNaturalist API after {attempts} attempts: {last_exc}"
        ) from last_exc

    def fetch_image_bytes(self, image_url: str) -> tuple[bytes, str]:
        """Fetch an observation image and return raw bytes with content-type."""
        if self.rate_limiter:
            self.rate_limiter.acquire()
        headers = {"User-Agent": self.headers["User-Agent"]}
        resp = httpx.get(image_url, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return resp.content, content_type

    def resolve_ebird_code_to_taxon_id(self, species_code: str) -> dict[str, Any] | None:
        """Bridge Cornell eBird 6-letter speciesCode (e.g.

        'baleag', 'snoowl1') to iNaturalist taxon info.
        """
        code = species_code.strip().lower()
        if self.cache:
            cached = self.cache.get(f"ebird_code:{code}")
            if cached is not None:
                return cached

        # Look up taxonomy from public eBird v2 ref endpoint
        ebird_url = f"https://api.ebird.org/v2/ref/taxonomy/ebird?species={code}&fmt=json"
        try:
            resp = httpx.get(
                ebird_url, headers={"User-Agent": self.headers["User-Agent"]}, timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list) or not data:
                return None
            sci_name = data[0].get("sciName")
            com_name = data[0].get("comName")
            if not sci_name:
                return None

            # Resolve scientific name against iNaturalist taxa search
            inat_taxa = self.search_species(sci_name, limit=1)
            results = inat_taxa.get("taxa", [])
            if not results:
                return None
            best_match = results[0]
            resolved = {
                "ebird_code": code,
                "ebird_common_name": com_name,
                "scientific_name": sci_name,
                "inat_taxon_id": best_match.get("id"),
                "inat_taxon": best_match,
            }
            if self.cache:
                self.cache.set(f"ebird_code:{code}", resolved, ttl_seconds=86400.0)
            return resolved
        except Exception:
            return None

    @staticmethod
    def _base_params(
        lat: float, lon: float, radius_km: int, limit: int, photos_only: bool
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "lat": lat,
            "lng": lon,
            "radius": radius_km,
            "per_page": limit,
            "order_by": "observed_on",
            "order": "desc",
        }
        if photos_only:
            params["photos"] = True
        return params

    # --- Core Observation Methods (Backwards Compatible) ---

    def observations_nearby(
        self,
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
        photos_only: bool = False,
    ) -> dict[str, Any]:
        """Fetch nearby observations within a given radius in kilometers."""
        params = self._base_params(lat, lon, radius_km, limit, photos_only)
        data = self._request("/observations", params)
        return {
            "total_results": data.get("total_results", len(data.get("results", []))),
            "observations": data.get("results", []),
        }

    def taxon_observations_nearby(
        self,
        taxon_query: str,
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
        photos_only: bool = False,
    ) -> dict[str, Any]:
        """Fetch nearby observations matching a taxon query string or eBird code."""
        # Auto-resolve if user supplied 6-letter ebird code
        params = self._base_params(lat, lon, radius_km, limit, photos_only)
        if len(taxon_query) == 6 and taxon_query.isalnum() and not taxon_query.isdigit():
            ebird_resolved = self.resolve_ebird_code_to_taxon_id(taxon_query)
            if ebird_resolved:
                params["taxon_id"] = ebird_resolved["inat_taxon_id"]
            else:
                params["q"] = taxon_query
        else:
            params["q"] = taxon_query
        data = self._request("/observations", params)
        return {
            "total_results": data.get("total_results", len(data.get("results", []))),
            "observations": data.get("results", []),
        }

    def rare_observations_nearby(
        self,
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
        taxon_query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch lightly confirmed or sparsely identified research-grade observations nearby."""
        params = self._base_params(lat, lon, radius_km, limit, False)
        params["quality_grade"] = "research"
        if taxon_query:
            params["q"] = taxon_query
        observations = self._request("/observations", params).get("results", [])
        scored = []
        for item in observations:
            score = item.get("identifications_count", 0)
            obscured = item.get("obscured", False)
            geoprivacy = item.get("geoprivacy")
            taxon_info = item.get("taxon") or {}
            conservation_status = taxon_info.get("conservation_status")
            scored.append(
                {
                    "id": item.get("id"),
                    "species_guess": item.get("species_guess") or taxon_info.get("name"),
                    "observed_on": item.get("observed_on"),
                    "photo_count": len(item.get("photos", [])),
                    "confidence_proxy": score,
                    "identifications_count": score,
                    "uri": item.get("uri"),
                    "location": item.get("location"),
                    "obscured": obscured,
                    "geoprivacy": geoprivacy,
                    "conservation_status": conservation_status,
                }
            )
        scored.sort(key=lambda item: item["confidence_proxy"])
        return {
            "total_results": len(scored),
            "observations": scored[:limit],
        }

    def taxon_photo_evidence_nearby(
        self,
        taxon_query: str,
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Fetch nearby observations with verified photo evidence."""
        return self.taxon_observations_nearby(
            taxon_query, lat, lon, radius_km, limit, photos_only=True
        )

    def place_taxon_activity(
        self,
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
        taxon_query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch recent taxon activity for a place."""
        return self.taxon_observations_nearby(taxon_query or "", lat, lon, radius_km, limit)

    # --- Extended Discovery & Taxonomy Methods ---

    def search_species(
        self,
        query: str,
        rank: str | None = None,
        iconic_taxa: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search and autocomplete taxa by common or scientific name."""
        params: dict[str, Any] = {"q": query, "per_page": limit}
        if rank:
            params["rank"] = rank
        if iconic_taxa:
            params["iconic_taxa"] = iconic_taxa
        data = self._request("/taxa/autocomplete", params, cache_ttl=86400.0)
        return {
            "total_results": data.get("total_results", len(data.get("results", []))),
            "taxa": data.get("results", []),
        }

    def get_taxon(self, taxon_id: int | str) -> dict[str, Any]:
        """Get complete taxon record by iNaturalist taxon ID."""
        data = self._request(f"/taxa/{taxon_id}", cache_ttl=86400.0)
        results = data.get("results", [])
        if not results:
            raise INaturalistNotFoundError(404, f"Taxon ID {taxon_id} not found")
        return results[0]

    def get_observation(self, observation_id: int | str) -> dict[str, Any]:
        """Get full details of a specific observation by ID."""
        data = self._request(f"/observations/{observation_id}")
        results = data.get("results", [])
        if not results:
            raise INaturalistNotFoundError(404, f"Observation ID {observation_id} not found")
        return results[0]

    def search_places(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Search places (parks, cities, administrative regions) by name."""
        params = {"q": query, "per_page": limit}
        data = self._request("/places/autocomplete", params, cache_ttl=86400.0)
        return {
            "total_results": data.get("total_results", len(data.get("results", []))),
            "places": data.get("results", []),
        }

    def get_place(self, place_id: int | str) -> dict[str, Any]:
        """Get place details by iNaturalist place ID."""
        data = self._request(f"/places/{place_id}", cache_ttl=86400.0)
        results = data.get("results", [])
        if not results:
            raise INaturalistNotFoundError(404, f"Place ID {place_id} not found")
        return results[0]

    def get_nearby_places(
        self,
        lat: float,
        lon: float,
        nelat: float | None = None,
        nelng: float | None = None,
        swlat: float | None = None,
        swlng: float | None = None,
    ) -> dict[str, Any]:
        """Find standard and community places intersecting coordinates or bounding box."""
        if nelat is not None and nelng is not None and swlat is not None and swlng is not None:
            params = {"nelat": nelat, "nelng": nelng, "swlat": swlat, "swlng": swlng}
        else:
            delta = 0.05
            params = {
                "nelat": lat + delta,
                "nelng": lon + delta,
                "swlat": lat - delta,
                "swlng": lon - delta,
            }
        data = self._request("/places/nearby", params, cache_ttl=86400.0)
        results = data.get("results", {})
        return {
            "standard": results.get("standard", []),
            "community": results.get("community", []),
        }

    def species_counts(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        place_id: int | None = None,
        taxon_id: int | None = None,
        term_id: int | None = None,
        term_value_id: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Aggregate observations by species to rank biodiversity in an area."""
        params: dict[str, Any] = {"per_page": limit}
        if lat is not None and lon is not None:
            params["lat"] = lat
            params["lng"] = lon
            if radius_km is not None:
                params["radius"] = radius_km
        if place_id is not None:
            params["place_id"] = place_id
        if taxon_id is not None:
            params["taxon_id"] = taxon_id
        if term_id is not None:
            params["term_id"] = term_id
        if term_value_id is not None:
            params["term_value_id"] = term_value_id

        data = self._request("/observations/species_counts", params)
        return {
            "total_results": data.get("total_results", len(data.get("results", []))),
            "species_counts": data.get("results", []),
        }

    def search_projects(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Search iNaturalist projects and bioblitz initiatives."""
        params = {"q": query, "per_page": limit}
        data = self._request("/projects", params, cache_ttl=86400.0)
        return {
            "total_results": data.get("total_results", len(data.get("results", []))),
            "projects": data.get("results", []),
        }

    def user_observations(
        self, username: str, limit: int = 25, photos_only: bool = False
    ) -> dict[str, Any]:
        """Fetch observations recorded by a specific user login."""
        params: dict[str, Any] = {
            "user_login": username,
            "per_page": limit,
            "order_by": "observed_on",
            "order": "desc",
        }
        if photos_only:
            params["photos"] = True
        data = self._request("/observations", params)
        return {
            "total_results": data.get("total_results", len(data.get("results", []))),
            "observations": data.get("results", []),
        }

    # --- Advanced Capabilities (Lookalikes, Phenology, Controlled Terms) ---

    def get_similar_species(
        self, taxon_id: int | str, place_id: int | str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """Fetch the mutual misidentification lookalikes for a taxon."""
        params: dict[str, Any] = {"taxon_id": taxon_id}
        if place_id is not None:
            params["place_id"] = place_id
        data = self._request("/identifications/similar_species", params, cache_ttl=604800.0)
        results = data.get("results", [])
        return {
            "total_results": data.get("total_results", len(results)),
            "similar_species": results[:limit],
        }

    def get_species_phenology(
        self,
        taxon_id: int | str,
        place_id: int | str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
    ) -> dict[str, Any]:
        """Fetch seasonal occurrence curve across months of the year."""
        params: dict[str, Any] = {
            "taxon_id": taxon_id,
            "date_field": "observed",
            "interval": "month_of_year",
        }
        if place_id is not None:
            params["place_id"] = place_id
        if lat is not None and lon is not None:
            params["lat"] = lat
            params["lng"] = lon
            if radius_km is not None:
                params["radius"] = radius_km

        data = self._request("/observations/histogram", params, cache_ttl=604800.0)
        histogram = data.get("results", {}).get("month_of_year", {})
        return {
            "taxon_id": taxon_id,
            "months": histogram,
        }

    def get_controlled_terms(self, taxon_id: int | str | None = None) -> list[dict[str, Any]]:
        """Fetch controlled biological attributes (flowering, life stage, evidence)."""
        path = (
            f"/controlled_terms/for_taxon?taxon_id={taxon_id}" if taxon_id else "/controlled_terms"
        )
        data = self._request(path, cache_ttl=604800.0)
        return data.get("results", [])
