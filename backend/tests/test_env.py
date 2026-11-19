"""Environment helpers used by config/settings.py."""

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.env import DEV_SECRET_KEY, env_bool, env_list, resolve_secret_key


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on", " On "])
def test_env_bool_true_values(monkeypatch, raw):
    monkeypatch.setenv("X_FLAG", raw)
    assert env_bool("X_FLAG", False) is True


@pytest.mark.parametrize("raw", ["0", "false", "False", "no", "OFF"])
def test_env_bool_false_values(monkeypatch, raw):
    monkeypatch.setenv("X_FLAG", raw)
    assert env_bool("X_FLAG", True) is False


def test_env_bool_unset_or_blank_uses_default(monkeypatch):
    monkeypatch.delenv("X_FLAG", raising=False)
    assert env_bool("X_FLAG", True) is True
    monkeypatch.setenv("X_FLAG", "")
    assert env_bool("X_FLAG", False) is False


def test_env_bool_rejects_garbage(monkeypatch):
    monkeypatch.setenv("X_FLAG", "maybe")
    with pytest.raises(ImproperlyConfigured):
        env_bool("X_FLAG", False)


def test_env_list_trims_and_drops_empty_items(monkeypatch):
    monkeypatch.setenv("X_LIST", " a.com , b.com,, ")
    assert env_list("X_LIST", ["d"]) == ["a.com", "b.com"]


def test_env_list_empty_value_is_empty_list(monkeypatch):
    monkeypatch.setenv("X_LIST", "")
    assert env_list("X_LIST", ["d"]) == []


def test_env_list_unset_returns_a_copy_of_the_default(monkeypatch):
    monkeypatch.delenv("X_LIST", raising=False)
    default = ["d"]
    result = env_list("X_LIST", default)
    assert result == ["d"]
    assert result is not default


def test_secret_key_missing_with_debug_off_raises():
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY must be set"):
        resolve_secret_key(False, None)
    with pytest.raises(ImproperlyConfigured):
        resolve_secret_key(False, "")


def test_secret_key_missing_with_debug_on_falls_back():
    assert resolve_secret_key(True, None) == DEV_SECRET_KEY


def test_secret_key_provided_is_used():
    assert resolve_secret_key(False, "abc") == "abc"
    assert resolve_secret_key(True, "abc") == "abc"
