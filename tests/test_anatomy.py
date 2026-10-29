"""Unit tests for anatomy resolution helpers."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from pytest_ayon import plugin

ANATOMY = {"roots": [{"name": "work"}], "templates": {"x": 1}}


def _response(status: int, payload: dict) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.json.return_value = payload
    return response


def _session(responses: dict[str, MagicMock]) -> MagicMock:
    session = MagicMock()
    session.get.side_effect = lambda url: responses.get(
        url.rsplit("/", 1)[-1], _response(404, {}))
    return session


def test_merge_dicts_is_recursive_and_non_mutating() -> None:
    """Test that _merge_dicts is recursive and does not mutate."""
    base = {"a": {"b": 1, "c": 2}, "d": [1]}
    merged = plugin._merge_dicts(base, {"a": {"b": 5}, "d": [2]})
    assert merged == {"a": {"b": 5, "c": 2}, "d": [2]}
    assert base == {"a": {"b": 1, "c": 2}, "d": [1]}


@pytest.mark.parametrize("payload", [ANATOMY, {"anatomy": ANATOMY}])
def test_extract_anatomy_formats(payload: dict) -> None:
    """Test that _extract_anatomy_from_preset.

    If the payload contains an "anatomy" key, it extracts from there;
    otherwise, it uses the payload directly.
    Correctly extracts anatomy from different payload formats.

    Args:
        payload (dict): The payload from which to extract anatomy.

    """
    assert plugin._extract_anatomy_from_preset(payload) == ANATOMY


@pytest.mark.parametrize("payload", [
    {"foo": "bar"}, {"roots": {}, "templates": {}}, [], None])
def test_extract_anatomy_invalid(payload: object) -> None:
    """Test  returns None for invalid payloads.

    Args:
        payload (object): The payload to check for anatomy.

    """
    assert plugin._extract_anatomy_from_preset(payload) is None


ITEMS = [{"name": "Generic"}, {"name": "Rendering"}, {"bad": 1}]


def test_pick_named_item_name() -> None:
    """Test that _pick_named_item_name correctly picks items by name."""
    assert plugin._pick_named_item_name(ITEMS, "rendering") == "Rendering"
    assert plugin._pick_named_item_name(ITEMS, "missing") == "Generic"
    assert plugin._pick_named_item_name(ITEMS) == "Generic"
    assert plugin._pick_named_item_name([], "x") is None
    assert plugin._pick_named_item_name(None) is None


def test_first_work_root_prefers_work() -> None:
    """Test that _first_work_root prefers the root named 'work'."""
    anatomy = {"roots": [{"name": "other"}, {"name": "work"}]}
    assert plugin._first_work_root(anatomy) == {"name": "work"}
    assert plugin._first_work_root({"roots": [{"name": "a"}]}) == {"name": "a"}
    assert plugin._first_work_root({})["name"] == "work"


def test_work_root_path_current_platform(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that it the correct path for the current platform."""
    root = {"windows": "C:/p", "linux": "/l", "darwin": "/d"}
    for name, expected in (("win32", "C:/p"), ("linux", "/l"),
                           ("darwin", "/d")):
        monkeypatch.setattr(plugin.sys, "platform", name)
        assert plugin._work_root_path(root) == expected
    assert plugin._work_root_path({}) == "C:/projects"


def test_fetch_anatomy_preset_not_found() -> None:
    """Test that it returns None when the preset is not found."""
    session = _session({})
    assert plugin._fetch_anatomy_preset(session, "http://x", "nope") is None


def test_fetch_anatomy_preset_ok() -> None:
    """Test that it returns the anatomy when the preset is found."""
    session = _session({"p": _response(plugin.STATUS_OK, ANATOMY)})
    assert plugin._fetch_anatomy_preset(session, "http://x", "p") == ANATOMY


def _resolve(session: MagicMock, **kwargs) -> dict:  # ruff:ignore[missing-type-kwargs]
    fixture = plugin.project_anatomy.__wrapped__
    return fixture(
        ("http://x", "key"),
        session,
        kwargs.get("preset", "__primary__"),
        kwargs.get("fallbacks", ("__builtin__",)),
        kwargs.get("overrides", {}),
    )


def test_project_anatomy_falls_back_to_builtin_preset() -> None:
    """Test that project_anatomy falls back to the built-in preset."""
    session = _session({"__builtin__": _response(plugin.STATUS_OK, ANATOMY)})
    assert _resolve(session) == ANATOMY


def test_project_anatomy_local_default_warns(
        caplog: pytest.LogCaptureFixture) -> None:
    """Test that project_anatomy warns when using the local default anatomy."""
    with caplog.at_level(logging.WARNING):
        result = _resolve(_session({}))
    assert result == plugin._default_project_anatomy()
    assert "built-in default anatomy" in caplog.text


def test_project_anatomy_overrides_applied() -> None:
    """Test that project_anatomy applies overrides correctly."""
    session = _session({"__primary__": _response(plugin.STATUS_OK, ANATOMY)})
    result = _resolve(session, overrides={"templates": {"y": 2}})
    assert result["templates"] == {"x": 1, "y": 2}
    assert ANATOMY["templates"] == {"x": 1}
