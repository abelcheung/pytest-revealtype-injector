import ast
import importlib
import json
import logging
import pathlib
import re
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

import mypy.api
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


class _MypyDiagObj(TypedDict):
    file: str
    line: int
    column: int
    message: str
    hint: str | None
    code: str
    severity: Literal["note", "warning", "error"]


class _NameCollector(NameCollectorBase):
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
            self.collected[ast.unparse(node)] = resolved
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
            return node

        if hasattr(self.collected["typing"], name):
            self.collected[name] = getattr(self.collected["typing"], name)
            return node

        raise NameError(f'Cannot resolve "{name}"')

    # For class defined inside local function scope, mypy outputs
    # something like "test_elem_class_lookup.FooClass@97".
    # Return only the left operand after processing.
    def visit_BinOp(self, node: ast.BinOp) -> ast.expr:
        if isinstance(node.op, ast.MatMult) and isinstance(node.right, ast.Constant):
            # Mypy disallows returning Any
            return cast("ast.expr", self.visit(node.left))
        # For expression that haven't been accounted for, just don't
        # process and allow name resolution to fail
        return node


class _MypyAdapter(TypeCheckerAdapter):
    id = "mypy"
    typechecker_result = {}
    _type_mesg_re = re.compile(r'^Revealed type is "(?P<type>.+?)"$')
    _schema = s.Schema({
        "file": str,
        "line": int,
        "column": int,
        "message": str,
        "hint": s.Or(str, s.Schema(None)),
        "code": str,
        "severity": s.Or(
            s.Schema("note"),
            s.Schema("warning"),
            s.Schema("error"),
        ),
    })

    @classmethod
    def run_typechecker_on(cls, paths: Iterable[pathlib.Path]) -> None:
        mypy_args = [
            "--output=json",
        ]
        if cls.config_file is not None:
            cfg_str = str(cls.config_file)
            if cfg_str == ".":  # see set_config_file() below
                cfg_str = ""
            mypy_args.append(f"--config-file={cfg_str}")

        mypy_args.extend(str(p) for p in paths)

        stdout, stderr, returncode = mypy.api.run(mypy_args)

        # fatal error, before evaluation happens
        # mypy prints text output to stderr, not json
        if stderr:
            raise TypeCheckerError(stderr, None, None)

        # So-called mypy json output is merely a line-by-line
        # transformation of plain text output into json object
        for line in stdout.splitlines():
            obj = json.loads(line)
            diag = cast(_MypyDiagObj, cls._schema.validate(obj))
            filename = pathlib.Path(diag["file"]).name
            pos = FilePos(filename, diag["line"])
            if diag["severity"] != "note":
                raise TypeCheckerError(
                    "Mypy {} with exit code {}: {}".format(
                        diag["severity"], returncode, diag["message"]
                    ),
                    diag["file"],
                    diag["line"],
                )
            if (m := cls._type_mesg_re.match(diag["message"])) is None:
                continue
            # Mypy can insert extra character into expression so that it
            # becomes invalid and unparsable. 0.9x days there
            # was '*', and now '?' (and '=' for typeddict too).
            # Try stripping those character and pray we get something
            # usable for evaluation
            expression = m["type"].translate({ord(c): None for c in "*?="})
            try:
                # Unlike pyright, mypy output doesn't contain variable name
                cls.typechecker_result[pos] = VarType(None, ForwardRef(expression))
            except SyntaxError as e:
                if (
                    m := re.fullmatch(r"<Deleted '(?P<var>.+)'>", expression)
                ) is not None:
                    raise TypeCheckerError(
                        "{} does not support reusing deleted variable '{}'".format(
                            cls.id, m["var"]
                        ),
                        diag["file"],
                        diag["line"],
                    ) from e
                raise TypeCheckerError(
                    f"Cannot parse type expression '{expression}'",
                    diag["file"],
                    diag["line"],
                ) from e

    @classmethod
    def create_collector(
        cls, globalns: dict[str, Any], localns: dict[str, Any]
    ) -> _NameCollector:
        return _NameCollector(globalns, localns)

    @classmethod
    def set_config_file(cls, config: pytest.Config) -> None:
        # Mypy doesn't have a default config file
        if (path_str := config.option.revealtype_mypy_config) is None:
            _logger.info("Using default mypy configuration")
            return

        # HACK: when path_str is empty string, use no config file
        # ('mypy --config-file=')
        # Take advantage of pathlib.Path() behavior that empty string
        # is treated as current directory, which is not a valid
        # config file name, while satisfying typing constraint
        if not path_str:
            cls.config_file = pathlib.Path()
            return

        relpath = pathlib.Path(path_str)
        if relpath.is_absolute():
            raise ValueError(f"Path '{path_str}' must be relative to pytest rootdir")
        result = (config.rootpath / relpath).resolve()
        if not result.exists():
            raise FileNotFoundError(f"Path '{result}' not found")

        _logger.info(f"Using mypy configuration file at {result}")
        cls.config_file = result

    @staticmethod
    def add_pytest_option(group: pytest.OptionGroup) -> None:
        group.addoption(
            "--revealtype-mypy-config",
            type=str,
            default=None,
            help="Mypy configuration file, path is relative to pytest rootdir. "
            "If unspecified, use mypy default behavior",
        )


adapter = _MypyAdapter()
