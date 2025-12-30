from __future__ import annotations

from ..models import TypeCheckerAdapter
from . import (
    basedpyright_,
    mypy_,
    pyrefly_,
    pyright_,
    ty_,
)


# Hardcode will do for now, it's not like we're going to have more
# adapters rapidly or make it user extensible.
def generate() -> set[TypeCheckerAdapter]:
    return {
        basedpyright_.generate_adapter(),
        mypy_.generate_adapter(),
        pyrefly_.generate_adapter(),
        pyright_.generate_adapter(),
        ty_.generate_adapter(),
    }


def get_adapter_classes() -> list[type[TypeCheckerAdapter]]:
    return [
        basedpyright_.BasedPyrightAdapter,
        mypy_.MypyAdapter,
        pyrefly_.PyreflyAdapter,
        pyright_.PyrightAdapter,
        ty_.TyAdapter,
    ]
