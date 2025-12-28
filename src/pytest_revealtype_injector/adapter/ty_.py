from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from typing import cast

import schema as s

from ..log import get_logger
from ..models import (
    BareNameCollector,
    FilePos,
    TypeCheckerAdapter,
    TypeCheckerError,
    VarType,
)

if sys.version_info >= (3, 11):
    from typing import TypedDict
else:
    from typing_extensions import TypedDict

if sys.version_info >= (3, 14):
    from annotationlib import ForwardRef
else:
    from typing import ForwardRef

_logger = get_logger()


class _TyDiagPosition(TypedDict):
    line: int
    column: int


class _TyDiagRange(TypedDict):
    begin: _TyDiagPosition
    end: _TyDiagPosition


class _TyDiagLocation(TypedDict):
    path: str
    positions: _TyDiagRange


class _TyDiagItem(TypedDict):
    check_name: str
    description: str
    severity: str
    fingerprint: str
    location: _TyDiagLocation


class NameCollector(BareNameCollector):
    type_checker = "ty"


class TyAdapter(TypeCheckerAdapter):
    id = "ty"
    _executable = "ty"
    _type_mesg_re = re.compile(r'Revealed type: `(?P<type>.+?)`')
    _namecollector_class = BareNameCollector
    _schema = s.Schema({
        "check_name": str,
        "description": str,
        "severity": s.Or(
            s.Schema("info"),
            s.Schema("minor"),
            s.Schema("major"),
        ),
        "fingerprint": str,
        "location": {
            "path": str,
            "positions": {
                "begin": {"line": int, "column": int},
                "end"  : {"line": int, "column": int},
            }
        },
    })

    def run_typechecker_on(self, paths: Iterable[pathlib.Path]) -> None:
        if shutil.which(self._executable) is None:
            raise FileNotFoundError(f"{self._executable} is required to run test suite")

        cmd = [
            self._executable,
            "check",
            "--no-progress",
            "--output-format",
            "gitlab",
        ]
        cmd.extend(str(p) for p in paths)

        if self.config_file is not None:
            cmd.extend(["--config-file", str(self.config_file)])

        _logger.debug(f"({self.id}) Run command: {cmd}")
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode == 101:  # internal error
            raise TypeCheckerError(proc.stderr.decode(), None, None)

        report = json.loads(proc.stdout)
        _logger.info(
            "({}) Return code = {}, diagnostic count = {}.{}".format(
                self.id,
                proc.returncode,
                len(report),
                " pytest -vv shows all items." if self.log_verbosity < 2 else "",
            )
        )

        for item in report:
            diag = cast(_TyDiagItem, self._schema.validate(item))
            if self.log_verbosity >= 2:
                _logger.debug(f"({self.id}) {diag}")
            if diag["severity"] != ("major" if proc.returncode else "info"):
                continue
            match proc.returncode:
                case 1 | 2:
                    filename, lineno = (
                        pathlib.Path(diag["location"]["path"]).name,
                        diag["location"]["positions"]["begin"]["line"],
                    )
                    raise TypeCheckerError(
                        "{} error with exit code {}: {}".format(
                            self.id,
                            proc.returncode,
                            diag["description"],
                        ),
                        filename,
                        lineno,
                        diag["check_name"],
                    )
                case 0:
                    pass
                case _:  # Some future error code
                    raise TypeCheckerError(
                        "Unknown {} error with exit code {}: {}".format(
                            self.id,
                            proc.returncode,
                            proc.stderr.decode(),
                        ),
                        None,
                        None,
                    )

            filename, lineno = (
                pathlib.Path(diag["location"]["path"]).name,
                diag["location"]["positions"]["begin"]["line"],
            )            
            if (m := self._type_mesg_re.search(diag["description"])) is None:
                continue
            pos = FilePos(filename, lineno)
            self.typechecker_result[pos] = VarType(None, ForwardRef(m["type"]))

def generate_adapter() -> TypeCheckerAdapter:
    return TyAdapter()