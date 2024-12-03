import ast
import json
import logging
import pathlib
import re
import shutil
import subprocess
from collections.abc import (
    Iterable,
)
from typing import (
    Any,
    ForwardRef,
    Literal,
    TypedDict,
    cast,
)

import pytest
import schema as s

from ..models import (
    FilePos,
    NameCollectorBase,
    TypeCheckerAdapter,
    TypeCheckerError,
    VarType,
)

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)


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


class _NameCollector(NameCollectorBase):
    # Pyright inferred type results always contain bare names only,
    # so don't need to bother with visit_Attribute()
    def visit_Name(self, node: ast.Name) -> ast.Name:
        name = node.id
        try:
            eval(name, self._globalns, self._localns | self.collected)
        except NameError:
            for m in ("typing", "typing_extensions"):
                if hasattr(self.collected[m], name):
                    self.collected[name] = getattr(self.collected[m], name)
                    return node
            raise
        return node


class _PyrightAdapter(TypeCheckerAdapter):
    id = "pyright"
    typechecker_result = {}
    _type_mesg_re = re.compile('^Type of "(?P<var>.+?)" is "(?P<type>.+?)"$')
    # We only care about diagnostic messages that contain type information.
    # Metadata not specified here.
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
    })

    @classmethod
    def run_typechecker_on(cls, paths: Iterable[pathlib.Path]) -> None:
        cmd: list[str] = []
        if shutil.which("pyright") is not None:
            cmd.append("pyright")
        elif shutil.which("npx") is not None:
            cmd.extend(["npx", "pyright"])
        else:
            raise FileNotFoundError("Pyright is required to run test suite")

        cmd.append("--outputjson")
        if cls.config_file is not None:
            cmd.extend(["--project", str(cls.config_file)])
        cmd.extend(str(p) for p in paths)

        proc = subprocess.run(cmd, capture_output=True)
        if len(proc.stderr):
            raise TypeCheckerError(proc.stderr.decode(), None, None)

        report = json.loads(proc.stdout)
        for item in report["generalDiagnostics"]:
            diag = cast(_PyrightDiagItem, cls._schema.validate(item))
            if diag["severity"] != ("error" if proc.returncode else "information"):
                continue
            # Pyright report lineno is 0-based, while
            # python frame lineno is 1-based
            lineno = diag["range"]["start"]["line"] + 1
            filename = pathlib.Path(diag["file"]).name
            if proc.returncode:
                raise TypeCheckerError(diag["message"], filename, lineno)
            if (m := cls._type_mesg_re.match(diag["message"])) is None:
                continue
            pos = FilePos(filename, lineno)
            cls.typechecker_result[pos] = VarType(m["var"], ForwardRef(m["type"]))

    @classmethod
    def create_collector(
        cls, globalns: dict[str, Any], localns: dict[str, Any]
    ) -> _NameCollector:
        return _NameCollector(globalns, localns)

    @classmethod
    def set_config_file(cls, config: pytest.Config) -> None:
        if (path_str := config.option.revealtype_pyright_config) is None:
            _logger.info("Using default pyright configuration")
            return

        relpath = pathlib.Path(path_str)
        if relpath.is_absolute():
            raise ValueError(f"Path '{path_str}' must be relative to pytest rootdir")
        result = (config.rootpath / relpath).resolve()
        if not result.exists():
            raise FileNotFoundError(f"Path '{result}' not found")

        _logger.info(f"Using pyright configuration file at {result}")
        cls.config_file = result

    @staticmethod
    def add_pytest_option(group: pytest.OptionGroup) -> None:
        group.addoption(
            "--revealtype-pyright-config",
            type=str,
            default=None,
            help="Pyright configuration file, path is relative to pytest rootdir. "
            "If unspecified, use pyright default behavior",
        )


adapter = _PyrightAdapter()
