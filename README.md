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
