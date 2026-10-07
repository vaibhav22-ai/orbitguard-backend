from fastapi import APIRouter, HTTPException

from orbitguard.backend.mock.data import DEMO_INCIDENTS
from orbitguard.backend.schemas.events import AnalysisResponse, EnvironmentalEvent
from orbitguard.backend.services.incident_store import IncidentStore
from orbitguard.backend.services.impact_analysis import analyze_event

router = APIRouter(prefix="/api/v1", tags=["analysis"])
incident_store = IncidentStore(initial=DEMO_INCIDENTS)


def _analyze_and_store(event: EnvironmentalEvent) -> AnalysisResponse:
    return incident_store.save(analyze_event(event))


@router.post("/analyze", response_model=AnalysisResponse)
def analyze_environmental_event(event: EnvironmentalEvent) -> AnalysisResponse:
    """Analyze a normalized event produced by a detection model."""
    return _analyze_and_store(event)


@router.post("/flood/analyze", response_model=AnalysisResponse)
def analyze_flood_event(event: EnvironmentalEvent) -> AnalysisResponse:
    if event.event_type != "flood":
        raise HTTPException(
            status_code=400,
            detail="Flood endpoint only accepts event_type='flood'.",
        )
    return _analyze_and_store(event)


@router.post("/forest/analyze", response_model=AnalysisResponse)
def analyze_forest_event(event: EnvironmentalEvent) -> AnalysisResponse:
    if event.event_type != "deforestation":
        raise HTTPException(
            status_code=400,
            detail="Forest endpoint only accepts event_type='deforestation'.",
        )
    return _analyze_and_store(event)


@router.get("/incidents/{incident_id}", response_model=AnalysisResponse)
def get_incident(incident_id: str) -> AnalysisResponse:
    incident = incident_store.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return incident
