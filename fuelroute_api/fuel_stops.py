from dataclasses import dataclass
from itertools import pairwise

import shapely
from pyproj import Transformer
from rest_framework import status
from rest_framework.exceptions import APIException

from .constants import (
    MAX_MILES_OFF_ROUTE,
    MAX_MILES_ON_FULL_TANK,
    METERS_PER_MILE,
    MILES_PER_GALLON,
)
from .models import TruckStop
from .routing import Route

# Step 1: a converter from (lon, lat) to a flat map of the US in metres.
# Shapely measures distances on a flat surface, but lon/lat are angles on a
# globe: a degree of longitude is ~52 miles in Texas but ~46 in North Dakota.
#   EPSG:4326 = lon/lat in degrees (GPS, our routing API and database).
#   EPSG:5070 = flat map of US in metres ("Conus Albers").
#   always_xy=True keeps the (lon, lat) order; EPSG:4326 officially puts lat first.

# Created once here, since building a Transformer is slow-ish.
TO_US_MAP_METRES = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
# The reverse converter: flat-map metres back to (lon, lat), used in step 4.
TO_LON_LAT = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)


class NoFuelPlanError(APIException):
    """
    The route has a stretch longer than a full tank with no truck stop on it.
    Raised inside a DRF view, DRF returns it as a 422 response: {"detail": "<message>"}.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY


def find_stops_along_route(route: Route) -> list[TruckStop]:
    """
    Return the truck stops at most MAX_MILES_OFF_ROUTE miles from the route,
    ordered along the route, each with a `route_mile` attribute: how many
    miles into the trip it is.

    Instead of hand written logic, we use shapely + pyproj
    """
    max_metres_off_route = MAX_MILES_OFF_ROUTE * METERS_PER_MILE

    # Step 2: the route as a shapely LineString on the flat map.
    # A LineString is a line through a list of points, joined in order by
    # straight segments - exactly what route.coordinates describes.
    # transform() takes all lons and all lats (two lists) and returns
    # all x's and all y's (two lists), so we split and re-pair the coordinates.
    # Basically, we turn the route from a list of GPS points
    # into a line that Shapely can measure distances along, in metres.
    route_lons, route_lats = zip(*route.coordinates)
    route_xs, route_ys = TO_US_MAP_METRES.transform(route_lons, route_lats)
    route_line = shapely.LineString(list(zip(route_xs, route_ys)))

    # Step 3: the line's bounding box, widened on every side.
    # .bounds is the smallest rectangle around the line: (min x, min y, max x, max y).
    # Widening it by max_metres_off_route guarantees that every point within
    # that distance of the line lies inside the rectangle.
    min_x, min_y, max_x, max_y = route_line.bounds
    box = (
        min_x - max_metres_off_route,
        min_y - max_metres_off_route,
        max_x + max_metres_off_route,
        max_y + max_metres_off_route,
    )

    # Step 4: the same rectangle in lon/lat, the units stored in the database.
    # A straight edge on the flat map is slightly curved in lon/lat, so
    # transform_bounds() samples points along each edge and returns the lon/lat
    # box that contains them all: (min lon, min lat, max lon, max lat).
    min_lon, min_lat, max_lon, max_lat = TO_LON_LAT.transform_bounds(*box)

    # Step 5: fetch only the stops inside that box.
    # Stops without a location (lon/lat None) never match a range filter.
    candidates = list(
        TruckStop.objects.filter(
            lon__range=(min_lon, max_lon),
            lat__range=(min_lat, max_lat),
        )
    )

    # Step 6: the candidate stops as shapely points on the flat map.
    # shapely.points() builds one Point per (x, y) pair, all at once,
    # as a numpy array of points.
    stop_xs, stop_ys = TO_US_MAP_METRES.transform(
        [stop.lon for stop in candidates],
        [stop.lat for stop in candidates],
    )
    stop_points = shapely.points(stop_xs, stop_ys)

    # Step 7: keep the stops within max_metres_off_route of the route line.
    # dwithin(a, b, distance) is True when a and b are at most `distance` apart.
    # Given one line and an array of points, it returns a numpy array with one
    # True/False per point; the distance is to the nearest part of the line,
    # including between route points.
    near_route = shapely.dwithin(route_line, stop_points, max_metres_off_route)

    # Step 8: how far into the trip each stop is, in miles.
    # line_locate_point() returns, per point, the distance in metres along the
    # line from its start to the line's closest point to that stop.
    # The flat-map line length differs slightly from the routing API's
    # distance, so we keep the fraction of the line and scale it by
    # route.distance_miles: the destination is then exactly at that mile.
    metres_along = shapely.line_locate_point(route_line, stop_points)
    miles_along = metres_along / route_line.length * route.distance_miles

    # Step 9: keep the stops near the route, ordered from start to end.
    stops = []
    for stop, is_near, mile in zip(candidates, near_route, miles_along):
        if is_near:
            stop.route_mile = float(mile)
            stops.append(stop)

    return sorted(stops, key=lambda stop: stop.route_mile)


def raise_if_gap_over_full_tank(stops: list[TruckStop], route: Route) -> None:
    """
    Raise NoFuelPlanError if the truck would have to drive more than
    MAX_MILES_ON_FULL_TANK miles without passing a stop.
    `stops` must be ordered by route_mile.
    """
    # The start (full tank) and the destination count as points too.
    miles = [0.0] + [stop.route_mile for stop in stops] + [route.distance_miles]

    for prev_mile, next_mile in pairwise(miles):
        if next_mile - prev_mile > MAX_MILES_ON_FULL_TANK:
            raise NoFuelPlanError(
                f"No truck stop between mile {prev_mile:.0f} and mile {next_mile:.0f} "
                f"of the route ({next_mile - prev_mile:.0f} miles); "
                f"a full tank lasts {MAX_MILES_ON_FULL_TANK} miles."
            )


def first_cheaper_mile_ahead(
    stops: list[TruckStop], i: int, route: Route
) -> float | None:
    """
    Return the route mile of the first point after stops[i], at most
    MAX_MILES_ON_FULL_TANK miles ahead, where fuel is cheaper than at stops[i].
    The destination counts as a $0 point: once in reach, it's always cheaper.
    Return None if there's no such point: stops[i] is the cheapest in reach.
    `stops` must be ordered by route_mile.
    """
    here = stops[i]
    reach = here.route_mile + MAX_MILES_ON_FULL_TANK

    for stop in stops[i + 1 :]:
        # Every stop after this one is out of reach too,
        # and so is the destination.
        if stop.route_mile > reach:
            return None

        # Strictly cheaper: an equal price gains nothing over buying here.
        if stop.price < here.price:
            return stop.route_mile

    # No cheaper stop before the destination.
    if route.distance_miles <= reach:
        return route.distance_miles
    return None


def compute_optimal_fuel_stops(stops: list[TruckStop], route: Route) -> list[TruckStop]:
    """
    Return the stops where the cheapest plan buys fuel, in route order,
    each with a `gallons` attribute: how many gallons it buys there.
    `stops` must be ordered by route_mile, with no gap over a full tank.
    """
    fuel_stops = []
    # Fuel in the tank, in miles of range. The trip starts with a full tank.
    fuel = MAX_MILES_ON_FULL_TANK
    previous_mile = 0.0

    for i, stop in enumerate(stops):
        # Drive from the previous point to this stop.
        # The tank never runs dry: each decision below leaves at least
        # enough fuel to reach the next stop, since no gap is over a full tank.
        fuel -= stop.route_mile - previous_mile
        previous_mile = stop.route_mile

        target_mile = first_cheaper_mile_ahead(stops, i, route)
        if target_mile is None:
            # This stop is the cheapest in reach, and the destination
            # is out of reach: fill up.
            buy = MAX_MILES_ON_FULL_TANK - fuel
        else:
            # Buy just enough to reach the cheaper point;
            # nothing if the tank already gets us there.
            buy = max(0.0, target_mile - stop.route_mile - fuel)

        # Ignore float rounding noise, e.g. arriving at a target with
        # -0.0000000000001 miles left.
        if buy > 1e-6:
            # Set on the model instance only, like route_mile.
            stop.gallons = buy / MILES_PER_GALLON
            fuel_stops.append(stop)
            fuel += buy

    return fuel_stops


@dataclass
class FuelStop:
    """A stop where the truck fuels up, as returned by the API."""

    city: str
    state: str
    address: str
    # "lat,lon", the same format the API takes start_loc and end_loc in.
    location: str
    price: float
    gallons: float


def compute_fuel_stops(route: Route) -> list[FuelStop]:
    # We assume we start the trip with a full tank,
    # so a trip distance of <= MAX_MILES_ON_FULL_TANK
    # needs no stops to fuel up.
    if route.distance_miles <= MAX_MILES_ON_FULL_TANK:
        return []

    stops_along_route = find_stops_along_route(route)
    raise_if_gap_over_full_tank(stops_along_route, route)

    fuel_stops = compute_optimal_fuel_stops(stops_along_route, route)
    return [
        FuelStop(
            city=stop.city,
            state=stop.state,
            address=stop.address,
            location=f"{stop.lat},{stop.lon}",
            price=stop.price,
            gallons=round(stop.gallons, 2),
        )
        for stop in fuel_stops
    ]
