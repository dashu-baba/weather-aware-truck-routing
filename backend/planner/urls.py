from django.urls import path

from .views import GeocodeView, HealthView

urlpatterns = [
    path("api/health", HealthView.as_view()),
    path("api/geocode", GeocodeView.as_view()),
]
