from __future__ import annotations

from ..models import TypeCheckerAdapter
from . import basedpyright_, mypy_, pyright_


# Hardcode will do for now, it's not like we're going to have more
# adapters soon. Pyre and PyType are not there yet.
def generate() -> set[TypeCheckerAdapter]:
    return {
        basedpyright_.generate_adapter(),
        pyright_.generate_adapter(),
        mypy_.generate_adapter(),
    }


def get_adapter_classes() -> list[type[TypeCheckerAdapter]]:
    return [
        basedpyright_.BasedPyrightAdapter,
        pyright_.PyrightAdapter,
        mypy_.MypyAdapter,
    ]
