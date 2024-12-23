from __future__ import annotations

import inspect
from typing import cast

import pytest

from . import adapter, log
from .main import revealtype_injector

_logger = log.get_logger()


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> None:
    assert pyfuncitem.module is not None
    for name in dir(pyfuncitem.module):
        if name.startswith("__") or name.startswith("@py"):
            continue

        item = getattr(pyfuncitem.module, name)
        if inspect.isfunction(item):
            if item.__name__ == "reveal_type" and item.__module__ in {
                "typing",
                "typing_extensions",
            }:
                setattr(pyfuncitem.module, name, revealtype_injector)
                _logger.info(
                    f"Replaced {name}() from global import with {revealtype_injector}"
                )
                continue

        if inspect.ismodule(item):
            if item.__name__ not in {"typing", "typing_extensions"}:
                continue
            assert hasattr(item, "reveal_type")
            setattr(item, "reveal_type", revealtype_injector)
            _logger.info(f"Replaced {name}.reveal_type() with {revealtype_injector}")
            continue


def pytest_collection_finish(session: pytest.Session) -> None:
    files = {i.path for i in session.items}
    for adp in adapter.discovery():
        if adp.enabled:
            adp.run_typechecker_on(files)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup(
        "revealtype-injector",
        description="Type checker related options for revealtype-injector",
    )
    adapters = adapter.discovery()
    choices = tuple(adp.id for adp in adapters)
    group.addoption(
        "--revealtype-disable-adapter",
        type=str,
        choices=choices,
        action="append",
        default=[],
        help="Disable specific type checker. Can be used multiple times"
        " to disable multiple checkers",
    )
    for adp in adapters:
        adp.add_pytest_option(group)


def pytest_configure(config: pytest.Config) -> None:
    verbosity = config.get_verbosity(config.VERBOSITY_TEST_CASES)
    log.set_verbosity(verbosity)
    # Forget config stash, it can't store collection of unserialized objects
    to_be_disabled = cast(list[str], config.getoption("revealtype_disable_adapter"))
    for adp in adapter.discovery():
        adp.log_verbosity = verbosity
        if adp.id in to_be_disabled:
            adp.enabled = False
            _logger.info(f"({adp.id}) this adapter disabled with command line option")
        else:
            adp.set_config_file(config)
