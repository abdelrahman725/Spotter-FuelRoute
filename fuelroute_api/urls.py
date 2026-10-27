from django.urls import path

from fuelroute_api.views import fuel_route

urlpatterns = [
    path("fuel-route/", fuel_route, name="fuel-route"),
]
