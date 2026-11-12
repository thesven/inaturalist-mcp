from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from inaturalist_mcp.client import INaturalistClient, INaturalistNotFoundError
from inaturalist_mcp.server import create_server


@pytest.fixture
def mock_client():
    client = MagicMock(spec=INaturalistClient)
    return client


def test_server_metadata(mock_client) -> None:
    server = create_server(mock_client)
    assert server.name == "inaturalist"
    assert server.version == "0.2.0"
    assert "iNaturalist MCP Server" in server.instructions


def test_tool_observations_nearby(mock_client) -> None:
    mock_client.observations_nearby.return_value = {
        "total_results": 1,
        "observations": [
            {
                "species_guess": "American Robin",
                "observed_on": "2026-04-01",
                "place_guess": "High Park, Toronto",
            }
        ],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("observations_nearby")
    assert tool_func is not None

    result = tool_func.fn(lat=43.7, lon=-79.4, radius_km=10, limit=10, photos_only=True)
    assert result["total_results"] == 1
    assert "American Robin on 2026-04-01 in High Park, Toronto" in result["summary"]


def test_tool_taxon_observations_nearby(mock_client) -> None:
    mock_client.taxon_observations_nearby.return_value = {
        "total_results": 1,
        "observations": [
            {
                "taxon": {"name": "Danaus plexippus"},
                "observed_on": "2026-05-15",
            }
        ],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("taxon_observations_nearby")

    result = tool_func.fn(
        taxon_query="Danaus plexippus", lat=40.7, lon=-74.0, radius_km=15, limit=5
    )
    assert result["total_results"] == 1
    assert "Danaus plexippus on 2026-05-15" in result["summary"]


def test_tool_rare_observations_nearby(mock_client) -> None:
    mock_client.rare_observations_nearby.return_value = {
        "total_results": 1,
        "observations": [
            {
                "species_guess": "Ghost Orchid",
                "photo_count": 2,
                "identifications_count": 1,
            }
        ],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("rare_observations_nearby")

    result = tool_func.fn(lat=26.0, lon=-81.0, radius_km=30, limit=5, taxon_query="Orchid")
    assert "Ghost Orchid (2 photos, 1 IDs)" in result["summary"]


def test_tool_rare_observations_nearby_empty(mock_client) -> None:
    mock_client.rare_observations_nearby.return_value = {
        "total_results": 0,
        "observations": [],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("rare_observations_nearby")

    result = tool_func.fn(lat=26.0, lon=-81.0, radius_km=30, limit=5)
    assert result["summary"] == "No rare observations found."


def test_tool_taxon_photo_evidence_nearby(mock_client) -> None:
    mock_client.taxon_photo_evidence_nearby.return_value = {
        "total_results": 1,
        "observations": [{"species_guess": "Grey Wolf", "observed_on": "2026-01-10"}],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("taxon_photo_evidence_nearby")

    result = tool_func.fn(taxon_query="Canis lupus", lat=45.0, lon=-75.0, radius_km=50)
    assert "Grey Wolf on 2026-01-10" in result["summary"]


def test_tool_place_taxon_activity(mock_client) -> None:
    mock_client.place_taxon_activity.return_value = {
        "total_results": 0,
        "observations": [],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("place_taxon_activity")

    result = tool_func.fn(lat=40.0, lon=-70.0, radius_km=25, limit=10)
    assert result["summary"] == "No observations found."


def test_tool_search_species(mock_client) -> None:
    mock_client.search_species.return_value = {
        "total_results": 2,
        "taxa": [
            {
                "id": 48662,
                "name": "Danaus plexippus",
                "preferred_common_name": "Monarch",
                "rank": "species",
            },
            {
                "id": 48663,
                "name": "Danaus",
                "rank": "genus",
            },
        ],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("search_species")

    result = tool_func.fn(query="Monarch", rank="species", iconic_taxa="Insecta", limit=5)
    assert "[species] Monarch (Danaus plexippus) (Taxon ID: 48662)" in result["summary"]
    assert "[genus] Danaus (Taxon ID: 48663)" in result["summary"]


def test_tool_search_species_empty(mock_client) -> None:
    mock_client.search_species.return_value = {"total_results": 0, "taxa": []}
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("search_species")

    result = tool_func.fn(query="NonExistent12345")
    assert "No taxa found matching 'NonExistent12345'." in result["summary"]


def test_tool_get_taxon_details(mock_client) -> None:
    mock_client.get_taxon.return_value = {
        "id": 48662,
        "name": "Danaus plexippus",
        "preferred_common_name": "Monarch",
        "rank": "species",
        "wikipedia_summary": "The monarch butterfly is a milkweed butterfly.",
        "conservation_status": {"status_name": "Endangered"},
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("get_taxon_details")

    result = tool_func.fn(taxon_id=48662)
    assert "Monarch (*Danaus plexippus*)" in result["summary"]
    assert "**Conservation Status:** Endangered" in result["summary"]
    assert "The monarch butterfly is a milkweed butterfly." in result["summary"]


def test_tool_get_observation_details(mock_client) -> None:
    mock_client.get_observation.return_value = {
        "id": 100,
        "species_guess": "Bald Eagle",
        "user": {"login": "birder42"},
        "observed_on": "2026-03-12",
        "quality_grade": "research",
        "uri": "https://inaturalist.org/observations/100",
        "photos": [{"url": "https://static.inaturalist.org/photos/1/medium.jpg"}],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("get_observation_details")

    result = tool_func.fn(observation_id=100)
    assert "Observation #100: Bald Eagle" in result["summary"]
    assert "@birder42" in result["summary"]
    assert "https://static.inaturalist.org/photos/1/medium.jpg" in result["summary"]


def test_tool_search_places(mock_client) -> None:
    mock_client.search_places.return_value = {
        "total_results": 1,
        "places": [{"id": 129274, "display_name": "Central Park, NY, US"}],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("search_places")

    result = tool_func.fn(query="Central Park")
    assert "Central Park, NY, US (Place ID: 129274)" in result["summary"]


def test_tool_search_places_empty(mock_client) -> None:
    mock_client.search_places.return_value = {"total_results": 0, "places": []}
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("search_places")

    result = tool_func.fn(query="NonExistentPlace")
    assert "No places found matching 'NonExistentPlace'." in result["summary"]


def test_tool_species_counts_nearby(mock_client) -> None:
    mock_client.species_counts.return_value = {
        "total_results": 2,
        "species_counts": [
            {
                "count": 50,
                "taxon": {
                    "name": "Acer saccharum",
                    "preferred_common_name": "Sugar Maple",
                },
            },
            {
                "count": 25,
                "taxon": {
                    "name": "Pinus strobus",
                },
            },
        ],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("species_counts_nearby")

    result = tool_func.fn(lat=45.0, lon=-75.0, radius_km=10, limit=5)
    assert "Sugar Maple (*Acer saccharum*): 50 observations" in result["summary"]
    assert "*Pinus strobus*: 25 observations" in result["summary"]


def test_tool_species_counts_nearby_empty(mock_client) -> None:
    mock_client.species_counts.return_value = {"total_results": 0, "species_counts": []}
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("species_counts_nearby")

    result = tool_func.fn(lat=45.0, lon=-75.0, radius_km=10)
    assert "No species counts found for the specified area." in result["summary"]


def test_tool_search_projects(mock_client) -> None:
    mock_client.search_projects.return_value = {
        "total_results": 1,
        "projects": [{"id": 12073, "title": "City Nature Challenge 2026", "slug": "cnc-2026"}],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("search_projects")

    result = tool_func.fn(query="City Nature Challenge")
    assert "**City Nature Challenge 2026** (ID: 12073, Slug: cnc-2026)" in result["summary"]


def test_tool_search_projects_empty(mock_client) -> None:
    mock_client.search_projects.return_value = {"total_results": 0, "projects": []}
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("search_projects")

    result = tool_func.fn(query="UnknownProjectXYZ")
    assert "No projects found matching 'UnknownProjectXYZ'." in result["summary"]


def test_tool_user_observations(mock_client) -> None:
    mock_client.user_observations.return_value = {
        "total_results": 1,
        "observations": [{"species_guess": "Monarch", "observed_on": "2026-08-01"}],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("user_observations")

    result = tool_func.fn(username="naturalist_dan", limit=10, photos_only=True)
    assert "Monarch on 2026-08-01" in result["summary"]


def test_resources(mock_client) -> None:
    mock_client.get_taxon.return_value = {"id": 1, "name": "Plantae"}
    mock_client.get_observation.return_value = {"id": 10, "species_guess": "Oak"}
    mock_client.get_place.return_value = {"id": 20, "name": "Park"}

    server = create_server(mock_client)

    for uri_template, template_obj in server._resource_manager._templates.items():
        if "taxa" in uri_template:
            content = template_obj.fn(taxon_id="1")
            parsed = json.loads(content)
            assert parsed["id"] == 1
        elif "observations" in uri_template:
            content = template_obj.fn(observation_id="10")
            parsed = json.loads(content)
            assert parsed["id"] == 10
        elif "places" in uri_template:
            content = template_obj.fn(place_id="20")
            parsed = json.loads(content)
            assert parsed["id"] == 20


def test_resources_error_handling(mock_client) -> None:
    mock_client.get_taxon.side_effect = INaturalistNotFoundError(404, "Not found")
    mock_client.get_observation.side_effect = INaturalistNotFoundError(404, "Not found")
    mock_client.get_place.side_effect = INaturalistNotFoundError(404, "Not found")
    server = create_server(mock_client)

    for uri_template, template_obj in server._resource_manager._templates.items():
        if "taxa" in uri_template:
            err_content = template_obj.fn(taxon_id="invalid")
            assert "error" in json.loads(err_content)
            err_content_404 = template_obj.fn(taxon_id="99999")
            assert "error" in json.loads(err_content_404)
        elif "observations" in uri_template:
            err_content = template_obj.fn(observation_id="invalid")
            assert "error" in json.loads(err_content)
        elif "places" in uri_template:
            err_content = template_obj.fn(place_id="invalid")
            assert "error" in json.loads(err_content)


def test_prompts(mock_client) -> None:
    server = create_server(mock_client)

    identify = server._prompt_manager.get_prompt("identify_specimen")
    assert identify is not None
    msg = identify.fn(
        organism_description="Small yellow warbler",
        location="Central Park",
        observed_date="2026-05-10",
    )
    assert "Small yellow warbler" in msg
    assert "Central Park" in msg
    assert "2026-05-10" in msg

    survey = server._prompt_manager.get_prompt("biodiversity_survey")
    assert survey is not None
    msg = survey.fn(place_name="Yellowstone National Park", radius_km=25)
    assert "Yellowstone National Park" in msg
    assert "25 km" in msg

    rare = server._prompt_manager.get_prompt("find_rare_species")
    assert rare is not None
    msg = rare.fn(region_or_coordinates="Everglades")
    assert "Everglades" in msg
