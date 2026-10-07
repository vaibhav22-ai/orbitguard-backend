"""Small in-memory incident store for the MVP API lifecycle."""

from threading import Lock

from orbitguard.backend.schemas.events import AnalysisResponse


class IncidentStore:
    """Thread-safe process-local storage; replace with a database later."""

    def __init__(self, initial: dict[str, AnalysisResponse] | None = None) -> None:
        self._incidents = dict(initial or {})
        self._lock = Lock()

    def save(self, incident: AnalysisResponse) -> AnalysisResponse:
        with self._lock:
            self._incidents[incident.incident_id] = incident
        return incident

    def get(self, incident_id: str) -> AnalysisResponse | None:
        with self._lock:
            return self._incidents.get(incident_id)
