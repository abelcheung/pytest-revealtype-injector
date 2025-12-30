from __future__ import annotations

import ast
import json
import pathlib
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from typing import ForwardRef, Literal, TypedDict, cast

if sys.version_info >= (3, 11):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

import schema as s

from ..log import get_logger
from ..models import (
    BareNameCollector,
    FilePos,
    TypeCheckerAdapter,
    TypeCheckerError,
    VarType,
)

_logger = get_logger()


class _PyreflyDiagItem(TypedDict):
    line: int
    column: int
    stop_line: int
    stop_column: int
    path: str
    code: int
    name: str
    description: str
    concise_description: str
    severity: Literal["error", "warn", "info"]


class NameCollector(BareNameCollector):
    type_checker = "pyrefly"

    # Pyrefly renders local class as Attribute nodes. Override to
    # only use bare names.
    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        self.modified = True
        # TODO should have been more robust by checking if node.value
        # resolves to a pytest function or method
        return ast.Name(id=node.attr, ctx=node.ctx)

class PyreflyAdapter(TypeCheckerAdapter):
    id = "pyrefly"
    _executable = "pyrefly"
    _type_mesg_re = re.compile(r'revealed type: (?P<type>.+)')
    _namecollector_class = NameCollector
    _schema = s.Schema({
        "line": int,
        "column": int,
        "stop_line": int,   
        "stop_column": int,
        "path": str,
        "code": int,
        "name": str,
        "description": str,
        "concise_description": str,
        "severity": s.Or(s.Schema("error"), s.Schema("warn"), s.Schema("info")),
    })

    def run_typechecker_on(self, paths: Iterable[pathlib.Path]) -> None:
        cmd: list[str] = []
        if shutil.which(self._executable) is not None:
            cmd.append(self._executable)
        else:
            raise FileNotFoundError(f"{self._executable} is required to run test suite")

        cmd.extend(["check", "--output-format", "json"])
        if True:  # TODO Needs to detect python version from project
            cmd.extend(["--python-version", "3.11"])
        cmd.extend(str(p) for p in paths)

        _logger.debug(f"({self.id}) Run command: {cmd}")
        proc = subprocess.run(cmd, capture_output=True)
        # Return code: 1=normal error, 2=facebook reserved, 3=internal error
        # Pyrefly unconditionally outputs error count to stderr regardless
        # of exit status
        if proc.returncode > 0:
            raise TypeCheckerError(
                "{} error with exit code {}: {}".format(self.id, proc.returncode, proc.stderr.decode()), None, None)

        try:
            report = json.loads(proc.stdout)
        except Exception as e:
            raise TypeCheckerError(f"Failed to parse pyrefly JSON output: {e}", None, None) from e

        assert isinstance(report, dict) and "errors" in report
        items = cast(list[_PyreflyDiagItem], report["errors"])

        _logger.info(
            "({}) Return code = {}, diagnostic count = {}.{}".format(
                self.id,
                proc.returncode,
                len(items),
                " pytest -vv shows all items." if self.log_verbosity < 2 else "",
            )
        )

        for item in items:
            diag = cast(_PyreflyDiagItem, self._schema.validate(item))
            if self.log_verbosity >= 2:
                _logger.debug(f"({self.id}) {diag}")

            if diag["name"] != "reveal-type":
                continue
            if (m := self._type_mesg_re.fullmatch(diag["description"])) is None:
                raise TypeCheckerError(
                    f"({self.id}) unexpected reveal-type message: {diag['description']}",
                    diag["path"],
                    diag["line"],
                )

            filename = pathlib.Path(diag["path"]).name
            lineno = diag["line"]
            pos = FilePos(filename, lineno)
            self.typechecker_result[pos] = VarType(None, ForwardRef(m["type"]))


def generate_adapter() -> TypeCheckerAdapter:
    return PyreflyAdapter()
