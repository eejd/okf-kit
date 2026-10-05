"""Tests for hub->serve convergence (okf_kit.core.gitio.GitWriter.converge and
okf_kit.core.sync.SyncCoordinator).

Real git repositories throughout, in the "local hub" shape used by
test_gitio.py: a bare hub plus a serving clone, so a compare-and-swap-style
hub advance (``update-ref``, not ``push``) is exercised exactly as
production does it.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from okf_kit.core.gitio import GitWriter
from okf_kit.core.sync import SyncCoordinator, SyncOutcome


def _run(cwd: Path, *args: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=env
    )
    return proc.stdout.strip()


def _hub_and_clone(tmp_path: Path, *, branch: str = "main") -> tuple[Path, Path]:
    hub = tmp_path / "hub.git"
    hub.mkdir()
    _run(hub, "init", "--bare", "-b", branch)
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", str(hub), str(clone)], capture_output=True, text=True, check=True
    )
    (clone / "index.md").write_text("---\nokf_version: '0.2'\n---\n# kb\n", encoding="utf-8")
    _run(clone, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _run(clone, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "seed")
    _run(clone, "push", "origin", branch)
    return hub, clone


def _advance_hub(hub: Path, tmp_path: Path, branch: str, name: str, *, tag: str) -> str:
    """Commit a new file to ``branch`` via a throwaway clone, pushed straight
    to the bare hub — simulating an out-of-band hub advance the serving
    clone hasn't seen yet."""
    other = tmp_path / f"other-{tag}"
    subprocess.run(
        ["git", "clone", "--branch", branch, str(hub), str(other)],
        capture_output=True,
        text=True,
        check=True,
    )
    (other / name).write_text(f"# {name}\n", encoding="utf-8")
    _run(other, "add", ".")
    _run(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", tag)
    _run(other, "push", "origin", branch)
    return _run(other, "rev-parse", "HEAD")


# -- GitWriter.converge -----------------------------------------------------


def test_converge_noop_when_already_current(tmp_path: Path):
    _, clone = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(clone)
    assert writer is not None
    result = writer.converge("main", lane="stable")
    assert result["action"] == "noop"


def test_converge_fast_forwards_when_behind(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    new_sha = _advance_hub(hub, tmp_path, "main", "new.md", tag="ff")
    writer = GitWriter.discover(clone)
    assert writer is not None
    result = writer.converge("main", lane="stable")
    assert result["action"] == "fast-forward"
    assert result["after"] == new_sha
    assert _run(clone, "rev-parse", "HEAD") == new_sha
    assert (clone / "new.md").exists()


def test_converge_reports_ahead_without_rewriting(tmp_path: Path):
    _, clone = _hub_and_clone(tmp_path)
    (clone / "local.md").write_text("# local\n", encoding="utf-8")
    _run(clone, "add", ".")
    _run(clone, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "local only")
    local_sha = _run(clone, "rev-parse", "HEAD")
    writer = GitWriter.discover(clone)
    assert writer is not None
    result = writer.converge("main", lane="preview")
    assert result["action"] == "ahead"
    assert _run(clone, "rev-parse", "HEAD") == local_sha


def test_converge_refuses_dirty_worktree(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    _advance_hub(hub, tmp_path, "main", "new.md", tag="ff")
    (clone / "index.md").write_text("dirty\n", encoding="utf-8")
    writer = GitWriter.discover(clone)
    assert writer is not None
    before = _run(clone, "rev-parse", "HEAD")
    result = writer.converge("main", lane="stable")
    assert result["action"] == "dirty"
    assert _run(clone, "rev-parse", "HEAD") == before


def test_converge_no_branch_is_not_an_error(tmp_path: Path):
    _, clone = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(clone)
    assert writer is not None
    result = writer.converge("preview", lane="preview")
    assert result["action"] == "no-branch"


def test_converge_diverged_without_preserve_refs_refuses(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path, branch="main")
    _run(hub, "update-ref", "refs/heads/preview", "refs/heads/main")
    subprocess.run(
        ["git", "clone", "--branch", "preview", str(hub), str(clone.parent / "review")],
        capture_output=True,
        text=True,
        check=True,
    )
    review = clone.parent / "review"
    (review / "draft.md").write_text("# draft\n", encoding="utf-8")
    _run(review, "add", ".")
    _run(review, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "draft")
    local_sha = _run(review, "rev-parse", "HEAD")
    # Rebuild preview on the hub without this checkout's commit (an admin
    # rebuild that did NOT include the draft, e.g. it was reverted).
    _advance_hub(hub, tmp_path, "preview", "rebuilt.md", tag="rebuild")
    writer = GitWriter.discover(review)
    assert writer is not None
    result = writer.converge("preview", lane="preview")
    assert result["action"] == "diverged"
    assert _run(review, "rev-parse", "HEAD") == local_sha


def test_converge_diverged_with_preserve_glob_matching_nothing_refuses(tmp_path: Path):
    """A preserve glob is configured (the ordinary preview-lane case) but
    the hub has never recorded a matching ref yet — the first-ever
    divergence after a fresh deployment, before any admin rebuild has run.
    Must refuse exactly like the no-globs-configured case, never treat
    "nothing to check" as "safe"."""
    hub, clone = _hub_and_clone(tmp_path, branch="main")
    _run(hub, "update-ref", "refs/heads/preview", "refs/heads/main")
    subprocess.run(
        ["git", "clone", "--branch", "preview", str(hub), str(clone.parent / "review")],
        capture_output=True,
        text=True,
        check=True,
    )
    review = clone.parent / "review"
    (review / "draft.md").write_text("# draft\n", encoding="utf-8")
    _run(review, "add", ".")
    _run(review, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "draft")
    local_sha = _run(review, "rev-parse", "HEAD")
    _advance_hub(hub, tmp_path, "preview", "rebuilt.md", tag="rebuild")
    writer = GitWriter.discover(review)
    assert writer is not None
    # No refs/okf/preview-before/* ref exists anywhere on the hub.
    assert _run(hub, "for-each-ref", "refs/okf/preview-before/*") == ""
    result = writer.converge(
        "preview", lane="preview", preserve_ref_globs=("refs/okf/preview-before/*",)
    )
    assert result["action"] == "diverged"
    assert _run(review, "rev-parse", "HEAD") == local_sha


def _preview_review_clone(tmp_path: Path) -> tuple[Path, Path, Path]:
    hub, clone = _hub_and_clone(tmp_path, branch="main")
    _run(hub, "update-ref", "refs/heads/preview", "refs/heads/main")
    review = clone.parent / "review"
    subprocess.run(
        ["git", "clone", "--branch", "preview", str(hub), str(review)],
        capture_output=True,
        text=True,
        check=True,
    )
    return hub, clone, review


def _push_draft(review: Path) -> str:
    (review / "draft.md").write_text("# draft\n", encoding="utf-8")
    _run(review, "add", ".")
    _run(review, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "draft")
    tip = _run(review, "rev-parse", "HEAD")
    _run(review, "push", "origin", "HEAD:refs/heads/preview")
    return tip


def test_converge_resets_when_hub_is_rewound_onto_a_preserved_ancestor(tmp_path: Path):
    """Reverting every candidate rewinds the hub's preview onto main, an ANCESTOR
    of the serving checkout. The checkout is then "ahead", but its extra commit
    is recorded under refs/okf/preview-before/, so following the hub loses
    nothing. Without this the lane refuses every write until someone resets
    its volume by hand."""
    hub, _clone, review = _preview_review_clone(tmp_path)
    old_tip = _push_draft(review)
    base = _run(hub, "rev-parse", "refs/heads/main")
    _run(hub, "update-ref", f"refs/okf/preview-before/{int(time.time())}", old_tip)
    _run(hub, "update-ref", "refs/heads/preview", base)
    writer = GitWriter.discover(review)
    assert writer is not None
    result = writer.converge(
        "preview", lane="preview", preserve_ref_globs=("refs/okf/preview-before/*",)
    )
    assert result["action"] == "reset"
    assert result["after"] == base
    assert _run(review, "rev-parse", "HEAD") == base
    assert not (review / "draft.md").exists()
    assert _run(review, "rev-parse", result["rescue_ref"]) == old_tip


def test_converge_stays_ahead_when_extra_commits_are_not_preserved(tmp_path: Path):
    hub, _clone, review = _preview_review_clone(tmp_path)
    old_tip = _push_draft(review)
    _run(hub, "update-ref", "refs/heads/preview", _run(hub, "rev-parse", "refs/heads/main"))
    writer = GitWriter.discover(review)
    assert writer is not None
    result = writer.converge(
        "preview", lane="preview", preserve_ref_globs=("refs/okf/preview-before/*",)
    )
    assert result["action"] == "ahead"
    assert _run(review, "rev-parse", "HEAD") == old_tip


def test_converge_diverged_resets_when_preserved(tmp_path: Path):
    """A serving checkout whose HEAD is a preview tip an admin rebuild has
    since recorded and moved past (ADR-0509 F4's refs/okf/preview-before/)
    resets forward onto the rebuild cleanly — this is the ordinary case a
    serving clone hits after every admin rebuild, not a checkout with its
    own unpushed commits (those go through sync_before_write, not this
    read-side convergence)."""
    hub, clone = _hub_and_clone(tmp_path, branch="main")
    _run(hub, "update-ref", "refs/heads/preview", "refs/heads/main")
    subprocess.run(
        ["git", "clone", "--branch", "preview", str(hub), str(clone.parent / "review")],
        capture_output=True,
        text=True,
        check=True,
    )
    review = clone.parent / "review"
    # This checkout already has a draft on top of the common base (pushed
    # to the hub's preview earlier, exactly as okf-kit's own write path
    # does synchronously — a serving checkout never has *unpushed* local
    # commits, only ones the hub itself hasn't rebuilt past yet).
    (review / "draft.md").write_text("# draft\n", encoding="utf-8")
    _run(review, "add", ".")
    _run(review, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "draft")
    old_tip = _run(review, "rev-parse", "HEAD")
    _run(review, "push", "origin", "HEAD:refs/heads/preview")
    # An admin rebuild: record the checkout's current tip (WITH the draft)
    # under a preserve-ref namespace, then REWRITE preview to a sibling
    # commit built from the common base, not from old_tip — a real rebuild
    # replays kept candidates onto the (possibly-advanced) main, which does
    # not, in general, descend from a preview-only draft.
    _run(hub, "update-ref", f"refs/okf/preview-before/{int(time.time())}", old_tip)
    rebuild = tmp_path / "rebuild-source"
    subprocess.run(
        ["git", "clone", "--branch", "main", str(hub), str(rebuild)],
        capture_output=True,
        text=True,
        check=True,
    )
    (rebuild / "rebuilt.md").write_text("# rebuilt\n", encoding="utf-8")
    _run(rebuild, "add", ".")
    _run(rebuild, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "rebuild")
    new_tip = _run(rebuild, "rev-parse", "HEAD")
    _run(rebuild, "push", "--force", "origin", "HEAD:refs/heads/preview")
    writer = GitWriter.discover(review)
    assert writer is not None
    result = writer.converge(
        "preview", lane="preview", preserve_ref_globs=("refs/okf/preview-before/*",)
    )
    assert result["action"] == "reset"
    assert result["after"] == new_tip
    assert _run(review, "rev-parse", "HEAD") == new_tip
    # The pre-reset tip (with the draft) is recoverable under its own
    # rescue ref too, independent of the hub's preview-before record.
    assert result["rescue_ref"] is not None
    assert _run(review, "rev-parse", result["rescue_ref"]) == old_tip

    # A SECOND admin rebuild, chained on top of the first: the checkout
    # (now at new_tip == B) must reset again onto a fresh, unrelated tip
    # C, with B itself (not A) recorded as the preserve ref this time.
    # This exercises that each rebuild's own preview-before entry is what
    # the safety check keys on — not something left over from the first.
    _run(hub, "update-ref", f"refs/okf/preview-before/{int(time.time()) + 1}", new_tip)
    rebuild2 = tmp_path / "rebuild-source-2"
    subprocess.run(
        ["git", "clone", "--branch", "main", str(hub), str(rebuild2)],
        capture_output=True,
        text=True,
        check=True,
    )
    (rebuild2 / "rebuilt2.md").write_text("# rebuilt again\n", encoding="utf-8")
    _run(rebuild2, "add", ".")
    _run(rebuild2, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "rebuild2")
    newest_tip = _run(rebuild2, "rev-parse", "HEAD")
    _run(rebuild2, "push", "--force", "origin", "HEAD:refs/heads/preview")

    second_result = writer.converge(
        "preview", lane="preview", preserve_ref_globs=("refs/okf/preview-before/*",)
    )
    assert second_result["action"] == "reset"
    assert second_result["after"] == newest_tip
    assert _run(review, "rev-parse", "HEAD") == newest_tip
    assert _run(review, "rev-parse", second_result["rescue_ref"]) == new_tip


def test_remote_branch_sha_matches_hub(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(clone)
    assert writer is not None
    assert writer.remote_branch_sha("main") == _run(hub, "rev-parse", "main")


def test_remote_branch_sha_none_for_missing_branch(tmp_path: Path):
    _, clone = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(clone)
    assert writer is not None
    assert writer.remote_branch_sha("does-not-exist") is None


# -- SyncCoordinator ---------------------------------------------------------


def test_sync_now_updates_outcome(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    new_sha = _advance_hub(hub, tmp_path, "main", "new.md", tag="ff")
    writer = GitWriter.discover(clone)
    assert writer is not None
    coordinator = SyncCoordinator()
    outcome = coordinator.sync_now(writer, "kb", branch="main", lane="stable")
    assert isinstance(outcome, SyncOutcome)
    assert outcome.action == "fast-forward"
    assert outcome.after == new_sha
    assert coordinator.last_outcome("kb") is outcome


def test_revalidate_if_stale_respects_interval(tmp_path: Path):
    hub, clone = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(clone)
    assert writer is not None
    coordinator = SyncCoordinator()
    first = coordinator.revalidate_if_stale(
        writer, "kb", branch="main", lane="stable", interval=100.0
    )
    assert first is not None
    assert first.action == "noop"
    _advance_hub(hub, tmp_path, "main", "new.md", tag="ff")
    # Within the interval: no second check, so the fast-forward is not seen yet.
    second = coordinator.revalidate_if_stale(
        writer, "kb", branch="main", lane="stable", interval=100.0
    )
    assert second is None
    assert _run(clone, "rev-parse", "HEAD") != _run(hub, "rev-parse", "main")


def test_revalidate_if_stale_zero_interval_disabled(tmp_path: Path):
    _, clone = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(clone)
    assert writer is not None
    coordinator = SyncCoordinator()
    assert (
        coordinator.revalidate_if_stale(writer, "kb", branch="main", lane="stable", interval=0)
        is None
    )


def test_sync_now_serializes_per_bundle_concurrent_calls(tmp_path: Path):
    """Two threads calling sync_now for the same bundle never race the
    same converge() at once; each still gets a correct outcome."""
    import threading

    hub, clone = _hub_and_clone(tmp_path)
    new_sha = _advance_hub(hub, tmp_path, "main", "new.md", tag="ff")
    writer = GitWriter.discover(clone)
    assert writer is not None
    coordinator = SyncCoordinator()
    results: list[SyncOutcome] = []
    lock = threading.Lock()

    def _call():
        outcome = coordinator.sync_now(writer, "kb", branch="main", lane="stable")
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=_call) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 4
    assert _run(clone, "rev-parse", "HEAD") == new_sha
    # First caller through the lock did the real fast-forward; the rest,
    # serialized behind it, correctly observe "noop" (already current).
    actions = {r.action for r in results}
    assert actions <= {"fast-forward", "noop"}
    assert "fast-forward" in actions
