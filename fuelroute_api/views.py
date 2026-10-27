from dataclasses import asdict

from rest_framework.decorators import api_view
from rest_framework.response import Response

from .fuel_stops import compute_fuel_stops
from .routing import get_route
from .serializers import RequestSerializer


@api_view(["GET"])
def fuel_route(request) -> Response:
    """Return a map of a route from the start_loc to end_loc
    along with optimal Truckstop/s to fuel up along the route.

    start_loc and end_loc are "lat, lon" query parameters, e.g.
    /api/fuel-route/?start_loc=41.8781,-87.6298&end_loc=34.0522,-118.2437
    """
    serializer = RequestSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)

    # The serializer switches both coordinates to
    # (lon, lat) tuples, the order our logic uses.
    route = get_route(
        serializer.validated_data["start_loc"],
        serializer.validated_data["end_loc"],
    )

    fuel_stops = compute_fuel_stops(route)

    # Total fuel cost in USD, from the gallons and prices in the response.
    total_fuel_cost = sum(stop.gallons * stop.price for stop in fuel_stops)

    return Response(
        {
            "route": asdict(route),
            "fuel_stops": [asdict(stop) for stop in fuel_stops],
            "total_fuel_cost": total_fuel_cost,
        }
    )
