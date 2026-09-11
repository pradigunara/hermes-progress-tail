"""Resolve Hermes core modules that moved during the Sep-2026 decomposition.

Two rules apply to everything in here:

* Resolve the module that OWNS the symbol, never a lazy facade. ``hermes_cli.commands``
  forwards reads through a module-level ``__getattr__`` but writes to it do NOT propagate
  to ``hermes_cli.commands_platforms``, which is where the Telegram and Slack adapters
  import from. Monkeypatching the facade is therefore a silent no-op for them.
* Keep the old path as a fallback. This plugin is installed across profiles that may run
  different Hermes versions, including builds that predate the split.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

COMMANDS_OWNER_MODULE = "hermes_cli.commands_platforms"
COMMANDS_FACADE_MODULE = "hermes_cli.commands"

TERMINAL_OWNER_MODULE = "tools.terminal_tool_lifecycle"
TERMINAL_FACADE_MODULE = "tools.terminal_tool"


def _first_importable(*names: str) -> Any:
    last: Exception | None = None
    for name in names:
        try:
            return import_module(name)
        except Exception as exc:  # pragma: no cover - depends on installed core
            last = exc
    raise last if last is not None else ModuleNotFoundError("no candidate modules given")


def resolve_commands_module() -> Any:
    """The module the platform adapters actually read the menu builders from."""
    return _first_importable(COMMANDS_OWNER_MODULE, COMMANDS_FACADE_MODULE)


def commands_module_label() -> str:
    """Dotted name of the module :func:`resolve_commands_module` would return."""
    try:
        return str(resolve_commands_module().__name__)
    except Exception:
        return COMMANDS_OWNER_MODULE


def resolve_terminal_module() -> Any:
    """The module owning ``get_active_env`` on this Hermes build."""
    return _first_importable(TERMINAL_OWNER_MODULE, TERMINAL_FACADE_MODULE)
