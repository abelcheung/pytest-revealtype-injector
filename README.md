![PyPI - Version](https://img.shields.io/pypi/v/pytest-revealtype-injector)
![GitHub Release Date](https://img.shields.io/github/release-date/abelcheung/pytest-revealtype-injector)
![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fgithub.com%2Fabelcheung%2Fpytest-revealtype-injector%2Fraw%2Frefs%2Fheads%2Fmain%2Fpyproject.toml)
![PyPI - Wheel](https://img.shields.io/pypi/wheel/pytest-revealtype-injector)

`pytest-revealtype-injector` is a `pytest` plugin for replacing [`reveal_type()`](https://docs.python.org/3/library/typing.html#typing.reveal_type) calls inside test functions as something more sophisticated. It does the following tasks in parallel:

- Launch external static type checkers (`basesdpyright`, `pyright` and `mypy`) and store `reveal_type` results.
- Use [`typeguard`](https://github.com/agronholm/typeguard) to verify the aforementioned static type checker result _really_ matches runtime code result.

## Usage

In short: install this plugin, create test functions which calls `reveal_type()` with variable or function return result, done.

### The longer story

This plugin would be automatically enabled when launching `pytest`.

For using `reveal_type()` inside tests, there is no boiler plate code involved. Import `reveal_type` normally, like:

```python
from typing import reveal_type
```

If you care about compatibility with older pythons, use:

```python
import sys
if sys.version >= (3, 11):
    from typing import reveal_type
else:
    from typing_extensions import reveal_type
```

Just importing `typing` (or `typing_extensions`) module is fine too:

```python
import typing

def test_something():
    x: str = 1  # type: ignore  # pyright: ignore
    typing.reveal_type(x)  # typeguard fails here
```

Since this plugin scans for `reveal_type()` for replacement under carpet, even `import ... as ...` syntax works:

```python
import typing as typ  # or...
from typing import reveal_type as rt
```

### Limitations

But there are 2 caveats.

1. This plugin only searches for global import in test files, so local import inside test function doesn't work. That means following code doesn't utilize this plugin at all:

```python
def test_something():
    from typing import reveal_type
    x = 1
    reveal_type(x)  # calls vanilla reveal_type()
```

2. `reveal_type()` calls have to stay within a single line, although you can use `reveal_type` result in assertion or other purpose:

```python
x = "1"
assert reveal_type(str(int(x))) == x
```

## Logging

This plugin uses standard [`logging`](https://docs.python.org/3/library/logging.html) internally. `pytest -v` can be used to reveal `INFO` and `DEBUG` logs. Given following example:

```python
def test_superfluous(self) -> None:
    x: list[str] = ['a', 'b', 'c', 1]  # type: ignore  # pyright: ignore
    reveal_type(x)
```

Something like this will be shown as test result:

```
...
    raise TypeCheckError(f"is not an instance of {qualified_name(origin_type)}")
E   typeguard.TypeCheckError: item 3 is not an instance of str (from pyright)
------------------------------------------------------------- Captured log call -------------------------------------------------------------
INFO     revealtype-injector:hooks.py:26 Replaced reveal_type() from global import with <function revealtype_injector at 0x00000238DB923D00>
DEBUG    revealtype-injector:main.py:60 Extraction OK: code='reveal_type(x)', result='x'
========================================================== short test summary info ==========================================================
FAILED tests/runtime/test_attrib.py::TestAttrib::test_superfluous - typeguard.TypeCheckError: item 3 is not an instance of str (from pyright)
============================================================= 1 failed in 3.38s =============================================================
```


## History

This pytest plugin starts its life as part of testsuite related utilities within [`types-lxml`](https://github.com/abelcheung/types-lxml). As `lxml` is a `cython` project and probably never incorporate inline python annotation in future, there is need to compare runtime result to static type checker output for discrepancy. As time goes by, it starts to make sense to manage as an independent project.
