# A pytest plugin for testing AYON

This plugin provides fixtures and helper functions to be used in various
test within AYON ecosystem.

## Installation

```shell
$ pip install pytest-ayon
```
or
```shell
$ uv add pytest-ayon
```

## Usage
In your test, import fixtures and helper functions from `pytest_ayon` module.

```python
from pytest_ayon import ayon_fixture, ayon_tool
```

`project` is now configurable through fixtures/indirect parameters:

- `project_anatomy_preset_name` (default `"__primary__"`)
- `project_anatomy_fallback_presets` (default `( "__builtin__", )`)
- `project_anatomy_overrides`
- `project_params`

Anatomy is resolved from server presets using:

- `GET /api/anatomy/presets/__primary__`
- fallback `GET /api/anatomy/presets/__builtin__`

If neither preset is available, a built-in local anatomy fallback is used
(a warning is logged).

The preferred preset can also be selected from the command line:

```shell
pytest --ayon-anatomy-preset=my_preset
```

Or per test via indirect parametrization:

```python
@pytest.mark.parametrize(
    "project_anatomy_preset_name", ["__builtin__"], indirect=True)
def test_something(project): ...
```

`project_anatomy_overrides` is deep-merged on top of the resolved anatomy.

Representations created by `project` are controlled through `project_params`:
`ext` (default `"exr"`), `template_name` (`"publish"` or `"hero"`) and the
frame range (`frame_start`, `frame_end_min`, `frame_end_max`; set
`frame_start` to `None` for single-file representations):

```python
@pytest.mark.parametrize("project_params", [
    {"template_name": "hero", "ext": "abc", "frame_start": None},
], indirect=True)
def test_hero_cache(project): ...
```

### Plain functions

The fixtures are thin wrappers around plain functions in `pytest_ayon.server`
(also exported from `pytest_ayon`). They have no pytest dependency, so you can
build fixtures of any scope on top of them:

- `create_session(api_key)`: `requests.Session` with the `x-api-key` header
- `resolve_anatomy(session, url, preset, fallbacks, overrides)`
- `create_project(session, url, anatomy, *, name=None, code=None, library=False)`
- `populate_project(session, url, project, anatomy, params=None)`: adds a
  folder, task, product, version, representations and links
  (`params` override `DEFAULT_PROJECT_PARAMS`)
- `delete_project(session, url, project_name)`
- `register_site(session, url, site_id, platform, *, hostname=None, version="0.0.0")`
- `unregister_site(session, url, site_id)` (requires an admin key)

They raise `AyonRequestError` when the server returns an unexpected status.

```python
import pytest
from pytest_ayon import (
    create_project, delete_project, populate_project, resolve_anatomy)


@pytest.fixture(scope="session")
def shared_project(ayon_server_session, ayon_connection_env):
    url, _ = ayon_connection_env
    anatomy = resolve_anatomy(ayon_server_session, url, "__builtin__")
    info = create_project(ayon_server_session, url, anatomy)
    try:
        yield populate_project(ayon_server_session, url, info, anatomy)
    finally:
        delete_project(ayon_server_session, url, info.project_name)
```
