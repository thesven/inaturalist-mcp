from __future__ import annotations

from typing import Any

import httpx


class INaturalistClient:
    def __init__(self, base_url: str = "https://api.inaturalist.org/v1") -> None:
        self.base_url = base_url.rstrip("/")

    def observations_nearby(
        self, lat: float, lon: float, radius_km: int = 25, limit: int = 25, photos_only: bool = False
    ) -> dict[str, Any]:
        params = self._base_params(lat, lon, radius_km, limit, photos_only)
        return {"observations": self._request("/observations", params).get("results", [])}

    def taxon_observations_nearby(
        self,
        taxon_query: str,
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
        photos_only: bool = False,
    ) -> dict[str, Any]:
        params = self._base_params(lat, lon, radius_km, limit, photos_only)
        params["q"] = taxon_query
        return {"observations": self._request("/observations", params).get("results", [])}

    def rare_observations_nearby(
        self, lat: float, lon: float, radius_km: int = 25, limit: int = 25, taxon_query: str | None = None
    ) -> dict[str, Any]:
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
                    "species_guess": item.get("species_guess") or item.get("taxon", {}).get("name"),
                    "observed_on": item.get("observed_on"),
                    "photo_count": len(item.get("photos", [])),
                    "confidence_proxy": score,
                }
            )
        scored.sort(key=lambda item: item["confidence_proxy"])
        return {"observations": scored[:limit]}

    def taxon_photo_evidence_nearby(
        self, taxon_query: str, lat: float, lon: float, radius_km: int = 25, limit: int = 25
    ) -> dict[str, Any]:
        return self.taxon_observations_nearby(taxon_query, lat, lon, radius_km, limit, photos_only=True)

    def place_taxon_activity(
        self, lat: float, lon: float, radius_km: int = 25, limit: int = 25, taxon_query: str | None = None
    ) -> dict[str, Any]:
        return self.taxon_observations_nearby(taxon_query or "", lat, lon, radius_km, limit)

    def _request(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = httpx.get(self.base_url + path, params=params, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected iNaturalist response shape for {path}")
        return data

    @staticmethod
    def _base_params(lat: float, lon: float, radius_km: int, limit: int, photos_only: bool) -> dict[str, Any]:
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
