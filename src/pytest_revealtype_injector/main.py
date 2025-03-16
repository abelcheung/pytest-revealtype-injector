import ast
import inspect
import pathlib
import sys
from typing import (
    Any,
    ForwardRef,
    TypeVar,
)

from typeguard import (
    TypeCheckError,
    TypeCheckMemo,
    check_type_internal,
)

from . import log
from .models import (
    FilePos,
    TypeCheckerAdapter,
    TypeCheckerError,
    VarType,
)

_T = TypeVar("_T")
_logger = log.get_logger()


class RevealTypeExtractor(ast.NodeVisitor):
    def __init__(self, funcname: str | None = None) -> None:
        self._rt_funcname = funcname  # normally "reveal_type"
        self.target: ast.expr | None = None

    def visit_Call(self, node: ast.Call) -> Any:
        # If we don't know how reveal_type is called, just assume
        # it is the outmost call.
        if not self._rt_funcname:
            self.target = node.args[0]
            return node
        if ast.unparse(node.func).strip() == self._rt_funcname:
            self.target = node.args[0]
        else:
            self.generic_visit(node)


def _get_var_name(frame: inspect.Traceback, rt_funcname: str) -> str | None:
    filename = pathlib.Path(frame.filename)
    if not filename.exists():
        _logger.warning(
            f"Stack frame points to file '{filename}' "
            "which doesn't exist on local system."
        )
    # TODO is it possible to have multiline reveal_type()?
    ctxt, idx = frame.code_context, frame.index
    assert ctxt is not None
    assert idx is not None
    code = ctxt[idx].strip()

    walker = RevealTypeExtractor(rt_funcname)
    # 'exec' mode results in more complex AST but doesn't impose
    # as much restriction on test code as 'eval' mode does.
    walker.visit(ast.parse(code, mode="exec"))
    assert walker.target is not None
    result = ast.get_source_segment(code, walker.target)
    _logger.debug(f"Extraction OK: {code=}, {result=}")
    return result


def revealtype_injector(
    var: _T,
    adapters: set[TypeCheckerAdapter],
    rt_funcname: str,
) -> _T:
    """Replacement of `reveal_type()` that matches static and runtime type
    checking result

    This function is intended as a drop-in replacement of `reveal_type()` from
    Python 3.11 or `typing_extensions` module. Under the hook, it uses
    `typeguard` to get runtime variable type, and compare it with static type
    checker results for coherence.

    Usage
    -----
    No special handling is required. Just import `reveal_type` as usual in
    pytest test functions, and it will be replaced with this function behind the
    scene. However, since `reveal_type()` is not available in Python 3.10 or
    earlier, you need to import it conditionally, like this:

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
    caller_frame = sys._getframe(1)  # pyright: ignore[reportPrivateUsage]
    caller = inspect.getframeinfo(caller_frame)
    var_name = _get_var_name(caller, rt_funcname)
    pos = FilePos(pathlib.Path(caller.filename).name, caller.lineno)

    globalns = caller_frame.f_globals
    localns = caller_frame.f_locals

    for adp in adapters:
        try:
            tc_result = adp.typechecker_result[pos]
        except KeyError as e:
            raise TypeCheckerError(
                f"No inferred type from {adp.id}", pos.file, pos.lineno
            ) from e

        if tc_result.var:  # Only pyright has this extra protection
            if tc_result.var != var_name:
                raise TypeCheckerError(
                    f'Variable name should be "{tc_result.var}", but got "{var_name}"',
                    pos.file,
                    pos.lineno,
                )
        else:
            adp.typechecker_result[pos] = VarType(var_name, tc_result.type)

        ref = tc_result.type
        walker = adp.create_collector(globalns, localns)
        try:
            evaluated = eval(ref.__forward_arg__, globalns, localns | walker.collected)
        except (TypeError, NameError):
            old_ast = ast.parse(ref.__forward_arg__, mode="eval")
            new_ast = walker.visit(old_ast)
            if walker.modified:
                ref = ForwardRef(ast.unparse(new_ast))
            evaluated = eval(ref.__forward_arg__, globalns, localns | walker.collected)

        # HACK Mainly serves as a guard against mypy's behavior of blanket
        # inferring to Any when it can't determine the type under non-strict
        # mode. This behavior causes typeguard to remain silent, since Any is
        # compatible with everything. This has a side effect of disallowing
        # use of reveal_type() on data truly of Any type.
        if evaluated is Any:
            raise TypeCheckerError(
                f"Inferred type of '{var_name}' is Any, which "
                "defeats the purpose of type checking",
                pos.file,
                pos.lineno,
            )
        memo = TypeCheckMemo(globalns, localns | walker.collected)

        try:
            check_type_internal(var, ref, memo)
        except TypeCheckError as e:
            # Only args[0] contains message
            e.args = (e.args[0] + f" (from {adp.id})",) + e.args[1:]
            raise

    return var
