"""Unit tests for anatomy resolution helpers."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from pytest_ayon import plugin, server

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
    merged = server._merge_dicts(base, {"a": {"b": 5}, "d": [2]})
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
    assert server._extract_anatomy_from_preset(payload) == ANATOMY


@pytest.mark.parametrize("payload", [
    {"foo": "bar"}, {"roots": {}, "templates": {}}, [], None])
def test_extract_anatomy_invalid(payload: object) -> None:
    """Test  returns None for invalid payloads.

    Args:
        payload (object): The payload to check for anatomy.

    """
    assert server._extract_anatomy_from_preset(payload) is None


ITEMS = [{"name": "Generic"}, {"name": "Rendering"}, {"bad": 1}]


def test_pick_named_item_name() -> None:
    """Test that _pick_named_item_name correctly picks items by name."""
    assert server._pick_named_item_name(ITEMS, "rendering") == "Rendering"
    assert server._pick_named_item_name(ITEMS, "missing") == "Generic"
    assert server._pick_named_item_name(ITEMS) == "Generic"
    assert server._pick_named_item_name([], "x") is None
    assert server._pick_named_item_name(None) is None


def test_first_work_root_prefers_work() -> None:
    """Test that _first_work_root prefers the root named 'work'."""
    anatomy = {"roots": [{"name": "other"}, {"name": "work"}]}
    assert server._first_work_root(anatomy) == {"name": "work"}
    assert server._first_work_root({"roots": [{"name": "a"}]}) == {"name": "a"}
    assert server._first_work_root({})["name"] == "work"


def test_work_root_path_current_platform(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that it the correct path for the current platform."""
    root = {"windows": "C:/p", "linux": "/l", "darwin": "/d"}
    for name, expected in (("win32", "C:/p"), ("linux", "/l"),
                           ("darwin", "/d")):
        monkeypatch.setattr(server.sys, "platform", name)
        assert server._work_root_path(root) == expected
    assert server._work_root_path({}) == "C:/projects"


def test_fetch_anatomy_preset_not_found() -> None:
    """Test that it returns None when the preset is not found."""
    session = _session({})
    assert server._fetch_anatomy_preset(session, "http://x", "nope") is None


def test_fetch_anatomy_preset_ok() -> None:
    """Test that it returns the anatomy when the preset is found."""
    session = _session({"p": _response(server.STATUS_OK, ANATOMY)})
    assert server._fetch_anatomy_preset(session, "http://x", "p") == ANATOMY


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
    session = _session({"__builtin__": _response(server.STATUS_OK, ANATOMY)})
    assert _resolve(session) == ANATOMY


def test_project_anatomy_local_default_warns(
        caplog: pytest.LogCaptureFixture) -> None:
    """Test that project_anatomy warns when using the local default anatomy."""
    with caplog.at_level(logging.WARNING):
        result = _resolve(_session({}))
    assert result == server._default_project_anatomy()
    assert "built-in default anatomy" in caplog.text


def test_project_anatomy_overrides_applied() -> None:
    """Test that project_anatomy applies overrides correctly."""
    session = _session({"__primary__": _response(server.STATUS_OK, ANATOMY)})
    result = _resolve(session, overrides={"templates": {"y": 2}})
    assert result["templates"] == {"x": 1, "y": 2}
    assert ANATOMY["templates"] == {"x": 1}


@pytest.mark.parametrize(
    "project_anatomy_fallback_presets", [()], indirect=True)
def test_fallback_presets_indirect(
        project_anatomy_fallback_presets: tuple[str, ...]) -> None:
    """Test that fallback presets honor indirect parametrization."""
    assert project_anatomy_fallback_presets == ()


@pytest.mark.parametrize(
    "project_anatomy_overrides", [{"templates": {"y": 2}}], indirect=True)
def test_anatomy_overrides_indirect(
        project_anatomy_overrides: dict) -> None:
    """Test that anatomy overrides honor indirect parametrization."""
    assert project_anatomy_overrides == {"templates": {"y": 2}}


def test_create_links_skips_out_of_range_pairs() -> None:
    """Test that _create_links skips pairs with out-of-range indices."""
    session = MagicMock()
    session.post.return_value = _response(server.STATUS_OK, {"id": "link"})
    representations = [
        server.IdNamePair(name=f"r{i}", id=f"id{i}") for i in range(2)]
    links = server._create_links(
        session, "http://x", "p", representations,
        [(-1, 0, "neg"), (0, 2, "high"), (0, 1, "ok")])
    assert links == ["link"]
    assert session.post.call_count == 1


def test_create_representation_uses_given_root_and_types() -> None:
    """Test that root name and types propagate into the representation."""
    template = [{"directory": "{root[publish]}/d", "file": "f.exr"}]
    rep = server.create_representation(
        "proj", "P", "folder", "task", "modelMain", 1, "vid",
        template, "/mnt/publish", 1001, 1003, "exr_1",
        root_name="publish", product_type="model",
        task_type="Modeling", task_short="mdl")
    context = rep["data"]["context"]
    assert context["root"] == {"publish": "/mnt/publish"}
    assert context["product"]["type"] == "model"
    assert context["family"] == "model"
    assert context["task"] == {
        "name": "task", "type": "Modeling", "short": "mdl"}
    for file_info in rep["files"]:
        assert file_info["path"].startswith("{root[publish]}/")
        assert "/model/v001/" in file_info["path"]


def test_resolve_anatomy_function() -> None:
    """Test that resolve_anatomy works without fixtures."""
    session = _session({"b": _response(server.STATUS_OK, ANATOMY)})
    result = server.resolve_anatomy(
        session, "http://x", "a", ("b",), {"templates": {"y": 2}})
    assert result["templates"] == {"x": 1, "y": 2}


def test_check_raises_on_unexpected_status() -> None:
    """Test that unexpected status codes raise AyonRequestError."""
    response = _response(500, {})
    response.text = "boom"
    with pytest.raises(server.AyonRequestError, match="boom"):
        server._check(response, server.STATUS_OK)


def test_register_site_sends_site_headers() -> None:
    """Test that register_site sends site headers and returns the site."""
    session = MagicMock()
    session.get.return_value = _response(
        server.STATUS_OK, {"sites": [{"id": "s1", "platform": "darwin"}]})
    site = server.register_site(
        session, "http://x", "s1", "darwin", hostname="h", version="1.0.0")
    assert site == {"id": "s1", "platform": "darwin"}
    session.get.assert_called_once_with("http://x/api/info", headers={
        "x-ayon-site-id": "s1",
        "x-ayon-platform": "darwin",
        "x-ayon-hostname": "h",
        "x-ayon-version": "1.0.0",
    })


def test_register_site_rejects_unknown_platform() -> None:
    """Test that register_site validates the platform."""
    with pytest.raises(ValueError, match="platform"):
        server.register_site(MagicMock(), "http://x", "s1", "amiga")


def test_register_site_not_reported() -> None:
    """Test that register_site raises when the server omits the site."""
    session = MagicMock()
    session.get.return_value = _response(server.STATUS_OK, {"sites": []})
    with pytest.raises(server.AyonRequestError):
        server.register_site(session, "http://x", "s1", "linux")
