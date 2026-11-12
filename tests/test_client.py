from __future__ import annotations

import httpx
import pytest

from inaturalist_mcp.client import (
    INaturalistAPIError,
    INaturalistClient,
    INaturalistError,
    INaturalistNotFoundError,
    INaturalistRateLimitError,
)


def test_client_init_and_headers(monkeypatch) -> None:
    # Test default
    client = INaturalistClient()
    assert client.base_url == "https://api.inaturalist.org/v1"
    assert "inaturalist-mcp/" in client.headers["User-Agent"]
    assert "Authorization" not in client.headers

    # Test custom token
    client_auth = INaturalistClient(api_token="test-token-123")
    assert client_auth.headers["Authorization"] == "Bearer test-token-123"

    # Test token from environment
    monkeypatch.setenv("INATURALIST_API_TOKEN", "env-token-xyz")
    client_env = INaturalistClient()
    assert client_env.headers["Authorization"] == "Bearer env-token-xyz"

    monkeypatch.delenv("INATURALIST_API_TOKEN")
    monkeypatch.setenv("INAT_API_TOKEN", "short-token-abc")
    client_short = INaturalistClient()
    assert client_short.headers["Authorization"] == "Bearer short-token-abc"


def test_request_success(monkeypatch) -> None:
    client = INaturalistClient()

    def mock_get(url, params=None, headers=None, timeout=None):
        return httpx.Response(
            status_code=200,
            json={"total_results": 1, "results": [{"id": 100, "species_guess": "Robin"}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", mock_get)
    result = client._request("/observations")
    assert result["total_results"] == 1
    assert result["results"][0]["id"] == 100


def test_request_not_found(monkeypatch) -> None:
    client = INaturalistClient()

    def mock_get(url, params=None, headers=None, timeout=None):
        return httpx.Response(status_code=404, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", mock_get)
    with pytest.raises(INaturalistNotFoundError) as exc_info:
        client._request("/taxa/99999999")
    assert exc_info.value.status_code == 404


def test_request_rate_limited_and_retries(monkeypatch) -> None:
    client = INaturalistClient(max_retries=2)
    attempts = 0

    def mock_get(url, params=None, headers=None, timeout=None):
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            status_code=429,
            text="Too Many Requests",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", mock_get)
    monkeypatch.setattr("time.sleep", lambda s: None)

    with pytest.raises(INaturalistRateLimitError) as exc_info:
        client._request("/observations", retry_delay=0.01)
    assert exc_info.value.status_code == 429
    assert attempts == 2


def test_request_server_error_and_eventual_success(monkeypatch) -> None:
    client = INaturalistClient(max_retries=3)
    call_count = 0

    def mock_get(url, params=None, headers=None, timeout=None):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return httpx.Response(
                status_code=502,
                text="Bad Gateway",
                request=httpx.Request("GET", url),
            )
        return httpx.Response(
            status_code=200,
            json={"total_results": 1, "results": [{"id": 1}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", mock_get)
    monkeypatch.setattr("time.sleep", lambda s: None)

    data = client._request("/observations", retry_delay=0.01)
    assert data["total_results"] == 1
    assert call_count == 2


def test_request_http_status_error(monkeypatch) -> None:
    client = INaturalistClient(max_retries=1)

    def mock_get(url, params=None, headers=None, timeout=None):
        req = httpx.Request("GET", url)
        resp = httpx.Response(status_code=400, text="Bad Request", request=req)
        raise httpx.HTTPStatusError("Bad Request", request=req, response=resp)

    monkeypatch.setattr(httpx, "get", mock_get)
    with pytest.raises(INaturalistAPIError) as exc_info:
        client._request("/observations")
    assert exc_info.value.status_code == 400


def test_request_invalid_json(monkeypatch) -> None:
    client = INaturalistClient(max_retries=1)

    def mock_get(url, params=None, headers=None, timeout=None):
        return httpx.Response(
            status_code=200,
            text="invalid json",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", mock_get)
    with pytest.raises(INaturalistError, match="Failed to decode JSON"):
        client._request("/observations")


def test_request_non_dict_json(monkeypatch) -> None:
    client = INaturalistClient(max_retries=1)

    def mock_get(url, params=None, headers=None, timeout=None):
        return httpx.Response(
            status_code=200,
            json=["not", "a", "dict"],
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", mock_get)
    with pytest.raises(INaturalistError, match="Unexpected iNaturalist response shape"):
        client._request("/observations")


def test_request_network_timeout(monkeypatch) -> None:
    client = INaturalistClient(max_retries=2)

    def mock_get(url, params=None, headers=None, timeout=None):
        raise httpx.ConnectTimeout("Connection timed out", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", mock_get)
    monkeypatch.setattr("time.sleep", lambda s: None)

    with pytest.raises(INaturalistError, match="Failed to connect to iNaturalist API"):
        client._request("/observations", retry_delay=0.01)


def test_observations_nearby(monkeypatch) -> None:
    client = INaturalistClient()
    recorded_params = {}

    def mock_request(path, params=None, retry_delay=1.0):
        nonlocal recorded_params
        recorded_params = params
        return {"total_results": 5, "results": [{"id": 10}, {"id": 11}]}

    monkeypatch.setattr(client, "_request", mock_request)

    res = client.observations_nearby(43.7, -79.4, radius_km=10, limit=2, photos_only=True)
    assert res["total_results"] == 5
    assert len(res["observations"]) == 2
    assert recorded_params["lat"] == 43.7
    assert recorded_params["lng"] == -79.4
    assert recorded_params["radius"] == 10
    assert recorded_params["per_page"] == 2
    assert recorded_params["photos"] is True


def test_taxon_observations_nearby(monkeypatch) -> None:
    client = INaturalistClient()
    recorded_params = {}

    def mock_request(path, params=None, retry_delay=1.0):
        nonlocal recorded_params
        recorded_params = params
        return {"total_results": 1, "results": [{"id": 20, "species_guess": "Danaus plexippus"}]}

    monkeypatch.setattr(client, "_request", mock_request)

    res = client.taxon_observations_nearby("Danaus plexippus", 40.7, -74.0, radius_km=15, limit=5)
    assert res["total_results"] == 1
    assert recorded_params["q"] == "Danaus plexippus"
    assert recorded_params["lat"] == 40.7
    assert "photos" not in recorded_params


def test_rare_observations_nearby(monkeypatch) -> None:
    client = INaturalistClient()

    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params: {
            "results": [
                {
                    "id": 1,
                    "species_guess": None,
                    "taxon": {"name": "Taxon Name Fallback"},
                    "observed_on": "2026-03-29",
                    "photos": [1, 2],
                    "identifications_count": 8,
                    "location": "43.7,-79.4",
                    "uri": "https://inaturalist.org/1",
                },
                {
                    "id": 2,
                    "species_guess": "Rare Orchid",
                    "observed_on": "2026-03-28",
                    "photos": [1],
                    "identifications_count": 1,
                    "location": "43.8,-79.5",
                    "uri": "https://inaturalist.org/2",
                },
            ]
        },
    )

    result = client.rare_observations_nearby(43.7, -79.4, limit=2, taxon_query="Orchid")
    assert result["total_results"] == 2
    assert len(result["observations"]) == 2
    assert result["observations"][0]["id"] == 2
    assert result["observations"][0]["species_guess"] == "Rare Orchid"
    assert result["observations"][1]["species_guess"] == "Taxon Name Fallback"


def test_taxon_photo_evidence_nearby(monkeypatch) -> None:
    client = INaturalistClient()

    def mock_taxon_obs(query, lat, lon, radius_km=25, limit=25, photos_only=False):
        assert photos_only is True
        assert query == "Canis lupus"
        return {"total_results": 1, "observations": [{"id": 50}]}

    monkeypatch.setattr(client, "taxon_observations_nearby", mock_taxon_obs)
    res = client.taxon_photo_evidence_nearby("Canis lupus", 45.0, -75.0)
    assert res["total_results"] == 1


def test_place_taxon_activity(monkeypatch) -> None:
    client = INaturalistClient()

    def mock_taxon_obs(query, lat, lon, radius_km=25, limit=25, photos_only=False):
        assert query == "Aves"
        return {"total_results": 3, "observations": [{"id": 1}, {"id": 2}, {"id": 3}]}

    monkeypatch.setattr(client, "taxon_observations_nearby", mock_taxon_obs)
    res = client.place_taxon_activity(40.0, -70.0, taxon_query="Aves")
    assert res["total_results"] == 3


def test_search_species(monkeypatch) -> None:
    client = INaturalistClient()
    recorded_params = {}

    def mock_request(path, params=None, retry_delay=1.0):
        nonlocal recorded_params
        recorded_params = params
        return {
            "total_results": 2,
            "results": [
                {"id": 48662, "name": "Danaus plexippus", "preferred_common_name": "Monarch"},
                {"id": 48663, "name": "Danaus", "preferred_common_name": "Tigers and Monarchs"},
            ],
        }

    monkeypatch.setattr(client, "_request", mock_request)
    res = client.search_species("Monarch", rank="species", iconic_taxa="Insecta", limit=2)
    assert res["total_results"] == 2
    assert len(res["taxa"]) == 2
    assert recorded_params["q"] == "Monarch"
    assert recorded_params["rank"] == "species"
    assert recorded_params["iconic_taxa"] == "Insecta"
    assert recorded_params["per_page"] == 2

    # Without optional params
    client.search_species("Monarch")
    assert "rank" not in recorded_params
    assert "iconic_taxa" not in recorded_params


def test_get_taxon_and_not_found(monkeypatch) -> None:
    client = INaturalistClient()

    # Success
    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params=None, retry_delay=1.0: {
            "results": [{"id": 48662, "name": "Danaus plexippus"}]
        },
    )
    taxon = client.get_taxon(48662)
    assert taxon["id"] == 48662

    # Not found when results list is empty
    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params=None, retry_delay=1.0: {"results": []},
    )
    with pytest.raises(INaturalistNotFoundError):
        client.get_taxon(99999999)


def test_get_observation_and_not_found(monkeypatch) -> None:
    client = INaturalistClient()

    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params=None, retry_delay=1.0: {
            "results": [{"id": 12345, "species_guess": "Blue Jay"}]
        },
    )
    obs = client.get_observation(12345)
    assert obs["id"] == 12345

    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params=None, retry_delay=1.0: {"results": []},
    )
    with pytest.raises(INaturalistNotFoundError):
        client.get_observation(99999999)


def test_search_places(monkeypatch) -> None:
    client = INaturalistClient()

    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params=None, retry_delay=1.0: {
            "total_results": 1,
            "results": [{"id": 129274, "name": "Central Park"}],
        },
    )
    places = client.search_places("Central Park", limit=5)
    assert places["total_results"] == 1
    assert places["places"][0]["id"] == 129274


def test_get_place_and_not_found(monkeypatch) -> None:
    client = INaturalistClient()

    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params=None, retry_delay=1.0: {
            "results": [{"id": 129274, "name": "Central Park"}]
        },
    )
    place = client.get_place(129274)
    assert place["id"] == 129274

    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params=None, retry_delay=1.0: {"results": []},
    )
    with pytest.raises(INaturalistNotFoundError):
        client.get_place(99999999)


def test_species_counts(monkeypatch) -> None:
    client = INaturalistClient()
    recorded_params = {}

    def mock_request(path, params=None, retry_delay=1.0):
        nonlocal recorded_params
        recorded_params = params
        return {
            "total_results": 10,
            "results": [{"count": 42, "taxon": {"id": 10, "name": "Quercus alba"}}],
        }

    monkeypatch.setattr(client, "_request", mock_request)
    res = client.species_counts(
        lat=40.0, lon=-73.0, radius_km=10, place_id=5, taxon_id=20, limit=15
    )
    assert res["total_results"] == 10
    assert recorded_params["lat"] == 40.0
    assert recorded_params["lng"] == -73.0
    assert recorded_params["radius"] == 10
    assert recorded_params["place_id"] == 5
    assert recorded_params["taxon_id"] == 20
    assert recorded_params["per_page"] == 15

    # Test without coordinates
    client.species_counts(place_id=12)
    assert "lat" not in recorded_params
    assert recorded_params["place_id"] == 12


def test_search_projects(monkeypatch) -> None:
    client = INaturalistClient()

    monkeypatch.setattr(
        client,
        "_request",
        lambda path, params=None, retry_delay=1.0: {
            "total_results": 1,
            "results": [{"id": 12073, "title": "City Nature Challenge"}],
        },
    )
    projects = client.search_projects("City Nature Challenge", limit=5)
    assert projects["total_results"] == 1
    assert projects["projects"][0]["id"] == 12073


def test_user_observations(monkeypatch) -> None:
    client = INaturalistClient()
    recorded_params = {}

    def mock_request(path, params=None, retry_delay=1.0):
        nonlocal recorded_params
        recorded_params = params
        return {
            "total_results": 2,
            "results": [{"id": 101}, {"id": 102}],
        }

    monkeypatch.setattr(client, "_request", mock_request)
    res = client.user_observations("thesven", limit=10, photos_only=True)
    assert res["total_results"] == 2
    assert recorded_params["user_login"] == "thesven"
    assert recorded_params["per_page"] == 10
    assert recorded_params["photos"] is True

    # Test photos_only=False
    client.user_observations("thesven", limit=10, photos_only=False)
    assert "photos" not in recorded_params
