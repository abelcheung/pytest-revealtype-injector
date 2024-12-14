import pytest


def test_basic(pytester: pytest.Pytester):
    pytester.makeconftest(
        "pytest_plugins = ['pytest_revealtype_injector.plugin']"
    )

    pytester.makepyfile(  # pyright: ignore[reportUnknownMemberType]
        """
        import sys
        import pytest
        from typeguard import TypeCheckError

        if sys.version_info >= (3, 11):
            from typing import reveal_type
        else:
            from typing_extensions import reveal_type

        def test_inferred():
            x = 1
            reveal_type(x)

        def test_bad_inline_hint():
            x: str = 1  # type: ignore  # pyright: ignore
            with pytest.raises(TypeCheckError, match='is not an instance of str'):
                reveal_type(x)
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=2)
