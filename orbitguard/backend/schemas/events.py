import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

EventType = Literal["flood", "deforestation"]
RiskLevel = Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]


class EnvironmentalEvent(BaseModel):
    """Normalized detector output accepted from FloodGuard and ForestGuard."""

    event_type: EventType
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    affected_area_km2: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    geometry: dict | None = None
    mask_path: str | None = None
    source: str = Field(default="unknown", min_length=1)
    acquisition_date: str | None = None
    change_percent: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_change_percent_for_deforestation(self) -> "EnvironmentalEvent":
        if self.event_type == "deforestation" and self.change_percent is None:
            raise ValueError("change_percent is required for deforestation events.")
        return self


class Location(BaseModel):
    latitude: float
    longitude: float


class Detection(BaseModel):
    affected_area_km2: float
    confidence: float
    source: str
    mask_path: str | None = None
    acquisition_date: str | None = None
    change_percent: float | None = None


class Impact(BaseModel):
    population_exposed: int = Field(ge=0)
    population_density_estimate: float | None = Field(default=None, ge=0)
    data_source: str
    infrastructure_data_source: str | None = None
    data_quality: str
    roads_affected_km: float = Field(ge=0)
    hospitals_nearby: int = Field(ge=0)
    buildings_affected: int = Field(ge=0)
    schools_nearby: int = Field(ge=0)


class Risk(BaseModel):
    score: int = Field(ge=0, le=100)
    level: RiskLevel


class Analysis(BaseModel):
    summary: str
    severity: RiskLevel
    priority_areas: list[str]
    recommended_actions: list[str]
    uncertainty: list[str]
    analysis_source: Literal["llm", "deterministic_fallback"] = (
        "deterministic_fallback"
    )

    @model_validator(mode="after")
    def reject_numeric_claims(self) -> "Analysis":
        prose = [
            self.summary,
            *self.priority_areas,
            *self.recommended_actions,
            *self.uncertainty,
        ]
        if any(re.search(r"\d", text) for text in prose):
            raise ValueError(
                "Analyst prose must not contain unverified numerical claims."
            )
        return self


class AnalysisResponse(BaseModel):
    incident_id: str
    event_type: EventType
    location: Location
    detection: Detection
    impact: Impact
    risk: Risk
    analysis: Analysis
    sources: list[str]
