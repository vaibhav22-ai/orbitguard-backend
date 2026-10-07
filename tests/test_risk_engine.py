import pytest
from pydantic import ValidationError

from orbitguard.backend.mock.data import DEMO_FLOOD_EVENT
from orbitguard.backend.schemas.events import EnvironmentalEvent, Impact
from orbitguard.backend.services.risk_engine import (
    DeforestationRiskWeights,
    FloodRiskWeights,
    InfrastructureWeights,
    NormalizationScale,
    RiskEngineConfig,
    calculate_deforestation_risk,
    calculate_flood_risk,
    classify_risk,
    normalize_population_exposure,
)


def _impact(**overrides) -> Impact:
    values = {
        "population_exposed": 12_400,
        "population_density_estimate": 331,
        "data_source": "demo population data",
        "data_quality": "demo",
        "roads_affected_km": 18.3,
        "hospitals_nearby": 2,
        "buildings_affected": 1_840,
        "schools_nearby": 7,
    }
    values.update(overrides)
    return Impact(**values)


def _event(event_type: str = "flood", **overrides) -> EnvironmentalEvent:
    values = {**DEMO_FLOOD_EVENT, "event_type": event_type}
    if event_type == "deforestation":
        values.update(change_percent=18.2)
    values.update(overrides)
    return EnvironmentalEvent(**values)


@pytest.mark.parametrize(
    ("score", "level"),
    [
        (0, "LOW"),
        (39, "LOW"),
        (40, "MODERATE"),
        (59, "MODERATE"),
        (60, "HIGH"),
        (79, "HIGH"),
        (80, "CRITICAL"),
        (100, "CRITICAL"),
    ],
)
def test_classify_risk_boundaries(score, level):
    assert classify_risk(score) == level


def test_classify_risk_rejects_out_of_range_scores():
    with pytest.raises(ValueError):
        classify_risk(-1)
    with pytest.raises(ValueError):
        classify_risk(101)


def test_population_normalization_uses_configured_thresholds():
    assert normalize_population_exposure(0) == 0
    assert normalize_population_exposure(1_000) == 20
    assert normalize_population_exposure(5_000) == 40
    assert normalize_population_exposure(50_000) == 100
    assert normalize_population_exposure(100_000) == 100


def test_normalization_rejects_negative_raw_values():
    with pytest.raises(ValueError):
        normalize_population_exposure(-1)


def test_weight_configuration_requires_sum_of_one():
    with pytest.raises(ValueError):
        FloodRiskWeights(hazard_severity=0.5)
    with pytest.raises(ValueError):
        InfrastructureWeights(roads=2.0, hospitals=-1.0)


def test_normalization_scale_validates_shape():
    with pytest.raises(ValueError):
        NormalizationScale(points=((0, 0), (10, 90)))
    with pytest.raises(ValueError):
        NormalizationScale(points=((0, 0), (0, 100)))


def test_flood_risk_uses_only_normalized_components():
    config = RiskEngineConfig(
        flood_weights=FloodRiskWeights(
            hazard_severity=1.0,
            population_exposure=0.0,
            infrastructure_exposure=0.0,
            model_confidence=0.0,
        )
    )
    result = calculate_flood_risk(
        _event(affected_area_km2=50, confidence=0),
        _impact(
            population_exposed=1_000_000,
            roads_affected_km=1_000,
            hospitals_nearby=1_000,
            buildings_affected=1_000_000,
            schools_nearby=1_000,
        ),
        config,
    )

    assert result.score == 100
    assert result.level == "CRITICAL"
    assert all(0 <= value <= 100 for value in result.normalized_components.values())


def test_deforestation_risk_uses_change_magnitude_weight():
    config = RiskEngineConfig(
        deforestation_weights=DeforestationRiskWeights(
            forest_loss=0.0,
            change_magnitude=1.0,
            population_exposure=0.0,
            infrastructure_exposure=0.0,
            model_confidence=0.0,
        )
    )
    result = calculate_deforestation_risk(
        _event("deforestation", change_percent=50, confidence=0),
        _impact(
            population_exposed=0,
            roads_affected_km=0,
            hospitals_nearby=0,
            buildings_affected=0,
            schools_nearby=0,
        ),
        config,
    )

    assert result.score == 100
    assert result.level == "CRITICAL"


def test_risk_functions_validate_event_type_and_required_forest_change():
    with pytest.raises(ValueError):
        calculate_flood_risk(_event("deforestation"), _impact())

    with pytest.raises(ValidationError):
        EnvironmentalEvent(**{**DEMO_FLOOD_EVENT, "event_type": "deforestation"})

