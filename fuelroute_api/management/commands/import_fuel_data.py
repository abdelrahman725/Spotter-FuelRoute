from django.core.management.base import BaseCommand

from fuelroute_api.importer import import_fuel_data
from fuelroute_api.models import TruckStop


class Command(BaseCommand):
    help = "Load the US truck stops from fuel-prices.csv into the database."

    def handle(self, *args, **options):
        import_fuel_data()

        total = TruckStop.objects.count()
        without_location = TruckStop.objects.filter(lon__isnull=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {total} US truck stops ({without_location} without a location)."
            )
        )
