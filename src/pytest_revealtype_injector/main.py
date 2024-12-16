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

from . import adapter, log
from .models import (
    FilePos,
    TypeCheckerError,
    VarType,
)

_T = TypeVar("_T")

_logger = log.get_logger()


class RevealTypeExtractor(ast.NodeVisitor):
    target = None

    def visit_Call(self, node: ast.Call) -> Any:
        # HACK node.func is not necessarily "reveal_type" as we allow
        # "import as" syntax. We just assume the outmost call is
        # reveal_type(), and never descend into recursive ast.Call nodes.
        # IDEA Is it possible to retrieve the function name from
        # pytest_pyfunc_call() hook and store it in stash somewhere?
        self.target = node.args[0]
        return node


def _get_var_name(frame: inspect.Traceback) -> str | None:
    filename = pathlib.Path(frame.filename)
    if not filename.exists():
        _logger.warning(
            f"Stack frame points to file '{filename}' "
            "which doesn't exist on local system."
        )
    ctxt, idx = frame.code_context, frame.index
    assert ctxt is not None
    assert idx is not None
    code = ctxt[idx].strip()

    walker = RevealTypeExtractor()
    # TODO Use 'exec' mode which results in more complex AST but doesn't impose
    # as much restriction on test code as 'eval' mode does.
    walker.visit(ast.parse(code, mode="eval"))
    assert walker.target is not None
    result = ast.get_source_segment(code, walker.target)
    _logger.debug(f"Extraction OK: {code=}, {result=}")
    return result


def revealtype_injector(var: _T) -> _T:
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
    var_name = _get_var_name(caller)
    pos = FilePos(pathlib.Path(caller.filename).name, caller.lineno)

    globalns = caller_frame.f_globals
    localns = caller_frame.f_locals

    for adp in adapter.discovery():
        if not adp.enabled:
            continue
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
        try:
            _ = eval(ref.__forward_arg__, globalns, localns)
        except (TypeError, NameError):
            ref_ast = ast.parse(ref.__forward_arg__, mode="eval")
            walker = adp.create_collector(globalns, localns)
            new_ast = walker.visit(ref_ast)
            if walker.modified:
                ref = ForwardRef(ast.unparse(new_ast))
            memo = TypeCheckMemo(globalns, localns | walker.collected)
        else:
            memo = TypeCheckMemo(globalns, localns)

        try:
            check_type_internal(var, ref, memo)
        except TypeCheckError as e:
            # Only args[0] contains message
            e.args = (e.args[0] + f" (from {adp.id})",) + e.args[1:]
            raise

    return var
