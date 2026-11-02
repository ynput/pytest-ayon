"""Integration tests against a live AYON server (configured via `.env`)."""
from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Any

import pytest
import requests

from pytest_ayon import server

if TYPE_CHECKING:
    from collections.abc import Generator

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
    url, _ = ayon_connection_env
    anatomy = server._fetch_anatomy_preset(ayon_server_session, url, preset)
    assert anatomy is not None
    assert server._first_work_root(anatomy) in anatomy["roots"]
    assert server._pick_named_item_name(anatomy["task_types"])
    assert server._pick_named_item_name(anatomy["folder_types"])


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


@pytest.fixture(scope="module")
def module_project(
        ayon_server_session: requests.Session,
        ayon_connection_env: tuple[str, str],
) -> Generator[server.ProjectInfo, None, None]:
    """Module-scoped project built from the plain server functions.

    Yields:
        server.ProjectInfo: The populated project.

    """
    url, _ = ayon_connection_env
    anatomy = server.resolve_anatomy(ayon_server_session, url)
    info = server.create_project(ayon_server_session, url, anatomy)
    try:
        yield server.populate_project(
            ayon_server_session, url, info, anatomy,
            {"representation_count": 2, "link_pairs": [(0, 1, "rel")]})
    finally:
        server.delete_project(ayon_server_session, url, info.project_name)


def test_module_project_contents(module_project: server.ProjectInfo) -> None:
    """Test that a project built from plain functions has its contents.

    Args:
        module_project (server.ProjectInfo): The module-scoped project.

    """
    assert module_project.version.id
    assert len(module_project.representations) == 2
    assert len(module_project.links) == 1


def test_register_site(ayon_server_session: requests.Session,
                       ayon_connection_env: tuple[str, str]) -> None:
    """Test that a site can be registered and unregistered.

    Args:
        ayon_server_session (requests.Session): The session to use
            for requests.
        ayon_connection_env (tuple[str, str]): The AYON server URL and token.

    """
    url, _ = ayon_connection_env
    site_id = f"pytest-{secrets.token_hex(4)}"
    site = server.register_site(ayon_server_session, url, site_id, "linux")
    try:
        assert site["id"] == site_id
        assert site["platform"] == "linux"
    finally:
        server.unregister_site(ayon_server_session, url, site_id)
