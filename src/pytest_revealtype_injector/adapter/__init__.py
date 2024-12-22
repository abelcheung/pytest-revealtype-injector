from __future__ import annotations

from ..models import TypeCheckerAdapter
from . import basedpyright_, mypy_, pyright_


# Hardcode will do for now, it's not like we're going to have more
# adapters soon. Pyre and PyType are not there yet.
def discovery() -> set[TypeCheckerAdapter]:
    return {
        basedpyright_.adapter,
        pyright_.adapter,
        mypy_.adapter,
    }
