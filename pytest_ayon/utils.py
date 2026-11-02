"""Package to hold utility functions used in tests."""
from __future__ import annotations

import hashlib
import random
import uuid
from pathlib import Path
from typing import Any, Optional

STATUS_OK = 200
STATUS_CREATED = 201
STATUS_NO_CONTENT = 204

TEMPLATE_NAMES = ("publish", "hero")


def _check_template_name(template_name: str) -> None:
    """Raise `ValueError` unless `template_name` is supported.

    Raises:
        ValueError: If `template_name` is not in `TEMPLATE_NAMES`.

    """
    if template_name not in TEMPLATE_NAMES:
        msg = (f"template_name must be one of {TEMPLATE_NAMES}, "
               f"got {template_name!r}")
        raise ValueError(msg)


def _frame_range(
        frame_start: Optional[int],
        frame_end: Optional[int]) -> Optional[range]:
    """Return the inclusive frame range, or None for a single file.

    Returns:
        Optional[range]: The frames, or None if no range is given.

    Raises:
        ValueError: If only one bound is given or the range is reversed.

    """
    if frame_start is None and frame_end is None:
        return None
    if frame_start is None or frame_end is None:
        msg = "frame_start and frame_end must be given together"
        raise ValueError(msg)
    if frame_end < frame_start:
        msg = f"frame_end ({frame_end}) is before frame_start ({frame_start})"
        raise ValueError(msg)
    return range(frame_start, frame_end + 1)


def create_file_list(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
        project_name: str,
        project_code: str,
        asset_name: str,
        product_name: str,
        version: int,
        ext: str,
        frame_start: Optional[int] = None,
        frame_end: Optional[int] = None,
        *,
        root_name: str = "work",
        product_type: str = "render",
        template_name: str = "publish") -> list[dict]:
    """Creates a list of file structures.

    One file per frame of the inclusive `frame_start`..`frame_end` range,
    or a single file without a frame number if no range is given.

    Args:
        project_name: Name of the project to be used in file names.
        project_code: Code of the project to be used in file names.
        asset_name: Name of the asset to be used in file names.
        product_name: Name of the product to be used in file names.
        version: Version number to be used in file names.
        ext: Extension to be used in file names.
        frame_start: Start frame of the range, or None for a single file.
        frame_end: End frame of the range (inclusive), or None.
        root_name: Name of the anatomy root used in file paths.
        product_type: Product type used in file paths.
        template_name: `publish` or `hero`; hero files use `hero`
            instead of the version in their paths and names.

    Returns:
        list: List of file structures.

    """
    _check_template_name(template_name)
    frames = _frame_range(frame_start, frame_end)
    version_part = "hero" if template_name == "hero" else f"v{version:03d}"
    base_name = f"{project_code}_{asset_name}_{product_name}_{version_part}"
    if frames is None:
        file_names = [f"{base_name}.{ext}"]
    else:
        file_names = [f"{base_name}.{frame:04d}.{ext}" for frame in frames]

    return [
        {
            "id": uuid.uuid4().hex,
            "name": file_name,
            "path": (
                f"{{root[{root_name}]}}/{project_name}/{asset_name}/publish"
                f"/{product_type}/{product_name}/{version_part}/{file_name}"),
            "size": random.randint(100000, 1000000),  # ruff: ignore[suspicious-non-cryptographic-random-usage]
            "hash": hashlib.md5(file_name.encode()).hexdigest(),  # ruff: ignore[hashlib-insecure-hash-function]
            "hashType": "md5"
        }
        for file_name in file_names
    ]


def _pick_template(
        templates: dict[str, Any], template_name: str) -> dict[str, str]:
    """Return the `default` entry of a template category, else the first.

    Returns:
        dict[str, str]: The template entry (`directory`, `file`, ...).

    Raises:
        ValueError: If the category is missing or empty.

    """
    entries = [
        entry for entry in templates.get(template_name) or []
        if isinstance(entry, dict)
    ]
    if not entries:
        msg = f"Anatomy defines no `{template_name}` templates"
        raise ValueError(msg)
    for entry in entries:
        if entry.get("name") == "default":
            return entry
    return entries[0]


def create_representation(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
        project_name: str,
        project_code: str,
        folder_name: str,
        task_name: str,
        product_name: str,
        version: int,
        version_id: str,
        templates: dict[str, Any],
        root_path: str,
        representation_name: str,
        *,
        template_name: str = "publish",
        ext: str = "exr",
        frame_start: Optional[int] = None,
        frame_end: Optional[int] = None,
        root_name: str = "work",
        product_type: str = "render",
        task_type: str = "Rendering",
        task_short: str = "rnd") -> dict:
    """Create representation data for `POST /projects/{name}/representations`.

    Args:
        project_name (str): The project name.
        project_code (str): The project code.
        folder_name (str): The folder name.
        task_name (str): The task name.
        product_name (str): The product name.
        version (int): The version number.
        version_id (str): The version ID.
        templates (dict[str, Any]): The anatomy `templates` section.
        root_path (str): The path of the root `root_name`.
        representation_name (str): The representation name.
        template_name (str): Template category to use, `publish` or `hero`.
        ext (str): The file extension (without the dot).
        frame_start (Optional[int]): Start frame; None for a single file.
        frame_end (Optional[int]): End frame (inclusive); None for a
            single file.
        root_name (str): The name of the anatomy root `root_path` belongs to.
        product_type (str): The product type.
        task_type (str): The task type.
        task_short (str): The task type short name.

    Returns:
        dict: The representation data.

    """
    _check_template_name(template_name)
    template = _pick_template(templates, template_name)
    file_list = create_file_list(project_name, project_code, folder_name,
                                 product_name, version, ext,
                                 frame_start, frame_end,
                                 root_name=root_name,
                                 product_type=product_type,
                                 template_name=template_name)

    context_data = {
        "ext": ext,
        "root": {
            root_name: root_path
        },
        "task": {
            "name": task_name,
            "type": task_type,
            "short": task_short
        },
        "user": "Test",
        "folder": {
            "name": folder_name,
        },
        "family": product_type,
        "product": {
            "name": product_name,
            "type": product_type
        },
        "project": {
            "code": project_code,
            "name": project_name
        },
        "version": version,
        "username": "Test",
        "hierarchy": "",
        "representation": ext
    }

    attrib: dict[str, Any] = {
        "template": f"{template['directory']}/{template['file']}",
    }
    if frame_start is not None:
        attrib["frameStart"] = frame_start
        attrib["frameEnd"] = frame_end

    return {
        "name": representation_name,
        "versionId": version_id,
        "files": file_list,
        "data": {
            "context": context_data,
        },
        "attrib": attrib,
    }


def replace_string_in_file(
        file_path: str, old_string: str, new_string: str) -> None:
    """Replace a string in a file.

    Args:
        file_path (str): The path to the file.
        old_string (str): The string to be replaced.
        new_string (str): The string to replace with.

    """
    file_data = Path(file_path).read_text(encoding="utf-8")

    # Replace the target string
    file_data = file_data.replace(old_string, new_string)

    # Write the file out again
    Path(file_path).write_text(file_data, encoding="utf-8")
