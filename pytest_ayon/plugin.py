"""Ayon plugin for pytest.

Some of the fixtures in this module require the AYON server to be running.
You need to set the AYON_SERVER_URL and AYON_API_KEY environment variables.

TODO (antirotor):
    - Add more fixtures.
    - Modularize the fixtures.
    - Use ayon_python_api functions than REST API calls.

"""
from __future__ import annotations

import contextlib
import copy
import os
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generator,
    NamedTuple,
    Optional,
)

import pytest

from .server import (
    DEFAULT_PROJECT_PARAMS,
    IdNamePair,
    ProjectInfo,
    create_project,
    create_session,
    delete_project,
    populate_project,
    resolve_anatomy,
)

if TYPE_CHECKING:
    from pathlib import Path

    import requests

__all__ = ["IdNamePair", "ProjectInfo"]


class AddonVersion(NamedTuple):
    """Addon version and name.

    Args:
        name (str): The addon name.
        version (str): The addon version.

    """
    name: str
    version: str


@pytest.fixture(scope="session")
def tmp_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Get the temporary directory path.

    Returns:
        Path: The temporary directory path.

    """
    return tmp_path_factory.mktemp("data")


@pytest.fixture(scope="session")
def project_root_path(request: pytest.FixtureRequest) -> Path:
    """Get the repository root path.

    Returns:
        Path: The project root path.

    """
    return request.config.rootpath


@pytest.fixture
def base_dir() -> str:
    """Provides the path to the base directory.

    Returns:
        str: The base directory path.

    """
    return os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(scope="session")
def ayon_connection_env() -> tuple[str, str]:
    """Get the server URL and the API key.

    Returns:
        tuple[str, str]: The server URL and the API key.

    """
    os.environ["AYON_SERVER_URL"] = os.getenv("AYON_SERVER_URL").rstrip("/")
    os.environ["AYON_API_KEY"] = os.getenv("AYON_API_KEY")
    return os.environ["AYON_SERVER_URL"], os.environ["AYON_API_KEY"]


@pytest.fixture(scope="session")
def ayon_server_session(
        ayon_connection_env: tuple[str, str]) -> requests.Session:
    """Get the server session.

    Returns:
        requests.Session: The server session.

    """
    _, api_key = ayon_connection_env
    return create_session(api_key)


@pytest.fixture(scope="session")
def addon_version(project_root_path: Path) -> NamedTuple:
    """Get the version of the addon.

    Returns:
        AddonVersion: The addon version and name.

    """
    version = None
    name = None
    with (
            contextlib.suppress(FileNotFoundError),
            open(project_root_path / "package.py", encoding="utf-8") as file):
        for line in file:
            if line.startswith("version"):
                version = line.split("=")[1].strip().strip('"')
                continue
            if line.startswith("name"):
                name = line.split("=")[1].strip().strip('"')
                continue
    return AddonVersion(name=name, version=version)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register pytest-ayon command line options."""
    parser.addoption(
        "--ayon-anatomy-preset",
        default="__primary__",
        help="Server anatomy preset used for test projects.",
    )


@pytest.fixture
def project_anatomy_preset_name(request: pytest.FixtureRequest) -> str:
    """Preferred server anatomy preset name.

    Can be overridden via indirect parametrization of this fixture,
    otherwise taken from `--ayon-anatomy-preset`.

    Args:
        request (pytest.FixtureRequest): The pytest fixture request object.

    Returns:
        str: The preferred server anatomy preset name.

    """
    if hasattr(request, "param"):
        return request.param
    return request.config.getoption("ayon_anatomy_preset")


@pytest.fixture
def project_anatomy_fallback_presets(
        request: pytest.FixtureRequest) -> tuple[str, ...]:
    """Fallback presets tried if preferred anatomy preset is not available.

    Args:
        request (pytest.FixtureRequest): The pytest fixture request object.

    Returns:
        tuple[str, ...]: The fallback anatomy preset names.

    """
    if hasattr(request, "param"):
        return tuple(request.param)
    return ("__builtin__",)


@pytest.fixture
def project_anatomy_overrides(
        request: pytest.FixtureRequest) -> dict[str, Any]:
    """Optional anatomy override data merged on top of resolved anatomy.

    Args:
        request (pytest.FixtureRequest): The pytest fixture request object.

    Returns:
        dict[str, Any]: The anatomy override data.

    """
    if hasattr(request, "param"):
        return request.param
    return {}


@pytest.fixture
def project_anatomy(
        ayon_connection_env: tuple[str, str],
        ayon_server_session: requests.Session,
        project_anatomy_preset_name: str,
        project_anatomy_fallback_presets: tuple[str, ...],
        project_anatomy_overrides: dict[str, Any]) -> dict[str, Any]:
    """Resolve anatomy from presets, with fallback to built-in defaults.

    Args:
        ayon_connection_env (tuple[str, str]): The Ayon server
            connection environment.
        ayon_server_session (requests.Session): The HTTP session for
            server communication.
        project_anatomy_preset_name (str): The preferred anatomy preset name.
        project_anatomy_fallback_presets (tuple[str, ...]): Fallback anatomy
            preset names.
        project_anatomy_overrides (dict[str, Any]): Anatomy override data.

    Returns:
        dict[str, Any]: The resolved anatomy data.

    """
    server_url, _ = ayon_connection_env
    return resolve_anatomy(
        ayon_server_session, server_url,
        project_anatomy_preset_name,
        project_anatomy_fallback_presets,
        project_anatomy_overrides)


@pytest.fixture
def project_params(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Project fixture defaults, overridable via indirect parametrization.

    Returns:
        dict[str, Any]: The combined project parameters.

    """
    return {**DEFAULT_PROJECT_PARAMS, **getattr(request, "param", {})}


@pytest.fixture
def project(
        printer: Callable[[Any], None],
        ayon_connection_env: tuple[str, str],
        project_anatomy: dict[str, Any],
        project_params: dict[str, Any]) -> Generator[ProjectInfo, None, None]:
    """Set up a project with some data and yield the project info.

    This will create a project with a folder, a task, a product, a version,
    and some representations. It will also create some links between the
    representations. See `pytest_ayon.server.populate_project`.

    Args:
        printer: The printer fixture.
        ayon_connection_env: The AYON connection environment fixture.
        project_anatomy: The resolved project anatomy.
        project_params: Parameters controlling the created entities.

    Yields:
        ProjectInfo: The project information.

    """
    server_url, api_key = ayon_connection_env
    session = create_session(api_key)
    info = create_project(
        session, server_url, project_anatomy,
        library=project_params["library"])
    printer(f"created project {info.project_name}, filling with data...")
    try:
        yield populate_project(
            session, server_url, info, project_anatomy, project_params)
    finally:
        printer(f"tearing down project {info.project_name}...")
        delete_project(session, server_url, info.project_name)


@pytest.fixture
def empty_project(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
    request: pytest.FixtureRequest,
    printer: Any,  # ruff: ignore[any-type] (fixture)
    ayon_connection_env: tuple[str, str],
    project_anatomy: dict[str, Any],
    project_name: Optional[str] = None,
    project_code: Optional[str] = None,
    folder_types: tuple[str, ...] = ("Asset", "Episode", "Sequence", "Shot"),
    task_types: tuple[str] = ("rendering",),
    statuses: tuple[str] = ("not_started",),
) -> Generator[ProjectInfo, None, None]:
    """Set up an empty project and yield the project info.

    This will create an empty project with the specified folder types,
    task types, and statuses.

    Args:
        request: The pytest request fixture.
        printer: The printer fixture.
        ayon_connection_env: The AYON connection environment fixture.
        project_anatomy: The project anatomy fixture.
        project_name: The project name. If None, a random
            name will be generated.
        project_code: The project code. If None, a random
            code will be generated.
        folder_types: The folder types to create in the project.
        task_types: The task types to create in the project.
        statuses: The statuses to create in the project.

    Yields:
        ProjectInfo: The project information.

    """
    server_url, api_key = ayon_connection_env
    values = {
        "project_name": project_name,
        "project_code": project_code,
        "folder_types": folder_types,
        "task_types": task_types,
        "statuses": statuses,
    }

    # override default values with the given parameters
    if hasattr(request, "param"):
        values.update(request.param)

    project_anatomy = copy.deepcopy(project_anatomy)
    project_anatomy["folder_types"] = [
        {
            "name": folder_type.capitalize(),
            "icon": "folder",
            "original_name": folder_type.capitalize(),
        } for folder_type in values["folder_types"]
    ]

    project_anatomy["task_types"] = [
        {
            "name": task_type.lower(),
            "shortName": task_type.lower(),
            "icon": "",
            "original_name": task_type.lower(),
        } for task_type in values["task_types"]
    ]

    project_anatomy["statuses"] = [
        {
            "name": status.lower(),
            "shortName": status.lower(),
            "state": status.lower(),
            "icon": "",
            "color": "#cacaca",
            "original_name": "string"
        } for status in values["statuses"]
    ]

    session = create_session(api_key)
    info = create_project(
        session, server_url, project_anatomy,
        name=values["project_name"], code=values["project_code"])
    printer(f"created project {info.project_name}")
    try:
        yield info
    finally:
        printer(f"tearing down project {info.project_name}...")
        delete_project(session, server_url, info.project_name)
