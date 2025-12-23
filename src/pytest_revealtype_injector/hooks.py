from __future__ import annotations

import functools
import inspect
from collections.abc import Iterator
from typing import cast

import pytest

from . import adapter, log
from .main import revealtype_injector
from .models import TypeCheckerAdapter

_logger = log.get_logger()
adapter_stash_key: pytest.StashKey[set[TypeCheckerAdapter]]


@pytest.hookimpl(wrapper=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> Iterator[None]:
    assert pyfuncitem.module is not None
    adp_stash = pyfuncitem.config.stash[adapter_stash_key]

    # Disable type checker based on marker
    mark = pyfuncitem.get_closest_marker("notypechecker")
    if mark:
        disabled_adapters = {a.id for a in adp_stash if a.id in mark.args}
        for a in disabled_adapters:
            _logger.info(
                f"{a} adapter disabled by 'notypechecker' marker in {pyfuncitem.name} test"
            )
        adapters = {a for a in adp_stash if a.id not in disabled_adapters}
    else:
        adapters = {a for a in adp_stash}

    if not adapters:
        pytest.fail("All type checkers have been disabled.")

    # Monkeypatch reveal_type() with our own function, to guarantee
    # each test func can receive different adapters
    with pytest.MonkeyPatch.context() as mp:
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
                mp.setattr(pyfuncitem.module, name, injected)
                _logger.info(
                    f"Replaced {name}() from global import with {injected} in {pyfuncitem.name} test"
                )
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
                mp.setattr(item, "reveal_type", injected)
                _logger.info(
                    f"Replaced {name}.reveal_type() with {injected} in {pyfuncitem.name} test"
                )
                break

        return cast(None, (yield))  # type: ignore[redundant-cast]


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
    # Globally disable adapters using command line options
    global adapter_stash_key
    adapter_stash_key = pytest.StashKey[set[TypeCheckerAdapter]]()
    config.stash[adapter_stash_key] = set()
    verbosity = config.get_verbosity(config.VERBOSITY_TEST_CASES)
    log.set_verbosity(verbosity)
    to_be_disabled = cast(list[str], config.getoption("revealtype_disable_adapter"))
    all_ids: list[str] = []
    for klass in adapter.get_adapter_classes():
        all_ids.append(klass.id)
        if klass.id in to_be_disabled:
            _logger.info(f"({klass.id}) adapter disabled with command line option")
            continue
        adp = klass()
        adp.set_config_file(config)
        adp.log_verbosity = verbosity
        config.stash[adapter_stash_key].add(adp)

    # Marker to disable adapters on demand
    config.addinivalue_line(
        "markers",
        "notypechecker(name, ...): mark reveal_type() test to disable "
        "specified type checker(s). Following type checkers are supported: "
        + ", ".join(all_ids),
    )
