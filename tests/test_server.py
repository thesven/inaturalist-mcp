from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from inaturalist_mcp.client import INaturalistClient
from inaturalist_mcp.server import create_server


@pytest.fixture
def mock_client():
    client = MagicMock(spec=INaturalistClient)
    return client


def test_server_metadata(mock_client) -> None:
    server = create_server(mock_client)
    assert server.name == "inaturalist"
    assert server.version == "1.0.0"
    assert "iNaturalist MCP Server" in server.instructions


def test_tool_observations_nearby(mock_client) -> None:
    mock_client.observations_nearby.return_value = {
        "total_results": 1,
        "observations": [
            {
                "species_guess": "American Robin",
                "observed_on": "2026-04-01",
                "place_guess": "High Park, Toronto",
                "obscured": True,
            }
        ],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("observations_nearby")
    assert tool_func is not None

    result = tool_func.fn(lat=43.7, lon=-79.4, radius_km=10, limit=10, photos_only=True)
    assert result["total_results"] == 1
    assert "American Robin on 2026-04-01 in High Park, Toronto" in result["summary"]
    assert "[Obscured Coordinates]" in result["summary"]


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
                "obscured": True,
                "conservation_status": {"status_name": "Endangered"},
            }
        ],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("rare_observations_nearby")

    result = tool_func.fn(lat=26.0, lon=-81.0, radius_km=30, limit=5, taxon_query="Orchid")
    assert (
        "Ghost Orchid (2 photos, 1 IDs) [Endangered] ⚠️ [Obscured Coordinates]" in result["summary"]
    )


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


def test_tool_search_species_ebird_code(mock_client) -> None:
    mock_client.resolve_ebird_code_to_taxon_id.return_value = {
        "ebird_code": "baleag",
        "ebird_common_name": "Bald Eagle",
        "scientific_name": "Haliaeetus leucocephalus",
        "inat_taxon_id": 5305,
        "inat_taxon": {"id": 5305, "name": "Haliaeetus leucocephalus", "rank": "species"},
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("search_species")

    result = tool_func.fn(query="baleag")
    assert "Bald Eagle (Haliaeetus leucocephalus) (Taxon ID: 5305)" in result["summary"]
    assert "eBird speciesCode: baleag" in result["summary"]


def test_tool_search_species_empty(mock_client) -> None:
    mock_client.search_species.return_value = {"total_results": 0, "taxa": []}
    mock_client.resolve_ebird_code_to_taxon_id.return_value = None
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
        "obscured": True,
        "uri": "https://inaturalist.org/observations/100",
        "photos": [{"url": "https://static.inaturalist.org/photos/1/medium.jpg"}],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("get_observation_details")

    result = tool_func.fn(observation_id=100)
    assert "Observation #100: Bald Eagle" in result["summary"]
    assert "@birder42" in result["summary"]
    assert "CONSERVATION NOTICE" in result["summary"]
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


def test_tool_get_nearby_places(mock_client) -> None:
    mock_client.get_nearby_places.return_value = {
        "standard": [{"id": 1, "name": "San Francisco", "place_type": "city"}],
        "community": [{"id": 2, "name": "Golden Gate Park"}],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("get_nearby_places")

    result = tool_func.fn(lat=37.7, lon=-122.4)
    assert "San Francisco (Place ID: 1, Type: city)" in result["summary"]
    assert "Golden Gate Park (Place ID: 2)" in result["summary"]


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


def test_tool_search_projects(mock_client) -> None:
    mock_client.search_projects.return_value = {
        "total_results": 1,
        "projects": [{"id": 12073, "title": "City Nature Challenge 2026", "slug": "cnc-2026"}],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("search_projects")

    result = tool_func.fn(query="City Nature Challenge")
    assert "**City Nature Challenge 2026** (ID: 12073, Slug: cnc-2026)" in result["summary"]


def test_tool_user_observations(mock_client) -> None:
    mock_client.user_observations.return_value = {
        "total_results": 1,
        "observations": [{"species_guess": "Monarch", "observed_on": "2026-08-01"}],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("user_observations")

    result = tool_func.fn(username="naturalist_dan", limit=10, photos_only=True)
    assert "Monarch on 2026-08-01" in result["summary"]


def test_tool_get_similar_species(mock_client) -> None:
    mock_client.get_similar_species.return_value = {
        "total_results": 1,
        "similar_species": [
            {
                "count": 2013,
                "taxon": {
                    "id": 68065,
                    "name": "Limenitis archippus",
                    "preferred_common_name": "Viceroy",
                },
            }
        ],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("get_similar_species")

    result = tool_func.fn(taxon_id=48662, place_id=14)
    assert (
        "**Viceroy** (*Limenitis archippus*) (Taxon ID: 68065): 2013 mutual misidentifications"
        in result["summary"]
    )


def test_tool_get_species_phenology(mock_client) -> None:
    mock_client.get_species_phenology.return_value = {
        "taxon_id": 48662,
        "months": {"1": "5", "7": "1000", "8": "1200"},
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("get_species_phenology")

    result = tool_func.fn(taxon_id=48662, place_id=14)
    assert "Aug | 1,200 |" in result["summary"]
    assert "(Peak)" in result["summary"]


def test_tool_get_controlled_terms(mock_client) -> None:
    mock_client.get_controlled_terms.return_value = [
        {
            "id": 12,
            "label": "Flowers and Fruits",
            "values": [{"id": 13, "label": "Flowers"}, {"id": 14, "label": "Fruits"}],
        }
    ]
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("get_controlled_terms")

    result = tool_func.fn(taxon_id=47126)
    assert "Flowers and Fruits (Term ID: 12)" in result["summary"]
    assert "Flowers (Value ID: 13)" in result["summary"]


def test_tool_view_observation_photos(mock_client) -> None:
    mock_client.get_observation.return_value = {
        "id": 55,
        "species_guess": "Peregrine Falcon",
        "photos": [
            {
                "url": "https://static.inaturalist.org/photos/101/square.jpg",
                "attribution": "(c) Birder",
            }
        ],
    }
    mock_client.fetch_image_bytes.return_value = (b"image-bytes", "image/jpeg")
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("view_observation_photos")

    result = tool_func.fn(observation_id=55, max_photos=1)
    # Returns CallToolResult
    assert len(result.content) == 3
    assert result.content[1].type == "image"
    assert result.content[1].mime_type == "image/jpeg"


def test_tool_view_observation_photos_no_photos(mock_client) -> None:
    mock_client.get_observation.return_value = {
        "id": 66,
        "species_guess": "Cave Cricket",
        "photos": [],
    }
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("view_observation_photos")

    result = tool_func.fn(observation_id=66)
    assert len(result.content) == 1
    assert "has no photos attached" in result.content[0].text


def test_tool_view_observation_photos_partial_failures(mock_client) -> None:
    mock_client.get_observation.return_value = {
        "id": 77,
        "species_guess": "Tree Frog",
        "photos": [
            {"url": ""},  # empty url branch
            {"url": "https://static.inaturalist.org/photos/202/square.jpg"},  # error branch
        ],
    }
    mock_client.fetch_image_bytes.side_effect = RuntimeError("Failed to download")
    server = create_server(mock_client)
    tool_func = server._tool_manager.get_tool("view_observation_photos")

    result = tool_func.fn(observation_id=77)
    assert any("Failed image fetch" in b.text for b in result.content if hasattr(b, "text"))


def test_resources(mock_client) -> None:
    mock_client.get_taxon.return_value = {"id": 1, "name": "Plantae"}
    mock_client.get_observation.return_value = {"id": 10, "species_guess": "Oak"}
    mock_client.get_place.return_value = {"id": 20, "name": "Park"}
    mock_client.get_species_phenology.return_value = {"taxon_id": 1, "months": {}}
    mock_client.get_similar_species.return_value = {"total_results": 0, "similar_species": []}

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
        elif "phenology" in uri_template:
            content = template_obj.fn(taxon_id="1")
            parsed = json.loads(content)
            assert parsed["taxon_id"] == 1
        elif "lookalikes" in uri_template:
            content = template_obj.fn(taxon_id="1")
            parsed = json.loads(content)
            assert parsed["total_results"] == 0


def test_resource_errors(mock_client) -> None:
    server = create_server(mock_client)
    for uri_template, template_obj in server._resource_manager._templates.items():
        if "taxa" in uri_template:
            res = json.loads(template_obj.fn(taxon_id="invalid"))
            assert "error" in res
        elif "observations" in uri_template:
            res = json.loads(template_obj.fn(observation_id="invalid"))
            assert "error" in res
        elif "places" in uri_template:
            res = json.loads(template_obj.fn(place_id="invalid"))
            assert "error" in res
        elif "phenology" in uri_template:
            res = json.loads(template_obj.fn(taxon_id="invalid"))
            assert "error" in res
        elif "lookalikes" in uri_template:
            res = json.loads(template_obj.fn(taxon_id="invalid"))
            assert "error" in res


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

    compare = server._prompt_manager.get_prompt("lookalike_comparison")
    assert compare is not None
    msg2 = compare.fn(candidate_taxon_name="Monarch Butterfly")
    assert "Monarch Butterfly" in msg2

    survey = server._prompt_manager.get_prompt("biodiversity_survey")
    assert survey is not None
    msg3 = survey.fn(place_name="Yellowstone National Park", radius_km=25)
    assert "Yellowstone National Park" in msg3

    rare = server._prompt_manager.get_prompt("find_rare_species")
    assert rare is not None
    msg4 = rare.fn(region_or_coordinates="Everglades")
    assert "Everglades" in msg4
