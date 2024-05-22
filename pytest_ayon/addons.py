"""Fixtures for addons."""
import contextlib
import hashlib
import os
import subprocess
import time
from pathlib import Path

import pytest
import requests

from .utils import replace_string_in_file


@pytest.fixture(scope="session")
def imprint_test_version(project_root_path, addon_version):
    """Imprint a test version of the package.

    This fixture will replace the version in the package.py file
    with a test version. This is useful for testing the package
    on the server without affecting existing addon installations.

    Yields:
        str: The test version of the package.

    """
    root = project_root_path
    current_version = addon_version.version
    test_version = f"{current_version}-test+{hashlib.md5(os.urandom(32)).hexdigest()[:8]}"
    replace_string_in_file(
        (Path(root) / "package.py").as_posix(),
        f'version = "{current_version}"',
        f'version = "{test_version}"')

    yield test_version

    # revert back to the original version
    replace_string_in_file(
        (Path(root) / "package.py").as_posix(),
        f'version = "{test_version}"',
        f'version = "{current_version}"')


@pytest.fixture(scope="session")
def build_addon_package(
        printer_session,
        imprint_test_version,
        tmp_path,
        project_root_path):
    """Build the addon package.

    This fixture will build the addon package with the test version
    and return the test version and the path to the package.

    Args:
        printer_session (function): The printer function.
        imprint_test_version (str): The test version of the package.
        tmp_path (pathlib.Path): The temporary directory path.
        project_root_path (pathlib.Path): The project root path.

    Returns:
        tuple[str, pathlib.Path]: The test version and the path to the package.

    """
    printer_session("Building addon package ...")
    process = subprocess.Popen(
        [
            "python",
            (project_root_path / "create_package.py").as_posix(),
            "-o", tmp_path.as_posix()
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    stdout, stderr = process.communicate()
    printer_session(stdout.decode())
    printer_session(stderr.decode())

    assert process.returncode == 0, f"Script failed with return code: {process.returncode}"
    return imprint_test_version, tmp_path


def _wait_for_the_event(
        server_url: str, api_key: str, event_id: str,
        tries: int = 10, sleep: int = 6):
    """Wait for the event to finish.

    Args:
        server_url (str): The server URL.
        api_key (str): The API key.
        event_id (str): The event ID.
        tries (int): The number of tries.
        sleep (int): The sleep time.

    Returns:
        dict: The event data.

    """
    session = requests.Session()
    session.headers.update({'x-api-key': api_key})

    max_tries = tries
    try_count = 0

    response = None

    while try_count < max_tries:
        response = session.get(f"{server_url}/api/events/{event_id}")
        assert response.status_code == 200, f"Failed to get event: {response.text}"  # noqa: E501
        if response.json()["status"] == "finished":
            break
        time.sleep(sleep)
        try_count += 1

    assert response is not None, "Failed to get event"
    assert response.json()["status"] == "finished", f"Event status is not 'finished': {response.text}"  # noqa: E501
    return response.json()


def _wait_for_server_restart(server_url, api_key):
    """Wait for the server to restart.

    This will ask server and wait for the server to restart.
    """
    session = requests.Session()
    session.headers.update({'x-api-key': api_key})

    response = session.post(f"{server_url}/api/system/restart")
    assert response.status_code == 204, f"Failed to restart server: {response.text}"  # noqa: E501

    time.sleep(1)

    max_tries = 10

    for _ in range(max_tries):
        with contextlib.suppress(requests.exceptions.ConnectionError):
            response = session.get(f"{server_url}/api/info")
            # if motd is present, server is up
            if "version" in response.json():
                return True
        time.sleep(6)

    assert False, "Server did not restart after 60 seconds."


@pytest.fixture
def installed_addon(
        ayon_connection_env,
        ayon_server_session,
        build_addon_package,
        printer_session
):
    """Install and uninstall the addon.

    This fixture will install the addon, restart the server,
    yield, and then uninstall the addon.

    Args:
        ayon_connection_env (tuple[str, str]): The server URL and the API key.
        ayon_server_session (requests.Session): The server session.
        build_addon_package (tuple[str, pathlib.Path]): The test version and
            the path to the package.
        printer_session (function): The printer function.

    """
    server_url, api_key = ayon_connection_env
    session = ayon_server_session
    version, _ = build_addon_package

    printer_session("Installing addon ...")
    response = session.post(
        f"{server_url}/api/addons/install",
        json={
            "addonName": "ayon_usd",
            "addonVersion": version
        },
        files={
            "upload_file": open(
                build_addon_package[1] / f"ayon_usd-{version}.zip", "rb")
        }
    )
    assert response.status_code == 200,\
        f"Failed to install addon: {response.text}"

    event_id = response.json()["eventId"]

    # wait for server to install addon
    printer_session("Waiting for the install event to finish ...")
    _wait_for_the_event(server_url, api_key, event_id)

    # restart server
    printer_session("Restarting server ...")
    _wait_for_server_restart(server_url, api_key)

    printer_session("Checking installed addons for ayon_usd ...")
    response = session.get(f"{server_url}/api/addons/install")
    assert response.status_code == 200,\
        f"Failed to get installed addons: {response.text}"

    addon_names = [item["addonName"] for item in response.json()["items"]]
    assert "ayon_usd" in addon_names,\
        f"Addon 'ayon_usd' not found in installed addons: {addon_names}"

    yield version

    printer_session("Uninstalling addon ...")
