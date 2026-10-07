"""Population exposure provider boundary and demo fallback."""

from dataclasses import dataclass, replace
from typing import Protocol, runtime_checkable

from shapely.geometry.base import BaseGeometry

from orbitguard.backend.schemas.events import EnvironmentalEvent


@dataclass(frozen=True)
class PopulationExposure:
    population_exposed: int
    population_density_estimate: float | None
    data_source: str
    data_quality: str

    def __post_init__(self) -> None:
        if self.population_exposed < 0:
            raise ValueError("population_exposed must be greater than or equal to 0.")
        if (
            self.population_density_estimate is not None
            and self.population_density_estimate < 0
        ):
            raise ValueError(
                "population_density_estimate must be greater than or equal to 0."
            )
        if not self.data_source or not self.data_quality:
            raise ValueError("Population source and quality are required.")


@runtime_checkable
class PopulationProvider(Protocol):
    def estimate_exposure(
        self, event: EnvironmentalEvent, hazard_geometry: BaseGeometry
    ) -> PopulationExposure:
        """Estimate population exposure for a WGS84 hazard geometry."""


class DemoPopulationProvider:
    """Stable local values used when real population data is unavailable."""

    def estimate_exposure(
        self, event: EnvironmentalEvent, hazard_geometry: BaseGeometry
    ) -> PopulationExposure:
        del hazard_geometry
        if event.event_type == "flood":
            return PopulationExposure(
                population_exposed=12_400,
                population_density_estimate=331,
                data_source="demo population data",
                data_quality="demo",
            )
        return PopulationExposure(
            population_exposed=2_600,
            population_density_estimate=110,
            data_source="demo population data",
            data_quality="demo",
        )


class PopulationExposureService:
    """Select a provider and degrade to clearly marked demo data on failure."""

    def __init__(
        self,
        provider: PopulationProvider | None = None,
        demo_provider: PopulationProvider | None = None,
        demo_mode: bool = True,
    ) -> None:
        self.provider = provider
        self.demo_provider = demo_provider or DemoPopulationProvider()
        self.demo_mode = demo_mode

    def estimate_exposure(
        self, event: EnvironmentalEvent, hazard_geometry: BaseGeometry
    ) -> PopulationExposure:
        if self.demo_mode or self.provider is None:
            return self.demo_provider.estimate_exposure(event, hazard_geometry)

        try:
            return self.provider.estimate_exposure(event, hazard_geometry)
        except Exception:
            fallback = self.demo_provider.estimate_exposure(event, hazard_geometry)
            return replace(
                fallback,
                data_source=f"{fallback.data_source} (provider unavailable)",
                data_quality="demo-fallback",
            )
