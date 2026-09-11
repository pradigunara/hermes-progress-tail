"""Behaviour of the plugin against the REAL Hermes core modules.

These tests deliberately avoid `types.ModuleType` fakes: the bug they pin only exists
because `hermes_cli.commands` is a lazy facade whose writes do not propagate to the
module the platform adapters actually import from.
"""

from __future__ import annotations

import importlib
import os
import sys
import warnings
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from hermes_progress_tail.hooks import command_menus
from hermes_progress_tail.runtime import environment as env

OWNER = "hermes_cli.commands_platforms"
FACADE = "hermes_cli.commands"

_CORE_HOME = Path(
    os.environ.get("HPT_HERMES_CORE_HOME", str(Path.home() / ".hermes" / "hermes-agent"))
)


def _purge_core_modules(baseline: frozenset[str]) -> None:
    """Undo every sys.modules entry the core import created.

    A name check is not enough: the core's plugin loader injects a synthetic
    ``hermes_plugins`` module with an empty ``__path__`` and no ``__file__``, which
    would otherwise survive and shadow the temp namespace packages other tests build.
    """
    for name in tuple(sys.modules):
        if name not in baseline:
            sys.modules.pop(name, None)


def _drop_core_from_sys_path() -> None:
    # Importing the core appends its own root again, so one remove() is not enough.
    wanted = {str(_CORE_HOME), str(_CORE_HOME.resolve())}
    sys.path[:] = [entry for entry in sys.path if entry not in wanted]
    importlib.invalidate_caches()


@pytest.fixture(scope="module")
def core(tmp_path_factory):
    """Import the real Hermes core, then leave the interpreter as it was found."""
    if not (_CORE_HOME / "hermes_cli").is_dir():
        pytest.skip(f"Hermes core not available at {_CORE_HOME}")
    previous_home = os.environ.get("HERMES_HOME")
    os.environ["HERMES_HOME"] = str(tmp_path_factory.mktemp("hermes_home"))
    baseline = frozenset(sys.modules)
    sys.path.append(str(_CORE_HOME))
    try:
        owner = importlib.import_module(OWNER)
        facade = importlib.import_module(FACADE)
        compat = importlib.import_module("hermes_cli.plugin_compat")
    except Exception as exc:  # pragma: no cover - environment dependent
        _drop_core_from_sys_path()
        pytest.skip(f"Hermes core not importable: {exc}")
    try:
        yield SimpleNamespace(owner=owner, facade=facade, compat=compat)
    finally:
        command_menus.uninstall_command_menu_monkeypatch(owner)
        command_menus.uninstall_command_menu_monkeypatch(facade)
        _purge_core_modules(baseline)
        _drop_core_from_sys_path()
        if previous_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = previous_home


@pytest.fixture
def clean_patch(core):
    command_menus.uninstall_command_menu_monkeypatch(core.owner)
    command_menus.uninstall_command_menu_monkeypatch(core.facade)
    yield
    command_menus.uninstall_command_menu_monkeypatch(core.owner)
    command_menus.uninstall_command_menu_monkeypatch(core.facade)


def _adapter_view():
    """Exactly how the Telegram adapter binds the function."""
    from hermes_cli.commands_platforms import telegram_menu_commands

    return telegram_menu_commands


def test_patch_is_visible_to_the_module_adapters_import_from(core, clean_patch):
    assert command_menus._mutate_command_menu_monkeypatch() is True

    assert _adapter_view().__name__ == "patched_telegram_menu_commands"


def test_pinned_command_survives_a_realistic_telegram_cap(core, clean_patch):
    assert command_menus._mutate_command_menu_monkeypatch() is True

    visible, _hidden = core.owner.telegram_menu_commands(max_commands=8)
    assert [name for name, _desc in visible][0] == "progresstail"


def test_slack_patch_is_visible_on_the_module_adapters_import_from(core, clean_patch):
    assert command_menus._mutate_command_menu_monkeypatch() is True

    from hermes_cli.commands_platforms import slack_native_slashes

    assert slack_native_slashes.__name__ == "patched_slack_native_slashes"
    assert [name for name, _desc, _hint in slack_native_slashes()][0] == "progresstail"


def test_install_then_uninstall_restores_the_original_on_the_owning_module(core, clean_patch):
    original_menu = core.owner.telegram_menu_commands
    original_slack = core.owner.slack_native_slashes

    assert command_menus.install_command_menu_monkeypatch() is True
    assert core.owner.telegram_menu_commands is not original_menu
    assert command_menus.command_menu_monkeypatch_active() is True

    assert command_menus.uninstall_command_menu_monkeypatch() is True
    assert core.owner.telegram_menu_commands is original_menu
    assert core.owner.slack_native_slashes is original_slack
    assert command_menus.command_menu_monkeypatch_active() is False


def test_patch_status_label_names_the_module_actually_patched(core, clean_patch):
    status = command_menus._command_menu_patch_status()
    try:
        assert status.installed is True
        assert status.target == f"{OWNER}.telegram_menu_commands"
    finally:
        command_menus.uninstall_command_menu_monkeypatch()


def test_falls_back_to_the_facade_when_the_owning_module_is_missing(core, monkeypatch):
    from hermes_progress_tail.hooks import core_modules

    real_import = core_modules.import_module

    def without_owner(name):
        if name == OWNER:
            raise ModuleNotFoundError(f"No module named {name!r}")
        return real_import(name)

    monkeypatch.setattr(core_modules, "import_module", without_owner)
    command_menus.uninstall_command_menu_monkeypatch(core.facade)
    original = core.facade.telegram_menu_commands

    assert core_modules.resolve_commands_module() is core.facade
    try:
        assert command_menus._mutate_command_menu_monkeypatch() is True
        assert core.facade.telegram_menu_commands.__name__ == "patched_telegram_menu_commands"
    finally:
        assert command_menus.uninstall_command_menu_monkeypatch() is True
    assert core.facade.telegram_menu_commands is original


def test_hook_install_emits_no_plugin_compat_warning(core, clean_patch):
    # warn_once() dedupes per process; clear it so this test sees real emissions.
    core.compat._seen.clear()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert command_menus._mutate_command_menu_monkeypatch() is True
        command_menus.command_menu_monkeypatch_active()
        command_menus._command_menu_patch_status()
        command_menus.uninstall_command_menu_monkeypatch()

    offenders = [
        str(item.message)
        for item in caught
        if issubclass(item.category, core.compat.HermesPluginCompatWarning)
    ]
    assert offenders == []


def _tools_package(monkeypatch):
    tools = ModuleType("tools")
    tools.__path__ = []
    monkeypatch.setitem(sys.modules, "tools", tools)
    return tools


def test_terminal_live_cwd_prefers_the_lifecycle_module(monkeypatch):
    _tools_package(monkeypatch)
    seen = []
    lifecycle = ModuleType("tools.terminal_tool_lifecycle")
    lifecycle.get_active_env = lambda task: seen.append(task) or SimpleNamespace(cwd="/new")
    legacy = ModuleType("tools.terminal_tool")
    legacy.get_active_env = lambda task: SimpleNamespace(cwd="/legacy")
    monkeypatch.setitem(sys.modules, "tools.terminal_tool_lifecycle", lifecycle)
    monkeypatch.setitem(sys.modules, "tools.terminal_tool", legacy)

    assert env._terminal_live_cwd() == "/new"
    assert seen == ["default"]


def test_terminal_live_cwd_falls_back_to_the_legacy_module(monkeypatch):
    _tools_package(monkeypatch)
    legacy = ModuleType("tools.terminal_tool")
    legacy.get_active_env = lambda task: SimpleNamespace(cwd="/legacy")
    monkeypatch.setitem(sys.modules, "tools.terminal_tool", legacy)
    monkeypatch.delitem(sys.modules, "tools.terminal_tool_lifecycle", raising=False)

    assert env._terminal_live_cwd("task") == "/legacy"


def test_terminal_live_cwd_is_total_when_every_module_fails(monkeypatch):
    _tools_package(monkeypatch)
    monkeypatch.delitem(sys.modules, "tools.terminal_tool_lifecycle", raising=False)
    monkeypatch.delitem(sys.modules, "tools.terminal_tool", raising=False)

    assert env._terminal_live_cwd() == ""

    boom = ModuleType("tools.terminal_tool_lifecycle")
    boom.get_active_env = lambda task: (_ for _ in ()).throw(RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "tools.terminal_tool_lifecycle", boom)
    assert env._terminal_live_cwd() == ""
