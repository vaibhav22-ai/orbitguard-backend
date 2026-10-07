"""Reusable geospatial utilities for ORBITGUARD impact analysis."""

from orbitguard.backend.geospatial.geometry import (
    BoundingBox,
    bounding_box_for_geometry,
    calculate_area_km2,
    calculate_length_km,
    create_bounding_box,
    create_point,
    distance_meters,
    geometry_to_geojson,
    geojson_to_geometry,
    intersect_geometries,
    buffer_geometry,
    validate_coordinates,
)

__all__ = [
    "BoundingBox",
    "bounding_box_for_geometry",
    "buffer_geometry",
    "calculate_area_km2",
    "calculate_length_km",
    "create_bounding_box",
    "create_point",
    "distance_meters",
    "geometry_to_geojson",
    "geojson_to_geometry",
    "intersect_geometries",
    "validate_coordinates",
]
