from django.urls import path

from .views import GeocodeView, HealthView, PlanHeatmapView, PlanStatusView, PlanView

urlpatterns = [
    path("api/health", HealthView.as_view()),
    path("api/geocode", GeocodeView.as_view()),
    path("api/plan", PlanView.as_view()),
    path("api/plan/<uuid:plan_id>", PlanStatusView.as_view()),
    path("api/plan/<uuid:plan_id>/heatmap", PlanHeatmapView.as_view()),
]
