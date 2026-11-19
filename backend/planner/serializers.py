from datetime import datetime, timedelta, timezone

from rest_framework import serializers


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField(required=False, allow_blank=True, default="")
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=60_000)

    def validate_departure(self, value):
        now = datetime.now(timezone.utc)
        if not (now - timedelta(hours=1) <= value <= now + timedelta(days=7)):
            raise serializers.ValidationError("Pick a departure within the next 7 days.")
        return value

    def validate(self, data):
        origin, destination = data["origin"], data["destination"]
        same_spot = (round(origin["lat"], 4), round(origin["lon"], 4)) == (
            round(destination["lat"], 4),
            round(destination["lon"], 4),
        )
        if same_spot:
            raise serializers.ValidationError("Origin and destination must be different.")
        return data
