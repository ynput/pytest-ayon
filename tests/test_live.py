"""Integration tests against a live AYON server (configured via `.env`)."""
from __future__ import annotations

from typing import Any

import pytest
import requests

pytestmark = pytest.mark.live


def test_server_reachable(ayon_server_session: requests.Session,
                          ayon_connection_env: tuple[str, str]) -> None:
    url, _ = ayon_connection_env
    response = ayon_server_session.get(f"{url}/api/info")
    assert response.status_code == requests.codes.ok


def test_project_anatomy_resolves(project_anatomy: dict[str, Any]) -> None:
    assert "roots" in project_anatomy
    assert "templates" in project_anatomy


@pytest.mark.parametrize(
    "project_anatomy_preset_name", ["__builtin__"], indirect=True)
def test_builtin_preset(project_anatomy: dict[str, Any]) -> None:
    assert project_anatomy["templates"]


def test_project_created(project: Any,  # noqa: ANN401
                         ayon_server_session: requests.Session,
                         ayon_connection_env: tuple[str, str]) -> None:
    url, _ = ayon_connection_env
    response = ayon_server_session.get(
        f"{url}/api/projects/{project.project_name}")
    assert response.status_code == requests.codes.ok
