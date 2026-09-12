"""Collapsible ``<details>`` support for long narrative sections.

Split out of :mod:`hermes_progress_tail.rendering.telegram_rich` to keep every
tracked file within the repository's 600-line rail.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol


class _Block(Protocol):
    def to_markdown(self) -> str: ...


@dataclass(frozen=True)
class RichDetails:
    """A Bot API 10.1 collapsible ``<details>`` block.

    Long narrative sections (Reasoning, Progress) push Plan/Tools/Status below
    the fold. Wrapping them in a collapsible block keeps the full text
    available behind a tap while the scannable sections stay visible.
    """

    summary: str
    body: str
    open: bool = False
    sanitize: Callable[[str], str] | None = None

    def to_markdown(self) -> str:
        body = str(self.body or "").strip()
        if not body:
            return ""
        raw_summary = str(self.summary or "")
        summary = (self.sanitize(raw_summary) if self.sanitize else raw_summary) or "Details"
        attr = " open" if self.open else ""
        return f"<details{attr}>\n<summary>{summary}</summary>\n\n{body}\n\n</details>"


@dataclass(frozen=True)
class RichRendered:
    """Already-rendered markdown passed through untouched.

    The peek re-emits units that were produced by the section's own blocks, so
    re-normalizing them would be a second, lossy pass over the same text.
    """

    markdown: str

    def to_markdown(self) -> str:
        return str(self.markdown or "").strip()


_MATH_IN_DETAILS_RE = re.compile(
    r"(\$\$.*?\$\$|"
    r"\\\[.*?\\\]|"
    r"\\\(.*?\\\)|"
    r"\\(?:sum|frac|alpha|beta|gamma|delta|theta|lambda|mu|pi|sigma|"
    r"int|prod|sqrt|lim|infty|begin\{(?:equation|align|matrix|cases)\}))",
    re.IGNORECASE | re.DOTALL,
)


def collapse_narrative(
    title: str,
    blocks: Sequence[_Block],
    *,
    threshold: int,
    sanitize: Callable[[str], str] | None = None,
    peek_units: int = 0,
) -> list[_Block] | None:
    """Collapse a long narrative section, optionally peeking its newest units.

    Returns ``None`` when collapsing is disabled or the section is short enough
    to stay inline, so short sections keep their existing flat rendering.

    With ``peek_units <= 0`` the whole section becomes one ``<details>`` block,
    which is what this function did before the peek existed. With a positive
    ``peek_units`` the result is the section heading, the newest units inline,
    and a ``<details>`` holding the older remainder in original order — a fully
    collapsed section hid its own heading and opened at the *oldest* line, so a
    long card showed nothing current without a tap.

    Math inside a ``<details>`` block crashes Telegram Desktop 6.9.1
    (telegramdesktop/tdesktop#30808). Hermes core screens its own send path,
    but this plugin drives ``editMessageText`` directly and never consults that
    guard, so refuse to collapse math-bearing narrative here. That keeps the
    crash shape out of every delivery path rather than one of them.
    """
    if threshold <= 0:
        return None
    rendered_blocks = [markdown for block in blocks if (markdown := block.to_markdown().strip())]
    rendered = "\n\n".join(rendered_blocks).strip()
    if not rendered or len(rendered) <= threshold:
        return None
    if _MATH_IN_DETAILS_RE.search(rendered):
        return None
    peek = _safe_peek(peek_units)
    if peek <= 0:
        return [RichDetails(summary=f"{title} · tap to expand", body=rendered, sanitize=sanitize)]
    units = _peek_units(rendered_blocks)
    if peek >= len(units):
        # The peek would swallow the whole section: render it flat rather than
        # emit a heading followed by an empty <details>.
        return None
    heading = (sanitize(title) if sanitize else title) or title
    older = "\n\n".join(units[: len(units) - peek]).strip()
    return [
        RichRendered(f"## {heading}"),
        RichRendered("\n\n".join(units[len(units) - peek :])),
        RichDetails(
            summary=f"Earlier {title} · tap to expand",
            body=older,
            sanitize=sanitize,
        ),
    ]


def _peek_units(rendered_blocks: Sequence[str]) -> list[str]:
    """Split a rendered section into the units a peek can take from its tail.

    A single block holds an entire section (Progress is one bullet list), so its
    own paragraph breaks are the only boundary available — that makes the
    Progress unit a line. Multiple blocks are already per-thought, but Reasoning
    alternates heading and body, so a trailing body is paired with the heading
    above it; taking the body alone would peek a thought with no title.
    """
    if len(rendered_blocks) <= 1:
        return [
            part.strip()
            for chunk in rendered_blocks
            for part in chunk.split("\n\n")
            if part.strip()
        ]
    units: list[str] = []
    pending_heading: str | None = None
    for markdown in rendered_blocks:
        if markdown.lstrip().startswith("#"):
            if pending_heading is not None:
                units.append(pending_heading)
            pending_heading = markdown
            continue
        units.append(f"{pending_heading}\n\n{markdown}" if pending_heading else markdown)
        pending_heading = None
    if pending_heading is not None:
        units.append(pending_heading)
    return units


def _safe_peek(value: object) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
