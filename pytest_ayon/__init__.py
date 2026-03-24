"""Pytest plugin for Ayon."""
from .addons import build_addon_package, imprint_test_version, installed_addon
from .plugin import (
                     ProjectInfo,
                     addon_version,
                     project_anatomy,
                     project_anatomy_fallback_presets,
                     project_anatomy_overrides,
                     project_anatomy_preset_name,
                     project_params,
                     ayon_connection_env,
                     ayon_server_session,
                     base_dir,
                     project,
                     project_root_path,
)

__all__ = [
                     "ProjectInfo",
                     "addon_version",
                     "ayon_connection_env",
                     "ayon_server_session",
                     "base_dir",
                     "build_addon_package",
                     "imprint_test_version",
                     "installed_addon",
                     "project_anatomy",
                     "project_anatomy_fallback_presets",
                     "project_anatomy_overrides",
                     "project_anatomy_preset_name",
                     "project_params",
                     "project",
                     "project_root_path",
]

__version__ = "0.1.1"
__author__ = "YNPUT, s.r.o. <team@ynput.io>"
__title__ = "pytest-ayon"
__homepage__ = "https://github.com/ynput/pytest-ayon"
