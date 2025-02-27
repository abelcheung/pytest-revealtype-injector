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
from _pytest.config import Notset
from schema import Schema

from .log import get_logger


class FilePos(NamedTuple):
    file: str
    lineno: int


class VarType(NamedTuple):
    var: str | None
    type: ForwardRef


class TypeCheckerError(Exception):
    # Can be None when type checker dies before any code evaluation
    def __init__(
        self,
        message: str,
        filename: str | None,
        lineno: int | None,
        rule: str | None = None,
    ) -> None:
        super().__init__(message)
        self._filename = filename
        self._lineno = lineno
        self._rule = rule

    def __str__(self) -> str:
        if self._filename:
            return '"{}"{}{}: {}'.format(
                self._filename,
                " line " + str(self._lineno) if self._lineno else "",
                ', violating "' + self._rule + '" rule' if self._rule else "",
                self.args[0],
            )
        else:
            return str(self.args[0])


class NameCollectorBase(ast.NodeTransformer):
    type_checker: ClassVar[str]
    # typing_extensions guaranteed to be present,
    # as a dependency of typeguard
    collected: dict[str, Any] = {
        m: importlib.import_module(m)
        for m in ("builtins", "typing", "typing_extensions")
    }

    def __init__(
        self,
        globalns: dict[str, Any],
        localns: dict[str, Any],
    ) -> None:
        super().__init__()
        self._globalns = globalns
        self._localns = localns
        self.modified: bool = False
        self.collected = type(self).collected.copy()

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
    # Subclasses need to specify default values for below
    id: ClassVar[str]
    _executable: ClassVar[str]
    _type_mesg_re: ClassVar[re.Pattern[str]]
    _schema: ClassVar[Schema]
    _namecollector_class: ClassVar[type[NameCollectorBase]]

    def __init__(self) -> None:
        # {('file.py', 10): ('var_name', 'list[str]'), ...}
        self.typechecker_result: dict[FilePos, VarType] = {}
        self._logger = get_logger()
        # logger level is already set by pytest_configure()
        # this only affects how much debug message is shown
        self.log_verbosity: int = 1
        self.enabled: bool = True
        self.config_file: pathlib.Path | None = None

    @classmethod
    def longopt_for_config(cls) -> str:
        return f"--revealtype-{cls.id}-config"

    @abc.abstractmethod
    def run_typechecker_on(self, paths: Iterable[pathlib.Path]) -> None: ...

    def create_collector(
        self, globalns: dict[str, Any], localns: dict[str, Any]
    ) -> NameCollectorBase:
        return self._namecollector_class(globalns, localns)

    def preprocess_config_file(self, path_str: str) -> bool:
        """Optional preprocessing of configuration file"""
        return False

    def set_config_file(self, config: pytest.Config) -> None:
        path_str = config.getoption(self.longopt_for_config())
        # pytest addoption() should have set default value
        # to None even when option is not specified
        assert not isinstance(path_str, Notset)

        if path_str is None:
            self._logger.info(f"({self.id}) Using default configuration")
            return

        if self.preprocess_config_file(path_str):
            return

        relpath = pathlib.Path(path_str)
        if relpath.is_absolute():
            raise ValueError(f"Path '{path_str}' must be relative to pytest rootdir")
        result = (config.rootpath / relpath).resolve()
        if not result.exists():
            raise FileNotFoundError(f"Path '{result}' not found")

        self._logger.info(f"({self.id}) Using config file at {result}")
        self.config_file = result

    @classmethod
    def add_pytest_option(cls, group: pytest.OptionGroup) -> None:
        group.addoption(
            cls.longopt_for_config(),
            type=str,
            default=None,
            metavar="RELATIVE_PATH",
            help=f"{cls.id} configuration file, path is relative to pytest "
            f"rootdir. If unspecified, use {cls.id} default behavior",
        )
