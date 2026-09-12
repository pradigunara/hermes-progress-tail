"""The newest narrative unit stays visible above the collapsed history.

A fully-collapsed Progress/Reasoning section hid its own heading and opened at
the *oldest* line, so a long card showed nothing current without a tap. The peek
keeps the section heading plus the newest unit inline and parks only the older
history inside ``<details>``.
"""

from __future__ import annotations

import re
from pathlib import Path

from hermes_progress_tail.rendering.telegram_rich import (
    RichHeading,
    RichParagraph,
    RichThinking,
    format_progress_tail_telegram_rich_markdown,
)
from hermes_progress_tail.rendering.telegram_rich_budget import (
    DEFAULT_RICH_BUDGET_BYTES,
    guarded_rich_markdown,
    markdown_byte_length,
)
from hermes_progress_tail.rendering.telegram_rich_details import collapse_narrative

BUDGET = DEFAULT_RICH_BUDGET_BYTES
FIXTURES = Path(__file__).parent / "fixtures"

PROGRESS_STEPS = 40
THOUGHTS = 20


def progress_body(steps: int = PROGRESS_STEPS) -> str:
    return "\n".join(
        f"- step {index}: reading the staging model and the generator view extension"
        for index in range(steps)
    )


def reasoning_body(thoughts: int = THOUGHTS) -> str:
    return "\n\n".join(
        f"**Thought {index}**\nI weighed option {index} against the alternatives here."
        for index in range(thoughts)
    )


def long_card(progress: str | None = None, reasoning: str | None = None) -> str:
    return (
        "**Hermes is working**\n"
        "**Now** rendering a long card\n"
        "**State** running\n\n"
        f"## Progress\n{progress if progress is not None else progress_body()}\n\n"
        f"## Reasoning\n{reasoning if reasoning is not None else reasoning_body()}\n\n"
        "## Plan\n- [x] Read the spec\n- [ ] Ship the peek\n\n"
        "## Tools\n- ✅ terminal: pytest -q · done\n- ❌ terminal: mypy . · failed\n\n"
        "## Status\nEvery section must stay visible.\n"
    )


def short_card() -> str:
    return long_card(progress="- step 0: done.", reasoning="**Thought 0**\nA brief thought.")


def _render(content: str, *, peek: int) -> str:
    return format_progress_tail_telegram_rich_markdown(
        content,
        max_table_rows=8,
        verification_table=True,
        thinking_blocks=True,
        compact_success=True,
        max_detail_items=8,
        collapse_narrative_chars=1200,
        collapse_peek_units=peek,
    )


def _visible(text: str) -> str:
    """The part a reader sees before expanding anything."""
    return re.sub(r"<details.*?</details>", "", text, flags=re.DOTALL)


class _Settings:
    """Minimal stand-in for ``TelegramSettings`` on the budget seam."""

    rich_messages = True
    verification_table = True
    thinking_blocks = True
    max_table_rows = 8
    compact_success = True
    max_detail_items = 8
    collapse_narrative_chars = 1200
    rich_budget_bytes = DEFAULT_RICH_BUDGET_BYTES
    min_narrative_chars = 300

    def __init__(self, peek: int = 1) -> None:
        self.collapse_peek_units = peek


def test_long_progress_peeks_the_newest_line_above_the_fold() -> None:
    """Acceptance 1: heading plus newest line inline, older lines collapsed."""
    out = _render(long_card(), peek=1)

    assert "## Progress" in out
    newest = f"step {PROGRESS_STEPS - 1}:"
    assert newest in out
    assert newest in _visible(out), "the newest progress line must not need a tap"
    # The newest line is above the fold: it precedes the first <details>.
    assert out.index(newest) < out.index("<details"), "newest line must precede the collapse"
    # The older history is still behind the collapse, in original (oldest-first) order.
    details = re.search(r"<details.*?</details>", out, flags=re.DOTALL)
    assert details is not None
    body = details.group(0)
    assert "step 0:" in body
    assert f"step {PROGRESS_STEPS - 2}:" in body
    assert body.index("step 0:") < body.index("step 1:")
    assert newest not in body, "the peeked line must not be duplicated inside the collapse"


def test_long_reasoning_peeks_the_newest_thought_with_its_heading() -> None:
    """Acceptance 2: the peeked reasoning unit keeps its ``###`` heading."""
    out = _render(long_card(), peek=1)
    visible = _visible(out)

    assert "## Reasoning" in out
    assert f"### Thought {THOUGHTS - 1}" in visible, "the newest thought keeps its heading inline"
    assert f"option {THOUGHTS - 1} against" in visible, "and its body"
    assert "### Thought 0" not in visible, "older thoughts stay collapsed"
    assert "### Thought 0" in out


def test_peek_zero_reproduces_todays_output_byte_identically() -> None:
    """Acceptance 3: ``collapse_peek_units: 0`` is the pre-change rendering."""
    baseline = (FIXTURES / "collapse_peek_baseline_long.md").read_text(encoding="utf-8")

    assert _render(long_card(), peek=0) == baseline


def test_section_below_the_threshold_is_byte_identical() -> None:
    """Acceptance 4: short sections keep today's flat rendering exactly."""
    baseline = (FIXTURES / "collapse_peek_baseline_short.md").read_text(encoding="utf-8")

    assert _render(short_card(), peek=1) == baseline
    assert "<details" not in baseline


def test_math_bearing_narrative_still_refuses_to_collapse() -> None:
    """Acceptance 5: math inside <details> crashes tdesktop 6.9.1 (#30808)."""
    math_reasoning = (
        reasoning_body() + "\n\n**Bound**\nThe bound is $$\\sum_{i=0}^{n} x_i \\le 1$$."
    )
    out = _render(long_card(reasoning=math_reasoning), peek=1)

    details_blocks = re.findall(r"<details.*?</details>", out, flags=re.DOTALL)
    assert all("$$" not in block for block in details_blocks)
    assert all("\\sum" not in block for block in details_blocks)
    # The section renders flat instead: every thought is visible without a tap.
    visible = _visible(out)
    assert "### Thought 0" in visible
    assert f"### Thought {THOUGHTS - 1}" in visible
    assert "\\sum_{i=0}^{n} x_i" in visible


def test_peeked_card_still_fits_the_byte_budget_on_the_wire() -> None:
    """Acceptance 6: assert transmitted bytes, not source text."""
    saturated = long_card(
        progress="\n".join(
            f"- step {index}: reading the staging model and the generator view extension"
            for index in range(400)
        ),
        reasoning="\n\n".join(
            f"**Thought {index}**\nI weighed option {index} against every alternative here."
            for index in range(400)
        ),
    )
    guarded = guarded_rich_markdown(saturated, _Settings(peek=1))

    assert markdown_byte_length(guarded) <= BUDGET
    # Negative control: the same card is over budget without the guard.
    assert markdown_byte_length(_render(saturated, peek=1)) > BUDGET


def test_no_empty_details_when_the_peek_covers_every_unit() -> None:
    """Acceptance 7: a peek wide enough to swallow the section renders it FLAT.

    Byte-identity against the never-collapse rendering is the assertion that
    bites: an empty ``<details>`` renders as the empty string and would leave no
    tag behind, so merely asserting the tag's absence passes either way.
    """
    out = _render(long_card(), peek=PROGRESS_STEPS + THOUGHTS)
    flat = format_progress_tail_telegram_rich_markdown(
        long_card(),
        max_table_rows=8,
        verification_table=True,
        thinking_blocks=True,
        compact_success=True,
        max_detail_items=8,
        collapse_narrative_chars=0,
    )

    assert "<details" not in out
    assert "<summary>" not in out
    assert out == flat, "a fully-covering peek must reproduce the flat section exactly"


def test_plan_tools_and_status_stay_visible_on_a_saturated_card() -> None:
    """Acceptance 8: the scannable sections are why the collapse exists."""
    saturated = long_card(
        progress="\n".join(f"- step {index}: {'filler ' * 12}" for index in range(300)),
        reasoning="\n\n".join(
            f"**Thought {index}**\n{'reasoning filler ' * 12}" for index in range(300)
        ),
    )
    guarded = guarded_rich_markdown(saturated, _Settings(peek=1))

    assert markdown_byte_length(guarded) <= BUDGET
    visible = _visible(guarded)
    assert "## Plan" in visible
    assert "Ship the peek" in visible
    assert "## Tools" in visible
    assert "mypy" in visible
    assert "## Status" in visible
    assert "Every section must stay visible." in visible


def test_peek_summary_marks_the_collapse_as_history_only() -> None:
    """The block no longer holds the whole section, so say so."""
    out = _render(long_card(), peek=1)

    summaries = re.findall(r"<summary>(.*?)</summary>", out)
    assert summaries
    assert all(summary.startswith("Earlier ") for summary in summaries), summaries
    assert "Earlier Progress · tap to expand" in summaries
    assert "Earlier Reasoning · tap to expand" in summaries


def test_collapse_narrative_returns_blocks_and_pairs_heading_with_body() -> None:
    """The unit for a reasoning peek is the heading+body pair, not a bare body."""
    blocks = [
        block
        for index in range(THOUGHTS)
        for block in (
            RichHeading(f"Thought {index}", level=3),
            RichThinking(f"I weighed option {index} against the alternatives here."),
        )
    ]

    result = collapse_narrative("Reasoning", blocks, threshold=200, peek_units=1)

    assert isinstance(result, list)
    rendered = [block.to_markdown() for block in result]
    assert rendered[0] == "## Reasoning"
    assert rendered[1] == (
        f"### Thought {THOUGHTS - 1}\n\nI weighed option {THOUGHTS - 1} "
        "against the alternatives here."
    )
    assert rendered[-1].startswith("<details>")


def test_collapse_narrative_peek_zero_still_returns_one_details_block() -> None:
    result = collapse_narrative(
        "Progress", [RichParagraph(progress_body())], threshold=200, peek_units=0
    )

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].to_markdown().startswith("<details>")
    assert "<summary>Progress · tap to expand</summary>" in result[0].to_markdown()


def test_collapse_narrative_returns_none_below_threshold_with_a_peek() -> None:
    assert collapse_narrative(
        "Reasoning", [RichParagraph("tiny")], threshold=1200, peek_units=1
    ) is (None)
