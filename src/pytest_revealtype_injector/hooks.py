from __future__ import annotations

import functools
import inspect
from typing import cast

import pytest

from . import adapter, log
from .main import revealtype_injector
from .models import TypeCheckerAdapter

_logger = log.get_logger()
adapter_stash_key: pytest.StashKey[set[TypeCheckerAdapter]]


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> None:
    assert pyfuncitem.module is not None
    adapters = pyfuncitem.config.stash[adapter_stash_key].copy()

    for name in dir(pyfuncitem.module):
        if name.startswith("__") or name.startswith("@py"):
            continue

        item = getattr(pyfuncitem.module, name)
        if inspect.isfunction(item):
            if item.__name__ != "reveal_type" or item.__module__ not in {
                "typing",
                "typing_extensions",
            }:
                continue
            injected = functools.partial(
                revealtype_injector,
                adapters=adapters,
                rt_funcname=name,
            )
            setattr(pyfuncitem.module, name, injected)
            _logger.info(f"Replaced {name}() from global import with {injected}")
            break

        elif inspect.ismodule(item):
            if item.__name__ not in {"typing", "typing_extensions"}:
                continue
            assert hasattr(item, "reveal_type")
            injected = functools.partial(
                revealtype_injector,
                adapters=adapters,
                rt_funcname=f"{name}.reveal_type",
            )
            setattr(item, "reveal_type", injected)
            _logger.info(f"Replaced {name}.reveal_type() with {injected}")
            break


def pytest_collection_finish(session: pytest.Session) -> None:
    files = {i.path for i in session.items}
    if not files:
        return
    for adp in session.config.stash[adapter_stash_key]:
        try:
            adp.run_typechecker_on(files)
        except Exception as e:
            _logger.error(f"({adp.id}) {e}")
            pytest.exit(
                f"({type(e).__name__}) " + str(e), pytest.ExitCode.INTERNAL_ERROR
            )
        else:
            _logger.info(f"({adp.id}) Type checker ran successfully")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup(
        "revealtype-injector",
        description="Type checker related options for revealtype-injector",
    )
    classes = adapter.get_adapter_classes()
    group.addoption(
        "--revealtype-disable-adapter",
        type=str,
        choices=tuple(c.id for c in classes),
        action="append",
        default=[],
        help="Disable specific type checker. Can be used multiple times"
        " to disable multiple checkers",
    )
    for c in classes:
        c.add_pytest_option(group)


def pytest_configure(config: pytest.Config) -> None:
    global adapter_stash_key
    adapter_stash_key = pytest.StashKey[set[TypeCheckerAdapter]]()
    config.stash[adapter_stash_key] = set()
    verbosity = config.get_verbosity(config.VERBOSITY_TEST_CASES)
    log.set_verbosity(verbosity)
    to_be_disabled = cast(list[str], config.getoption("revealtype_disable_adapter"))
    for klass in adapter.get_adapter_classes():
        if klass.id in to_be_disabled:
            _logger.info(f"({klass.id}) adapter disabled with command line option")
            continue
        adp = klass()
        adp.set_config_file(config)
        adp.log_verbosity = verbosity
        config.stash[adapter_stash_key].add(adp)
