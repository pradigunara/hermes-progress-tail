# Provenance & update workflow

Installed from the fork: `pradigunara/hermes-progress-tail`, branch `hardened` —
a single hardening commit (this one) on top of upstream
`tickernelz/hermes-progress-tail` v0.2.23 / `fa2ccb1b052bc46f1f9e500b6b532cb1eadd0325`.
The exact installed SHA is the `revision` pin in `~/.hermes/plugins/.install-metadata.json`.

Two refs, two jobs:

- `main` — a pure MIRROR of upstream, no patches, ever. Advances by fast-forward
  only, so `gh repo sync` / GitHub's "Sync fork" always apply cleanly to it.
- `hardened` — `main` + the hardening commit. The only branch we force-push, and the
  one the plugin is installed from.

Order matters: sync the mirror FIRST, then rebase `hardened` onto the synced `main`.
Rebasing onto a stale mirror is a silent no-op — it reports success while keeping the
old upstream version, which is how the fork sat on v0.2.22 through the v0.2.23 release.

The hardening patches live IN the fork (no local file edits to re-apply):

1. `announcements.py` — remote HackMD announcements fetch disabled (author-controlled text into chat).
2. `commands.py` — `progresstail-update` self-updater disabled (applied unsigned remote tarballs).
3. `pyproject.toml` — dev `ruff>=0.15.12` relaxed to `>=0.15.10` (resolves conflict with Hermes's uv.lock).

## Updating (sync the mirror, then rebase hardened onto it)

```bash
B=~/.hermes/cache/scratch/progress-tail-fork
git clone -b hardened git@github.com:pradigunara/hermes-progress-tail.git $B && cd $B
git remote add upstream https://github.com/tickernelz/hermes-progress-tail.git  # for the sync check

# 1. refresh the mirror: fork main <- upstream main (fast-forward; never -f on main)
gh repo sync pradigunara/hermes-progress-tail
#    equivalent without gh: git fetch upstream && git push origin upstream/main:main

# 2. verify the sync landed — both SHAs must match, otherwise stop and fix step 1
git fetch origin main --tags && git fetch upstream
git rev-parse origin/main upstream/main

# 3. rebase the hardening commit onto the synced main
git rebase origin/main              # resolve conflicts if upstream touched the 3 hardening files

# 4. push the rebased branch, reinstall pinned to its new SHA
git push -f origin hardened
NEW=$(git rev-parse HEAD)
hermes plugins install pradigunara/hermes-progress-tail --ref $NEW --yes-deps --force --enable
```

Notes:
- `gh repo sync` is fast-forward only — which is exactly why `main` must stay
  unpatched (`--force` would hard-reset it, and a plain sync refuses once main diverges).
- `--force` on the plugin install reinstalls over the installed copy, keeping untracked files.
- `--no-deps` refuses to replace an enabled plugin, so use `--yes-deps --force --enable`.
- The install security scanner may block on the usual ~53 noise findings (emoji ZWJ,
  docs/CI patterns, bundled PNGs) — `--force` after re-triaging is expected.
- After a rebase onto a new upstream version, review what upstream changed
  (`git log --stat origin/main^-..origin/main`, esp. anything touching network/rendering)
  before pushing.
- Update alternative: PR the hardening upstream; if merged, point the pin back at
  tickernelz's SHA and retire `hardened`.

## Test suite status (13 expected failures, checked 2026-10-16 on v0.2.24 + hardening)

`uv run --with pytest pytest -q` — same set as the v0.2.22/v0.2.23 baselines; none caused by the rebase
(v0.2.24 upstream delta: one coroutine-scheduling fix in runtime/scheduling, no network/renderer changes).
Verified old-SHA vs new-SHA failure sets are identical in matching worktrees:

- 11 across `test_update_command.py`, `test_runtime_command_demo_and_async.py`,
  `test_announcements_and_status.py`, `test_plugin_runtime_corrective.py` — they assert
  the self-updater / remote announcements actually run, which hardening disables.
- `test_c10_baseline_compatibility.py`, `test_renderer_delivery.py` — timezone
  dependent; also fail on pristine upstream `fa2ccb1` on this machine.
- `test_compression_lifecycle.py` (2, only when run inside the working clone) — the
  renderer reads the live git state of the checkout and the footer emits a `-1`
  segment; passes in a clean worktree of the same commit.
