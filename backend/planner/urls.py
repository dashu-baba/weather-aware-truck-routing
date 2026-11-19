from django.urls import path

from .views import GeocodeView, HealthView, PlanHeatmapView, PlanStatusView, PlanView, ReverseGeocodeView

urlpatterns = [
    path("api/health", HealthView.as_view()),
    path("api/geocode", GeocodeView.as_view()),
    path("api/reverse", ReverseGeocodeView.as_view()),
    path("api/plan", PlanView.as_view()),
    path("api/plan/<uuid:plan_id>", PlanStatusView.as_view()),
    path("api/plan/<uuid:plan_id>/heatmap", PlanHeatmapView.as_view()),
]
