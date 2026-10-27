from django.db import models


class TruckStop(models.Model):
    """A US truck stop from fuel-prices.csv, placed on the map at its city."""
    opis_id = models.IntegerField()
    name = models.CharField(max_length=255)
    # e.g. "I-44, EXIT 283 & US-69"
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    # USD per gallon
    price = models.FloatField()
    # Centre of the stop's city; empty if the city couldn't be found.
    lon = models.FloatField(null=True)
    lat = models.FloatField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gt=0), name='price_positive'),
        ]

    def __str__(self):
        return f'{self.name}, {self.address} ({self.city}, {self.state})'
