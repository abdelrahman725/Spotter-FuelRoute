import csv
from typing import TypedDict

from django.conf import settings
from django.db import transaction

from .models import TruckStop


class TruckStopRow(TypedDict):
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    price: float
    lon: float | None
    lat: float | None


def read_and_clean_fuel_prices() -> list[TruckStopRow]:
    """
    Step 1: read fuel-prices.csv rows into a list of dicts.
    We skip Canadian rows and exact duplicate rows.
    """

    def _clean(text: str) -> str:
        # Trim and collapse repeated spaces if any.
        return "".join(text.split())

    CANADIAN_PROVINCES = {
        "AB",
        "BC",
        "MB",
        "NB",
        "NL",
        "NS",
        "NT",
        "NU",
        "ON",
        "PE",
        "QC",
        "SK",
        "YT",
    }
    rows: list[TruckStopRow] = []
    rows_seen = set()

    with open(settings.BASE_DIR / "fuel-prices.csv", newline="") as file:
        reader = csv.DictReader(file)
        for csv_row in reader:
            state = _clean(csv_row["State"])
            if state.upper() in CANADIAN_PROVINCES:
                continue

            row: TruckStopRow = {
                "opis_id": int(csv_row["OPIS Truckstop ID"]),
                "name": _clean(csv_row["Truckstop Name"]),
                "address": _clean(csv_row["Address"]),
                "city": _clean(csv_row["City"]),
                "state": state,
                "price": float(csv_row["Retail Price"]),
                "lon": _clean(csv_row["lon"]) or None,
                "lat": _clean(csv_row["lat"]) or None,
            }

            row_values = tuple(row.values())
            if row_values in rows_seen:
                continue

            rows_seen.add(row_values)
            rows.append(row)
    return rows


def import_fuel_data() -> None:
    """Clean fuel-prices.csv and load its rows into db"""
    rows = read_and_clean_fuel_prices()

    # One transaction: if anything fails, the old rows stay.
    with transaction.atomic():
        TruckStop.objects.all().delete()
        TruckStop.objects.bulk_create([TruckStop(**row) for row in rows])
