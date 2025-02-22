from __future__ import annotations

from ..log import get_logger
from ..models import TypeCheckerAdapter
from . import pyright_

_logger = get_logger()


class NameCollector(pyright_.NameCollector):
    type_checker = "basedpyright"


class BasedPyrightAdapter(pyright_.PyrightAdapter):
    id = "basedpyright"
    _executable = "basedpyright"
    _namecollector_class = NameCollector


def generate_adapter() -> TypeCheckerAdapter:
    return BasedPyrightAdapter()
