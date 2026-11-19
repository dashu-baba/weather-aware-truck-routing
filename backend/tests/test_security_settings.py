"""Throttle identity and CORS configuration."""

from unittest import mock

ORIGIN = "http://localhost:5173"


def test_spoofed_forwarded_for_does_not_bypass_the_throttle(api):
    with (
        mock.patch("planner.views.start_plan"),
        mock.patch("planner.views.plan_status", return_value={"status": "weather"}),
    ):
        codes = [
            api.post(
                "/api/plan",
                {
                    "origin": {"lat": 32.7767, "lon": -96.797},
                    "destination": {"lat": 32.7555, "lon": -97.3308},
                    "load_lb": 1000 + i,
                },
                format="json",
                HTTP_X_FORWARDED_FOR=f"10.0.0.{i}",
            ).status_code
            for i in range(8)
        ]

    assert codes[-1] == 429


def test_preflight_from_the_dev_frontend_is_allowed(api):
    response = api.options(
        "/api/plan",
        HTTP_ORIGIN=ORIGIN,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
    )

    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == ORIGIN


def test_unlisted_origin_gets_no_cors_headers(api):
    response = api.get("/api/health", HTTP_ORIGIN="https://evil.example")

    assert "Access-Control-Allow-Origin" not in response
