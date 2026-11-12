from __future__ import annotations

import argparse
import base64
import json
import sys
from typing import Any

from mcp.server import MCPServer
from mcp.types import CallToolResult, ImageContent, TextContent

from . import __version__
from .client import INaturalistClient, INaturalistError

DEFAULT_INSTRUCTIONS = """
iNaturalist MCP Server: Access global community-contributed biodiversity observations,
authoritative species taxonomy, lookalike species, seasonal phenology curves, photo evidence,
and conservation alerts.

Key Best Practices:
1. When a user asks about an organism by common or ambiguous name, use `search_species`
   first to resolve its official scientific name, taxon ID, and rank. You may also pass eBird
   6-letter codes (e.g. 'baleag', 'snoowl1') directly.
2. For visual and morphological identification, ALWAYS check `get_similar_species` to discover
   species most frequently confused with your candidate taxon and review diagnostic field marks.
3. Use `get_species_phenology` to verify seasonal occurrence curves across months of the year
   so you never recommend a seasonally impossible identification.
4. Call `view_observation_photos` to load binary image content directly into context for visual
   inspection of plumage, leaf margins, wing venation, or gill attachments.
5. Watch for `[CONSERVATION NOTICE]` and obscured coordinate flags on sensitive/endangered taxa.
6. For regional park queries, use `search_places` or `get_nearby_places` to resolve
   official place IDs.
""".strip()

MONTH_NAMES = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
]


def _format_obs_summary(observations: list[dict[str, Any]]) -> str:
    lines = []
    for item in observations[:10]:
        guess = item.get("species_guess") or item.get("taxon", {}).get("name", "Unknown taxon")
        observed = item.get("observed_on") or "Date unknown"
        place = item.get("place_guess")
        suffix = f" in {place}" if place else ""
        obscured_note = " ⚠️ [Obscured Coordinates]" if item.get("obscured") else ""
        lines.append(f"- {guess} on {observed}{suffix}{obscured_note}")
    return "\n".join(lines) if lines else "No observations found."


def _render_ascii_phenology_bar(count: int, max_count: int, bar_width: int = 15) -> str:
    if max_count <= 0 or count <= 0:
        return "."
    chars = int(round((count / max_count) * bar_width))
    return "█" * max(1, chars)


def create_server(client: INaturalistClient | None = None) -> MCPServer:
    """Create and configure the production-grade iNaturalist MCPServer instance."""
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
        """Fetch nearby iNaturalist observations matching a taxon, species query, or eBird code."""
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
        lines = []
        for item in result["observations"][:10]:
            name = item.get("species_guess", "Unknown taxon")
            p_count = item.get("photo_count", 0)
            id_count = item.get("identifications_count", 0)
            obs_flag = " ⚠️ [Obscured Coordinates]" if item.get("obscured") else ""
            status_flag = ""
            status_info = item.get("conservation_status")
            if status_info:
                status_flag = f" [{status_info.get('status_name', 'Threatened')}]"
            lines.append(f"- {name} ({p_count} photos, {id_count} IDs){status_flag}{obs_flag}")
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

    # --- Extended Discovery & Taxonomy Tools ---

    @server.tool()
    def search_species(
        query: str,
        rank: str | None = None,
        iconic_taxa: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search and autocomplete taxa by common name, scientific name, or eBird code.

        Use this to find exact iNaturalist taxon IDs and taxonomy ranks before running queries.
        """
        # If user passed an eBird code, check cross-bridge
        if len(query) == 6 and query.isalnum() and not query.isdigit():
            ebird_match = api.resolve_ebird_code_to_taxon_id(query)
            if ebird_match:
                taxa = [ebird_match["inat_taxon"]]
                summary = (
                    f"- [{taxa[0].get('rank', 'species')}] {ebird_match['ebird_common_name']} "
                    f"({ebird_match['scientific_name']}) (Taxon ID: {taxa[0].get('id')}) "
                    f"[eBird speciesCode: {query}]"
                )
                return {"total_results": 1, "taxa": taxa, "summary": summary}

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
        obscured_warning = ""
        if obs.get("obscured"):
            obscured_warning = (
                "\n> ⚠️ **CONSERVATION NOTICE:** Coordinates for this observation are "
                "obscured by iNaturalist for species protection. Do not rely on coordinates "
                "for micro-habitat navigation.\n"
            )

        summary = (
            f"### Observation #{observation_id}: {guess}\n"
            f"- **Observer:** @{user}\n"
            f"- **Observed On:** {observed}\n"
            f"- **Quality Grade:** {quality}\n"
            f"- **URL:** {uri}\n"
            f"- **Photos:** {len(photos)} photo(s)\n"
            f"{obscured_warning}"
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
    def get_nearby_places(lat: float, lon: float) -> dict[str, Any]:
        """Find administrative boundaries, parks, and community places containing coordinates."""
        result = api.get_nearby_places(lat, lon)
        lines = ["**Standard Administrative Places:**"]
        for p in result["standard"][:5]:
            lines.append(
                f"- {p.get('name')} (Place ID: {p.get('id')}, Type: {p.get('place_type')})"
            )
        if result["community"]:
            lines.append("\n**Community & Protected Reserves:**")
            for p in result["community"][:5]:
                lines.append(f"- {p.get('name')} (Place ID: {p.get('id')})")
        result["summary"] = "\n".join(lines)
        return result

    @server.tool()
    def species_counts_nearby(
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
        place_id: int | None = None,
        taxon_id: int | None = None,
        term_id: int | None = None,
        term_value_id: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Discover frequently observed species in an area, optionally filtered by term."""
        result = api.species_counts(
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            place_id=place_id,
            taxon_id=taxon_id,
            term_id=term_id,
            term_value_id=term_value_id,
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

    # --- Advanced Capabilities (Lookalikes, Phenology, Multimodal Vision) ---

    @server.tool()
    def get_similar_species(
        taxon_id: int, place_id: int | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """Fetch species most frequently confused with this taxon in community identifications.

        Essential for visual identification and ruling out mimics/lookalikes.
        """
        result = api.get_similar_species(taxon_id, place_id=place_id, limit=limit)
        lines = []
        for item in result["similar_species"]:
            count = item.get("count", 0)
            t = item.get("taxon", {})
            name = t.get("name", "Unknown")
            common = t.get("preferred_common_name")
            tid = t.get("id")
            display = f"**{common}** (*{name}*)" if common else f"*{name}*"
            lines.append(f"- {display} (Taxon ID: {tid}): {count} mutual misidentifications")
        result["summary"] = (
            "\n".join(lines)
            if lines
            else "No frequently confused lookalike species recorded for this taxon."
        )
        return result

    @server.tool()
    def get_species_phenology(
        taxon_id: int,
        place_id: int | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: int | None = None,
    ) -> dict[str, Any]:
        """Retrieve seasonal occurrence curve (by month) to verify phenology and flight times."""
        result = api.get_species_phenology(
            taxon_id, place_id=place_id, lat=lat, lon=lon, radius_km=radius_km
        )
        months_dict = result["months"]
        counts = [int(months_dict.get(str(m), 0)) for m in range(1, 13)]
        max_c = max(counts) if counts else 0

        header = "Month | Observations | Relative Seasonal Frequency"
        divider = "--- | ---: | ---"
        rows = [header, divider]
        for m_name, count in zip(MONTH_NAMES, counts, strict=False):
            bar = _render_ascii_phenology_bar(count, max_c)
            is_peak = " (Peak)" if count == max_c and max_c > 0 else ""
            rows.append(f"{m_name} | {count:,} | {bar}{is_peak}")

        result["summary"] = "\n".join(rows)
        return result

    @server.tool()
    def get_controlled_terms(taxon_id: int | None = None) -> dict[str, Any]:
        """Retrieve biological attribute terms (Life Stage, Flowers/Fruits, Evidence)."""
        terms = api.get_controlled_terms(taxon_id)
        lines = []
        for term in terms:
            label = term.get("label", "Term")
            tid = term.get("id")
            vals = [f"{v.get('label')} (Value ID: {v.get('id')})" for v in term.get("values", [])]
            lines.append(f"### {label} (Term ID: {tid})\n- Values: {', '.join(vals)}")
        summary = "\n\n".join(lines) if lines else "No controlled terms found."
        return {"terms": terms, "summary": summary}

    @server.tool()
    def view_observation_photos(observation_id: int, max_photos: int = 2) -> CallToolResult:
        """Fetch high-resolution observation images directly into context for visual analysis.

        Allows multimodal models to inspect bill morphology, plumage, and wing venation.
        """
        obs = api.get_observation(observation_id)
        guess = obs.get("species_guess") or obs.get("taxon", {}).get("name", "Unknown taxon")
        photos = obs.get("photos", [])
        if not photos:
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"Observation #{observation_id} ({guess}) has no photos attached.",
                    )
                ]
            )

        total_photos = len(photos)
        header_text = (
            f"Visual evidence for Observation #{observation_id} ({guess}) - "
            f"{total_photos} photo(s) available:"
        )
        content_blocks: list[TextContent | ImageContent] = [
            TextContent(type="text", text=header_text)
        ]

        for idx, photo in enumerate(photos[:max_photos], start=1):
            url = photo.get("url")
            if not url:
                continue
            # Upgrade standard 75x75 square thumbnail to 500px medium resolution
            medium_url = url.replace("square.", "medium.")
            try:
                img_bytes, mime_type = api.fetch_image_bytes(medium_url)
                b64_data = base64.b64encode(img_bytes).decode("ascii")
                content_blocks.append(
                    ImageContent(
                        type="image",
                        data=b64_data,
                        mime_type=mime_type,
                    )
                )
                attribution = photo.get("attribution", "")
                p_count = min(len(photos), max_photos)
                content_blocks.append(
                    TextContent(
                        type="text",
                        text=f"Photo {idx}/{p_count}: {attribution} ({medium_url})",
                    )
                )
            except Exception as exc:
                content_blocks.append(
                    TextContent(
                        type="text",
                        text=f"Photo {idx}: Failed image fetch ({exc}) - URL: {medium_url}",
                    )
                )

        return CallToolResult(content=content_blocks)

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

    @server.resource("inaturalist://phenology/{taxon_id}")
    def phenology_resource(taxon_id: str) -> str:
        """Resource exposing seasonal occurrence curves across months."""
        try:
            data = api.get_species_phenology(int(taxon_id))
            return json.dumps(data, indent=2)
        except (ValueError, INaturalistError) as exc:
            return json.dumps({"error": str(exc), "taxon_id": taxon_id})

    @server.resource("inaturalist://lookalikes/{taxon_id}")
    def lookalikes_resource(taxon_id: str) -> str:
        """Resource exposing top mutual misidentification species."""
        try:
            data = api.get_similar_species(int(taxon_id))
            return json.dumps(data, indent=2)
        except (ValueError, INaturalistError) as exc:
            return json.dumps({"error": str(exc), "taxon_id": taxon_id})

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
            "3. Query `get_similar_species` to identify lookalikes and diagnostic field marks.\n"
            "4. Check `get_species_phenology` to ensure candidate species is in season.\n"
            "5. If photo evidence exists, inspect images with `view_observation_photos`.\n"
            "6. Provide the most probable identification, lookalikes, and confirmation steps."
        )

    @server.prompt()
    def lookalike_comparison(candidate_taxon_name: str, observation_context: str = "") -> str:
        """Perform a rigorous side-by-side diagnostic comparison with common mimics."""
        title = f"Perform a diagnostic field mark comparison for: '{candidate_taxon_name}'."
        ctx_str = f" Context: {observation_context}\n" if observation_context else ""
        return (
            f"{title}\n{ctx_str}\n"
            "Instructions:\n"
            "1. Resolve the candidate species using `search_species`.\n"
            "2. Fetch its top confusion lookalikes using `get_similar_species`.\n"
            "3. Compare diagnostic morphological keys (plumage, venation, spore print, margins).\n"
            "4. Check phenology differences with `get_species_phenology`.\n"
            "5. Provide a clear field identification table highlighting distinguishing traits."
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
            "3. Check for obscured coordinates and conservation status warnings.\n"
            "4. For highlighted records, call `get_observation_details` for photos and notes.\n"
            "5. Summarize potential significant findings and needed community confirmations."
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
