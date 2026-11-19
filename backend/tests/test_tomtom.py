import pytest

from routing import config, tomtom


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self.ok = status_code < 400
        self._body = body
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class FakeSession:
    """Stands in for requests.Session and records the call."""

    def __init__(self, response):
        self.response = response
        self.url = None
        self.params = None
        self.timeout = None

    def get(self, url, params=None, timeout=None):
        self.url, self.params, self.timeout = url, params, timeout
        return self.response


def result(label="Dallas, TX", lat=32.77, lon=-96.79, type_="Geography"):
    return {"address": {"freeformAddress": label}, "position": {"lat": lat, "lon": lon}, "type": type_}


def test_geocode_maps_results():
    session = FakeSession(FakeResponse(body={"results": [result()]}))
    assert tomtom.geocode("Dallas", session=session) == [
        {"label": "Dallas, TX", "lat": 32.77, "lon": -96.79, "type": "Geography"}
    ]


def test_geocode_skips_results_without_position():
    body = {"results": [{"address": {"freeformAddress": "Nowhere"}}, result()]}
    hits = tomtom.geocode("x", session=FakeSession(FakeResponse(body=body)))
    assert [h["label"] for h in hits] == ["Dallas, TX"]


def test_geocode_falls_back_to_poi_name():
    body = {"results": [{"poi": {"name": "Big Tex"}, "position": {"lat": 1, "lon": 2}, "type": "POI"}]}
    hits = tomtom.geocode("x", session=FakeSession(FakeResponse(body=body)))
    assert hits[0]["label"] == "Big Tex"


def test_geocode_handles_empty_results():
    assert tomtom.geocode("x", session=FakeSession(FakeResponse(body={"results": []}))) == []


def test_geocode_sends_expected_params():
    session = FakeSession(FakeResponse(body={"results": []}))
    tomtom.geocode("Dallas", typeahead=True, limit=3, session=session)
    assert session.params == {"key": "test-key-123", "limit": 3, "typeahead": "true", "countrySet": "US"}
    assert session.timeout == config.HTTP_TIMEOUT_S


def test_geocode_omits_country_set_when_empty():
    session = FakeSession(FakeResponse(body={"results": []}))
    tomtom.geocode("Dallas", country_set="", session=session)
    assert "countrySet" not in session.params


def test_geocode_encodes_slashes_in_query():
    session = FakeSession(FakeResponse(body={"results": []}))
    tomtom.geocode("A/B Street", session=session)
    assert "A%2FB%20Street.json" in session.url


def reverse_body(address=None):
    return {
        "summary": {"numResults": 1},
        "addresses": [{"address": address or {}, "position": "32.77,-96.79"}],
    }


def test_reverse_geocode_returns_the_label_and_country_code():
    address = {
        "freeformAddress": "1400 Young Street, Dallas, TX 75201",
        "countryCode": "US",
        "streetName": "x",
    }
    session = FakeSession(FakeResponse(body=reverse_body(address)))

    hit = tomtom.reverse_geocode(32.7767, -96.797, session=session)

    assert hit == {"label": "1400 Young Street, Dallas, TX 75201", "country": "US"}


def test_reverse_geocode_calls_the_reverse_endpoint_with_only_the_key():
    session = FakeSession(FakeResponse(body=reverse_body({"freeformAddress": "x"})))

    tomtom.reverse_geocode(32.7767, -96.797, session=session)

    assert session.url == "https://api.tomtom.com/search/2/reverseGeocode/32.7767,-96.797.json"
    assert session.params == {"key": "test-key-123"}  # no countrySet: a map pick can be anywhere
    assert session.timeout == config.HTTP_TIMEOUT_S


@pytest.mark.parametrize(
    "body",
    [
        reverse_body({"routeNumbers": []}),  # what TomTom returns for open water
        reverse_body({"freeformAddress": ""}),
        {"summary": {"numResults": 0}, "addresses": []},
        {},
    ],
)
def test_reverse_geocode_returns_none_when_there_is_no_address(body):
    assert tomtom.reverse_geocode(0.0, 0.0, session=FakeSession(FakeResponse(body=body))) is None


def test_reverse_geocode_country_is_none_when_tomtom_omits_it():
    session = FakeSession(FakeResponse(body=reverse_body({"freeformAddress": "Somewhere"})))

    assert tomtom.reverse_geocode(1.0, 1.0, session=session) == {"label": "Somewhere", "country": None}


def test_reverse_geocode_requires_api_key_and_raises_on_http_errors(monkeypatch):
    session = FakeSession(FakeResponse(status_code=403, body={"error": "Forbidden"}))
    with pytest.raises(tomtom.TomTomError):
        tomtom.reverse_geocode(1.0, 1.0, session=session)

    monkeypatch.setattr(config, "TOMTOM_API_KEY", "")
    with pytest.raises(tomtom.TomTomError, match="TOMTOM_API_KEY"):
        tomtom.reverse_geocode(1.0, 1.0, session=FakeSession(FakeResponse(body={})))


def test_geocode_requires_api_key(monkeypatch):
    monkeypatch.setattr(config, "TOMTOM_API_KEY", "")
    with pytest.raises(tomtom.TomTomError, match="TOMTOM_API_KEY"):
        tomtom.geocode("Dallas", session=FakeSession(FakeResponse(body={})))


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"detailedError": {"message": "bad weight"}}, "bad weight"),
        ({"error": {"description": "quota exceeded"}}, "quota exceeded"),
        ({"error": "plain error"}, "plain error"),
        ({"errorText": "text error"}, "text error"),
    ],
)
def test_error_body_formats_are_parsed(body, expected):
    session = FakeSession(FakeResponse(status_code=403, body=body))
    with pytest.raises(tomtom.TomTomError, match=f"HTTP 403: {expected}"):
        tomtom.geocode("x", session=session)


def test_non_json_error_uses_raw_text_truncated():
    session = FakeSession(FakeResponse(status_code=500, text="x" * 1000))
    with pytest.raises(tomtom.TomTomError) as exc:
        tomtom.geocode("x", session=session)
    assert str(exc.value).startswith("TomTom HTTP 500: ")
    assert len(str(exc.value)) < 400
