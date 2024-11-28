import ast
import inspect
import logging
import pathlib
import sys
import typing as _t

from typeguard import TypeCheckError, TypeCheckMemo, check_type_internal

from .adapter import mypy_, pyright_
from .models import FilePos, TypeCheckerError, VarType

_T = _t.TypeVar("_T")

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.WARN)


class RevealTypeExtractor(ast.NodeVisitor):
    target = None

    def visit_Call(self, node: ast.Call) -> _t.Any:
        # Condition no more holds, as we allow importing reveal_type() or typing
        # module as any name
        # func_name = node.func
        # if isinstance(func_name, ast.Name) and func_name.id == "reveal_type":
        self.target = node.args[0]
        return self.generic_visit(node)


def _get_var_name(frame: inspect.Traceback) -> str | None:
    ctxt, idx = frame.code_context, frame.index
    assert ctxt is not None and idx is not None
    code = ctxt[idx].strip()

    walker = RevealTypeExtractor()
    walker.visit(ast.parse(code, mode="eval"))
    assert walker.target is not None
    return ast.get_source_segment(code, walker.target)


def reveal_type_wrapper(var: _T) -> _T:
    """Replacement of `reveal_type()` that matches static
    and runtime result

    This function is intended as a drop-in replacement of
    `reveal_type()`, replacing official one from Python 3.11
    or `typing_extensions` module. Under the hook, it uses
    `typeguard` to get runtime variable type, and compare it
    with static type checker results for coherence.

    Usage
    -----
    No special handling is required. Just import `reveal_type`
    as usual in pytest test functions, and it will be replaced
    with this function behind the scene. However, since
    `reveal_type()` is not available in Python 3.10 or earlier,
    you need to import it conditionally, like this:

        ```python
        if sys.version_info >= (3, 11):
            from typing import reveal_type
        else:
            from typing_extensions import reveal_type
        ```

    The signature is identical to official `reveal_type()`:
    returns input argument unchanged.

    Raises
    ------
    `TypeCheckerError`
        If static type checker failed to get inferred type
        for variable
    `typeguard.TypeCheckError`
        If type checker result doesn't match runtime result
    """
    # As a wrapper of typeguard.check_type_interal(),
    # get data from my caller, not mine
    caller_frame = sys._getframe(1)
    caller = inspect.getframeinfo(caller_frame)
    var_name = _get_var_name(caller)
    pos = FilePos(pathlib.Path(caller.filename).name, caller.lineno)

    globalns = caller_frame.f_globals
    localns = caller_frame.f_locals

    for adapter in (pyright_.adapter, mypy_.adapter):
        try:
            tc_result = adapter.typechecker_result[pos]
        except KeyError as e:
            raise TypeCheckerError(
                f"No inferred type from {adapter.id}", pos.file, pos.lineno
            ) from e

        if tc_result.var:  # Only pyright has this extra protection
            if tc_result.var != var_name:
                raise TypeCheckerError(
                    f'Variable name should be "{tc_result.var}", but got "{var_name}"',
                    pos.file,
                    pos.lineno,
                )
        else:
            adapter.typechecker_result[pos] = VarType(var_name, tc_result.type)

        ref = tc_result.type
        try:
            _ = eval(ref.__forward_arg__, globalns, localns)
        except NameError:
            ref_ast = ast.parse(ref.__forward_arg__, mode="eval")
            walker = adapter.create_collector(globalns, localns)
            new_ast = walker.visit(ref_ast)
            if walker.modified:
                ref = _t.ForwardRef(ast.unparse(new_ast))
            memo = TypeCheckMemo(globalns, localns | walker.collected)
        else:
            memo = TypeCheckMemo(globalns, localns)

        try:
            check_type_internal(var, ref, memo)
        except TypeCheckError as e:
            e.args = (f"({adapter.id}) " + e.args[0],) + e.args[1:]
            raise

    return var