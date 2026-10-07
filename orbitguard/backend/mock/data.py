from orbitguard.backend.schemas.events import (
    Analysis,
    AnalysisResponse,
    Detection,
    Impact,
    Location,
    Risk,
)


DEMO_FLOOD_EVENT = {
    "event_type": "flood",
    "latitude": 12.9716,
    "longitude": 77.5946,
    "affected_area_km2": 37.4,
    "confidence": 0.91,
    "geometry": None,
    "mask_path": "outputs/flood_mask.png",
    "source": "Sentinel-1",
    "acquisition_date": "2026-10-07",
}

DEMO_FOREST_EVENT = {
    "event_type": "deforestation",
    "latitude": 12.9716,
    "longitude": 77.5946,
    "affected_area_km2": 23.7,
    "confidence": 0.88,
    "change_percent": 18.2,
    "geometry": None,
    "mask_path": "outputs/forest_loss_mask.png",
    "source": "Sentinel-2",
    "acquisition_date": "2026-10-07",
}

DEMO_INCIDENTS = {
    "demo-flood-bengaluru": AnalysisResponse(
        incident_id="demo-flood-bengaluru",
        event_type="flood",
        location=Location(latitude=12.9716, longitude=77.5946),
        detection=Detection(
            affected_area_km2=37.4,
            confidence=0.91,
            source="Sentinel-1",
            mask_path="outputs/flood_mask.png",
            acquisition_date="2026-10-07",
        ),
        impact=Impact(
            population_exposed=12400,
            population_density_estimate=331,
            data_source="demo population data",
            infrastructure_data_source="demo infrastructure data",
            data_quality="demo",
            roads_affected_km=18.3,
            hospitals_nearby=2,
            buildings_affected=1840,
            schools_nearby=7,
        ),
        risk=Risk(score=76, level="HIGH"),
        analysis=Analysis(
            summary="Demo flood incident affecting a populated urban area.",
            severity="HIGH",
            priority_areas=[
                "Validate flood extent with latest satellite pass",
                "Review exposed road corridors and nearby hospitals",
            ],
            recommended_actions=[
                "Coordinate local field verification",
                "Prepare traffic diversion and shelter support if confirmed",
            ],
            uncertainty=[
                "Population and infrastructure values are demo estimates",
                "No live external datasets were queried",
            ],
        ),
        sources=["Sentinel-1", "demo population data", "demo infrastructure data"],
    )
}
