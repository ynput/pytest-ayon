"""Test configuration: load `.env` and register the plugin."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        os.environ.setdefault(key, value.strip().strip("'\""))


_load_dotenv(ROOT / ".env")


def pytest_configure(config: pytest.Config) -> None:
    """Register the plugin when the package is not installed."""
    config.addinivalue_line(
        "markers", "live: requires a live AYON server (see .env.example)")
    if not config.pluginmanager.has_plugin("ayon"):
        from pytest_ayon import plugin
        config.pluginmanager.register(plugin, "ayon")


def pytest_collection_modifyitems(
        config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip live tests when server credentials are missing."""
    if os.getenv("AYON_SERVER_URL") and os.getenv("AYON_API_KEY"):
        return
    skip = pytest.mark.skip(
        reason="AYON_SERVER_URL and AYON_API_KEY not set (.env)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
