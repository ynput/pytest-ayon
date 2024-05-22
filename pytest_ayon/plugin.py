"""Ayon plugin for pytest.

Some of the fixtures in this module require the AYON server to be running.
You need to set the AYON_SERVER_URL and AYON_API_KEY environment variables.

TODO:
    - Add more fixtures.
    - Modularize the fixtures.
    - Use ayon_python_api functions than REST API calls.

"""
import contextlib
import os
import random
import secrets
from collections import namedtuple
from dataclasses import dataclass
from typing import List

import pytest
import requests

from .utils import create_representation


@dataclass
class IdNamePair(object):
    id: str
    name: str


@dataclass
class ProjectInfo(object):
    project_name: str
    project_code: str
    project_root_folders: dict[str, str]
    folder: IdNamePair
    task: IdNamePair
    product: IdNamePair
    version: IdNamePair
    representations: List[IdNamePair]
    links: List[str]


@pytest.fixture(scope="session")
def tmp_path(tmp_path_factory):
    """Get the temporary directory path."""
    return tmp_path_factory.mktemp("data")


@pytest.fixture(scope="session")
def project_root_path(request):
    """Get the repository root path."""
    return request.config.rootpath


@pytest.fixture
def base_dir():
    """
    Provides the path to the base directory.
    """
    return os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(scope="session")
def ayon_connection_env():
    """Get the server URL and the API key."""
    os.environ["AYON_SERVER_URL"] = os.getenv("AYON_SERVER_URL")
    os.environ["AYON_API_KEY"] = os.getenv("AYON_API_KEY")
    return os.environ["AYON_SERVER_URL"], os.environ["AYON_API_KEY"]


@pytest.fixture(scope="session")
def ayon_server_session(ayon_connection_env):
    """Get the server session."""
    _, api_key = ayon_connection_env
    session = requests.Session()
    session.headers.update({'x-api-key': api_key})
    return session


@pytest.fixture(scope="session")
def addon_version(project_root_path):
    """Get the version of the addon.

    Returns:
        AddonVersion: The addon version and name.

    """
    version = None
    name = None
    with contextlib.suppress(FileNotFoundError):
        with open(project_root_path / "package.py") as file:
            for line in file:
                if line.startswith("version"):
                    version = line.split("=")[1].strip().strip("\"")
                    continue
                if line.startswith("name"):
                    name = line.split("=")[1].strip().strip("\"")
                    continue
    return namedtuple("AddonVersion", ["name", "version"])(name, version)


@pytest.fixture
def project(printer, ayon_connection_env) -> pytest.fixture:
    """Set up a project with some data and yield the project info.

    This will create a project with a folder, a task, a product, a version,
    and some representations. It will also create some links between the
    representations.

    Todo: split this fixture into smaller fixtures. Make it more modular.

    Args:
        printer: The printer fixture.
        ayon_connection_env: The AYON connection environment fixture.

    """
    server_url, api_key = ayon_connection_env
    _token = secrets.token_hex(5)
    project_name = f"{_token}_test_project"
    project_code = f"TP_{_token[:3]}"
    folder_name = f"t_folder_{secrets.token_hex(3)}"
    product_name = "renderMain"
    version = 1
    task_name = "rendering"
    representation_name = "exr"

    printer(f"creating project {project_name}...")
    session = requests.Session()
    session.headers.update({'x-api-key': api_key})

    project_data = {
        "name": project_name,
        "code": project_code,
        "anatomy": {
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
                        "directory": "{root[work]}/{project[name]}/{hierarchy}/{folder[name]}/work/{task[name]}",
                        "file": "{project[code]}_{folder[name]}_{task[name]}_{@version}<_{comment}>.{ext}"
                    }
                ],
                "publish": [
                    {
                        "name": "default",
                        "directory": "{root[work]}/{project[name]}/{hierarchy}/{folder[name]}/publish/{product[type]}/{product[name]}/v{version:0>3}",
                        "file": "{project[code]}_{folder[name]}_{product[name]}_v{version:0>3}<_{output}><.{frame:0>4}><_{udim}>.{ext}"
                    }
                ],
                "hero": [
                    {
                        "name": "default",
                        "directory": "{root[work]}/{project[name]}/{hierarchy}/{folder[name]}/publish/{product[type]}/{product[name]}/hero",
                        "file": "{project[code]}_{folder[name]}_{task[name]}_hero<_{comment}>.{ext}"
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
        },
        "library": False
    }
    response = session.post(
        f"{server_url}/api/projects", json=project_data)
    assert response.status_code == 201

    # due to the bug in AYON server, create `relationship` link type
    # TODO: remove this once the bug is fixed
    response = session.put(
        (f"{server_url}/api/projects/{project_name}/links/types/"
         "relationship|representation|representation"),
        json={
            "data": {
                "color": "#73149F",
            }
        }
    )
    assert response.status_code == 204

    # fill project with some data
    # Create a folder
    printer(f"filling project {project_name} with data...")
    response = session.post(
        f"{server_url}/api/projects/{project_name}/folders", json={
            "name": folder_name,
            "folderType": "Asset",
        })
    assert response.status_code == 201
    folder_id = response.json()["id"]

    # Create a task
    response = session.post(
        f"{server_url}/api/projects/{project_name}/tasks", json={
            "name": task_name,
            "taskType": "rendering",
            "folderId": folder_id,
        })
    assert response.status_code == 201
    task_id = response.json()["id"]

    # Create a product
    response = session.post(
        f"{server_url}/api/projects/{project_name}/products",
        json={
            "name": product_name,
            "folderId": folder_id,
            "productType": "render",
        })
    assert response.status_code == 201
    product_id = response.json()["id"]

    # Create a version
    response = session.post(
        f"{server_url}/api/projects/{project_name}/versions", json={
            "version": version,
            "productId": product_id,
            "taskId": task_id,
        })
    assert response.status_code == 201
    version_id = response.json()["id"]

    # Create a representations
    representations = []
    for i in range(1, 5):
        representation_name = f"exr_{i}"
        rep_data = create_representation(
            project_name, project_code, folder_name, task_name,
            product_name, version, version_id,
            project_data["anatomy"]["templates"]["publish"],
            project_data["anatomy"]["roots"][0]["windows"],
            1001, random.randint(1020, 1200), representation_name
        )

        response = session.post(
            f"{server_url}/api/projects/{project_name}/representations",
            json=rep_data)
        assert response.status_code == 201
        printer(
            f"Created representation {representation_name} with "
            f"{len(rep_data['files'])} files"
        )
        representations.append(IdNamePair(
            name=representation_name, id=response.json()["id"]))

    # links
    links = []

    # link first representation to the second one
    response = session.post(
        f"{server_url}/api/projects/{project_name}/links",
        json={
            "input": representations[0].id,
            "output": representations[1].id,
            "name": "relationship_2",
            "link": "relationship|representation|representation",
            "linkType": "relationship|representation|representation",
            "data": {}
        }
    )
    assert response.status_code == 200, response.json()
    links.append(response.json()["id"])

    # link second representation to the third one
    response = session.post(
        f"{server_url}/api/projects/{project_name}/links",
        json={
            "input": representations[2].id,
            "output": representations[3].id,
            "name": "relationship_1",
            "link": "relationship|representation|representation",
            "linkType": "relationship|representation|representation",
            "data": {}
        }
    )
    assert response.status_code == 200, response.json()
    links.append(response.json()["id"])

    yield ProjectInfo(
        project_name=project_name,
        project_code=project_code,
        project_root_folders=project_data["anatomy"]["roots"][0],
        folder=IdNamePair(name=folder_name, id=folder_id),
        task=IdNamePair(name=task_name, id=task_id),
        product=IdNamePair(name=product_name, id=product_id),
        version=IdNamePair(name=f"v{version:03d}", id=version_id),
        representations=representations,
        links=links
    )

    # teardown the project
    printer(f"tearing down project {project_name}...")
    response = session.delete(
        f"{server_url}/api/projects/{project_name}")
    assert response.status_code == 204
