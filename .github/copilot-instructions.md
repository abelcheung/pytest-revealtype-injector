<!-- Short, targeted instructions for AI coding agents working on this repo -->
# pytest-revealtype-injector — Copilot instructions

## Overview
- Purpose: this repo is a pytest plugin that replaces `reveal_type()` calls in test code with a runtime wrapper that verifies static type-checker results (pyright/basedpyright, mypy, ty) against runtime types via `typeguard`.

## Big Picture (High-Level Architecture)
- Hooks entry points: `src/pytest_revealtype_injector/hooks.py` — registers pytest hooks and injects the replacement `reveal_type` into test modules.
- Runtime wrapper: `src/pytest_revealtype_injector/main.py::revealtype_injector` — extracts the expression, consults adapters, and uses `typeguard` to validate runtime vs static results.
- Adapters: `src/pytest_revealtype_injector/adapter/*` — adapter per checker (`pyright_.py`, `basedpyright_.py`, `mypy_.py`, `ty_.py`). Each adapter implements `TypeCheckerAdapter` in `models.py` and populates `typechecker_result` keyed by `FilePos`.
- Models & collectors: `src/pytest_revealtype_injector/models.py` contains `NameCollector`/`NameCollectorBase` logic used to evaluate or rewrite type expressions before `eval`/`typeguard` checks.

## Important Workflows & Commands
- Run tests: use `pytest -vv` from repository root. Tests use `pytester` fixtures that create temporary test projects; example tests call `pytester.runpytest("--tb=short", "-vv")`.
- External tools required for full test coverage: install the type checkers you intend to exercise — `pyright` (or `npx pyright` / `basedpyright`), `mypy` (python package), and `ty` if you want that adapter tested. Missing executables cause adapters to raise `FileNotFoundError`.
- Configure adapters: tests set per-adapter configs in temporary `pyproject.toml` (see tests/test_import.py).

## CLI options
  - `--revealtype-disable-adapter` to globally disable an adapter
  - per-adapter config option: `--revealtype-<adapter_id>-config` (see `models.TypeCheckerAdapter.longopt_for_config`).

## Project-Specific Conventions & Patterns
- Global-import-only detection: the plugin only recognizes `reveal_type` when imported at module/global scope. Local imports inside test functions are ignored (see README limitations).
- One-line reveal_type: extraction uses AST on the source context line; multi-line `reveal_type(...)` expressions are not supported.
- Adapter message parsing: adapters parse checker-specific output using regexes and JSON schemas. `pyright` provides variable name info sometimes; `mypy` usually does not — the code handles both cases (see `main.py` and `models.py`).
- Name collection: adapters use AST transformers (`NameCollector*`) to replace or collect runtime names so `eval` can succeed. Check `models.NameCollectorBase` and adapter-specific collectors.

## Name collection / Collector transforms
- Purpose: adapters may receive type expressions from static checkers that contain names or attributes not resolvable at runtime (stub-only symbols, module-qualified names, or mypy's synthesized names). The project uses `NameCollector` transformers to either provide runtime objects for those names or rewrite the AST so `eval()` can succeed.
- Core building block: `NameCollectorBase` (`src/pytest_revealtype_injector/models.py`) provides:
  - a pre-seeded `collected` dict with `builtins`, `typing`, and `typing_extensions` modules for evaluation.
  - `collected` is copied per instance and populated when missing names are encountered.
  - `modified` flag indicates when the transformer rewrote the AST (used to switch to a modified `ForwardRef`).
- Simple case (pyright & `BareNameCollector`): `BareNameCollector` (used by `pyright`/`ty`) tries to `eval(name)` and, if missing, will look up and register common typing names (e.g. `List`, `Union`) so that expressions like `list[str]` can be evaluated without importing the library runtime symbols.
- Complex case (mypy): `mypy` often emits fully-qualified module paths or synthesized names. Its `NameCollector` implements:
  - `visit_Attribute`: attempt to import the attribute prefix; if the module doesn't exist at runtime, try to resolve the bare name and, if successful, replace the attribute expression with a `Name` node.
  - `visit_Name`: resolve bare names by checking runtime globals, imports, and `typing` helpers; register resolved modules/objects into `collected`.
  - `visit_BinOp`: handle mypy-specific constructs (e.g. `@97` suffixes for local classes) and union syntax by selectively rewriting or leaving nodes.
- How adapters use collectors: adapters call `create_collector(globalns, localns)`, then attempt `eval(ref.__forward_arg__, globalns, localns | walker.collected)`. If `eval` fails, they parse the expression into an AST, run the walker (`walker.visit(...)`) and, when `walker.modified` is true, replace the `ForwardRef` with the rewritten `ast.unparse(new_ast)` before re-evaluating.
- Why this matters: collector transforms let tests evaluate type expressions that refer to
  - runtime-only symbols (registered into `collected`),
  - stub-only names (rewritten into simpler forms), and
  - mypy's mangled local-class names (stripped to the bare local name).


## Where to Look for Quick Edits or Fixes
- Replace/extend adapter behavior: `src/pytest_revealtype_injector/adapter/*.py` and `src/pytest_revealtype_injector/models.py` (NameCollector logic).
- Hook behavior & CLI options: `src/pytest_revealtype_injector/hooks.py` (markers, stash usage, monkeypatching reveal_type).
- Extraction / comparison logic: `src/pytest_revealtype_injector/main.py`.
- Logging: `src/pytest_revealtype_injector/log.py` — verbosity mapping to pytest verbosity.

## Examples (Copyable Snippets)
- Disable adapter in a test via marker:

```py
@pytest.mark.notypechecker("mypy")
def test_foo():
    reveal_type(x)
```

- Disable multiple adapters in a test via marker:

```py
@pytest.mark.notypechecker("pyright", "basedpyright")
def test_multiple_disabled():
  reveal_type(x)
```

- Run pytest with verbose output to see typechecker logs:

```bash
pytest -vv
```

## Notes for AI Agents
- Do not change public APIs unless necessary; follow existing patterns in `TypeCheckerAdapter` subclasses.
- When adding a new adapter, ensure you implement `generate_adapter()` returning the adapter instance and register parsing logic consistent with the other adapters.
- Tests assume ability to execute external checkers; mock or gate tests that call adapters when adding CI automation.

If anything here is unclear or you want sections expanded (examples of collector transforms, adapter debug workflow, or test-run instructions), tell me what to expand. 
