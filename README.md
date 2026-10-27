# FuelRoute - Django API

Given a start and end location (as lat, lon coordinates) inside the US, our API computes:
1. The route, a list of coordinates.


2. Fuel stops, a list of coordinates representing optimal (in terms of cost) stops along the route for our truck to fuel up from if needed.

3. Total cost, in USD, spent on fuel.

## Pre-processing of CSV file
Geocoding: One of the challenges were how to map each row to an actual location (lat, lon), so that we can later compute which stops are along the route.

In a real production setting, I believe the locations for 
those truckstops should be known and saved in advance, so our API should not really
bother computing this. That's why I used Claude (Opus 5.5) to do this step for me, with a good instructions and few-shot prompt. Claude added 2 new fileds to the csv file: lat, lon. For rows Claude couldn't gecode, values are empty.

### Coordinates realiability by Claude

| Rows | How the coordinates were found | Reliability |
| :--- | :--- | :--- |
| 3,806 | Store number matched in the brand's own store-locator data | Pinned to the station |
| 1,581 | Brand or name matched to a single nearby station | Pinned to the station |
| 65 | Agent found the station in the chain's official site list (Quarles, Kum & Go, etc.) | Pinned to the station |
| 350 | Weaker brand/name match | Probably right; worth checking |
| 1,024 | Several stations matched; the best-scoring one was used | May be a nearby station of the same brand |
| 303 | Only the highway exit could be located | Estimate, usually within about 1 km |
| 402 | Only the town could be located (city centre) | Rough estimate, a few km off |


## Approach
Our API calls 2 main functions:

### get_route()

**AI usage:** Partially written by Claude and I understand the code.

Call the free API provider and returns the driving route from
start to end as a list of coordinates.

The function works with both:
1. (default) https://openrouteservice.org
2. https://project-osrm.org

You can change `ROUTING_PROVIDER` in `routing.py` to test.

### compute_fuel_stops()

It calls 3 functions:

1.`find_stops_along_route()`

**AI usage:** Written by Claude.


Using `shapely` and `pyproj` libraries, it returns TruckStops that are 
at most 5 miles from the route, each with a `route_mile` attribute which indicates
the number of miles into the trip it is.

The result is ordered by that `route_mil` field.

2.`raise_if_gap_over_full_tank()`


**AI usage:** Written by Claude, and I understand the code.

Spot any distance of more than 500 miles that exists between any two stops,
and raise as the trip would be impossible. 500 is the max miles the truck can drive on a full tank. 


3.`compute_optimal_fuel_stops()`

**AI usage:** Partially written by Claude BUT I understand the algorithm.

Our main **Greedy** algorithm that computes the optimal (cost efficient)
truck stops to fuel up from.