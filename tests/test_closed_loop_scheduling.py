import asyncio
import gc
import warnings
from types import SimpleNamespace as NS

import pytest

from hermes_progress_tail.models.state import ToolEvent
from hermes_progress_tail.rendering.renderer import ProgressRenderer
from hermes_progress_tail.runtime import agent_events, clarify, tool_events
from hermes_progress_tail.settings.loading import load_settings
from tests.support.rendering import EditableAdapter, make_live_context


def closed_loop():
    loop = asyncio.new_event_loop()
    loop.close()
    return loop


def unawaited_coroutines(action):
    gc.collect()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = action()
        gc.collect()
    return result, [str(w.message) for w in caught if "never awaited" in str(w.message)]


async def accept(*_args, **_kwargs):
    return True


def test_finalize_scheduled_on_a_closed_loop_is_closed(monkeypatch):
    target = NS(session_id="sid", loop=closed_loop(), generation=1)
    renderer = NS(finalize=accept)
    monkeypatch.setattr(agent_events, "_runtime_provider", NS(get_renderer=lambda: renderer))
    monkeypatch.setattr(agent_events, "_finalize_target_context", lambda *_args: target)

    assert unawaited_coroutines(lambda: agent_events._schedule_finalize("sid")) == (None, [])


def test_render_scheduled_on_a_closed_loop_reports_failure_without_leaking(monkeypatch):
    renderer = NS(handle_event=accept)
    monkeypatch.setattr(tool_events, "_runtime_provider", NS(get_renderer=lambda: renderer))
    ctx = NS(session_id="sid", session_key="key", loop=closed_loop())
    event = ToolEvent("sid", "key", "discord", "x")

    assert unawaited_coroutines(lambda: tool_events._schedule_render(ctx, event)) == (False, [])


@pytest.mark.parametrize(
    ("bridge", "expected"),
    [(clarify.run_clarify_freeze_barrier, False), (clarify.run_clarify_resolution_bridge, None)],
)
def test_clarify_bridges_close_the_operation_when_the_loop_closes_after_the_check(
    monkeypatch, bridge, expected
):
    loop = closed_loop()
    monkeypatch.setattr(clarify, "_usable_loop", lambda _ctx: loop)

    assert unawaited_coroutines(lambda: bridge(NS(), accept)) == (expected, [])


async def _live_context():
    return make_live_context(EditableAdapter())


def _rendering_state(monkeypatch):
    renderer = ProgressRenderer(
        load_settings(
            {"progress_tail": {"cleanup": {"auto_delete": True, "delete_on_success": True}}}
        )
    )
    ctx = asyncio.run(_live_context())
    ctx.loop = closed_loop()
    ctx.delivery.message_id = "progress"
    monkeypatch.setattr(tool_events, "_runtime_provider", NS(get_renderer=lambda: renderer))
    return renderer, ctx


@pytest.mark.parametrize(
    "schedule",
    [
        lambda renderer, ctx: renderer.delivery.schedule_delayed_live_flush(ctx, 0),
        lambda renderer, ctx: renderer.delivery.schedule_auto_delete(ctx, success=True),
        lambda renderer, ctx: renderer._schedule_delegate_cleanup(
            ctx, "sub", NS(cleanup_task=None)
        ),
        lambda renderer, ctx: tool_events._schedule_background_job_cleanup(ctx, "proc"),
        lambda renderer, ctx: tool_events._schedule_background_job_poll(ctx, "proc"),
    ],
    ids=["delayed-flush", "delete", "delegate-cleanup", "job-cleanup", "job-poll"],
)
def test_tasks_created_on_a_closed_loop_raise_without_leaking(monkeypatch, schedule):
    renderer, ctx = _rendering_state(monkeypatch)

    def run():
        with pytest.raises(RuntimeError, match="closed"):
            schedule(renderer, ctx)

    assert unawaited_coroutines(run) == (None, [])
