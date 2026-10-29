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
import logging
import os
import random
import secrets
import sys
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generator,
    NamedTuple,
    Optional,
)

import pytest
import requests

from .utils import (
    STATUS_CREATED,
    STATUS_NO_CONTENT,
    STATUS_OK,
    create_representation,
)

if TYPE_CHECKING:
    from pathlib import Path


class AddonVersion(NamedTuple):
    """Addon version and name.

    Args:
        name (str): The addon name.
        version (str): The addon version.

    """
    name: str
    version: str


@dataclass
class IdNamePair:
    """Id and name pair."""
    id: str
    name: str


@dataclass
class ProjectInfo:
    """Project information.

    Deprecated:
        folder, task, product, version are deprecated. Use their
        entity counterparts instead.

    """
    project_name: str
    project_code: str
    project_root_folders: dict[str, str]
    folder: Optional[IdNamePair] = None
    folder_entity: Optional[dict] = None
    task: Optional[IdNamePair] = None
    task_entity: Optional[dict] = None
    product: Optional[IdNamePair] = None
    product_entity: Optional[dict] = None
    version: Optional[IdNamePair] = None
    version_entity: Optional[dict] = None
    representations: Optional[list[IdNamePair]] = field(default_factory=list)
    links: Optional[list[str]] = field(default_factory=list)


def _default_project_anatomy() -> dict[str, Any]:
    """Default anatomy used when server presets are unavailable.

    Returns:
        dict: The default project anatomy.

    """
    return {
        "roots": [
            {
                "name": "work",
                "windows": "C:/projects",
                "linux": "/mnt/share/projects",
                "darwin": "/Volumes/projects"
            }
        ],
        "templates": {
            "version_padding": 3,
            "version": "v{version:0>{@version_padding}}",
            "frame_padding": 4,
            "frame": "{frame:0>{@frame_padding}}",
            "work": [
                {
                    "name": "default",
                    "directory": (
                        "{root[work]}/{project[name]}/{hierarchy}/"
                        "{folder[name]}/work/{task[name]}"
                    ),
                    "file": (
                        "{project[code]}_{folder[name]}_{task[name]}_"
                        "{@version}<_{comment}>.{ext}"
                    )
                }
            ],
            "publish": [
                {
                    "name": "default",
                    "directory": (
                        "{root[work]}/{project[name]}/{hierarchy}/"
                        "{folder[name]}/publish/{product[type]}/"
                        "{product[name]}/v{version:0>3}"
                    ),
                    "file": (
                        "{project[code]}_{folder[name]}_{product[name]}"
                        "_v{version:0>3}<_{output}><.{frame:0>4}>"
                        "<_{udim}>.{ext}"
                    )
                }
            ],
            "hero": [
                {
                    "name": "default",
                     "directory": "{root[work]}/{project[name]}/"
                                     "{hierarchy}/{folder[name]}/publish/"
                                     "{product[type]}"
                                     "/{product[name]}/hero",
                    "file": "{project[code]}_{folder[name]}_"
                                "{product[name]}_hero<_{output}>"
                                "<.{@frame}><_{udim}>.{ext}"
                }
            ],
        },
        "attributes": {
            "fps": 25,
            "resolutionWidth": 1920,
            "resolutionHeight": 1080,
            "pixelAspect": 1,
            "clipIn": 1,
            "clipOut": 1,
            "frameStart": 1001,
            "frameEnd": 1050,
            "handleStart": 0,
            "handleEnd": 0,
            "startDate": "2021-01-01T00:00:00+00:00",
            "endDate": "2021-01-01T00:00:00+00:00",
            "description": "A very nice entity",
            "applications": [],
            "tools": []
        },
        "folder_types": [
            {
                "name": "Asset",
                "icon": "folder",
                "original_name": "Asset"
            }
        ],
        "task_types": [
            {
                "name": "rendering",
                "shortName": "rendering",
                "icon": "",
                "original_name": "rendering"
            }
        ],
        "linkTypes": [
            {
                "name": "relationship|representation|representation",
                "link_type": "relationship",
                "input_type": "representation",
                "output_type": "representation",
                "data": {
                    "color": "#73149F",
                }
            }
        ],
        "statuses": [
            {
                "name": "not_started",
                "shortName": "not_started",
                "state": "not_started",
                "icon": "",
                "color": "#cacaca",
                "original_name": "string"
            }
        ]
    }


def _merge_dicts(
        base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge dictionaries.

    Args:
        base (dict[str, Any]): The base dictionary.
        override (dict[str, Any]): The dictionary with overriding values.

    Returns:
        dict[str, Any]: The merged dictionary.

    """
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
            continue
        merged[key] = copy.deepcopy(value)
    return merged


def _extract_anatomy_from_preset(
        data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Extract anatomy payload from a preset response.

    `GET /api/anatomy/presets/{name}` returns the anatomy object itself
    (`roots`, `templates`, `attributes`, `folder_types`, `task_types`, ...).

    Returns:
        Optional[dict[str, Any]]: The extracted anatomy data
            if available, else None.

    """
    if not isinstance(data, dict):
        return None
    for candidate in (data, data.get("anatomy")):
        if (
            isinstance(candidate, dict)
            and isinstance(candidate.get("roots"), list)
            and isinstance(candidate.get("templates"), dict)
        ):
            return candidate
    return None


def _fetch_anatomy_preset(
        session: requests.Session,
        server_url: str,
        preset_name: str) -> Optional[dict[str, Any]]:
    """Fetch anatomy preset from server and return anatomy data.

    Args:
        session (requests.Session): The HTTP session to use for the request.
        server_url (str): The base URL of the server.
        preset_name (str): The name of the anatomy preset to fetch.

    Returns:
        Optional[dict[str, Any]]: The anatomy data if the
            request is successful and the data is valid, else None.

    """
    response = session.get(f"{server_url}/api/anatomy/presets/{preset_name}")
    if response.status_code != STATUS_OK:
        return None
    anatomy = _extract_anatomy_from_preset(response.json())
    if anatomy is None:
        return None
    return copy.deepcopy(anatomy)


def _pick_named_item_name(
        items: Any, preferred: Optional[str] = None) -> Optional[str]:  # ruff: ignore[any-type]
    """Return the `name` of the preferred item, else of the first item.

    The match against `preferred` is case-insensitive.
    """
    if not isinstance(items, list):
        return None
    names = [
        item["name"] for item in items
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ]
    if preferred:
        for name in names:
            if name.lower() == preferred.lower():
                return name
    return names[0] if names else None


def _first_work_root(anatomy: dict[str, Any]) -> dict[str, str]:
    """Return the `work` root, else the first root, from the anatomy."""
    roots = [
        root for root in anatomy.get("roots") or []
        if isinstance(root, dict)
    ]
    for root in roots:
        if root.get("name") == "work":
            return root
    if roots:
        return roots[0]
    return {"name": "work", "windows": "C:/projects"}


def _work_root_path(root: dict[str, str]) -> str:
    """Resolve root path for the current platform, with fallbacks.

    Args:
        root (dict[str, str]): The root dictionary containing
            platform-specific paths.

    Returns:
        str: The resolved root path for the current platform, or a fallback
            path if not found.

    """
    current = {
        "win32": "windows", "darwin": "darwin"}.get(sys.platform, "linux")
    for platform_key in (current, "windows", "linux", "darwin"):
        value = root.get(platform_key)
        if isinstance(value, str) and value:
            return value
    return "C:/projects"


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
    session = requests.Session()
    session.headers.update({"x-api-key": api_key})
    return session


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
def project_anatomy_fallback_presets() -> tuple[str, ...]:
    """Fallback presets tried if preferred anatomy preset is not available.

    Returns:
        tuple[str, ...]: The fallback anatomy preset names.

    """
    return ("__builtin__",)


@pytest.fixture
def project_anatomy_overrides() -> dict[str, Any]:
    """Optional anatomy override data merged on top of resolved anatomy.

    Returns:
        dict[str, Any]: The anatomy override data.

    """
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
    preset_names: list[str] = [
        project_anatomy_preset_name, *project_anatomy_fallback_presets]
    seen: set[str] = set()
    anatomy: Optional[dict[str, Any]] = None

    for preset_name in preset_names:
        if preset_name in seen:
            continue
        seen.add(preset_name)
        anatomy = _fetch_anatomy_preset(
            ayon_server_session, server_url, preset_name)
        if anatomy is not None:
            break

    if anatomy is None:
        logging.getLogger(__name__).warning(
            "No anatomy preset available on server (tried %s); "
            "using built-in default anatomy.", sorted(seen))
        anatomy = _default_project_anatomy()

    if project_anatomy_overrides:
        anatomy = _merge_dicts(anatomy, project_anatomy_overrides)

    return anatomy


@pytest.fixture
def project_params(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Project fixture defaults, overridable via indirect parametrization.

    Returns:
        dict[str, Any]: The combined project parameters.

    """
    defaults = {
        "product_name": "renderMain",
        "product_type": "render",
        "version": 1,
        "task_name": "rendering",
        "task_type": "rendering",
        "folder_type": "Asset",
        "representation_count": 4,
        "representation_name_prefix": "exr",
        "frame_start": 1001,
        "frame_end_min": 1020,
        "frame_end_max": 1200,
        "link_pairs": [(0, 1, "relationship_2"), (2, 3, "relationship_1")],
        "library": False,
    }
    return {**defaults, **getattr(request, "param", {})}


_RELATIONSHIP_LINK_TYPE = "relationship|representation|representation"


def _create_project(
        session: requests.Session,
        server_url: str,
        project_data: dict[str, Any]) -> None:
    """Create a project and its `relationship` link type."""
    response = session.post(f"{server_url}/api/projects", json=project_data)
    assert response.status_code == STATUS_CREATED, response.text

    # due to the bug in AYON server, create `relationship` link type
    # TODO(antirotor): remove this once the bug is fixed
    response = session.put(
        (f"{server_url}/api/projects/{project_data['name']}"
         f"/links/types/{_RELATIONSHIP_LINK_TYPE}"),
        json={"data": {"color": "#73149F"}},
    )
    assert response.status_code == STATUS_NO_CONTENT


def _create_entity(
        session: requests.Session,
        server_url: str,
        project_name: str,
        endpoint: str,
        payload: dict[str, Any]) -> dict[str, Any]:
    """Create an entity through `/projects/{name}/{endpoint}`.

    Returns:
        dict[str, Any]: Server response (contains at least the `id`).

    """
    response = session.post(
        f"{server_url}/api/projects/{project_name}/{endpoint}", json=payload)
    assert response.status_code == STATUS_CREATED, response.text
    return response.json()


def _create_folder(
        session: requests.Session,
        server_url: str,
        project_name: str,
        folder_name: str,
        folder_type: str) -> dict[str, Any]:
    """Create a folder and return its full entity.

    Returns:
        dict[str, Any]: The created folder entity.

    """
    created = _create_entity(
        session, server_url, project_name, "folders",
        {"name": folder_name, "folderType": folder_type})
    response = session.get(
        f"{server_url}/api/projects/{project_name}/folders/{created['id']}")
    assert response.status_code == STATUS_OK
    return response.json()


def _create_representations(  # ruff: ignore[too-many-arguments]
        session: requests.Session,
        server_url: str,
        printer: Callable[[Any], None],
        *,
        project_name: str,
        project_code: str,
        folder_name: str,
        task_name: str,
        product_name: str,
        version: int,
        version_id: str,
        anatomy: dict[str, Any],
        params: dict[str, Any]) -> list[IdNamePair]:
    """Create representations for a version.

    Returns:
        list[IdNamePair]: The created representations.

    """
    publish_templates = anatomy.get("templates", {}).get("publish", [])
    assert publish_templates, "Project anatomy must define templates.publish"
    work_root = _work_root_path(_first_work_root(anatomy))

    representations = []
    for i in range(1, params["representation_count"] + 1):
        representation_name = f"{params['representation_name_prefix']}_{i}"
        rep_data = create_representation(
            project_name, project_code, folder_name, task_name,
            product_name, version, version_id,
            publish_templates,
            work_root,
            params["frame_start"],
            random.randint(params["frame_end_min"], params["frame_end_max"]),  # ruff: ignore[suspicious-non-cryptographic-random-usage]
            representation_name,
        )
        created = _create_entity(
            session, server_url, project_name, "representations", rep_data)
        printer(
            f"Created representation {representation_name} with "
            f"{len(rep_data['files'])} files"
        )
        representations.append(
            IdNamePair(name=representation_name, id=created["id"]))
    return representations


def _create_links(
        session: requests.Session,
        server_url: str,
        project_name: str,
        representations: list[IdNamePair],
        link_pairs: list[tuple[int, int, str]]) -> list[str]:
    """Link representations by index pairs; out-of-range pairs are skipped.

    Args:
        session: The HTTP session for server communication.
        server_url: The base URL of the AYON server.
        project_name: The name of the project.
        representations: The list of representations to link.
        link_pairs: A list of tuples containing input index, output
            index, and link name.

    Returns:
        list[str]: The IDs of the created links.

    """
    links = []
    for input_idx, output_idx, link_name in link_pairs:
        if max(input_idx, output_idx) >= len(representations):
            continue
        response = session.post(
            f"{server_url}/api/projects/{project_name}/links",
            json={
                "input": representations[input_idx].id,
                "output": representations[output_idx].id,
                "name": link_name,
                "link": _RELATIONSHIP_LINK_TYPE,
                "linkType": _RELATIONSHIP_LINK_TYPE,
                "data": {},
            },
        )
        assert response.status_code == STATUS_OK, response.json()
        links.append(response.json()["id"])
    return links


@pytest.fixture
def project(  # ruff: ignore[too-many-locals]
        printer: Callable[[Any], None],
        ayon_connection_env: tuple[str, str],
        project_anatomy: dict[str, Any],
        project_params: dict[str, Any]) -> Generator[ProjectInfo, None, None]:
    """Set up a project with some data and yield the project info.

    This will create a project with a folder, a task, a product, a version,
    and some representations. It will also create some links between the
    representations. The individual steps live in the `_create_*` helpers.

    Args:
        printer: The printer fixture.
        ayon_connection_env: The AYON connection environment fixture.
        project_anatomy: The resolved project anatomy.
        project_params: Parameters controlling the created entities.

    Yields:
        ProjectInfo: The project information.

    """
    server_url, api_key = ayon_connection_env
    token = secrets.token_hex(5)
    project_name = f"{token}_test_project"
    project_code = f"TP_{token[:3]}"
    folder_name = f"t_folder_{secrets.token_hex(3)}"
    product_name = project_params["product_name"]
    product_type = project_params["product_type"]
    version = project_params["version"]

    task_type = _pick_named_item_name(
        project_anatomy.get("task_types"),
        project_params["task_type"]) or project_params["task_type"]
    task_name = project_params["task_name"] or task_type

    folder_type = _pick_named_item_name(
        project_anatomy.get("folder_types"),
        project_params["folder_type"]) or project_params["folder_type"]

    printer(f"creating project {project_name}...")
    session = requests.Session()
    session.headers.update({"x-api-key": api_key})

    _create_project(session, server_url, {
        "name": project_name,
        "code": project_code,
        "anatomy": project_anatomy,
        "library": project_params["library"],
    })

    printer(f"filling project {project_name} with data...")
    folder_entity = _create_folder(
        session, server_url, project_name, folder_name, folder_type)
    printer(folder_entity)
    task_entity = _create_entity(
        session, server_url, project_name, "tasks", {
            "name": task_name,
            "taskType": task_type,
            "folderId": folder_entity["id"],
        })
    product_entity = _create_entity(
        session, server_url, project_name, "products", {
            "name": product_name,
            "folderId": folder_entity["id"],
            "productType": product_type,
        })
    version_entity = _create_entity(
        session, server_url, project_name, "versions", {
            "version": version,
            "productId": product_entity["id"],
            "taskId": task_entity["id"],
        })

    root_entry = _first_work_root(project_anatomy)
    representations = _create_representations(
        session, server_url, printer,
        project_name=project_name,
        project_code=project_code,
        folder_name=folder_name,
        task_name=task_name,
        product_name=product_name,
        version=version,
        version_id=version_entity["id"],
        anatomy=project_anatomy,
        params=project_params,
    )
    links = _create_links(
        session, server_url, project_name,
        representations, project_params["link_pairs"])

    yield ProjectInfo(
        project_name=project_name,
        project_code=project_code,
        project_root_folders=root_entry,
        folder=IdNamePair(name=folder_name, id=folder_entity["id"]),
        folder_entity=folder_entity,
        task=IdNamePair(name=task_name, id=task_entity["id"]),
        task_entity=task_entity,
        product=IdNamePair(name=product_name, id=product_entity["id"]),
        product_entity=product_entity,
        version=IdNamePair(name=f"v{version:03d}", id=version_entity["id"]),
        version_entity=version_entity,
        representations=representations,
        links=links
    )

    # teardown the project
    printer(f"tearing down project {project_name}...")
    response = session.delete(
        f"{server_url}/api/projects/{project_name}")
    assert response.status_code == STATUS_NO_CONTENT


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
    token = secrets.token_hex(5)

    values = {
        "project_name": project_name or f"{token}_test_project",
        "project_code": project_code or f"TP_{token[:3]}",
        "folder_types": folder_types,
        "task_types": task_types,
        "statuses": statuses,
    }

    # override default values with the given parameters
    if hasattr(request, "param"):
        values.update(request.param)

    printer(f'creating project {values["project_name"]}...')
    session = requests.Session()
    session.headers.update({"x-api-key": api_key})

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

    project_data: dict[str, Any] = {
        "name": values["project_name"],
        "code": values["project_code"],
        "anatomy": project_anatomy,
        "library": False
    }
    response = session.post(
        f"{server_url}/api/projects", json=project_data)
    assert response.status_code == STATUS_CREATED, response.text

    # due to the bug in AYON server, create `relationship` link type
    # TODO (antirotor): remove this once the bug is fixed
    response = session.put(
        (f'{server_url}/api/projects/{values["project_name"]}/links/types/'
         "relationship|representation|representation"),
        json={
            "data": {
                "color": "#73149F",
            }
        }
    )
    assert response.status_code == STATUS_NO_CONTENT

    yield ProjectInfo(
        project_name=values["project_name"],
        project_code=values["project_code"],
        project_root_folders=project_data["anatomy"]["roots"][0],
    )

    # teardown the project
    printer(f'tearing down project {values["project_name"]}...')
    response = session.delete(
        f'{server_url}/api/projects/{values["project_name"]}')
    assert response.status_code == STATUS_NO_CONTENT
