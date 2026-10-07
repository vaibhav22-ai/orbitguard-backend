"""Structured evidence passed to the AI analyst."""

from pydantic import BaseModel, Field

from orbitguard.backend.schemas.events import EventType, RiskLevel


class IncidentEvidence(BaseModel):
    """Authoritative facts available to an analyst; the model must not alter them."""

    event_type: EventType
    affected_area_km2: float = Field(gt=0)
    model_confidence: float = Field(ge=0, le=1)
    population_exposed: int = Field(ge=0)
    population_density_estimate: float | None = Field(default=None, ge=0)
    roads_affected_km: float = Field(ge=0)
    hospitals_nearby: int = Field(ge=0)
    buildings_affected: int = Field(ge=0)
    schools_nearby: int = Field(ge=0)
    risk_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    data_quality: str = Field(min_length=1)
    sources: list[str] = Field(min_length=1)
