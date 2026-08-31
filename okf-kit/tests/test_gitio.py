"""Tests for the --git-commit write backend (okf_kit.core.gitio + mcp wiring).

Uses real git repositories under tmp_path in the deployment's "local hub"
shape: a bare repository (the hub) plus a working clone containing the
bundle, so ``git push origin HEAD`` exercises a credential-free file-path
remote exactly as production does.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from okf_kit.core.gitio import GitWriter
from okf_kit.core.parse import parse_concept
from okf_kit.mcp import (
    BundleRegistry,
    GitBackend,
    tool_create_concept,
    tool_init_bundle,
    tool_sync_status,
)

RICH_BODY = "# Overview\n\n" + ("word " * 130) + "\n\n# Examples\n\nexample\n"


def _run(cwd: Path, *args: str) -> str:
    # GIT_* scrubbed so fixture plumbing is immune to test-injected (or
    # hook-inherited) GIT_DIR/GIT_INDEX_FILE redirection.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=env
    )
    return proc.stdout.strip()


def _hub_and_clone(tmp_path: Path) -> tuple[Path, Path]:
    """A bare hub repo plus a working clone with one committed bundle dir."""
    hub = tmp_path / "hub.git"
    hub.mkdir()
    _run(hub, "init", "--bare", "-b", "main")
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", str(hub), str(clone)], capture_output=True, text=True, check=True
    )
    bundle = clone / "kb"
    bundle.mkdir()
    (bundle / "index.md").write_text("---\nokf_version: '0.2'\n---\n# kb\n", encoding="utf-8")
    _run(clone, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _run(clone, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "seed")
    _run(clone, "push", "origin", "HEAD")
    return hub, bundle


def _hub_files(hub: Path) -> set[str]:
    out = _run(hub, "ls-tree", "-r", "--name-only", "main")
    return set(out.splitlines())


# -- GitWriter ------------------------------------------------------------


def test_discover_finds_repo_from_bundle_subdir(tmp_path: Path):
    _, bundle = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(bundle)
    assert writer is not None
    assert writer.repo_root == bundle.parent


def test_discover_returns_none_outside_git(tmp_path: Path):
    loose = tmp_path / "loose"
    loose.mkdir()
    assert GitWriter.discover(loose) is None


def test_commit_and_push_lands_in_hub(tmp_path: Path):
    hub, bundle = _hub_and_clone(tmp_path)
    (bundle / "new.md").write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    writer = GitWriter.discover(bundle)
    assert writer is not None
    result = writer.commit_and_push([bundle / "new.md"], "okf-mcp: create concept new")
    assert result["committed"] is True
    assert result["pushed"] is True
    assert result["sha"] == _run(hub, "rev-parse", "main")
    assert "kb/new.md" in _hub_files(hub)


def test_commit_nothing_to_commit_is_noop_not_failure(tmp_path: Path):
    _, bundle = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(bundle)
    assert writer is not None
    result = writer.commit_and_push([bundle / "index.md"], "no change")
    assert result == {"committed": False, "pushed": False, "detail": "nothing to commit"}


def test_push_failure_degrades_commit_survives(tmp_path: Path):
    hub, bundle = _hub_and_clone(tmp_path)
    clone = bundle.parent
    _run(clone, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    (bundle / "new.md").write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    writer = GitWriter.discover(bundle)
    assert writer is not None
    result = writer.commit_and_push([bundle / "new.md"], "msg")
    assert result["committed"] is True
    assert result["pushed"] is False
    assert "git push" in result["detail"]
    # The local commit survives for the next successful push.
    assert "kb/new.md" in _run(clone, "ls-tree", "-r", "--name-only", "HEAD")


def test_path_outside_repo_is_rejected_structurally(tmp_path: Path):
    _, bundle = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(bundle)
    assert writer is not None
    outside = tmp_path / "outside.md"
    outside.write_text("x", encoding="utf-8")
    result = writer.commit_and_push([outside], "msg")
    assert result["committed"] is False
    assert "outside repository" in result["detail"]


def test_all_outside_paths_reported_and_inside_path_not_committed(tmp_path: Path):
    """Mixed batch with any out-of-bounds path: nothing commits, every bad
    path is named (not just the first)."""
    _, bundle = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(bundle)
    assert writer is not None
    bad1 = tmp_path / "bad1.md"
    bad2 = tmp_path / "bad2.md"
    bad1.write_text("x", encoding="utf-8")
    bad2.write_text("x", encoding="utf-8")
    inside = bundle / "good.md"
    inside.write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    result = writer.commit_and_push([bad1, inside, bad2], "msg")
    assert result["committed"] is False
    assert "bad1.md" in result["detail"] and "bad2.md" in result["detail"]
    assert "good.md" not in _run(bundle.parent, "ls-tree", "-r", "--name-only", "HEAD")


def test_git_dir_env_cannot_redirect_operations(tmp_path: Path, monkeypatch):
    """Inherited GIT_DIR/GIT_INDEX_FILE (e.g. from a git hook that launched
    the server) must not redirect commits away from the writer's repo."""
    hub, bundle = _hub_and_clone(tmp_path)
    decoy = tmp_path / "decoy.git"
    decoy.mkdir()
    _run(decoy, "init", "--bare", "-b", "main")
    monkeypatch.setenv("GIT_DIR", str(decoy))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "decoy-index"))
    (bundle / "new.md").write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    writer = GitWriter.discover(bundle)
    assert writer is not None
    assert writer.repo_root == bundle.parent
    result = writer.commit_and_push([bundle / "new.md"], "msg")
    assert result["committed"] is True and result["pushed"] is True
    assert "kb/new.md" in _hub_files(hub)


def test_push_rejected_when_hub_diverged_commit_survives(tmp_path: Path):
    """Hub moved on independently → push is rejected non-fast-forward; the
    local commit survives and is reported committed but not pushed."""
    hub, bundle = _hub_and_clone(tmp_path)
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", str(hub), str(other)], capture_output=True, text=True, check=True
    )
    (other / "kb" / "hub-side.md").write_text("---\ntype: Table\n---\nx\n", encoding="utf-8")
    _run(other, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _run(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "hub side")
    _run(other, "push", "origin", "HEAD")

    (bundle / "new.md").write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    writer = GitWriter.discover(bundle)
    assert writer is not None
    result = writer.commit_and_push([bundle / "new.md"], "msg")
    assert result["committed"] is True
    assert result["pushed"] is False
    assert "git push" in result["detail"]
    assert "kb/new.md" in _run(bundle.parent, "ls-tree", "-r", "--name-only", "HEAD")


def test_unrelated_staged_changes_are_not_swept_into_commit(tmp_path: Path):
    """An operator's manual `git add` must never leak into an okf-mcp commit."""
    hub, bundle = _hub_and_clone(tmp_path)
    clone = bundle.parent
    (clone / "operator.md").write_text("operator WIP\n", encoding="utf-8")
    _run(clone, "add", "operator.md")

    (bundle / "new.md").write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    writer = GitWriter.discover(bundle)
    assert writer is not None
    result = writer.commit_and_push([bundle / "new.md"], "okf-mcp: create concept new")
    assert result["committed"] is True
    committed_files = _run(clone, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    assert committed_files.splitlines() == ["kb/new.md"]
    # The operator's staged file is still staged, untouched.
    assert "operator.md" in _run(clone, "diff", "--cached", "--name-only")


def test_commit_message_format(tmp_path: Path):
    hub, bundle = _hub_and_clone(tmp_path)
    (bundle / "new.md").write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    writer = GitWriter.discover(bundle)
    assert writer is not None
    writer.commit_and_push([bundle / "new.md"], "okf-mcp: create concept new")
    assert _run(hub, "log", "--format=%s", "-1", "main") == "okf-mcp: create concept new"


def test_status_detached_head_reports_detached_not_branch(tmp_path: Path):
    _, bundle = _hub_and_clone(tmp_path)
    _run(bundle.parent, "checkout", "--detach")
    writer = GitWriter.discover(bundle)
    assert writer is not None
    status = writer.status()
    assert status["branch"] is None
    assert status["detached"] is True
    assert status["sha"]


def test_status_reports_sha_branch_dirty(tmp_path: Path):
    _, bundle = _hub_and_clone(tmp_path)
    writer = GitWriter.discover(bundle)
    assert writer is not None
    status = writer.status()
    assert status["branch"] == "main"
    assert status["detached"] is False
    assert status["sha"]
    assert status["dirty"] is False
    (bundle / "dirty.md").write_text("x", encoding="utf-8")
    assert writer.status()["dirty"] is True


# -- MCP wiring -----------------------------------------------------------


def test_create_concept_git_mode_commits_and_stamps_trust_fields(tmp_path: Path):
    hub, bundle = _hub_and_clone(tmp_path)
    reg = BundleRegistry({"kb": bundle})
    res = tool_create_concept(
        reg, "kb", "tables/users", "Table", "Users", "users table", RICH_BODY,
        git=GitBackend(reg),
    )
    assert res["created"] is True
    assert res["git"]["committed"] is True
    assert res["git"]["pushed"] is True
    assert "kb/tables/users.md" in _hub_files(hub)
    fm = parse_concept(bundle / "tables" / "users.md", bundle).frontmatter
    assert fm["status"] == "draft"
    assert fm["generated"]["by"] == "process:okf-mcp"
    assert fm["generated"]["at"]


def test_create_concept_git_mode_caller_trust_fields_win(tmp_path: Path):
    _, bundle = _hub_and_clone(tmp_path)
    reg = BundleRegistry({"kb": bundle})
    tool_create_concept(
        reg, "kb", "stable-one", "Table", "T", "d", RICH_BODY,
        extra={"status": "stable", "generated": {"by": "human:dep"}},
        git=GitBackend(reg),
    )
    fm = parse_concept(bundle / "stable-one.md", bundle).frontmatter
    assert fm["status"] == "stable"
    assert fm["generated"] == {"by": "human:dep"}


def test_create_concept_without_git_mode_stamps_nothing(tmp_path: Path):
    _, bundle = _hub_and_clone(tmp_path)
    reg = BundleRegistry({"kb": bundle})
    res = tool_create_concept(reg, "kb", "plain", "Table", "T", "d", RICH_BODY)
    assert "git" not in res
    fm = parse_concept(bundle / "plain.md", bundle).frontmatter
    assert "status" not in fm
    assert "generated" not in fm


def test_create_concept_git_mode_non_git_bundle_degrades(tmp_path: Path):
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "index.md").write_text("---\nokf_version: '0.2'\n---\n# kb\n", encoding="utf-8")
    reg = BundleRegistry({"kb": loose})
    res = tool_create_concept(
        reg, "kb", "orphan", "Table", "T", "d", RICH_BODY, git=GitBackend(reg)
    )
    assert res["created"] is True  # the write itself must never fail on git problems
    assert res["git"]["committed"] is False
    assert "not inside a git repository" in res["git"]["detail"]
    assert (loose / "orphan.md").is_file()


def test_init_bundle_git_mode_commits(tmp_path: Path):
    hub, bundle = _hub_and_clone(tmp_path)
    sub = bundle.parent / "kb2"
    reg = BundleRegistry({"kb2": sub})
    res = tool_init_bundle(reg, "kb2", git=GitBackend(reg))
    assert res["initialized"] is True
    assert res["git"]["committed"] is True
    assert "kb2/index.md" in _hub_files(hub)


def test_sync_status_tracked_and_untracked(tmp_path: Path):
    _, bundle = _hub_and_clone(tmp_path)
    loose = tmp_path / "loose"
    loose.mkdir()
    reg = BundleRegistry({"kb": bundle, "loose": loose})
    git = GitBackend(reg)
    tracked = tool_sync_status(reg, git, "kb", git_commit=True)
    assert tracked["tracked"] is True
    assert tracked["git_commit"] is True
    assert tracked["branch"] == "main"
    assert tracked["sha"]
    untracked = tool_sync_status(reg, git, "loose", git_commit=False)
    assert untracked["tracked"] is False
    assert untracked["git_commit"] is False
    assert "sha" not in untracked


def test_commit_retries_once_on_object_visibility_race(tmp_path: Path, monkeypatch):
    """virtiofs-class cache race: the first commit fails with a race
    signature; the single delayed retry must succeed and land the push."""
    import okf_kit.core.gitio as gitio

    hub, bundle = _hub_and_clone(tmp_path)
    (bundle / "new.md").write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    writer = GitWriter.discover(bundle)
    assert writer is not None

    real_git = writer._git
    commit_calls = {"n": 0}
    slept = {"s": 0.0}

    def flaky(*args):
        if args and args[0] == "commit":
            commit_calls["n"] += 1
            if commit_calls["n"] == 1:
                return gitio.GitResult(
                    ok=False,
                    detail="fatal: loose object deadbeef00 (stored in .git/objects/de/adbeef00) is corrupt",
                )
        return real_git(*args)

    monkeypatch.setattr(writer, "_git", flaky)
    monkeypatch.setattr(gitio.time, "sleep", lambda s: slept.__setitem__("s", s))
    result = writer.commit_and_push([bundle / "new.md"], "okf-mcp: create concept new")
    assert commit_calls["n"] == 2
    assert slept["s"] == gitio._OBJECT_RACE_RETRY_DELAY_S
    assert result["committed"] is True
    assert result["pushed"] is True
    assert "kb/new.md" in _hub_files(hub)


def test_commit_any_failure_gets_exactly_one_retry(tmp_path: Path, monkeypatch):
    """The retry is deliberately NOT signature-matched (the live race produced
    two different error strings): any commit failure gets exactly one delayed
    retry, then the failure surfaces."""
    import okf_kit.core.gitio as gitio

    _, bundle = _hub_and_clone(tmp_path)
    (bundle / "new.md").write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    writer = GitWriter.discover(bundle)
    assert writer is not None

    real_git = writer._git
    commit_calls = {"n": 0}
    sleeps = {"n": 0}

    def failing(*args):
        if args and args[0] == "commit":
            commit_calls["n"] += 1
            return gitio.GitResult(ok=False, detail="fatal: some unrelated failure")
        return real_git(*args)

    monkeypatch.setattr(writer, "_git", failing)
    monkeypatch.setattr(gitio.time, "sleep", lambda s: sleeps.__setitem__("n", sleeps["n"] + 1))
    result = writer.commit_and_push([bundle / "new.md"], "msg")
    assert commit_calls["n"] == 2
    assert sleeps["n"] == 1
    assert result["committed"] is False
    assert "some unrelated failure" in result["detail"]


def test_commit_double_race_fails_after_single_retry(tmp_path: Path, monkeypatch):
    """If the retry itself hits the race marker again, there is no second
    retry: exactly two attempts, one sleep, committed: False."""
    import okf_kit.core.gitio as gitio

    _, bundle = _hub_and_clone(tmp_path)
    (bundle / "new.md").write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    writer = GitWriter.discover(bundle)
    assert writer is not None

    real_git = writer._git
    commit_calls = {"n": 0}
    sleeps = {"n": 0}

    def always_racing(*args):
        if args and args[0] == "commit":
            commit_calls["n"] += 1
            return gitio.GitResult(ok=False, detail="fatal: cafebabe is not a valid object")
        return real_git(*args)

    monkeypatch.setattr(writer, "_git", always_racing)
    monkeypatch.setattr(gitio.time, "sleep", lambda s: sleeps.__setitem__("n", sleeps["n"] + 1))
    result = writer.commit_and_push([bundle / "new.md"], "msg")
    assert commit_calls["n"] == 2
    assert sleeps["n"] == 1
    assert result["committed"] is False
    assert "is not a valid object" in result["detail"]


def test_push_any_failure_gets_exactly_one_retry(tmp_path: Path, monkeypatch):
    """Push gets the same single unconditional retry as commit: exactly two
    push attempts, one sleep, pushed: False surfaces on permanent failure
    while the local commit survives."""
    import okf_kit.core.gitio as gitio

    _, bundle = _hub_and_clone(tmp_path)
    (bundle / "new.md").write_text("---\ntype: Table\n---\nbody\n", encoding="utf-8")
    writer = GitWriter.discover(bundle)
    assert writer is not None

    real_git = writer._git
    push_calls = {"n": 0}
    sleeps = {"n": 0}

    def failing_push(*args):
        if args and args[0] == "push":
            push_calls["n"] += 1
            return gitio.GitResult(ok=False, detail="fatal: remote unreachable")
        return real_git(*args)

    monkeypatch.setattr(writer, "_git", failing_push)
    monkeypatch.setattr(gitio.time, "sleep", lambda s: sleeps.__setitem__("n", sleeps["n"] + 1))
    result = writer.commit_and_push([bundle / "new.md"], "msg")
    assert push_calls["n"] == 2
    assert sleeps["n"] == 1
    assert result["committed"] is True
    assert result["pushed"] is False
    assert "remote unreachable" in result["detail"]
