from __future__ import annotations

import pytest


class TestAstExecMode:
    def test_return_result(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(
            """
            [tool.basedpyright]
            reportUnreachable = false
            """
        )
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            """
            import sys

            if sys.version_info >= (3, 11):
                from typing import reveal_type
            else:
                from typing_extensions import reveal_type

            def test_result_int() -> None:
                x = 1
                assert reveal_type(x) == 0 + 1

            def test_result_str() -> None:
                x = "foo"
                if hasattr(x, "lower"):
                    assert reveal_type(x.lower()) is not None
            """
        )
        result = pytester.runpytest("--tb=short", "-v")
        result.assert_outcomes(passed=2)

    def test_nested_call(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(
            """
            [tool.basedpyright]
            reportUnreachable = false
            """
        )
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            """
            import sys

            if sys.version_info >= (3, 11):
                from typing import reveal_type as rt
            else:
                from typing_extensions import reveal_type as rt

            def test_inner_call() -> None:
                x = 42
                assert int(rt(str(x).upper())) == x

            def test_outer_call() -> None:
                x = "42"
                assert rt(str(int(x)).upper()) == x
            """
        )
        result = pytester.runpytest("--tb=short", "-v")
        result.assert_outcomes(passed=2)
