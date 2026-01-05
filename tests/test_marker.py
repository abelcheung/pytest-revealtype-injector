from __future__ import annotations

import textwrap

import pytest


class TestOnlyTypeCheckerMarker:
    PYPROJECT_TOML = """
    [tool.pyright]
    reportUnreachable = false
    """
    TEST_CONTENT = """
    import sys
    import pytest
    from typing import cast
    if sys.version_info >= (3, 11):
        from typing import reveal_type
    else:
        from typing_extensions import reveal_type

    # GLOBAL MARK

    def test_foo() -> None:
        MYPY = False
        if MYPY:
            x = 1
        else:
            x = cast(str, 1)  # pyright: ignore[reportInvalidCast]
        reveal_type(x)

    # CLASS MARK
    class TestFoo:
        # FUNC MARK
        def test_foo(self) -> None:
            MYPY = False
            if MYPY:
                x = 1
            else:
                x = cast(str, 1)  # pyright: ignore[reportInvalidCast]
            reveal_type(x)

        def test_foo2(self) -> None:
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
        result.assert_outcomes(passed=0, failed=3)

    def test_function_marker(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT.replace("# FUNC MARK", "@pytest.mark.onlytypechecker('mypy')")
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=1, failed=2)

    def test_class_marker(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT.replace("# CLASS MARK", "@pytest.mark.onlytypechecker('mypy')")
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=2, failed=1)

    def test_global_marker(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT.replace("# GLOBAL MARK", "pytestmark = pytest.mark.onlytypechecker('mypy')")
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=3, failed=0)


class TestNoTypeCheckerMarker:
    PYPROJECT_TOML = """
    [tool.pyright]
    reportUnreachable = false
    """
    TEST_CONTENT = """
    import sys
    import pytest
    from typing import cast
    if sys.version_info >= (3, 11):
        from typing import reveal_type
    else:
        from typing_extensions import reveal_type

    # GLOBAL MARK

    def test_foo() -> None:
        MYPY = False
        if MYPY:
            x = cast(str, 1)  # pyright: ignore[reportInvalidCast]
        else:
            x = 1
        reveal_type(x)

    # CLASS MARK
    class TestFoo:
        # FUNC MARK
        def test_foo(self) -> None:
            MYPY = False
            if MYPY:
                x = cast(str, 1)  # pyright: ignore[reportInvalidCast]
            else:
                x = 1
            reveal_type(x)

        def test_foo2(self) -> None:
            MYPY = False
            if MYPY:
                x = cast(str, 1)  # pyright: ignore[reportInvalidCast]
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
        result.assert_outcomes(passed=0, failed=3)

    def test_function_marker(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT.replace("# FUNC MARK", "@pytest.mark.notypechecker('mypy')")
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=1, failed=2)

    def test_class_marker(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT.replace("# CLASS MARK", "@pytest.mark.notypechecker('mypy')")
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=2, failed=1)

    def test_global_marker(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT.replace("# GLOBAL MARK", "pytestmark = pytest.mark.notypechecker('mypy')")
        )
        result = pytester.runpytest("--tb=short", "-vv")
        result.assert_outcomes(passed=3, failed=0)

class TestMarkerConflicts:
    PYPROJECT_TOML = """
    [tool.pyright]
    reportUnreachable = false
    """
    TEST_CONTENT = """
    import pytest

    # PLACEHOLDER
    def test_foo() -> None:
        pass
    """
    def test_typechecker_exclusive(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            textwrap.dedent(self.TEST_CONTENT).replace(
                "# PLACEHOLDER",
                "@pytest.mark.notypechecker('mypy')\n"
                "@pytest.mark.onlytypechecker('pyright')"
            )
        )
        result = pytester.runpytest("--tb=short", "-vv")
        assert result.ret == pytest.ExitCode.INTERNAL_ERROR
        result.assert_outcomes(passed=0, failed=0)

    def test_no_typechecker_left(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(self.PYPROJECT_TOML)
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.TEST_CONTENT.replace(
                "# PLACEHOLDER",
                "@pytest.mark.onlytypechecker()"
            )
        )
        result = pytester.runpytest("--tb=short", "-vv")
        assert result.ret == pytest.ExitCode.INTERNAL_ERROR
        result.assert_outcomes(passed=0, failed=0)
