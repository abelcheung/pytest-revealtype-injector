from __future__ import annotations

import pytest


class TestFuncAndGlobalMarker:
    PYPROJECT_TOML = """
    [tool.pyright]
    reportUnreachable = false
    defineConstant = {"MYPY" = false}

    [tool.mypy]
    always_true = ["MYPY"]
    """
    TEST_CONTENT = """
    import sys
    import pytest
    from typing import cast
    if sys.version_info >= (3, 11):
        from typing import reveal_type
    else:
        from typing_extensions import reveal_type

    # pytestmark = pytest.mark.notypechecker('mypy')

    # @pytest.mark.notypechecker('mypy')
    def test_foo() -> None:
        MYPY = False
        if MYPY:
            x = cast(str, 1)  # type: ignore[assignment]
        else:
            x = 1
        reveal_type(x)
    """

    def test_vanilla(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=0, failed=1)

    def test_function_marker(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT.replace("# @pytest.mark", "@pytest.mark")
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=1, failed=0)

    def test_global_marker(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT.replace("# pytestmark", "pytestmark")
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=1, failed=0)


class TestClassMarker:
    PYPROJECT_TOML = """
    [tool.pyright]
    reportUnreachable = false
    defineConstant = {"MYPY" = false}

    [tool.mypy]
    always_true = ["MYPY"]
    """
    TEST_CONTENT = """
    import sys
    import pytest
    from typing import cast
    if sys.version_info >= (3, 11):
        from typing import reveal_type
    else:
        from typing_extensions import reveal_type

    # @pytest.mark.notypechecker('pyright', 'basedpyright', 'ty')
    class TestFoo:
        def test_foo(self) -> None:
            MYPY = False
            if MYPY:
                x = 1
            else:
                x = cast(str, 1)  # pyright: ignore[reportInvalidCast]
            reveal_type(x)
    """

    def test_vanilla(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=0, failed=1)

    def test_marker_applied(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT.replace("# @pytest.mark", "@pytest.mark")
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=1, failed=0)
