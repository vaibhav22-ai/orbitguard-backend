from uuid import uuid4

from shapely.geometry.base import BaseGeometry

from orbitguard.backend.config import get_settings
from orbitguard.backend.geospatial.geometry import (
    buffer_geometry,
    create_point,
    geojson_to_geometry,
)
from orbitguard.backend.schemas.events import (
    AnalysisResponse,
    Detection,
    EnvironmentalEvent,
    Impact,
    Location,
    Risk,
)
from orbitguard.backend.services.infrastructure import (
    InfrastructureExposureService,
    InfrastructureProvider,
    OverpassInfrastructureProvider,
)
from orbitguard.backend.services.analyst import (
    AnalystService,
    OpenAIAnalystProvider,
    build_incident_evidence,
)
from orbitguard.backend.services.population import (
    PopulationExposureService,
    PopulationProvider,
)
from orbitguard.backend.services.risk_engine import (
    calculate_deforestation_risk,
    calculate_flood_risk,
)


def build_hazard_geometry(
    event: EnvironmentalEvent, buffer_radius_meters: float = 1000
) -> BaseGeometry:
    """Use supplied GeoJSON when valid, otherwise build a metric point buffer."""
    if event.geometry is not None:
        try:
            return geojson_to_geometry(event.geometry)
        except (TypeError, KeyError, ValueError):
            # Detector geometry is optional; a point buffer keeps demo analysis usable.
            pass
    return buffer_geometry(
        create_point(event.latitude, event.longitude), buffer_radius_meters
    )


def calculate_impact(
    event: EnvironmentalEvent,
    *,
    demo_mode: bool = True,
    population_provider: PopulationProvider | None = None,
    infrastructure_provider: InfrastructureProvider | None = None,
    overpass_url: str = "https://overpass-api.de/api/interpreter",
    overpass_timeout_seconds: float = 15,
    buffer_radius_meters: float = 1000,
) -> Impact:
    """Build an impact response from isolated population and infrastructure providers."""
    hazard_geometry = build_hazard_geometry(event, buffer_radius_meters)
    population = PopulationExposureService(
        provider=population_provider,
        demo_mode=demo_mode,
    ).estimate_exposure(event, hazard_geometry)

    if infrastructure_provider is None and not demo_mode:
        infrastructure_provider = OverpassInfrastructureProvider(
            overpass_url=overpass_url,
            timeout_seconds=overpass_timeout_seconds,
        )
    infrastructure = InfrastructureExposureService(
        provider=infrastructure_provider,
        demo_mode=demo_mode,
    ).estimate_exposure(event, hazard_geometry)

    data_quality = (
        population.data_quality
        if population.data_quality == infrastructure.data_quality
        else (
            f"population:{population.data_quality};"
            f" infrastructure:{infrastructure.data_quality}"
        )
    )
    return Impact(
        population_exposed=population.population_exposed,
        population_density_estimate=population.population_density_estimate,
        data_source=population.data_source,
        infrastructure_data_source=infrastructure.data_source,
        data_quality=data_quality,
        roads_affected_km=infrastructure.roads_affected_km,
        hospitals_nearby=infrastructure.hospitals_nearby,
        buildings_affected=infrastructure.buildings_affected,
        schools_nearby=infrastructure.schools_nearby,
    )


def _calculate_risk(event: EnvironmentalEvent, impact: Impact) -> Risk:
    calculation = (
        calculate_flood_risk(event, impact)
        if event.event_type == "flood"
        else calculate_deforestation_risk(event, impact)
    )
    return Risk(score=calculation.score, level=calculation.level)


def analyze_event(event: EnvironmentalEvent) -> AnalysisResponse:
    settings = get_settings()
    impact = calculate_impact(
        event,
        demo_mode=settings.demo_mode,
        overpass_url=settings.overpass_url,
        overpass_timeout_seconds=settings.overpass_timeout_seconds,
        buffer_radius_meters=settings.hazard_buffer_meters,
    )
    risk = _calculate_risk(event, impact)
    evidence = build_incident_evidence(event, impact, risk)
    analyst_provider = None
    if not settings.demo_mode and settings.openai_api_key:
        analyst_provider = OpenAIAnalystProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            timeout_seconds=settings.openai_timeout_seconds,
        )
    analysis = AnalystService(provider=analyst_provider).analyze(evidence).analysis

    return AnalysisResponse(
        incident_id=f"inc-{uuid4().hex[:12]}",
        event_type=event.event_type,
        location=Location(latitude=event.latitude, longitude=event.longitude),
        detection=Detection(
            affected_area_km2=event.affected_area_km2,
            confidence=event.confidence,
            source=event.source,
            mask_path=event.mask_path,
            acquisition_date=event.acquisition_date,
            change_percent=event.change_percent,
        ),
        impact=impact,
        risk=risk,
        analysis=analysis,
        sources=[
            event.source,
            impact.data_source,
            impact.infrastructure_data_source or "unknown infrastructure source",
        ],
    )
