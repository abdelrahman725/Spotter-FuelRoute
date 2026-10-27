"""
Driving route between two points, from a free routing API.

Code can work with either API provider:
1. ORS, OpenRouteService (https://openrouteservice.org).
Needs an API key.

2. OSRM, Open Source Routing Machine (https://project-osrm.org).
Public demo server, no key required.

each makes one HTTP request and returns the same Route;
the rest of the app doesn't care which provider is configured.
"""

import os
from dataclasses import dataclass
from typing import Literal

import requests
from rest_framework import status
from rest_framework.exceptions import APIException

from .constants import METERS_PER_MILE

ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{coords}"

# key acquired from https://account.heigit.org/signup
ORS_API_KEY = os.environ.get("ORS_API_KEY", "")

# Routing API to use:
# ors: truck routing, needs ORS_API_KEY
# osrm: public demo server, car routing, no key
ROUTING_PROVIDER: Literal["ors", "osrm"] = "ors"


class RoutingError(APIException):
    """
    The routing API failed or found no route.
    Raised inside a DRF view, DRF returns it as a 502 response: {"detail": "<message>"}.
    """
    status_code = status.HTTP_502_BAD_GATEWAY


# (lon, lat) points.
Coordinates = tuple[float, float]


@dataclass
class Route:
    distance_miles: float
    # Coordinates on the road path, ordered from start to end.
    coordinates: list[Coordinates]


def get_route(start: Coordinates, end: Coordinates) -> Route:
    """Return the driving route from start to end, both given as (lon, lat)."""

    if ROUTING_PROVIDER not in ["ors", "osrm"]:
        raise RoutingError(f"Unknown ROUTING_PROVIDER: {ROUTING_PROVIDER!r}")

    if ROUTING_PROVIDER == "ors":
        return ors_route(start, end)

    return osrm_route(start, end)


def ors_route(start: Coordinates, end: Coordinates) -> Route:
    if not ORS_API_KEY:
        raise RoutingError("ORS_API_KEY is not set.")

    response = requests.post(
        ORS_URL,
        headers={"Authorization": ORS_API_KEY},
        json={
            "coordinates": [list(start), list(end)],
            "instructions": False,
        },
        timeout=30,
    )
    data = json_or_raise(response)
    feature = data["features"][0]
    return to_route(
        meters=feature["properties"]["summary"]["distance"],
        coordinates_list=feature["geometry"]["coordinates"],
    )


def osrm_route(start: Coordinates, end: Coordinates) -> Route:
    coords = ";".join(f"{lon},{lat}" for lon, lat in (start, end))
    response = requests.get(
        OSRM_URL.format(coords=coords),
        params={"overview": "full", "geometries": "geojson"},
        timeout=30,
    )

    data = json_or_raise(response)
    if data.get("code") != "Ok":
        raise RoutingError(f"OSRM: {data.get('message', data.get('code'))}")

    route = data["routes"][0]
    return to_route(
        meters=route["distance"],
        coordinates_list=route["geometry"]["coordinates"],
    )


def json_or_raise(response):
    if not response.ok:
        raise RoutingError(f"{response.status_code}: {response.text[:300]}")
    return response.json()


def to_route(meters: float, coordinates_list: list[list[float]]) -> Route:
    return Route(
        distance_miles=meters / METERS_PER_MILE,
        coordinates=[(lon, lat) for lon, lat in coordinates_list],
    )
