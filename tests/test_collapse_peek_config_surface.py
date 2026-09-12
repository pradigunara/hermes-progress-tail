"""``progress_tail.telegram.collapse_peek_units`` must exist on every surface.

This project keeps its config surfaces strictly in sync: dataclass defaults,
loader coercion, schema contract, installer defaults, the runtime status line
and the README example. A key missing from one of them is a broken contract.
"""

from __future__ import annotations

from pathlib import Path

from hermes_progress_tail.cli.installer_defaults import DEFAULT_CONFIG
from hermes_progress_tail.settings.loading import load_settings
from hermes_progress_tail.settings.migration import find_unknown_config_keys
from hermes_progress_tail.settings.types import Settings


def test_dataclass_default_is_one_unit() -> None:
    assert Settings().telegram.collapse_peek_units == 1


def test_loader_reads_and_clamps_the_key() -> None:
    def peek(value: object) -> int:
        return load_settings(
            {"progress_tail": {"telegram": {"collapse_peek_units": value}}}
        ).telegram.collapse_peek_units

    assert peek(3) == 3
    assert peek(0) == 0, "0 must restore today's fully-collapsed behaviour"
    assert peek(-5) == 1, "a negative value falls back to the default"
    assert peek("bad") == 1


def test_schema_contract_accepts_the_key() -> None:
    unknown = find_unknown_config_keys({"progress_tail": {"telegram": {"collapse_peek_units": 1}}})

    assert "progress_tail.telegram.collapse_peek_units" not in unknown


def test_installer_default_matches_the_dataclass_default() -> None:
    assert DEFAULT_CONFIG["telegram"]["collapse_peek_units"] == 1


def test_readme_documents_the_key() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "collapse_peek_units:" in readme


def test_runtime_status_line_reports_the_peek() -> None:
    source = Path("hermes_progress_tail/runtime/commands.py").read_text(encoding="utf-8")

    assert "collapse_peek_units" in source
