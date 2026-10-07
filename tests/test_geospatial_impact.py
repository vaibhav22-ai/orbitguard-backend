import httpx
import pytest
from shapely.geometry import box

from orbitguard.backend.geospatial.geometry import (
    buffer_geometry,
    calculate_area_km2,
    calculate_length_km,
    create_bounding_box,
    create_point,
    distance_meters,
    geometry_to_geojson,
    geojson_to_geometry,
    intersect_geometries,
    validate_coordinates,
)
from orbitguard.backend.mock.data import DEMO_FLOOD_EVENT
from orbitguard.backend.schemas.events import EnvironmentalEvent
from orbitguard.backend.services.impact_analysis import calculate_impact
from orbitguard.backend.services.infrastructure import (
    InfrastructureExposure,
    InfrastructureExposureService,
    OverpassInfrastructureProvider,
    build_overpass_query,
    parse_overpass_response,
)
from orbitguard.backend.services.population import (
    PopulationExposure,
    PopulationExposureService,
)


def test_geometry_uses_wgs84_coordinates_and_validates_bounds():
    point = create_point(12.9716, 77.5946)
    assert point.x == pytest.approx(77.5946)
    assert point.y == pytest.approx(12.9716)
    assert validate_coordinates(12.9716, 77.5946) == (12.9716, 77.5946)

    with pytest.raises(ValueError):
        create_point(91, 77)
    with pytest.raises(ValueError):
        create_point(12, 181)


def test_metric_buffer_area_and_intersection_are_crs_safe():
    point = create_point(12.9716, 77.5946)
    hazard = buffer_geometry(point, 1_000)
    inner = buffer_geometry(point, 500)
    intersection = intersect_geometries(hazard, inner)

    assert 2.5 < calculate_area_km2(hazard) < 4.0
    assert intersection is not None
    assert calculate_area_km2(intersection) == pytest.approx(
        calculate_area_km2(inner), rel=0.05
    )


def test_bounding_box_and_geodesic_distance():
    bbox = create_bounding_box(12.9716, 77.5946, 1_000)
    assert bbox.south < 12.9716 < bbox.north
    assert bbox.west < 77.5946 < bbox.east
    assert len(bbox.as_overpass().split(",")) == 4

    distance = distance_meters(create_point(0, 0), create_point(1, 0))
    assert distance == pytest.approx(111_195, rel=0.01)


def test_geojson_round_trip():
    original = box(77.59, 12.97, 77.60, 12.98)
    restored = geojson_to_geometry(geometry_to_geojson(original))
    assert restored.equals(original)


def test_overpass_parser_counts_only_features_intersecting_hazard():
    center = create_point(12.9716, 77.5946)
    hazard = buffer_geometry(center, 1_000)
    payload = {
        "elements": [
            {
                "type": "way",
                "id": 1,
                "tags": {"highway": "primary"},
                "geometry": [
                    {"lat": 12.9716, "lon": 77.5896},
                    {"lat": 12.9716, "lon": 77.5996},
                ],
            },
            {
                "type": "node",
                "id": 2,
                "tags": {"amenity": "hospital"},
                "lat": 12.9716,
                "lon": 77.5946,
            },
            {
                "type": "way",
                "id": 3,
                "tags": {"building": "yes"},
                "geometry": [
                    {"lat": 12.9708, "lon": 77.5938},
                    {"lat": 12.9708, "lon": 77.5942},
                    {"lat": 12.9712, "lon": 77.5942},
                    {"lat": 12.9708, "lon": 77.5938},
                ],
            },
            {
                "type": "node",
                "id": 4,
                "tags": {"amenity": "school"},
                "lat": 12.9716,
                "lon": 77.5946,
            },
            {
                "type": "node",
                "id": 5,
                "tags": {"amenity": "hospital"},
                "lat": 13.1,
                "lon": 77.8,
            },
        ]
    }

    result = parse_overpass_response(payload, hazard)

    assert result.roads_affected_km > 0
    assert result.hospitals_nearby == 1
    assert result.buildings_affected == 1
    assert result.schools_nearby == 1
    assert calculate_length_km(hazard) > 0


def test_overpass_provider_uses_one_cached_request_and_parses_response():
    center = create_point(12.9716, 77.5946)
    hazard = buffer_geometry(center, 1_000)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST"
        return httpx.Response(200, json={"elements": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = OverpassInfrastructureProvider(
            "https://example.test/overpass", client=client
        )
        provider.estimate_exposure(
            EnvironmentalEvent(**DEMO_FLOOD_EVENT), hazard
        )
        provider.estimate_exposure(
            EnvironmentalEvent(**DEMO_FLOOD_EVENT), hazard
        )

    assert calls == 1


def test_services_fall_back_to_demo_when_provider_fails():
    class BrokenPopulationProvider:
        def estimate_exposure(self, event, hazard_geometry):
            raise RuntimeError("population service unavailable")

    class BrokenInfrastructureProvider:
        def estimate_exposure(self, event, hazard_geometry):
            raise RuntimeError("OSM unavailable")

    event = EnvironmentalEvent(**DEMO_FLOOD_EVENT)
    hazard = buffer_geometry(create_point(event.latitude, event.longitude), 1_000)

    population = PopulationExposureService(
        provider=BrokenPopulationProvider(), demo_mode=False
    ).estimate_exposure(event, hazard)
    infrastructure = InfrastructureExposureService(
        provider=BrokenInfrastructureProvider(), demo_mode=False
    ).estimate_exposure(event, hazard)

    assert population.data_quality == "demo-fallback"
    assert infrastructure.data_quality == "demo-fallback"
    assert "unavailable" in population.data_source
    assert "OSM unavailable" in infrastructure.data_source


def test_calculate_impact_uses_injected_local_providers():
    class LocalPopulationProvider:
        def estimate_exposure(self, event, hazard_geometry):
            return PopulationExposure(42, 12.5, "local population", "local")

    class LocalInfrastructureProvider:
        def estimate_exposure(self, event, hazard_geometry):
            return InfrastructureExposure(
                roads_affected_km=1.2,
                hospitals_nearby=1,
                buildings_affected=3,
                schools_nearby=1,
                data_source="local OSM fixture",
                data_quality="local",
            )

    event = EnvironmentalEvent(**DEMO_FLOOD_EVENT)
    impact = calculate_impact(
        event,
        demo_mode=False,
        population_provider=LocalPopulationProvider(),
        infrastructure_provider=LocalInfrastructureProvider(),
    )

    assert impact.population_exposed == 42
    assert impact.infrastructure_data_source == "local OSM fixture"
    assert impact.roads_affected_km == 1.2
    assert impact.data_quality == "local"


def test_overpass_query_contains_supported_feature_filters():
    bbox = create_bounding_box(12.9716, 77.5946, 1_000)
    query = build_overpass_query(bbox)
    assert 'way["highway"]' in query
    assert 'amenity"="hospital' in query
    assert 'way["building"]' in query
    assert 'amenity"="school' in query
