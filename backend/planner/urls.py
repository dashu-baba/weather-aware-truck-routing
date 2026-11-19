from django.urls import path

from .views import GeocodeView, HealthView, PlanView

urlpatterns = [
    path("api/health", HealthView.as_view()),
    path("api/geocode", GeocodeView.as_view()),
    path("api/plan", PlanView.as_view()),
]
