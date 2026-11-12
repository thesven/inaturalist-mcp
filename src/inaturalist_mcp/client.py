from __future__ import annotations

import os
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


class INaturalistClient:
    """Client for the iNaturalist REST API v1."""

    def __init__(
        self,
        base_url: str = "https://api.inaturalist.org/v1",
        api_token: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = (
            api_token or os.environ.get("INATURALIST_API_TOKEN") or os.environ.get("INAT_API_TOKEN")
        )
        self.timeout = timeout
        self.max_retries = max_retries

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
        self, path: str, params: dict[str, Any] | None = None, retry_delay: float = 1.0
    ) -> dict[str, Any]:
        url = self.base_url + path
        attempts = 0
        last_exc: Exception | None = None

        while attempts < self.max_retries:
            attempts += 1
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
        """Fetch nearby observations matching a taxon query string."""
        params = self._base_params(lat, lon, radius_km, limit, photos_only)
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
            scored.append(
                {
                    "id": item.get("id"),
                    "species_guess": item.get("species_guess") or item.get("taxon", {}).get("name"),
                    "observed_on": item.get("observed_on"),
                    "photo_count": len(item.get("photos", [])),
                    "confidence_proxy": score,
                    "identifications_count": score,
                    "uri": item.get("uri"),
                    "location": item.get("location"),
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
        data = self._request("/taxa/autocomplete", params)
        return {
            "total_results": data.get("total_results", len(data.get("results", []))),
            "taxa": data.get("results", []),
        }

    def get_taxon(self, taxon_id: int | str) -> dict[str, Any]:
        """Get complete taxon record by iNaturalist taxon ID."""
        data = self._request(f"/taxa/{taxon_id}")
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
        data = self._request("/places/autocomplete", params)
        return {
            "total_results": data.get("total_results", len(data.get("results", []))),
            "places": data.get("results", []),
        }

    def get_place(self, place_id: int | str) -> dict[str, Any]:
        """Get place details by iNaturalist place ID."""
        data = self._request(f"/places/{place_id}")
        results = data.get("results", [])
        if not results:
            raise INaturalistNotFoundError(404, f"Place ID {place_id} not found")
        return results[0]

    def species_counts(
        self,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        place_id: int | None = None,
        taxon_id: int | None = None,
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

        data = self._request("/observations/species_counts", params)
        return {
            "total_results": data.get("total_results", len(data.get("results", []))),
            "species_counts": data.get("results", []),
        }

    def search_projects(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Search iNaturalist projects and bioblitz initiatives."""
        params = {"q": query, "per_page": limit}
        data = self._request("/projects", params)
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
