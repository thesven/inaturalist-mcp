from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from mcp.server import MCPServer

from . import __version__
from .client import INaturalistClient, INaturalistError

DEFAULT_INSTRUCTIONS = """
iNaturalist MCP Server: Access global community-contributed biodiversity observations,
authoritative species taxonomy, regional checklists, photo evidence, and places.

Key Best Practices:
1. When a user asks about a species or organism by common or ambiguous name, use `search_species`
   first to resolve its official scientific name, taxon ID, and rank.
2. For regional or local park queries, use `search_places` to resolve official place IDs or pass
   exact GPS coordinates with `lat`, `lon`, and `radius_km`.
3. To survey what species are most frequently recorded in an area, call `species_counts_nearby`.
4. For rare or notable wildlife sightings, use `rare_observations_nearby`.
5. High-resolution photo URLs and community identification counts are included with observations.
""".strip()


def _format_obs_summary(observations: list[dict[str, Any]]) -> str:
    lines = []
    for item in observations[:10]:
        guess = item.get("species_guess") or item.get("taxon", {}).get("name", "Unknown taxon")
        observed = item.get("observed_on") or "Date unknown"
        place = item.get("place_guess")
        suffix = f" in {place}" if place else ""
        lines.append(f"- {guess} on {observed}{suffix}")
    return "\n".join(lines) if lines else "No observations found."


def create_server(client: INaturalistClient | None = None) -> MCPServer:
    """Create and configure the iNaturalist MCPServer instance."""
    api = client or INaturalistClient()

    server = MCPServer(
        "inaturalist",
        version=__version__,
        instructions=DEFAULT_INSTRUCTIONS,
    )

    # --- Core Observation Tools (Backwards Compatible) ---

    @server.tool()
    def observations_nearby(
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
        photos_only: bool = False,
    ) -> dict[str, Any]:
        """Fetch nearby iNaturalist biodiversity observations within a radius in kilometers."""
        result = api.observations_nearby(lat, lon, radius_km, limit, photos_only)
        result["summary"] = _format_obs_summary(result["observations"])
        return result

    @server.tool()
    def taxon_observations_nearby(
        taxon_query: str,
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
        photos_only: bool = False,
    ) -> dict[str, Any]:
        """Fetch nearby iNaturalist observations matching a specific taxon or species query."""
        result = api.taxon_observations_nearby(taxon_query, lat, lon, radius_km, limit, photos_only)
        result["summary"] = _format_obs_summary(result["observations"])
        return result

    @server.tool()
    def rare_observations_nearby(
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
        taxon_query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch lightly confirmed or sparsely identified research-grade observations nearby."""
        result = api.rare_observations_nearby(lat, lon, radius_km, limit, taxon_query)
        lines = [
            f"- {item.get('species_guess', 'Unknown taxon')} "
            f"({item.get('photo_count', 0)} photos, {item.get('identifications_count', 0)} IDs)"
            for item in result["observations"][:10]
        ]
        result["summary"] = "\n".join(lines) if lines else "No rare observations found."
        return result

    @server.tool()
    def taxon_photo_evidence_nearby(
        taxon_query: str,
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Fetch nearby iNaturalist observations that contain verified photographic evidence."""
        result = api.taxon_photo_evidence_nearby(taxon_query, lat, lon, radius_km, limit)
        result["summary"] = _format_obs_summary(result["observations"])
        return result

    @server.tool()
    def place_taxon_activity(
        lat: float,
        lon: float,
        radius_km: int = 25,
        limit: int = 25,
        taxon_query: str | None = None,
    ) -> dict[str, Any]:
        """Fetch recent iNaturalist taxon activity for a place or region."""
        result = api.place_taxon_activity(lat, lon, radius_km, limit, taxon_query)
        result["summary"] = _format_obs_summary(result["observations"])
        return result

    # --- Extended Discovery Tools ---

    @server.tool()
    def search_species(
        query: str,
        rank: str | None = None,
        iconic_taxa: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search and autocomplete taxa by common name, genus, or scientific name.

        Use this to find exact iNaturalist taxon IDs and taxonomy ranks before running queries.
        """
        result = api.search_species(query, rank=rank, iconic_taxa=iconic_taxa, limit=limit)
        lines = []
        for taxon in result["taxa"][:10]:
            name = taxon.get("name", "Unknown")
            common = taxon.get("preferred_common_name")
            display_name = f"{common} ({name})" if common else name
            rank_str = taxon.get("rank", "taxon")
            tid = taxon.get("id")
            lines.append(f"- [{rank_str}] {display_name} (Taxon ID: {tid})")
        result["summary"] = "\n".join(lines) if lines else f"No taxa found matching '{query}'."
        return result

    @server.tool()
    def get_taxon_details(taxon_id: int) -> dict[str, Any]:
        """Lookup complete taxonomic information, conservation status, and summary by taxon ID."""
        taxon = api.get_taxon(taxon_id)
        name = taxon.get("name", "Unknown")
        common = taxon.get("preferred_common_name")
        rank = taxon.get("rank", "taxon")
        wiki = taxon.get("wikipedia_summary") or "No Wikipedia summary available."
        status_info = taxon.get("conservation_status") or {}
        status = status_info.get("status_name", "Not evaluated / Least Concern")
        summary = (
            f"### {common or name} (*{name}*)\n"
            f"- **Rank:** {rank.capitalize()}\n"
            f"- **Taxon ID:** {taxon_id}\n"
            f"- **Conservation Status:** {status}\n\n"
            f"{wiki}"
        )
        return {"taxon": taxon, "summary": summary}

    @server.tool()
    def get_observation_details(observation_id: int) -> dict[str, Any]:
        """Fetch comprehensive details for an observation including photos, IDs, and location."""
        obs = api.get_observation(observation_id)
        guess = obs.get("species_guess") or obs.get("taxon", {}).get("name", "Unknown")
        user = obs.get("user", {}).get("login", "unknown_user")
        observed = obs.get("observed_on", "Unknown date")
        quality = obs.get("quality_grade", "casual")
        uri = obs.get("uri", f"https://www.inaturalist.org/observations/{observation_id}")
        photos = obs.get("photos", [])
        photo_urls = [p.get("url") for p in photos if p.get("url")]

        summary = (
            f"### Observation #{observation_id}: {guess}\n"
            f"- **Observer:** @{user}\n"
            f"- **Observed On:** {observed}\n"
            f"- **Quality Grade:** {quality}\n"
            f"- **URL:** {uri}\n"
            f"- **Photos:** {len(photos)} photo(s)\n"
        )
        if photo_urls:
            summary += "\n**Photo Previews:**\n" + "\n".join(f"- {u}" for u in photo_urls[:5])

        return {"observation": obs, "summary": summary}

    @server.tool()
    def search_places(query: str, limit: int = 10) -> dict[str, Any]:
        """Search parks, cities, counties, and protected reserves for official place IDs."""
        result = api.search_places(query, limit=limit)
        lines = []
        for place in result["places"][:10]:
            name = place.get("display_name") or place.get("name", "Unknown place")
            pid = place.get("id")
            lines.append(f"- {name} (Place ID: {pid})")
        result["summary"] = "\n".join(lines) if lines else f"No places found matching '{query}'."
        return result

    @server.tool()
    def species_counts_nearby(
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        place_id: int | None = None,
        taxon_id: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Discover the most frequently observed species in a geographic area or place."""
        result = api.species_counts(
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            place_id=place_id,
            taxon_id=taxon_id,
            limit=limit,
        )
        lines = []
        for item in result["species_counts"][:limit]:
            count = item.get("count", 0)
            taxon = item.get("taxon", {})
            name = taxon.get("name", "Unknown")
            common = taxon.get("preferred_common_name")
            display = f"{common} (*{name}*)" if common else f"*{name}*"
            lines.append(f"- {display}: {count} observations")
        result["summary"] = (
            "\n".join(lines) if lines else "No species counts found for the specified area."
        )
        return result

    @server.tool()
    def search_projects(query: str, limit: int = 10) -> dict[str, Any]:
        """Search iNaturalist projects, bioblitzes, and monitoring initiatives."""
        result = api.search_projects(query, limit=limit)
        lines = []
        for proj in result["projects"][:10]:
            title = proj.get("title", "Untitled project")
            pid = proj.get("id")
            slug = proj.get("slug")
            lines.append(f"- **{title}** (ID: {pid}, Slug: {slug})")
        result["summary"] = "\n".join(lines) if lines else f"No projects found matching '{query}'."
        return result

    @server.tool()
    def user_observations(
        username: str, limit: int = 25, photos_only: bool = False
    ) -> dict[str, Any]:
        """Fetch observations recorded by a specific iNaturalist naturalist or researcher."""
        result = api.user_observations(username, limit=limit, photos_only=photos_only)
        result["summary"] = _format_obs_summary(result["observations"])
        return result

    # --- Resources ---

    @server.resource("inaturalist://taxa/{taxon_id}")
    def taxon_resource(taxon_id: str) -> str:
        """Resource exposing detailed taxonomic records."""
        try:
            data = api.get_taxon(int(taxon_id))
            return json.dumps(data, indent=2)
        except (ValueError, INaturalistError) as exc:
            return json.dumps({"error": str(exc), "taxon_id": taxon_id})

    @server.resource("inaturalist://observations/{observation_id}")
    def observation_resource(observation_id: str) -> str:
        """Resource exposing full observation details and metadata."""
        try:
            data = api.get_observation(int(observation_id))
            return json.dumps(data, indent=2)
        except (ValueError, INaturalistError) as exc:
            return json.dumps({"error": str(exc), "observation_id": observation_id})

    @server.resource("inaturalist://places/{place_id}")
    def place_resource(place_id: str) -> str:
        """Resource exposing place boundaries and metadata."""
        try:
            data = api.get_place(int(place_id))
            return json.dumps(data, indent=2)
        except (ValueError, INaturalistError) as exc:
            return json.dumps({"error": str(exc), "place_id": place_id})

    # --- Prompts ---

    @server.prompt()
    def identify_specimen(
        organism_description: str,
        location: str | None = None,
        observed_date: str | None = None,
    ) -> str:
        """Guide the identification of a plant, animal, or fungus specimen."""
        loc_str = f" Near: {location}." if location else ""
        date_str = f" Observed on: {observed_date}." if observed_date else ""
        return (
            f"You are an expert naturalist identifying a wild organism.{loc_str}{date_str}\n\n"
            f'Observed organism description:\n"{organism_description}"\n\n'
            "Instructions:\n"
            "1. If location is provided, query nearby observations or species counts.\n"
            "2. Search species with `search_species` to find candidate taxa and traits.\n"
            "3. Compare candidate diagnostic morphology and phenology against description.\n"
            "4. Provide most probable identification, lookalikes, and confirmation steps."
        )

    @server.prompt()
    def biodiversity_survey(place_name: str, radius_km: int = 15) -> str:
        """Survey biodiversity and common species for a park, reserve, or region."""
        return (
            f"Conduct a biodiversity assessment for '{place_name}' (~{radius_km} km radius).\n\n"
            "Instructions:\n"
            "1. Search for the place using `search_places` or resolve coordinates.\n"
            "2. Fetch top species counts using `species_counts_nearby` for dominant taxa.\n"
            "3. Query `rare_observations_nearby` to check species of conservation interest.\n"
            "4. Present a structured report: birds, insects, plants, fungi, and mammals."
        )

    @server.prompt()
    def find_rare_species(region_or_coordinates: str) -> str:
        """Investigate rare, threatened, or lightly confirmed species in an area."""
        return (
            f"Investigate rare biodiversity sightings in: '{region_or_coordinates}'.\n\n"
            "Instructions:\n"
            "1. Resolve coordinates or place identifier.\n"
            "2. Run `rare_observations_nearby` for lightly confirmed research-grade records.\n"
            "3. For highlighted records, call `get_observation_details` for photos and notes.\n"
            "4. Summarize potential significant findings and needed community confirmations."
        )

    return server


# Global default server instance
mcp = create_server()


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for running the iNaturalist MCP server."""
    parser = argparse.ArgumentParser(
        prog="inaturalist-mcp",
        description="Model Context Protocol (MCP) server for iNaturalist",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport layer to run (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host for SSE transport (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args(argv)

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        mcp.run(transport="sse")
    else:
        print(f"Unsupported transport: {args.transport}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
