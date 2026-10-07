"""CRS-safe geometry helpers.

Public geometries use WGS84 coordinates in (longitude, latitude) order, as
required by GeoJSON and Shapely. Metric operations are performed in a local
UTM projection selected from the geometry's representative point.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Any

from pyproj import CRS, Geod, Transformer
from shapely.geometry import Point, Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

WGS84 = CRS.from_epsg(4326)
WGS84_GEOD = Geod(ellps="WGS84")


def _finite(value: float | int, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number.")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    """Validate and return a latitude/longitude pair in decimal degrees."""
    latitude = _finite(latitude, "latitude")
    longitude = _finite(longitude, "longitude")
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90 degrees.")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180 degrees.")
    return latitude, longitude


def create_point(latitude: float, longitude: float) -> Point:
    """Create a WGS84 point; Shapely stores it as (longitude, latitude)."""
    latitude, longitude = validate_coordinates(latitude, longitude)
    return Point(longitude, latitude)


@dataclass(frozen=True)
class BoundingBox:
    """A WGS84 bounding box in south, west, north, east form."""

    south: float
    west: float
    north: float
    east: float

    def __post_init__(self) -> None:
        validate_coordinates(self.south, self.west)
        validate_coordinates(self.north, self.east)
        if self.south >= self.north:
            raise ValueError("Bounding box south must be less than north.")
        if self.west >= self.east:
            raise ValueError("Bounding box west must be less than east.")

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.south, self.west, self.north, self.east

    def as_overpass(self) -> str:
        return ",".join(str(value) for value in self.as_tuple())

    def to_geometry(self) -> Polygon:
        return box(self.west, self.south, self.east, self.north)


def _local_metric_crs(geometry: BaseGeometry) -> CRS:
    if geometry.is_empty:
        raise ValueError("Cannot select a projected CRS for an empty geometry.")
    reference = geometry.representative_point()
    longitude = reference.x
    latitude = reference.y
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        raise ValueError("Geometry must contain WGS84 longitude/latitude coordinates.")

    # UTM is accurate for normal latitudes; an azimuthal equidistant CRS avoids
    # invalid UTM zones close to the poles.
    if abs(latitude) > 83:
        return CRS.from_proj4(
            f"+proj=aeqd +lat_0={latitude} +lon_0={longitude} "
            "+datum=WGS84 +units=m +no_defs"
        )

    zone = int((longitude + 180) // 6) + 1
    epsg = 32600 + zone if latitude >= 0 else 32700 + zone
    return CRS.from_epsg(epsg)


def _projected(geometry: BaseGeometry) -> tuple[BaseGeometry, Transformer, Transformer]:
    metric_crs = _local_metric_crs(geometry)
    to_metric = Transformer.from_crs(WGS84, metric_crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(metric_crs, WGS84, always_xy=True)
    return transform(to_metric.transform, geometry), to_metric, to_wgs84


def buffer_geometry(geometry: BaseGeometry, radius_meters: float) -> BaseGeometry:
    """Buffer a WGS84 geometry by meters using a local projected CRS."""
    radius_meters = _finite(radius_meters, "radius_meters")
    if radius_meters <= 0:
        raise ValueError("radius_meters must be greater than 0.")
    if geometry.is_empty:
        raise ValueError("Cannot buffer an empty geometry.")
    projected, _, to_wgs84 = _projected(geometry)
    return transform(to_wgs84.transform, projected.buffer(radius_meters))


def create_bounding_box(
    latitude: float, longitude: float, radius_meters: float
) -> BoundingBox:
    """Create a WGS84 bounding box around a coordinate and radius."""
    buffered = buffer_geometry(create_point(latitude, longitude), radius_meters)
    west, south, east, north = buffered.bounds
    return BoundingBox(
        south=max(-90.0, south),
        west=max(-180.0, west),
        north=min(90.0, north),
        east=min(180.0, east),
    )


def bounding_box_for_geometry(geometry: BaseGeometry) -> BoundingBox:
    if geometry.is_empty:
        raise ValueError("Cannot create a bounding box for an empty geometry.")
    west, south, east, north = geometry.bounds
    return BoundingBox(south=south, west=west, north=north, east=east)


def calculate_area_km2(geometry: BaseGeometry) -> float:
    """Calculate area in km2 after projecting from WGS84 into meters."""
    if geometry.is_empty:
        return 0.0
    projected, _, _ = _projected(geometry)
    return projected.area / 1_000_000


def calculate_length_km(geometry: BaseGeometry) -> float:
    """Calculate line or collection length in km in a local metric CRS."""
    if geometry.is_empty:
        return 0.0
    projected, _, _ = _projected(geometry)
    return projected.length / 1_000


def intersect_geometries(
    first: BaseGeometry, second: BaseGeometry
) -> BaseGeometry | None:
    """Return the non-empty WGS84 intersection of two geometries."""
    intersection = first.intersection(second)
    return None if intersection.is_empty else intersection


def distance_meters(first: Point, second: Point) -> float:
    """Calculate geodesic distance between two WGS84 points."""
    if not isinstance(first, Point) or not isinstance(second, Point):
        raise ValueError("distance_meters requires two Shapely Point objects.")
    if first.is_empty or second.is_empty:
        raise ValueError("Cannot calculate distance from an empty point.")
    _, _, distance = WGS84_GEOD.inv(first.x, first.y, second.x, second.y)
    return abs(distance)


def geometry_to_geojson(geometry: BaseGeometry) -> dict[str, Any]:
    return dict(mapping(geometry))


def geojson_to_geometry(value: dict[str, Any]) -> BaseGeometry:
    if not isinstance(value, dict) or "type" not in value:
        raise ValueError("GeoJSON geometry must be an object with a type.")
    geometry = shape(value)
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("GeoJSON geometry must be valid and non-empty.")
    return geometry
