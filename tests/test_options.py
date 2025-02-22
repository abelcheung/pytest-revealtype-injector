from __future__ import annotations

import inspect

import pytest


class TestDisableTypeChecker:
    content_fail = inspect.cleandoc(
        """
        import sys
        import pytest
        from typeguard import TypeCheckError

        if sys.version_info >= (3, 11):
            from typing import reveal_type
        else:
            from typing_extensions import reveal_type

        def test_bad_inline_hint() -> None:
            x: str = 1  # {}
            with pytest.raises(TypeCheckError, match='is not an instance of str'):
                reveal_type(x)
        """
    )

    def _gen_pytest_opts(self, adapter: list[str]) -> list[str]:
        result = [f"--revealtype-disable-adapter={a}" for a in adapter]
        result.extend(["--tb=short", "-vv"])
        return result

    def test_disable_mypy_fail(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(
            """
            [tool.pyright]
            typeCheckingMode = 'strict'
            enableTypeIgnoreComments = false
            reportUnreachable = false
            reportUnusedCallResult = false
            """
        )
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.content_fail
        )
        opts = self._gen_pytest_opts(["mypy"])
        result = pytester.runpytest(*opts)
        assert result.ret == pytest.ExitCode.INTERNAL_ERROR
        result.assert_outcomes(passed=0, failed=0)

    def test_disable_mypy_pass(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(
            """
            [tool.pyright]
            typeCheckingMode = 'strict'
            enableTypeIgnoreComments = false
            reportUnreachable = false
            reportUnusedCallResult = false
            """
        )
        content_masked = self.content_fail.format(
            "pyright: ignore[reportAssignmentType]",
        )
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            content_masked
        )
        opts = self._gen_pytest_opts(["mypy"])
        result = pytester.runpytest(*opts)
        assert result.ret == pytest.ExitCode.OK
        result.assert_outcomes(passed=1, failed=0)

    def test_enable_mypy_only(self, pytester: pytest.Pytester) -> None:
        pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
        pytester.makepyprojecttoml(
            """
            [tool.mypy]
            strict = true
            """
        )
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            self.content_fail
        )
        opts = self._gen_pytest_opts(["basedpyright", "pyright"])
        result = pytester.runpytest(*opts)
        assert result.ret == pytest.ExitCode.INTERNAL_ERROR
        result.assert_outcomes(passed=0, failed=0)

        content_masked = self.content_fail.format("type: ignore[assignment]")
        pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
            content_masked
        )
        result = pytester.runpytest(*opts)
        assert result.ret == pytest.ExitCode.OK
        result.assert_outcomes(passed=1, failed=0)
