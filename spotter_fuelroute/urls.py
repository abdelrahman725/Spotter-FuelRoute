from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='fuel-route')),
    path('admin/', admin.site.urls),
    path('api/', include('fuelroute_api.urls')),
]
