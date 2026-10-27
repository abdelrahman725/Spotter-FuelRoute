from rest_framework import serializers


def parse_coordinates(value: str) -> tuple[float, float]:
    """
    Parse a "lat,lon" string (the order Google Maps uses) into a (lon, lat)
    tuple, the order used everywhere else in the code.
    e.g. "41.8781,-87.6298" -> (-87.6298, 41.8781)
    """
    try:
        lat, lon = (float(part) for part in value.split(","))
    except ValueError:
        raise serializers.ValidationError(
            'Expected "lat,lon", e.g. "41.8781,-87.6298".'
        )

    # Rough bounding box of the contiguous USA (where the truck stops are).
    if not (-125 <= lon <= -66 and 24 <= lat <= 50):
        raise serializers.ValidationError("Location must be within the contiguous USA.")

    return lon, lat


class RequestSerializer(serializers.Serializer):
    # The API takes "lat,lon" (like Google Maps), and
    # validation converts it to (lon, lat)
    start_loc = serializers.CharField(
        help_text='Start point as "lat,lon", e.g. "41.8781,-87.6298".'
    )
    end_loc = serializers.CharField(
        help_text='End point as "lat,lon", e.g. "34.0522,-118.2437".'
    )

    def validate_start_loc(self, value: str) -> tuple[float, float]:
        return parse_coordinates(value)

    def validate_end_loc(self, value: str) -> tuple[float, float]:
        return parse_coordinates(value)
