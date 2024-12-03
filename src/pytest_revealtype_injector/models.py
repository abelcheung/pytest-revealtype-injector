from __future__ import annotations

import abc
import ast
import importlib
import pathlib
import re
from collections.abc import Iterable
from typing import (
    Any,
    ClassVar,
    ForwardRef,
    NamedTuple,
    cast,
)

import pytest
from schema import Schema


class FilePos(NamedTuple):
    file: str
    lineno: int


class VarType(NamedTuple):
    var: str | None
    type: ForwardRef


class TypeCheckerError(Exception):
    # Can be None when type checker dies before any code evaluation
    def __init__(self, message: str, filename: str | None, lineno: int | None) -> None:
        super().__init__(message)
        self._filename = filename
        self._lineno = lineno

    def __str__(self) -> str:
        if self._filename:
            return '"{}"{}: {}'.format(
                self._filename,
                " line " + str(self._lineno) if self._lineno else "",
                self.args[0],
            )
        else:
            return str(self.args[0])


class NameCollectorBase(ast.NodeTransformer):
    def __init__(
        self,
        globalns: dict[str, Any],
        localns: dict[str, Any],
    ) -> None:
        super().__init__()
        self._globalns = globalns
        self._localns = localns
        self.modified: bool = False
        # typing_extensions guaranteed to be present,
        # as a dependency of typeguard
        self.collected: dict[str, Any] = {
            m: importlib.import_module(m)
            for m in ("builtins", "typing", "typing_extensions")
        }

    def visit_Subscript(self, node: ast.Subscript) -> ast.expr:
        node.value = cast("ast.expr", self.visit(node.value))
        node.slice = cast("ast.expr", self.visit(node.slice))

        # When type reference is a stub-only specialized class
        # which don't have runtime support (e.g. lxml classes have
        # no __class_getitem__), concede by verifying
        # non-subscripted type.
        try:
            eval(ast.unparse(node), self._globalns, self._localns | self.collected)
        except TypeError as e:
            if "is not subscriptable" not in e.args[0]:
                raise
            # TODO Insert node.value dependent hook for extra
            # verification of subscript type
            self.modified = True
            return node.value
        else:
            return node


class TypeCheckerAdapter:
    enabled: bool = True
    config_file: ClassVar[pathlib.Path | None] = None
    # Subclasses need to specify default values for below
    id: ClassVar[str]
    # {('file.py', 10): ('var_name', 'list[str]'), ...}
    typechecker_result: ClassVar[dict[FilePos, VarType]]
    _type_mesg_re: ClassVar[re.Pattern[str]]
    _schema: ClassVar[Schema]

    @classmethod
    @abc.abstractmethod
    def run_typechecker_on(cls, paths: Iterable[pathlib.Path]) -> None: ...
    @classmethod
    @abc.abstractmethod
    def create_collector(
        cls, globalns: dict[str, Any], localns: dict[str, Any]
    ) -> NameCollectorBase: ...
    @classmethod
    @abc.abstractmethod
    def set_config_file(cls, config: pytest.Config) -> None: ...
    @staticmethod
    @abc.abstractmethod
    def add_pytest_option(group: pytest.OptionGroup) -> None: ...
