"""Infrastructure exposure providers, including an isolated Overpass client."""

from dataclasses import dataclass, replace
from typing import Any, Protocol, runtime_checkable

import httpx
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

from orbitguard.backend.geospatial.geometry import (
    bounding_box_for_geometry,
    calculate_length_km,
    intersect_geometries,
)
from orbitguard.backend.schemas.events import EnvironmentalEvent


@dataclass(frozen=True)
class InfrastructureExposure:
    roads_affected_km: float
    hospitals_nearby: int
    buildings_affected: int
    schools_nearby: int
    data_source: str
    data_quality: str

    def __post_init__(self) -> None:
        if self.roads_affected_km < 0:
            raise ValueError("roads_affected_km must be greater than or equal to 0.")
        for name, value in (
            ("hospitals_nearby", self.hospitals_nearby),
            ("buildings_affected", self.buildings_affected),
            ("schools_nearby", self.schools_nearby),
        ):
            if value < 0:
                raise ValueError(f"{name} must be greater than or equal to 0.")
        if not self.data_source or not self.data_quality:
            raise ValueError("Infrastructure source and quality are required.")


@runtime_checkable
class InfrastructureProvider(Protocol):
    def estimate_exposure(
        self, event: EnvironmentalEvent, hazard_geometry: BaseGeometry
    ) -> InfrastructureExposure:
        """Estimate infrastructure exposure for a WGS84 hazard geometry."""


class DemoInfrastructureProvider:
    def estimate_exposure(
        self, event: EnvironmentalEvent, hazard_geometry: BaseGeometry
    ) -> InfrastructureExposure:
        del hazard_geometry
        if event.event_type == "flood":
            return InfrastructureExposure(
                roads_affected_km=18.3,
                hospitals_nearby=2,
                buildings_affected=1_840,
                schools_nearby=7,
                data_source="demo infrastructure data",
                data_quality="demo",
            )
        return InfrastructureExposure(
            roads_affected_km=4.8,
            hospitals_nearby=0,
            buildings_affected=120,
            schools_nearby=1,
            data_source="demo infrastructure data",
            data_quality="demo",
        )


def build_overpass_query(bounding_box) -> str:
    """Build one bounded Overpass request for all supported feature types."""
    bbox = bounding_box.as_overpass()
    return f"""[out:json][timeout:25];
(
  way["highway"]({bbox});
  node["amenity"="hospital"]({bbox});
  way["amenity"="hospital"]({bbox});
  way["building"]({bbox});
  node["amenity"="school"]({bbox});
  way["amenity"="school"]({bbox});
);
out geom;"""


def _element_geometry(element: dict[str, Any]) -> BaseGeometry | None:
    element_type = element.get("type")
    if element_type == "node":
        if "lat" not in element or "lon" not in element:
            return None
        return Point(float(element["lon"]), float(element["lat"]))

    coordinates = [
        (float(point["lon"]), float(point["lat"]))
        for point in element.get("geometry", [])
        if "lon" in point and "lat" in point
    ]
    if len(coordinates) < 2:
        center = element.get("center")
        if center and "lon" in center and "lat" in center:
            return Point(float(center["lon"]), float(center["lat"]))
        return None

    if coordinates[0] == coordinates[-1] and len(coordinates) >= 4:
        return Polygon(coordinates)
    return LineString(coordinates)


def parse_overpass_response(
    payload: dict[str, Any], hazard_geometry: BaseGeometry
) -> InfrastructureExposure:
    """Convert a local Overpass-shaped JSON payload into infrastructure metrics."""
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Overpass response must contain an elements list.")

    roads_affected_km = 0.0
    hospitals_nearby = 0
    buildings_affected = 0
    schools_nearby = 0

    for element in payload["elements"]:
        tags = element.get("tags", {})
        geometry = _element_geometry(element)
        if geometry is None or not geometry.intersects(hazard_geometry):
            continue

        if "highway" in tags and geometry.geom_type in {"LineString", "MultiLineString"}:
            intersection = intersect_geometries(hazard_geometry, geometry)
            if intersection is not None:
                roads_affected_km += calculate_length_km(intersection)
        elif tags.get("amenity") == "hospital":
            hospitals_nearby += 1
        elif "building" in tags:
            buildings_affected += 1
        elif tags.get("amenity") == "school":
            schools_nearby += 1

    return InfrastructureExposure(
        roads_affected_km=round(roads_affected_km, 3),
        hospitals_nearby=hospitals_nearby,
        buildings_affected=buildings_affected,
        schools_nearby=schools_nearby,
        data_source="OpenStreetMap Overpass",
        data_quality="live",
    )


class OverpassInfrastructureProvider:
    """One-request OSM provider with injectable HTTP client and query caching."""

    def __init__(
        self,
        overpass_url: str,
        timeout_seconds: float = 15,
        client: httpx.Client | None = None,
        cache_enabled: bool = True,
    ) -> None:
        if not overpass_url:
            raise ValueError("overpass_url is required.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0.")
        self.overpass_url = overpass_url
        self.timeout_seconds = timeout_seconds
        self.client = client
        self.cache_enabled = cache_enabled
        self._cache: dict[str, InfrastructureExposure] = {}

    def estimate_exposure(
        self, event: EnvironmentalEvent, hazard_geometry: BaseGeometry
    ) -> InfrastructureExposure:
        del event
        bounding_box = bounding_box_for_geometry(hazard_geometry)
        query = build_overpass_query(bounding_box)
        if self.cache_enabled and query in self._cache:
            return self._cache[query]

        if self.client is None:
            with httpx.Client() as client:
                response = client.post(
                    self.overpass_url,
                    data={"data": query},
                    timeout=self.timeout_seconds,
                )
        else:
            response = self.client.post(
                self.overpass_url,
                data={"data": query},
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        result = parse_overpass_response(response.json(), hazard_geometry)
        if self.cache_enabled:
            self._cache[query] = result
        return result


class InfrastructureExposureService:
    """Select OSM in live mode and preserve a usable demo fallback on failure."""

    def __init__(
        self,
        provider: InfrastructureProvider | None = None,
        demo_provider: InfrastructureProvider | None = None,
        demo_mode: bool = True,
    ) -> None:
        self.provider = provider
        self.demo_provider = demo_provider or DemoInfrastructureProvider()
        self.demo_mode = demo_mode

    def estimate_exposure(
        self, event: EnvironmentalEvent, hazard_geometry: BaseGeometry
    ) -> InfrastructureExposure:
        if self.demo_mode or self.provider is None:
            return self.demo_provider.estimate_exposure(event, hazard_geometry)

        try:
            return self.provider.estimate_exposure(event, hazard_geometry)
        except Exception:
            fallback = self.demo_provider.estimate_exposure(event, hazard_geometry)
            return replace(
                fallback,
                data_source=f"{fallback.data_source} (OSM unavailable)",
                data_quality="demo-fallback",
            )
