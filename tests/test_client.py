from inaturalist_mcp.client import INaturalistClient


def test_rare_observations_prefers_low_confirmation_entries(monkeypatch) -> None:
    client = INaturalistClient()
    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params: {
            "results": [
                {"species_guess": "Species A", "observed_on": "2026-03-29", "photos": [1], "identifications_count": 5},
                {"species_guess": "Species B", "observed_on": "2026-03-29", "photos": [1], "identifications_count": 1},
            ]
        },
    )

    result = client.rare_observations_nearby(43.7, -79.4)

    assert result["observations"][0]["species_guess"] == "Species B"
