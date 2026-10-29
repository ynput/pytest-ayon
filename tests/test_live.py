"""Integration tests against a live AYON server (configured via `.env`)."""
from __future__ import annotations

from typing import Any

import pytest
import requests

pytestmark = pytest.mark.live


def test_server_reachable(ayon_server_session: requests.Session,
                          ayon_connection_env: tuple[str, str]) -> None:
    """Test that the AYON server is reachable.

    Args:
        ayon_server_session (requests.Session): The session to
            use for requests.
        ayon_connection_env (tuple[str, str]): The AYON server URL and token.

    """
    url, _ = ayon_connection_env
    response = ayon_server_session.get(f"{url}/api/info")
    assert response.status_code == requests.codes.ok


@pytest.mark.parametrize(
    "preset", ["__primary__", "__builtin__"])
def test_fetch_preset_parses(ayon_server_session: requests.Session,
                             ayon_connection_env: tuple[str, str],
                             preset: str) -> None:
    """Test that fetching a preset parses correctly.

    Args:
        ayon_server_session (requests.Session): The session to use
            for requests.
        ayon_connection_env (tuple[str, str]): The AYON server URL and token.
        preset (str): The name of the preset to fetch.

    """
    from pytest_ayon import plugin
    url, _ = ayon_connection_env
    anatomy = plugin._fetch_anatomy_preset(ayon_server_session, url, preset)
    assert anatomy is not None
    assert plugin._first_work_root(anatomy)["name"] == "work"
    assert plugin._pick_named_item_name(anatomy["task_types"])
    assert plugin._pick_named_item_name(anatomy["folder_types"])


def test_project_anatomy_resolves(project_anatomy: dict[str, Any]) -> None:
    """Test that the project anatomy resolves correctly.

    Args:
        project_anatomy (dict[str, Any]): The resolved project anatomy.

    """
    assert "roots" in project_anatomy
    assert "templates" in project_anatomy


@pytest.mark.parametrize(
    "project_anatomy_preset_name", ["__builtin__"], indirect=True)
def test_builtin_preset(project_anatomy: dict[str, Any]) -> None:
    """Test that the built-in preset resolves correctly.

    Args:
        project_anatomy (dict[str, Any]): The resolved project anatomy.

    """
    assert project_anatomy["templates"]


def test_project_created(project: Any,  # ruff:ignore[any-type]
                         ayon_server_session: requests.Session,
                         ayon_connection_env: tuple[str, str]) -> None:
    """Test that the project is created on the AYON server.

    Args:
        project (Any): The project object.
        ayon_server_session (requests.Session): The session to use
        for requests.

        ayon_connection_env (tuple[str, str]): The AYON server URL and token.

    """
    url, _ = ayon_connection_env
    response = ayon_server_session.get(
        f"{url}/api/projects/{project.project_name}")
    assert response.status_code == requests.codes.ok


def test_project_contents(project: Any) -> None:  # ruff:ignore[any-type]
    """Test that the project contains the expected contents.

    Args:
        project (Any): The project object.

    """
    assert project.folder.id
    assert project.task.id
    assert project.product.id
    assert project.version.name == "v001"
    assert len(project.representations) == 4
    assert len(project.links) == 2
