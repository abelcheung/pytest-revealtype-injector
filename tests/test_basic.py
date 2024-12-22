import pytest

# These tests are fragile. If return type is taken away from function (the
# "-> None" part), mypy will not complain about the type hint under non-strict
# mode. Instead, it infers a blanket type of "Any" for "x", which nullifies
# typeguard checking (no TypeCheckError raised). A crude guard against this
# situation is implemented inside revealtype_injector.

def test_basic(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
    pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
        """
        import sys
        import pytest
        from typeguard import TypeCheckError

        if sys.version_info >= (3, 11):
            from typing import reveal_type
        else:
            from typing_extensions import reveal_type

        def test_inferred() -> None:
            x = 1
            reveal_type(x)

        def test_bad_inline_hint() -> None:
            x: str = 1  # type: ignore[assignment]  # pyright: ignore[reportAssignmentType]
            with pytest.raises(TypeCheckError, match='is not an instance of str'):
                reveal_type(x)
        """
    )
    result = pytester.runpytest("--tb=short", "-v")
    result.assert_outcomes(passed=2)


def test_import_as(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
    pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
        """
        import sys
        import pytest
        from typeguard import TypeCheckError

        if sys.version_info >= (3, 11):
            from typing import reveal_type as rt
        else:
            from typing_extensions import reveal_type as rt

        def test_inferred() -> None:
            x = 1
            rt(x)

        def test_bad_inline_hint() -> None:
            x: str = 1  # type: ignore[assignment]  # pyright: ignore[reportAssignmentType]
            with pytest.raises(TypeCheckError, match='is not an instance of str'):
                rt(x)
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=2)


def test_import_module_as(pytester: pytest.Pytester) -> None:
    pytester.makeconftest("pytest_plugins = ['pytest_revealtype_injector.plugin']")
    pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
        """
        import sys
        import pytest
        from typeguard import TypeCheckError

        if sys.version_info >= (3, 11):
            import typing as t
        else:
            import typing_extensions as t

        def test_inferred() -> None:
            x = 1
            t.reveal_type(x)

        def test_bad_inline_hint() -> None:
            x: str = 1  # type: ignore[assignment]  # pyright: ignore[reportAssignmentType]
            with pytest.raises(TypeCheckError, match='is not an instance of str'):
                t.reveal_type(x)
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=2)
