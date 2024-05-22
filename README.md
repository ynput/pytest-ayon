# A pytest plugin for testing AYON

This plugin provides fixtures and helper functions to be used in various
test within AYON ecosystem.

## Installation

```shell
$ pip install pytest-ayon
```
or
```shell
$ poetry add --dev pytest-ayon
```

## Usage
In your test, import fixtures and helper functions from `pytest_ayon` module.

```python
from pytest_ayon import ayon_fixture, ayon_tool
```