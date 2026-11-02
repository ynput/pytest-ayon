"""Pytest plugin for Ayon."""
from .addons import build_addon_package, imprint_test_version, installed_addon
from .plugin import (
                     ProjectInfo,
                     addon_version,
                     ayon_connection_env,
                     ayon_server_session,
                     base_dir,
                     project,
                     project_anatomy,
                     project_anatomy_fallback_presets,
                     project_anatomy_overrides,
                     project_anatomy_preset_name,
                     project_params,
                     project_root_path,
                     session_tmp_path,
)
from .server import (
                     DEFAULT_PROJECT_PARAMS,
                     AyonRequestError,
                     IdNamePair,
                     create_project,
                     create_session,
                     delete_project,
                     populate_project,
                     register_site,
                     resolve_anatomy,
                     unregister_site,
)

__all__ = [
                     "DEFAULT_PROJECT_PARAMS",
                     "AyonRequestError",
                     "IdNamePair",
                     "ProjectInfo",
                     "addon_version",
                     "ayon_connection_env",
                     "ayon_server_session",
                     "base_dir",
                     "build_addon_package",
                     "create_project",
                     "create_session",
                     "delete_project",
                     "imprint_test_version",
                     "installed_addon",
                     "populate_project",
                     "project",
                     "project_anatomy",
                     "project_anatomy_fallback_presets",
                     "project_anatomy_overrides",
                     "project_anatomy_preset_name",
                     "project_params",
                     "project_root_path",
                     "register_site",
                     "resolve_anatomy",
                     "session_tmp_path",
                     "unregister_site",
]

__version__ = "0.1.1"
__author__ = "YNPUT, s.r.o. <team@ynput.io>"
__title__ = "pytest-ayon"
__homepage__ = "https://github.com/ynput/pytest-ayon"
