from __future__ import annotations

import ast
import importlib
import json
import pathlib
import re
from collections.abc import (
    Iterable,
)
from typing import (
    ForwardRef,
    Literal,
    TypedDict,
    cast,
)

import mypy.api
import schema as s

from ..log import get_logger
from ..models import (
    FilePos,
    NameCollectorBase,
    TypeCheckerAdapter,
    TypeCheckerError,
    VarType,
)

_logger = get_logger()


class _MypyDiagObj(TypedDict):
    file: str
    line: int
    column: int
    message: str
    hint: str | None
    code: str
    severity: Literal["note", "warning", "error"]


class NameCollector(NameCollectorBase):
    type_checker = "mypy"

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        prefix = ast.unparse(node.value)
        name = node.attr

        setattr(node.value, "is_parent", True)
        if not hasattr(node, "is_parent"):  # Outmost attribute node
            try:
                _ = importlib.import_module(prefix)
            except ModuleNotFoundError:
                # Mypy resolve names according to external stub if
                # available. For example, _ElementTree is determined
                # as lxml.etree._element._ElementTree, which doesn't
                # exist in runtime. Try to resolve bare names
                # instead, which rely on runtime tests importing
                # them properly before resolving.
                try:
                    eval(name, self._globalns, self._localns | self.collected)
                except NameError as e:
                    raise NameError(f'Cannot resolve "{prefix}" or "{name}"') from e
                else:
                    self.modified = True
                    return ast.Name(id=name, ctx=node.ctx)

        _ = self.visit(node.value)

        if resolved := getattr(self.collected[prefix], name, False):
            code = ast.unparse(node)
            self.collected[code] = resolved
            _logger.debug(
                f"{self.type_checker} NameCollector resolved '{code}' as {resolved}"
            )
            return node

        # For class defined in local scope, mypy just prepends test
        # module name to class name. Of course concerned class does
        # not exist directly under test module. Use bare name here.
        try:
            eval(name, self._globalns, self._localns | self.collected)
        except NameError:
            raise
        else:
            self.modified = True
            return ast.Name(id=name, ctx=node.ctx)

    # Mypy usually dumps full inferred type with module name,
    # but with a few exceptions (like tuple, Union).
    # visit_Attribute can ultimately recurse into visit_Name
    # as well
    def visit_Name(self, node: ast.Name) -> ast.Name:
        name = node.id
        try:
            eval(name, self._globalns, self._localns | self.collected)
        except NameError:
            pass
        else:
            return node

        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError:
            pass
        else:
            self.collected[name] = mod
            _logger.debug(
                f"{self.type_checker} NameCollector resolved '{name}' as {mod}"
            )
            return node

        if hasattr(self.collected["typing"], name):
            obj = getattr(self.collected["typing"], name)
            self.collected[name] = obj
            _logger.debug(
                f"{self.type_checker} NameCollector resolved '{name}' as {obj}"
            )
            return node

        raise NameError(f'Cannot resolve "{name}"')

    # For class defined inside local function scope, mypy outputs
    # something like "test_elem_class_lookup.FooClass@97".
    # Return only the left operand after processing.
    def visit_BinOp(self, node: ast.BinOp) -> ast.expr:
        if isinstance(node.op, ast.MatMult) and isinstance(node.right, ast.Constant):
            return cast("ast.expr", self.visit(node.left))
        # For expression that haven't been accounted for, just don't
        # process and allow name resolution to fail
        return node


class MypyAdapter(TypeCheckerAdapter):
    id = "mypy"
    _executable = ""  # unused, calls mypy.api.run() here
    _type_mesg_re = re.compile(r'Revealed type is "(?P<type>.+?)"')
    _namecollector_class = NameCollector
    _schema = s.Schema({
        "file": str,
        "line": int,
        "column": int,
        "message": str,
        "hint": s.Or(str, s.Schema(None)),
        "code": s.Or(str, s.Schema(None)),
        "severity": s.Or(
            s.Schema("note"),
            s.Schema("warning"),
            s.Schema("error"),
        ),
    })

    def run_typechecker_on(self, paths: Iterable[pathlib.Path]) -> None:
        mypy_args = [
            "--output=json",
        ]
        if self.config_file is not None:
            if self.config_file == pathlib.Path():
                cfg_str = ""  # see preprocess_config_file() below
            else:
                cfg_str = str(self.config_file)
            mypy_args.append(f"--config-file={cfg_str}")

        mypy_args.extend(str(p) for p in paths)

        _logger.debug(f"({self.id}) api.run(): {mypy_args}")
        stdout, stderr, returncode = mypy.api.run(mypy_args)

        # fatal error, before evaluation happens
        # mypy prints text output to stderr, not json
        if stderr:
            raise TypeCheckerError(stderr, None, None)

        lines = stdout.splitlines()
        _logger.info(
            "({}) Return code = {}, diagnostic count = {}.{}".format(
                self.id,
                returncode,
                len(lines),
                " pytest -vv shows all items." if self.log_verbosity < 2 else "",
            )
        )

        # So-called mypy json output is merely a line-by-line
        # transformation of plain text output into json object
        for line in lines:
            if len(line) <= 2 or line[0] != "{":
                continue
            if self.log_verbosity >= 2:
                _logger.debug(f"({self.id}) {line}")
            obj = json.loads(line)
            diag = cast(_MypyDiagObj, self._schema.validate(obj))
            filename = pathlib.Path(diag["file"]).name
            pos = FilePos(filename, diag["line"])
            # HACK: Never trust return code from mypy. During early 1.11.x
            # versions, mypy always return 1 for JSON output even when
            # there's no error. Later on mypy command line has fixed this,
            # but not mypy.api.run(), as of 1.13.
            if diag["severity"] != "note":
                raise TypeCheckerError(
                    "{} {} with exit code {}: {}".format(
                        self.id, diag["severity"], returncode, diag["message"]
                    ),
                    diag["file"],
                    diag["line"],
                    diag["code"],
                )
            if (m := self._type_mesg_re.fullmatch(diag["message"])) is None:
                continue
            # Mypy can insert extra character into expression so that it
            # becomes invalid and unparsable. 0.9x days there
            # was '*', and now '?' (and '=' for typeddict too).
            # Try stripping those character and pray we get something
            # usable for evaluation
            expression = m["type"].translate({ord(c): None for c in "*?="})
            try:
                # Unlike pyright, mypy output doesn't contain variable name
                self.typechecker_result[pos] = VarType(None, ForwardRef(expression))
            except SyntaxError as e:
                if (
                    m := re.fullmatch(r"<Deleted '(?P<var>.+)'>", expression)
                ) is not None:
                    raise TypeCheckerError(
                        "{} does not support reusing deleted variable '{}'".format(
                            self.id, m["var"]
                        ),
                        diag["file"],
                        diag["line"],
                    ) from e
                raise TypeCheckerError(
                    f"Cannot parse type expression '{expression}'",
                    diag["file"],
                    diag["line"],
                ) from e

    def preprocess_config_file(self, path_str: str) -> bool:
        if path_str:
            return False
        # HACK: when path_str is empty string, use no config file
        # ('mypy --config-file=')
        # The special value is for satisfying typing constraint;
        # it will be treated specially in run_typechecker_on()
        self.config_file = pathlib.Path()
        self._logger.info(f"({self.id}) Config file usage forbidden")
        return True


def generate_adapter() -> TypeCheckerAdapter:
    return MypyAdapter()
