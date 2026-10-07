from fastapi.testclient import TestClient

from orbitguard.backend.main import app
from orbitguard.backend.mock.data import DEMO_FLOOD_EVENT, DEMO_FOREST_EVENT

client = TestClient(app)


def test_root_health_check():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["demo_mode"] is True


def test_analyze_mock_flood_event():
    response = client.post("/api/v1/analyze", json=DEMO_FLOOD_EVENT)

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "flood"
    assert payload["location"] == {
        "latitude": DEMO_FLOOD_EVENT["latitude"],
        "longitude": DEMO_FLOOD_EVENT["longitude"],
    }
    assert payload["detection"]["source"] == "Sentinel-1"
    assert payload["impact"]["data_quality"] == "demo"
    assert payload["impact"]["infrastructure_data_source"] == "demo infrastructure data"
    assert payload["analysis"]["analysis_source"] == "deterministic_fallback"
    assert payload["risk"]["level"] in {"LOW", "MODERATE", "HIGH", "CRITICAL"}


def test_flood_pipeline_can_retrieve_created_incident():
    response = client.post("/api/v1/flood/analyze", json=DEMO_FLOOD_EVENT)

    assert response.status_code == 200
    created = response.json()
    incident = client.get(f"/api/v1/incidents/{created['incident_id']}")

    assert incident.status_code == 200
    assert incident.json() == created
    assert created["event_type"] == "flood"
    assert created["impact"]["data_quality"] == "demo"
    assert created["analysis"]["analysis_source"] == "deterministic_fallback"


def test_forest_pipeline_returns_complete_demo_response():
    response = client.post("/api/v1/forest/analyze", json=DEMO_FOREST_EVENT)

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_type"] == "deforestation"
    assert payload["detection"]["change_percent"] == 18.2
    assert payload["impact"]["data_quality"] == "demo"
    assert payload["impact"]["infrastructure_data_source"] == "demo infrastructure data"
    assert payload["analysis"]["analysis_source"] == "deterministic_fallback"
    assert 0 <= payload["risk"]["score"] <= 100


def test_specialized_routes_reject_mismatched_event_types():
    flood_on_forest = client.post("/api/v1/forest/analyze", json=DEMO_FLOOD_EVENT)
    forest_on_flood = client.post("/api/v1/flood/analyze", json=DEMO_FOREST_EVENT)

    assert flood_on_forest.status_code == 400
    assert forest_on_flood.status_code == 400


def test_forest_route_validates_required_change_percent():
    invalid_event = {key: value for key, value in DEMO_FOREST_EVENT.items()}
    invalid_event.pop("change_percent")

    response = client.post("/api/v1/forest/analyze", json=invalid_event)

    assert response.status_code == 422


def test_incident_lookup_returns_404_for_unknown_id():
    response = client.get("/api/v1/incidents/does-not-exist")

    assert response.status_code == 404
