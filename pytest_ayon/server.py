"""Plain helpers for talking to an AYON server from tests.

These functions do not depend on pytest, so fixtures of any scope (or
plain scripts) can build on them. The fixtures in `pytest_ayon.plugin`
are thin wrappers around them.

"""
from __future__ import annotations

import copy
import logging
import random
import secrets
import socket
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

from .utils import (
    STATUS_CREATED,
    STATUS_NO_CONTENT,
    STATUS_OK,
    create_representation,
)

log = logging.getLogger(__name__)

PLATFORMS = ("windows", "linux", "darwin")

DEFAULT_PROJECT_PARAMS: dict[str, Any] = {
    "product_name": "renderMain",
    "product_type": "render",
    "version": 1,
    "task_name": "rendering",
    "task_type": "rendering",
    "folder_type": "Asset",
    "representation_count": 4,
    "representation_name_prefix": "exr",
    "ext": "exr",
    "template_name": "publish",
    # `None` creates single-file representations without a frame range
    "frame_start": 1001,
    "frame_end_min": 1020,
    "frame_end_max": 1200,
    "link_pairs": [(0, 1, "relationship_2"), (2, 3, "relationship_1")],
    "library": False,
}

_RELATIONSHIP_LINK_TYPE = "relationship|representation|representation"


class AyonRequestError(RuntimeError):
    """Raised when the AYON server returns an unexpected status code."""


def _check(response: requests.Response, expected: int) -> requests.Response:
    """Raise `AyonRequestError` unless the response has `expected` status.

    Returns:
        requests.Response: The checked response.

    Raises:
        AyonRequestError: If the status code does not match.

    """
    if response.status_code != expected:
        msg = (
            f"{response.request.method} {response.url} returned "
            f"{response.status_code} (expected {expected}): {response.text}"
        )
        raise AyonRequestError(msg)
    return response


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


def create_session(api_key: str) -> requests.Session:
    """Create an HTTP session authenticated with an API key.

    Args:
        api_key (str): The AYON API key.

    Returns:
        requests.Session: The authenticated session.

    """
    session = requests.Session()
    session.headers.update({"x-api-key": api_key})
    return session


def resolve_anatomy(
        session: requests.Session,
        server_url: str,
        preset: str = "__primary__",
        fallbacks: tuple[str, ...] = ("__builtin__",),
        overrides: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Resolve anatomy from server presets, with fallback to local defaults.

    Presets are tried in order (`preset`, then `fallbacks`); the first one
    available on the server wins. If none is, the built-in local anatomy is
    used and a warning is logged. `overrides` are merged recursively on top.

    Args:
        session (requests.Session): The authenticated HTTP session.
        server_url (str): The base URL of the AYON server.
        preset (str): The preferred anatomy preset name.
        fallbacks (tuple[str, ...]): Fallback anatomy preset names.
        overrides (Optional[dict[str, Any]]): Anatomy override data.

    Returns:
        dict[str, Any]: The resolved anatomy data.

    """
    seen: set[str] = set()
    anatomy: Optional[dict[str, Any]] = None

    for preset_name in (preset, *fallbacks):
        if preset_name in seen:
            continue
        seen.add(preset_name)
        anatomy = _fetch_anatomy_preset(session, server_url, preset_name)
        if anatomy is not None:
            break

    if anatomy is None:
        log.warning(
            "No anatomy preset available on server (tried %s); "
            "using built-in default anatomy.", sorted(seen))
        anatomy = _default_project_anatomy()

    if overrides:
        anatomy = _merge_dicts(anatomy, overrides)

    return anatomy


def create_project(  # ruff: ignore[too-many-arguments]
        session: requests.Session,
        server_url: str,
        anatomy: dict[str, Any],
        *,
        name: Optional[str] = None,
        code: Optional[str] = None,
        library: bool = False) -> ProjectInfo:
    """Create an empty project with the given anatomy.

    Also creates the `relationship` link type used by `populate_project`.

    Args:
        session (requests.Session): The authenticated HTTP session.
        server_url (str): The base URL of the AYON server.
        anatomy (dict[str, Any]): The project anatomy.
        name (Optional[str]): The project name; random if not given.
        code (Optional[str]): The project code; random if not given.
        library (bool): Whether to create a library project.

    Returns:
        ProjectInfo: The created project (no entities yet).

    """
    token = secrets.token_hex(5)
    name = name or f"{token}_test_project"
    code = code or f"TP_{token[:3]}"

    _check(session.post(f"{server_url}/api/projects", json={
        "name": name,
        "code": code,
        "anatomy": anatomy,
        "library": library,
    }), STATUS_CREATED)

    # due to the bug in AYON server, create `relationship` link type
    # TODO(antirotor): remove this once the bug is fixed
    _check(session.put(
        (f"{server_url}/api/projects/{name}"
         f"/links/types/{_RELATIONSHIP_LINK_TYPE}"),
        json={"data": {"color": "#73149F"}},
    ), STATUS_NO_CONTENT)

    return ProjectInfo(
        project_name=name,
        project_code=code,
        project_root_folders=_first_work_root(anatomy),
    )


def delete_project(
        session: requests.Session,
        server_url: str,
        project_name: str) -> None:
    """Delete a project.

    Args:
        session (requests.Session): The authenticated HTTP session.
        server_url (str): The base URL of the AYON server.
        project_name (str): The name of the project to delete.

    """
    _check(session.delete(f"{server_url}/api/projects/{project_name}"),
           STATUS_NO_CONTENT)


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
    return _check(session.post(
        f"{server_url}/api/projects/{project_name}/{endpoint}",
        json=payload), STATUS_CREATED).json()


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
    return _check(session.get(
        f"{server_url}/api/projects/{project_name}/folders/{created['id']}"),
        STATUS_OK).json()


def _create_representations(  # ruff: ignore[too-many-arguments]
        session: requests.Session,
        server_url: str,
        *,
        project_name: str,
        project_code: str,
        folder_name: str,
        task_name: str,
        task_type: str,
        product_name: str,
        product_type: str,
        version: int,
        version_id: str,
        anatomy: dict[str, Any],
        params: dict[str, Any]) -> list[IdNamePair]:
    """Create representations for a version.

    Returns:
        list[IdNamePair]: The created representations.

    """
    root_entry = _first_work_root(anatomy)
    work_root = _work_root_path(root_entry)
    task_short = next(
        (item.get("shortName") or task_type
         for item in anatomy.get("task_types") or []
         if isinstance(item, dict) and item.get("name") == task_type),
        task_type)

    representations = []
    for i in range(1, params["representation_count"] + 1):
        representation_name = f"{params['representation_name_prefix']}_{i}"
        frame_start = params["frame_start"]
        frame_end = None if frame_start is None else random.randint(  # ruff: ignore[suspicious-non-cryptographic-random-usage]
            params["frame_end_min"], params["frame_end_max"])
        rep_data = create_representation(
            project_name, project_code, folder_name, task_name,
            product_name, version, version_id,
            anatomy.get("templates") or {},
            work_root,
            representation_name,
            template_name=params["template_name"],
            ext=params["ext"],
            frame_start=frame_start,
            frame_end=frame_end,
            root_name=root_entry["name"],
            product_type=product_type,
            task_type=task_type,
            task_short=task_short,
        )
        created = _create_entity(
            session, server_url, project_name, "representations", rep_data)
        log.debug(
            "Created representation %s with %d files",
            representation_name, len(rep_data["files"]))
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
        if not all(0 <= idx < len(representations)
                   for idx in (input_idx, output_idx)):
            continue
        response = _check(session.post(
            f"{server_url}/api/projects/{project_name}/links",
            json={
                "input": representations[input_idx].id,
                "output": representations[output_idx].id,
                "name": link_name,
                "link": _RELATIONSHIP_LINK_TYPE,
                "linkType": _RELATIONSHIP_LINK_TYPE,
                "data": {},
            },
        ), STATUS_OK)
        links.append(response.json()["id"])
    return links


def populate_project(
        session: requests.Session,
        server_url: str,
        project: ProjectInfo,
        anatomy: dict[str, Any],
        params: Optional[dict[str, Any]] = None) -> ProjectInfo:
    """Fill a project with folder, task, product, version, representations.

    Representations are linked according to `params["link_pairs"]`.

    Args:
        session (requests.Session): The authenticated HTTP session.
        server_url (str): The base URL of the AYON server.
        project (ProjectInfo): The project, as returned by `create_project`.
        anatomy (dict[str, Any]): The anatomy the project was created with.
        params (Optional[dict[str, Any]]): Overrides of
            `DEFAULT_PROJECT_PARAMS`.

    Returns:
        ProjectInfo: The project info with entity fields filled in.

    """
    params = {**DEFAULT_PROJECT_PARAMS, **(params or {})}
    project_name = project.project_name
    folder_name = f"t_folder_{secrets.token_hex(3)}"
    product_name = params["product_name"]
    product_type = params["product_type"]
    version = params["version"]

    task_type = _pick_named_item_name(
        anatomy.get("task_types"), params["task_type"]) or params["task_type"]
    task_name = params["task_name"] or task_type
    folder_type = _pick_named_item_name(
        anatomy.get("folder_types"),
        params["folder_type"]) or params["folder_type"]

    folder_entity = _create_folder(
        session, server_url, project_name, folder_name, folder_type)
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

    representations = _create_representations(
        session, server_url,
        project_name=project_name,
        project_code=project.project_code,
        folder_name=folder_name,
        task_name=task_name,
        task_type=task_type,
        product_name=product_name,
        product_type=product_type,
        version=version,
        version_id=version_entity["id"],
        anatomy=anatomy,
        params=params,
    )
    links = _create_links(
        session, server_url, project_name,
        representations, params["link_pairs"])

    project.folder = IdNamePair(name=folder_name, id=folder_entity["id"])
    project.folder_entity = folder_entity
    project.task = IdNamePair(name=task_name, id=task_entity["id"])
    project.task_entity = task_entity
    project.product = IdNamePair(name=product_name, id=product_entity["id"])
    project.product_entity = product_entity
    project.version = IdNamePair(
        name=f"v{version:03d}", id=version_entity["id"])
    project.version_entity = version_entity
    project.representations = representations
    project.links = links
    return project


def register_site(  # ruff: ignore[too-many-arguments]
        session: requests.Session,
        server_url: str,
        site_id: str,
        platform: str,
        *,
        hostname: Optional[str] = None,
        version: str = "0.0.0") -> dict[str, Any]:
    """Register (or update) a site for the current user.

    The server upserts a site when `GET /api/info` carries all of
    the `x-ayon-site-id`, `x-ayon-platform`, `x-ayon-hostname` and
    `x-ayon-version` headers. The session's own headers are not changed.

    Args:
        session (requests.Session): The authenticated HTTP session.
        server_url (str): The base URL of the AYON server.
        site_id (str): The site identifier.
        platform (str): One of `windows`, `linux`, `darwin`.
        hostname (Optional[str]): Machine hostname; current host if not given.
        version (str): Client (launcher) version reported for the site.

    Returns:
        dict[str, Any]: The site info as returned by the server.

    Raises:
        ValueError: If `platform` is not supported.
        AyonRequestError: If the server did not register the site.

    """
    if platform not in PLATFORMS:
        msg = f"platform must be one of {PLATFORMS}, got {platform!r}"
        raise ValueError(msg)
    response = _check(session.get(f"{server_url}/api/info", headers={
        "x-ayon-site-id": site_id,
        "x-ayon-platform": platform,
        "x-ayon-hostname": hostname or socket.gethostname(),
        "x-ayon-version": version,
    }), STATUS_OK)
    for site in response.json().get("sites") or []:
        if site.get("id") == site_id:
            return site
    msg = f"Site {site_id!r} not reported by server after registration"
    raise AyonRequestError(msg)


def unregister_site(
        session: requests.Session,
        server_url: str,
        site_id: str) -> None:
    """Unregister a site (requires an admin API key).

    Args:
        session (requests.Session): The authenticated HTTP session.
        server_url (str): The base URL of the AYON server.
        site_id (str): The site identifier.

    """
    # The server cleans up after the site in a background task; if that task
    # fails, uvicorn drops the keep-alive connection and the next request on
    # it fails. Don't let the session reuse this connection.
    _check(session.delete(
        f"{server_url}/api/system/sites/{site_id}",
        headers={"Connection": "close"}), STATUS_NO_CONTENT)
