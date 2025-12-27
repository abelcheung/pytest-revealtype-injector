from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
from collections.abc import (
    Iterable,
)
from typing import (
    ForwardRef,
    Literal,
    cast,
)

if sys.version_info >= (3, 11):
    from typing import NotRequired, TypedDict
else:
    from typing_extensions import NotRequired, TypedDict

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


class _PyrightDiagPosition(TypedDict):
    line: int
    character: int


class _PyrightDiagRange(TypedDict):
    start: _PyrightDiagPosition
    end: _PyrightDiagPosition


class _PyrightDiagItem(TypedDict):
    file: str
    severity: Literal["information", "warning", "error"]
    message: str
    range: _PyrightDiagRange
    rule: NotRequired[str]


class NameCollector(BareNameCollector):
    type_checker = "pyright"


class PyrightAdapter(TypeCheckerAdapter):
    id = "pyright"
    _executable = "pyright"
    _type_mesg_re = re.compile('Type of "(?P<var>.+?)" is "(?P<type>.+?)"')
    _namecollector_class = NameCollector
    # We only care about diagnostic messages that contain type information, that
    # is, items under "generalDiagnostics" key. Metadata not validated here.
    _schema = s.Schema({
        "file": str,
        "severity": s.Or(
            s.Schema("information"),
            s.Schema("warning"),
            s.Schema("error"),
        ),
        "message": str,
        "range": {
            "start": {"line": int, "character": int},
            "end": {"line": int, "character": int},
        },
        s.Optional("rule"): str,
    })

    def run_typechecker_on(self, paths: Iterable[pathlib.Path]) -> None:
        cmd: list[str] = []
        if shutil.which(self._executable) is not None:
            cmd.append(self._executable)
        elif shutil.which("npx") is not None:
            cmd.extend(["npx", self._executable])
        else:
            raise FileNotFoundError(f"{self._executable} is required to run test suite")

        cmd.append("--outputjson")
        if self.config_file is not None:
            cmd.extend(["--project", str(self.config_file)])
        cmd.extend(str(p) for p in paths)

        _logger.debug(f"({self.id}) Run command: {cmd}")
        proc = subprocess.run(cmd, capture_output=True)
        if len(proc.stderr):
            raise TypeCheckerError(proc.stderr.decode(), None, None)

        report = json.loads(proc.stdout)
        _logger.info(
            "({}) Return code = {}, diagnostic count = {}.{}".format(
                self.id,
                proc.returncode,
                len(report["generalDiagnostics"]),
                " pytest -vv shows all items." if self.log_verbosity < 2 else "",
            )
        )

        for item in report["generalDiagnostics"]:
            diag = cast(_PyrightDiagItem, self._schema.validate(item))
            if self.log_verbosity >= 2:
                _logger.debug(f"({self.id}) {diag}")
            if diag["severity"] != ("error" if proc.returncode else "information"):
                continue
            # Pyright report lineno is 0-based, while
            # python frame lineno is 1-based
            lineno = diag["range"]["start"]["line"] + 1
            filename = pathlib.Path(diag["file"]).name
            if proc.returncode:
                assert "rule" in diag
                raise TypeCheckerError(
                    "{} {} with exit code {}: {}".format(
                        self.id, diag["severity"], proc.returncode, diag["message"]
                    ),
                    filename,
                    lineno,
                    diag["rule"],
                )
            if (m := self._type_mesg_re.fullmatch(diag["message"])) is None:
                continue
            pos = FilePos(filename, lineno)
            self.typechecker_result[pos] = VarType(m["var"], ForwardRef(m["type"]))


def generate_adapter() -> TypeCheckerAdapter:
    return PyrightAdapter()
