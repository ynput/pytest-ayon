# -*- coding: utf-8 -*-
"""Package to hold utility functions used in tests."""
import uuid
import hashlib
import random


def create_file_list(
        project_name: str, project_code: str, asset_name: str, product_name: str,
        version: int, ext: str, frame_start: int, frame_end: int) -> list[dict]:
    """Creates a list of file structures with the given project name and number of files

    Args:
        project_name: Name of the project to be used in file names.
        project_code: Code of the project to be used in file names.
        asset_name: Name of the asset to be used in file names.
        product_name: Name of the product to be used in file names.
        version: Version number to be used in file names.
        ext: Extension to be used in file names.
        frame_start: Start frame to use for the frame range.
        frame_end: End frame to use for the frame range.

    Returns:
        list: List of file structures.

    """
    files = []

    for frame in range(frame_start, frame_end):
        file_name = f"{project_code}_{asset_name}_{product_name}_v{version:03d}.{frame:04d}.{ext}"
        files.append({
            "id": uuid.uuid4().hex,
            "name": file_name,
            "path": f"{{root[work]}}/{project_name}/{asset_name}/publish/render/v{version:03d}/{file_name}",
            "size": random.randint(100000, 1000000),
            "hash": hashlib.md5(file_name.encode()).hexdigest(),
            "hashType": "md5"
        })
    return files


def create_representation(
        project_name, project_code, folder_name, task_name,
        product_name, version, version_id, publish_template, work_root,
        start_frame, end_frame, representation_name):
    """Create a representation file list.

    Args:
        project_name (str): The project name.
        project_code (str): The project code.
        folder_name (str): The folder name.
        task_name (str): The task name.
        product_name (str): The product name.
        version (int): The version number.
        version_id (str): The version ID.
        publish_template (str): The publishing template.
        work_root (str): The work root path.
        start_frame (int): The start frame.
        end_frame (int): The end frame.
        representation_name (str): The representation name.

    Returns:
        dict: The representation file list.

    """
    context_data = {
        "ext": "exr",
        "root": {
            "work": work_root
        },
        "task": {
            "name": task_name,
            "type": "Rendering",
            "short": "rnd"
        },
        "user": "Test",
        "folder": {
            "name": folder_name,
        },
        "family": "render",
        "product": {
            "name": product_name,
            "type": "render"
        },
        "project": {
            "code": project_code,
            "name": project_name
        },
        "version": version,
        "username": "Test",
        "hierarchy": "",
        "representation": "exr"
    }

    file_list = create_file_list(project_name, project_code, folder_name,
                                 product_name, version, "exr",
                                 start_frame, end_frame)

    return {
        "name": representation_name,
        "versionId": version_id,
        "files": file_list,
        "data": {
            "context": context_data,
        },
        "attrib": {
            "frameStart": start_frame,
            "frameEnd": end_frame,
            "template": publish_template[0]["directory"] + "/" +
                        publish_template[0]["file"],  # noqa
        }
    }


def replace_string_in_file(
        file_path: str, old_string: str, new_string: str):
    """Replace a string in a file.

    Args:
        file_path (str): The path to the file.
        old_string (str): The string to be replaced.
        new_string (str): The string to replace with.

    """
    with open(file_path, 'r') as file:
        file_data = file.read()

    # Replace the target string
    file_data = file_data.replace(old_string, new_string)

    # Write the file out again
    with open(file_path, 'w') as file:
        file.write(file_data)
