"""Explainable ORBITGUARD MVP risk scoring.

The scoring functions only combine normalized 0-100 components. Raw impact
values are converted by the normalization helpers before weighting.
"""

from dataclasses import dataclass
from math import isclose, isfinite
from typing import Literal, Mapping

from orbitguard.backend.schemas.events import EnvironmentalEvent, Impact

RiskLevel = Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]


def _validate_number(value: float | int, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    numeric_value = float(value)
    if not isfinite(numeric_value):
        raise ValueError(f"{name} must be a finite number.")
    return numeric_value


def _validate_non_negative(value: float | int, name: str) -> float:
    numeric_value = _validate_number(value, name)
    if numeric_value < 0:
        raise ValueError(f"{name} must be greater than or equal to 0.")
    return numeric_value


@dataclass(frozen=True)
class NormalizationScale:
    """Piecewise-linear mapping from a raw metric to a 0-100 score."""

    points: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError("A normalization scale requires at least two points.")

        previous_raw = None
        previous_normalized = None
        for raw_value, normalized_value in self.points:
            raw_value = _validate_non_negative(raw_value, "normalization raw value")
            normalized_value = _validate_number(
                normalized_value, "normalization score"
            )
            if not 0 <= normalized_value <= 100:
                raise ValueError("Normalization scores must be between 0 and 100.")
            if previous_raw is not None and raw_value <= previous_raw:
                raise ValueError("Normalization raw values must be strictly increasing.")
            if (
                previous_normalized is not None
                and normalized_value <= previous_normalized
            ):
                raise ValueError(
                    "Normalization scores must be strictly increasing."
                )
            previous_raw = raw_value
            previous_normalized = normalized_value

        if self.points[0] != (0, 0):
            raise ValueError("Normalization scales must start at (0, 0).")
        if self.points[-1][1] != 100:
            raise ValueError("Normalization scales must end at a score of 100.")

    def normalize(self, value: float | int) -> float:
        numeric_value = _validate_non_negative(value, "raw metric")

        if numeric_value >= self.points[-1][0]:
            return 100.0

        for (lower_raw, lower_score), (upper_raw, upper_score) in zip(
            self.points, self.points[1:]
        ):
            if numeric_value <= upper_raw:
                fraction = (numeric_value - lower_raw) / (upper_raw - lower_raw)
                return lower_score + fraction * (upper_score - lower_score)

        return 100.0


def _validate_weights(weights: Mapping[str, float]) -> None:
    for name, weight in weights.items():
        numeric_weight = _validate_number(weight, f"weight '{name}'")
        if not 0 <= numeric_weight <= 1:
            raise ValueError(f"weight '{name}' must be between 0 and 1.")

    if not isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
        raise ValueError("Risk weights must sum to 1.0.")


@dataclass(frozen=True)
class FloodRiskWeights:
    hazard_severity: float = 0.30
    population_exposure: float = 0.30
    infrastructure_exposure: float = 0.20
    model_confidence: float = 0.20

    def __post_init__(self) -> None:
        _validate_weights(self.as_mapping())

    def as_mapping(self) -> dict[str, float]:
        return {
            "hazard_severity": self.hazard_severity,
            "population_exposure": self.population_exposure,
            "infrastructure_exposure": self.infrastructure_exposure,
            "model_confidence": self.model_confidence,
        }


@dataclass(frozen=True)
class DeforestationRiskWeights:
    forest_loss: float = 0.35
    change_magnitude: float = 0.25
    population_exposure: float = 0.20
    infrastructure_exposure: float = 0.10
    model_confidence: float = 0.10

    def __post_init__(self) -> None:
        _validate_weights(self.as_mapping())

    def as_mapping(self) -> dict[str, float]:
        return {
            "forest_loss": self.forest_loss,
            "change_magnitude": self.change_magnitude,
            "population_exposure": self.population_exposure,
            "infrastructure_exposure": self.infrastructure_exposure,
            "model_confidence": self.model_confidence,
        }


@dataclass(frozen=True)
class InfrastructureWeights:
    roads: float = 0.35
    hospitals: float = 0.30
    buildings: float = 0.25
    schools: float = 0.10

    def __post_init__(self) -> None:
        _validate_weights(self.as_mapping())

    def as_mapping(self) -> dict[str, float]:
        return {
            "roads": self.roads,
            "hospitals": self.hospitals,
            "buildings": self.buildings,
            "schools": self.schools,
        }


DEFAULT_AREA_SCALE = NormalizationScale(
    points=((0, 0), (1, 20), (5, 40), (10, 60), (25, 80), (50, 100))
)
DEFAULT_POPULATION_SCALE = NormalizationScale(
    points=((0, 0), (1_000, 20), (5_000, 40), (10_000, 60), (25_000, 80), (50_000, 100))
)
DEFAULT_CHANGE_SCALE = NormalizationScale(
    points=((0, 0), (5, 20), (10, 40), (20, 60), (40, 80), (50, 100))
)
DEFAULT_ROADS_SCALE = NormalizationScale(
    points=((0, 0), (1, 20), (5, 40), (10, 60), (25, 80), (50, 100))
)
DEFAULT_HOSPITALS_SCALE = NormalizationScale(
    points=((0, 0), (1, 40), (2, 70), (5, 100))
)
DEFAULT_BUILDINGS_SCALE = NormalizationScale(
    points=((0, 0), (100, 20), (500, 40), (1_000, 60), (2_500, 80), (5_000, 100))
)
DEFAULT_SCHOOLS_SCALE = NormalizationScale(
    points=((0, 0), (1, 30), (3, 60), (6, 85), (10, 100))
)


@dataclass(frozen=True)
class RiskEngineConfig:
    """Centralized weights and normalization thresholds for the MVP."""

    flood_weights: FloodRiskWeights = FloodRiskWeights()
    deforestation_weights: DeforestationRiskWeights = DeforestationRiskWeights()
    infrastructure_weights: InfrastructureWeights = InfrastructureWeights()
    area_scale: NormalizationScale = DEFAULT_AREA_SCALE
    population_scale: NormalizationScale = DEFAULT_POPULATION_SCALE
    change_scale: NormalizationScale = DEFAULT_CHANGE_SCALE
    roads_scale: NormalizationScale = DEFAULT_ROADS_SCALE
    hospitals_scale: NormalizationScale = DEFAULT_HOSPITALS_SCALE
    buildings_scale: NormalizationScale = DEFAULT_BUILDINGS_SCALE
    schools_scale: NormalizationScale = DEFAULT_SCHOOLS_SCALE


DEFAULT_RISK_ENGINE_CONFIG = RiskEngineConfig()


@dataclass(frozen=True)
class RiskCalculation:
    score: int
    level: RiskLevel
    normalized_components: dict[str, float]
    weights: dict[str, float]


def classify_risk(score: float | int) -> RiskLevel:
    """Classify a validated 0-100 MVP risk score."""
    numeric_score = _validate_number(score, "risk score")
    if not 0 <= numeric_score <= 100:
        raise ValueError("Risk score must be between 0 and 100.")

    if numeric_score >= 80:
        return "CRITICAL"
    if numeric_score >= 60:
        return "HIGH"
    if numeric_score >= 40:
        return "MODERATE"
    return "LOW"


def normalize_population_exposure(
    population_exposed: int | float,
    config: RiskEngineConfig = DEFAULT_RISK_ENGINE_CONFIG,
) -> float:
    return config.population_scale.normalize(population_exposed)


def normalize_model_confidence(confidence: float, name: str = "confidence") -> float:
    numeric_confidence = _validate_number(confidence, name)
    if not 0 <= numeric_confidence <= 1:
        raise ValueError(f"{name} must be between 0 and 1.")
    return numeric_confidence * 100


def normalize_infrastructure_exposure(
    impact: Impact,
    config: RiskEngineConfig = DEFAULT_RISK_ENGINE_CONFIG,
) -> float:
    normalized_components = {
        "roads": config.roads_scale.normalize(impact.roads_affected_km),
        "hospitals": config.hospitals_scale.normalize(impact.hospitals_nearby),
        "buildings": config.buildings_scale.normalize(impact.buildings_affected),
        "schools": config.schools_scale.normalize(impact.schools_nearby),
    }
    return _weighted_average(
        normalized_components, config.infrastructure_weights.as_mapping()
    )


def _weighted_average(
    normalized_components: Mapping[str, float], weights: Mapping[str, float]
) -> float:
    if set(normalized_components) != set(weights):
        raise ValueError("Normalized components and weights must have matching keys.")

    for name, component in normalized_components.items():
        numeric_component = _validate_number(component, f"component '{name}'")
        if not 0 <= numeric_component <= 100:
            raise ValueError(f"component '{name}' must be between 0 and 100.")

    _validate_weights(weights)
    return max(
        0.0,
        min(
            100.0,
            sum(normalized_components[name] * weights[name] for name in weights),
        ),
    )


def _build_calculation(
    normalized_components: dict[str, float], weights: Mapping[str, float]
) -> RiskCalculation:
    weighted_score = round(_weighted_average(normalized_components, weights))
    return RiskCalculation(
        score=weighted_score,
        level=classify_risk(weighted_score),
        normalized_components=normalized_components,
        weights=dict(weights),
    )


def calculate_flood_risk(
    event: EnvironmentalEvent,
    impact: Impact,
    config: RiskEngineConfig = DEFAULT_RISK_ENGINE_CONFIG,
) -> RiskCalculation:
    """Calculate the explainable ORBITGUARD MVP Risk Score for a flood."""
    if event.event_type != "flood":
        raise ValueError("calculate_flood_risk requires a flood event.")

    normalized_components = {
        "hazard_severity": config.area_scale.normalize(event.affected_area_km2),
        "population_exposure": normalize_population_exposure(
            impact.population_exposed, config
        ),
        "infrastructure_exposure": normalize_infrastructure_exposure(impact, config),
        "model_confidence": normalize_model_confidence(event.confidence),
    }
    return _build_calculation(normalized_components, config.flood_weights.as_mapping())


def calculate_deforestation_risk(
    event: EnvironmentalEvent,
    impact: Impact,
    config: RiskEngineConfig = DEFAULT_RISK_ENGINE_CONFIG,
) -> RiskCalculation:
    """Calculate the explainable ORBITGUARD MVP Risk Score for forest loss."""
    if event.event_type != "deforestation":
        raise ValueError("calculate_deforestation_risk requires a deforestation event.")
    if event.change_percent is None:
        raise ValueError("Deforestation risk requires change_percent.")

    normalized_components = {
        "forest_loss": config.area_scale.normalize(event.affected_area_km2),
        "change_magnitude": config.change_scale.normalize(event.change_percent),
        "population_exposure": normalize_population_exposure(
            impact.population_exposed, config
        ),
        "infrastructure_exposure": normalize_infrastructure_exposure(impact, config),
        "model_confidence": normalize_model_confidence(event.confidence),
    }
    return _build_calculation(
        normalized_components, config.deforestation_weights.as_mapping()
    )
