![PyPI - Version](https://img.shields.io/pypi/v/pytest-revealtype-injector)
![GitHub Release Date](https://img.shields.io/github/release-date/abelcheung/pytest-revealtype-injector)
![Python Version from PEP 621 TOML](https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fgithub.com%2Fabelcheung%2Fpytest-revealtype-injector%2Fraw%2Frefs%2Fheads%2Fmain%2Fpyproject.toml)
![PyPI - Wheel](https://img.shields.io/pypi/wheel/pytest-revealtype-injector)

`pytest-revealtype-injector` is a `pytest` plugin for replacing [`reveal_type()`](https://docs.python.org/3/library/typing.html#typing.reveal_type) calls inside test functions as something more sophisticated. It does the following tasks in parallel:

- Launch external static type checkers (`pyright` and `mypy`) and store `reveal_type` results.
- Use [`typeguard`](https://github.com/agronholm/typeguard) to verify the aforementioned static type checker result _really_ matches runtime code result.

## Usage

In short: install this plugin, create test functions which calls `reveal_type()` with variable or function return result, done.

### The longer story

This plugin would be automatically enabled when launching `pytest`.

For using `reveal_type()` inside tests, there is no boiler plate code involved. Import `reveal_type` normally, like:

```python
from typing import reveal_type
```

Just importing `typing` module is fine too (or import `typing_extensions` for Python 3.10, because `reveal_type()` is only available officially since 3.11):

```python
import typing

def test_something():
    x: str = 1  # type: ignore  # pyright: ignore
    typing.reveal_type(x)  # typeguard fails here
```

Since this plugin scans for `reveal_type()` for replacement under carpet, even `import ... as ...` syntax works too:

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

2. `reveal_type()` calls have to stay in a single line, without anything else. This limitation comes from using [`eval` mode in AST parsing](https://docs.python.org/3/library/ast.html#ast.Expression).

## History

This pytest plugin starts its life as part of testsuite related utilities within [`types-lxml`](https://github.com/abelcheung/types-lxml). As `lxml` is a `cython` project and probably never incorporate inline python annotation in future, there is need to compare runtime result to static type checker output for discrepancy. As time goes by, it starts to make sense to manage as an independent project.
