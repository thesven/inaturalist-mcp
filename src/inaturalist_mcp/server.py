from __future__ import annotations

from mcp.server import FastMCP

from .client import INaturalistClient


mcp = FastMCP("inaturalist-mcp")
client = INaturalistClient()


@mcp.tool()
def observations_nearby(lat: float, lon: float, radius_km: int = 25, limit: int = 25, photos_only: bool = False) -> dict:
    """Fetch nearby iNaturalist observations."""
    result = client.observations_nearby(lat, lon, radius_km, limit, photos_only)
    result["summary"] = "\n".join(
        f"{item.get('species_guess', item.get('taxon', {}).get('name', 'Unknown taxon'))} on {item.get('observed_on', 'n/a')}"
        for item in result["observations"][:10]
    )
    return result


@mcp.tool()
def taxon_observations_nearby(
    taxon_query: str,
    lat: float,
    lon: float,
    radius_km: int = 25,
    limit: int = 25,
    photos_only: bool = False,
) -> dict:
    """Fetch nearby iNaturalist observations for a taxon query."""
    result = client.taxon_observations_nearby(taxon_query, lat, lon, radius_km, limit, photos_only)
    result["summary"] = "\n".join(
        f"{item.get('species_guess', item.get('taxon', {}).get('name', taxon_query))} on {item.get('observed_on', 'n/a')}"
        for item in result["observations"][:10]
    )
    return result


@mcp.tool()
def rare_observations_nearby(
    lat: float,
    lon: float,
    radius_km: int = 25,
    limit: int = 25,
    taxon_query: str | None = None,
) -> dict:
    """Fetch sparse or lightly confirmed nearby iNaturalist observations."""
    result = client.rare_observations_nearby(lat, lon, radius_km, limit, taxon_query)
    result["summary"] = "\n".join(
        f"{item.get('species_guess', 'Unknown taxon')} with {item.get('photo_count', 0)} photos"
        for item in result["observations"][:10]
    )
    return result


@mcp.tool()
def taxon_photo_evidence_nearby(taxon_query: str, lat: float, lon: float, radius_km: int = 25, limit: int = 25) -> dict:
    """Fetch nearby iNaturalist observations with photo evidence for a taxon."""
    result = client.taxon_photo_evidence_nearby(taxon_query, lat, lon, radius_km, limit)
    result["summary"] = "\n".join(
        f"{item.get('species_guess', item.get('taxon', {}).get('name', taxon_query))} on {item.get('observed_on', 'n/a')}"
        for item in result["observations"][:10]
    )
    return result


@mcp.tool()
def place_taxon_activity(
    lat: float,
    lon: float,
    radius_km: int = 25,
    limit: int = 25,
    taxon_query: str | None = None,
) -> dict:
    """Fetch recent iNaturalist taxon activity for a place."""
    result = client.place_taxon_activity(lat, lon, radius_km, limit, taxon_query)
    result["summary"] = "\n".join(
        f"{item.get('species_guess', item.get('taxon', {}).get('name', 'Unknown taxon'))} on {item.get('observed_on', 'n/a')}"
        for item in result["observations"][:10]
    )
    return result


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
