"""Git commit/push backend for MCP-authored bundle writes (eejd eco#11).

When ``okf-mcp`` runs with ``--write-mode draft --lane preview``, every successful write tool
(``create_concept``, ``init_bundle``) commits the written file into the git
repository containing the bundle and pushes to its default remote. The
intended deployment is the "local hub" pattern: the serving checkout's
``origin`` is a file-path bare repository on the same host, so no network
credentials ever exist inside the serving process/container.

Design rules, in order of importance:

1. **A preview-lane write is all or nothing** (``expected_branch`` set, which
   every draft-mode tool call does). Before writing, the checkout
   fast-forwards to the hub's preview branch and refuses to write if it has
   unpushed commits or has diverged. A failed commit or push undoes the
   write: the commit is rolled back and the file restored, and the result
   carries ``failed: true`` so the tool call fails visibly (ADR-0509 E6(3),
   eejd/okf-kit#15). A write that was reported but never reached the hub
   would otherwise be stranded when the hub preview is rebuilt.
2. **Without an expected branch, git is best-effort.** Any git problem
   degrades to a structured warning; a commit that fails to push reports
   ``pushed: false`` and the next successful push carries it.
3. **No global git config dependence.** Author identity is passed with
   ``-c user.name``/``-c user.email`` per invocation, and the repository is
   whitelisted with ``-c safe.directory=<root>`` so a uid mismatch between
   the checkout owner and the serving user does not disable git.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_GIT_TIMEOUT_S = 30
# Retry window for filesystem-cache object-visibility races (virtiofs and
# kin) — see commit_and_push. Live deployment produced TWO distinct error
# signatures for the same race ("<sha> is not a valid object" and "loose
# object <sha> ... is corrupt" — the object was valid and readable moments
# later in both cases), so the retry is deliberately NOT signature-matched:
# commit and push each get one unconditional delayed retry on failure. A
# genuine failure simply fails identically twice, costing one 2s sleep; a
# cache race succeeds on the second attempt. The cost is visible to clients:
# a preview-lane push the hub refuses (frozen or diverged) returns its tool
# error after one 2s retry.
_OBJECT_RACE_RETRY_DELAY_S = 2.0
_DEFAULT_AUTHOR_NAME = "okf-mcp"
_DEFAULT_AUTHOR_EMAIL = "okf-mcp@hive.local"


@dataclass(frozen=True)
class GitResult:
    """Outcome of one git plumbing call (never an exception)."""

    ok: bool
    stdout: str = ""
    detail: str = ""
    returncode: int = 0


class GitWriter:
    """Commit-and-push helper bound to one repository root."""

    def __init__(
        self,
        repo_root: Path,
        *,
        remote: str = "origin",
        author_name: str = _DEFAULT_AUTHOR_NAME,
        author_email: str = _DEFAULT_AUTHOR_EMAIL,
        push: bool = True,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.remote = remote
        self.author_name = author_name
        self.author_email = author_email
        self.push = push

    # -- plumbing ---------------------------------------------------------

    def _git(self, *args: str) -> GitResult:
        cmd = [
            "git",
            "-C",
            str(self.repo_root),
            "-c",
            f"safe.directory={self.repo_root}",
            "-c",
            f"user.name={self.author_name}",
            "-c",
            f"user.email={self.author_email}",
            *args,
        ]
        # Strip inherited GIT_* variables: if the serving process was itself
        # started from a git hook or similar context (GIT_DIR/GIT_INDEX_FILE
        # exported), an unscrubbed child git would silently target the
        # caller's repository instead of repo_root.
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_S,
                check=False,
                env=env,
            )
        except FileNotFoundError:
            return GitResult(ok=False, detail="git executable not found")
        except subprocess.TimeoutExpired:
            return GitResult(ok=False, detail=f"git {args[0]} timed out after {_GIT_TIMEOUT_S}s")
        except OSError as exc:
            return GitResult(ok=False, detail=f"git {args[0]} failed to start: {exc}")
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            return GitResult(
                ok=False,
                stdout=proc.stdout.strip(),
                detail=detail[:500],
                returncode=proc.returncode,
            )
        return GitResult(ok=True, stdout=proc.stdout.strip())

    # -- discovery --------------------------------------------------------

    @classmethod
    def discover(cls, bundle_root: Path, *, push: bool = True) -> GitWriter | None:
        """Return a writer for the repository containing ``bundle_root``, or None.

        Uses ``git rev-parse --show-toplevel`` from the bundle directory; a
        bundle outside any git work tree (or with git unavailable) yields
        ``None``, which callers treat as "git mode requested but not
        available for this bundle" — a logged warning, not an error.
        """
        bundle = Path(bundle_root).resolve()
        probe_root = bundle
        while not probe_root.exists() and probe_root != probe_root.parent:
            probe_root = probe_root.parent
        probe = cls(probe_root, push=push)
        result = probe._git("rev-parse", "--show-toplevel")
        if not result.ok or not result.stdout:
            return None
        repo_root = Path(result.stdout).resolve()
        try:
            bundle.relative_to(repo_root)
        except ValueError:
            return None
        return cls(repo_root, push=push)

    # -- operations -------------------------------------------------------

    def require_branch(self, expected_branch: str) -> None:
        """Raise unless this checkout is attached to ``expected_branch``."""
        if expected_branch == "main":
            raise ValueError("draft writes may not target the stable main branch")
        branch = self._git("symbolic-ref", "--short", "HEAD")
        if not branch.ok:
            raise ValueError("draft writes require an attached git branch")
        if branch.stdout != expected_branch:
            raise ValueError(
                f"draft write branch mismatch: expected {expected_branch!r}, "
                f"found {branch.stdout!r}"
            )

    def sync_before_write(self, expected_branch: str) -> None:
        """Fast-forward to the remote ``expected_branch`` before a write, or raise.

        The hub branch is the source of truth for a preview lane; it can move
        (another writer, or an administrative rebuild), and a write on a stale
        checkout would be refused on push. Refuses when the checkout has
        commits the hub lacks (unpushed or diverged), since those are exactly
        the writes a rebuild would strand. A branch the remote doesn't have
        yet is allowed: the first push creates it.
        """
        exists = self._git("ls-remote", "--exit-code", self.remote, f"refs/heads/{expected_branch}")
        if not exists.ok:
            if exists.returncode == 2:
                return
            raise ValueError(f"cannot reach {self.remote} before writing: {exists.detail}")
        tracking = f"refs/remotes/{self.remote}/{expected_branch}"
        fetched = self._retry_once(
            "fetch", "--quiet", self.remote, f"+refs/heads/{expected_branch}:{tracking}"
        )
        if not fetched.ok:
            raise ValueError(f"git fetch before write: {fetched.detail}")
        head = self._git("rev-parse", "HEAD")
        upstream = self._git("rev-parse", tracking)
        if not (head.ok and upstream.ok):
            raise ValueError("cannot resolve the checkout or hub preview before writing")
        if head.stdout == upstream.stdout:
            return
        if self._git("merge-base", "--is-ancestor", "HEAD", tracking).ok:
            merged = self._git("merge", "--ff-only", "--quiet", tracking)
            if not merged.ok:
                raise ValueError(f"git fast-forward before write: {merged.detail}")
            return
        state = (
            "has commits the hub lacks"
            if self._git("merge-base", "--is-ancestor", tracking, "HEAD").ok
            else "has diverged from the hub"
        )
        raise ValueError(
            f"preview checkout {state} ({head.stdout[:12]} vs {upstream.stdout[:12]}); "
            "refusing to write until the lane is reconciled"
        )

    def _discard(self, rels: list[str]) -> None:
        """Undo uncommitted writes to ``rels``: restore tracked files, delete new ones."""
        self._git("reset", "-q", "--", *rels)
        root = self.repo_root.resolve()
        for rel in rels:
            if self._git("cat-file", "-e", f"HEAD:{rel}").ok:
                self._git("checkout", "HEAD", "--", rel)
                continue
            path = root / rel
            path.unlink(missing_ok=True)
            # Remove directories the write created, as `reset --keep` would.
            parent = path.parent
            while parent != root and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent

    def commit_and_push(
        self,
        paths: list[Path],
        message: str,
        *,
        expected_branch: str | None = None,
    ) -> dict[str, Any]:
        """``git add`` the paths, commit, and (optionally) push to the remote.

        Returns a structured dict — ``{committed, sha?, pushed, detail?}`` —
        and never raises. An empty diff (e.g. ``init_bundle`` rewriting an
        identical index.md) reports ``committed: false`` with detail
        ``"nothing to commit"``; that is a no-op, not a failure.

        With ``expected_branch`` set the call is all or nothing (module rule
        1): any failure undoes the write and adds ``failed: true``.
        """
        strict = expected_branch is not None
        if expected_branch is not None:
            try:
                self.require_branch(expected_branch)
            except ValueError as exc:
                return self._failed(paths, str(exc))

        rels: list[str] = []
        outside: list[str] = []
        for path in paths:
            try:
                rels.append(str(Path(path).resolve().relative_to(self.repo_root.resolve())))
            except ValueError:
                outside.append(str(path))
        if outside:
            detail = f"path(s) outside repository {self.repo_root}: {', '.join(outside)}"
            if strict:
                return self._failed(paths, detail, rels=rels)
            return {"committed": False, "pushed": False, "detail": detail}
        added = self._git("add", "--", *rels)
        if not added.ok:
            if strict:
                return self._failed(paths, f"git add: {added.detail}", rels=rels)
            return {"committed": False, "pushed": False, "detail": f"git add: {added.detail}"}

        # Scoped to OUR paths: exit 0 == none of them differ from HEAD. An
        # unscoped check would see unrelated staged changes (e.g. an
        # operator's manual `git add`) as "something to commit".
        diff_quiet = self._git("diff", "--cached", "--quiet", "--", *rels)
        if diff_quiet.ok:
            return {"committed": False, "pushed": False, "detail": "nothing to commit"}

        # `--only` takes the named paths from the WORKING TREE into a
        # temporary index at commit time, so pre-existing staged changes from
        # outside this call are never swept into an okf-mcp commit (and remain
        # staged afterwards, untouched). The working-tree re-read is safe here:
        # the file was written synchronously by this same call, with no
        # intervening I/O.
        committed = self._retry_once("commit", "--only", "-m", message, "--", *rels)
        if not committed.ok:
            if strict:
                return self._failed(paths, f"git commit: {committed.detail}", rels=rels)
            return {
                "committed": False,
                "pushed": False,
                "detail": f"git commit: {committed.detail}",
            }
        sha = self._git("rev-parse", "HEAD")
        result: dict[str, Any] = {
            "committed": True,
            "sha": sha.stdout if sha.ok else None,
            "pushed": False,
        }
        if not self.push:
            return result
        refspec = f"HEAD:refs/heads/{expected_branch}" if expected_branch is not None else "HEAD"
        pushed = self._retry_once("push", self.remote, refspec)
        if pushed.ok:
            result["pushed"] = True
        elif strict:
            return self._rollback(result["sha"], f"git push: {pushed.detail}")
        else:
            result["detail"] = f"git push: {pushed.detail}"
        return result

    def _failed(
        self, paths: list[Path], detail: str, *, rels: list[str] | None = None
    ) -> dict[str, Any]:
        """Strict-mode failure before any commit: discard the write and report it."""
        if rels is None:
            rels = []
            for path in paths:
                try:
                    rels.append(str(Path(path).resolve().relative_to(self.repo_root.resolve())))
                except ValueError:
                    continue
        if rels:
            self._discard(rels)
        return {"committed": False, "pushed": False, "failed": True, "detail": detail}

    def _rollback(self, sha: str | None, detail: str) -> dict[str, Any]:
        """Strict-mode push failure: drop our own unpushed commit and its files."""
        head = self._git("rev-parse", "HEAD")
        if sha and head.ok and head.stdout == sha:
            undone = self._git("reset", "--keep", "HEAD~1")
            if undone.ok:
                return {
                    "committed": False,
                    "pushed": False,
                    "failed": True,
                    "rolled_back": True,
                    "detail": detail,
                }
            detail += f"; rollback failed ({undone.detail}), local commit {sha} remains"
        elif sha is None:
            detail += "; could not read the new commit's sha, so it was not rolled back"
        else:
            detail += f"; HEAD moved, local commit {sha} not rolled back"
        return {
            "committed": True,
            "sha": sha,
            "pushed": False,
            "failed": True,
            "rolled_back": False,
            "detail": detail,
        }

    def _retry_once(self, *args: str) -> GitResult:
        """Run a git command; on failure, one delayed retry (see the
        _OBJECT_RACE_RETRY_DELAY_S rationale — cache races have produced
        multiple error signatures, so no signature matching)."""
        result = self._git(*args)
        if result.ok:
            return result
        time.sleep(_OBJECT_RACE_RETRY_DELAY_S)
        return self._git(*args)

    def remote_branch_sha(self, branch: str) -> str | None:
        """Cheap ``ls-remote`` check for ``branch`` on this writer's remote.

        No fetch, no object transfer — one ref advertisement round trip.
        Returns ``None`` when the branch does not exist on the remote (exit
        code 2) or the remote is unreachable, so callers treat "no answer"
        and "branch absent" alike: both mean "nothing to converge to yet".
        """
        result = self._git("ls-remote", "--exit-code", self.remote, f"refs/heads/{branch}")
        if not result.ok or not result.stdout:
            return None
        return result.stdout.split()[0]

    def converge(
        self,
        branch: str,
        *,
        lane: str = "stable",
        rescue_ref_prefix: str = "refs/okf/rescue",
        preserve_ref_globs: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Bring this checkout's ``branch`` up to date with the hub, in place.

        The read side of the hub<->serve relationship (the write side is
        :meth:`sync_before_write`, which this method's fast-forward/ahead
        logic mirrors). Never restarts a process and never raises: every
        outcome is a structured dict with an ``action`` key, so a caller
        (the sync coordinator, or an admin refresh route) can report it
        without a try/except.

        ``action`` values:
          - ``"noop"``: already at the hub's tip.
          - ``"fast-forward"``: this checkout was behind; merged forward.
          - ``"ahead"``: this checkout has commits the hub lacks (normal only
            for a lane with local writers, e.g. a review lane between a
            push and the hub observing it) — reported, never rewritten.
          - ``"reset"``: diverged, but every one of this checkout's own
            commits is reachable from a ref matching ``preserve_ref_globs``
            (e.g. ``refs/okf/preview-before/*`` recorded by an admin
            rebuild) — so nothing this checkout held is actually lost by
            resetting onto the hub. The pre-reset tip is recorded under
            ``rescue_ref_prefix`` first, so it stays recoverable either way.
          - ``"diverged"``: reset would be unsafe (some local commit is not
            covered by a preserve ref) — reported, nothing changed.
          - ``"dirty"``: the worktree has uncommitted changes — refused,
            nothing changed, since a reset/merge would clobber them.
          - ``"no-branch"``: the hub has no such branch yet.
          - ``"error"``: a git operation failed unexpectedly; ``detail``
            carries the message.

        ``lane`` is carried through into the result only for the caller's
        own reporting (e.g. ``sync_status``); it changes no behavior here —
        the safety of a reset is decided entirely by ``preserve_ref_globs``,
        which the caller sets per lane.
        """
        before = self._git("rev-parse", "HEAD")
        if not before.ok:
            return {"action": "error", "lane": lane, "branch": branch, "detail": before.detail}
        porcelain = self._git("status", "--porcelain")
        if porcelain.ok and porcelain.stdout:
            return {
                "action": "dirty",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "after": before.stdout,
                "detail": "worktree has uncommitted changes; refusing to converge",
            }
        tracking = f"refs/remotes/{self.remote}/{branch}"
        exists = self._git("ls-remote", "--exit-code", self.remote, f"refs/heads/{branch}")
        if not exists.ok:
            if exists.returncode == 2:
                return {
                    "action": "no-branch",
                    "lane": lane,
                    "branch": branch,
                    "before": before.stdout,
                    "after": before.stdout,
                }
            return {
                "action": "error",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "detail": f"ls-remote: {exists.detail}",
            }
        fetched = self._retry_once(
            "fetch", "--quiet", self.remote, f"+refs/heads/{branch}:{tracking}"
        )
        if not fetched.ok:
            return {
                "action": "error",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "detail": f"git fetch: {fetched.detail}",
            }
        hub_sha = self._git("rev-parse", tracking)
        if not hub_sha.ok:
            return {
                "action": "error",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "detail": f"resolving {tracking}: {hub_sha.detail}",
            }
        if before.stdout == hub_sha.stdout:
            return {
                "action": "noop",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "after": before.stdout,
                "hub_sha": hub_sha.stdout,
            }
        if self._git("merge-base", "--is-ancestor", "HEAD", tracking).ok:
            merged = self._git("merge", "--ff-only", "--quiet", tracking)
            if not merged.ok:
                return {
                    "action": "error",
                    "lane": lane,
                    "branch": branch,
                    "before": before.stdout,
                    "hub_sha": hub_sha.stdout,
                    "detail": f"fast-forward: {merged.detail}",
                }
            after = self._git("rev-parse", "HEAD")
            return {
                "action": "fast-forward",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "after": after.stdout if after.ok else None,
                "hub_sha": hub_sha.stdout,
            }
        if self._git("merge-base", "--is-ancestor", tracking, "HEAD").ok:
            return {
                "action": "ahead",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "after": before.stdout,
                "hub_sha": hub_sha.stdout,
            }
        # Diverged. Safe to reset only if every commit HEAD has that the hub
        # lacks is already reachable from a preserved ref (e.g. an admin
        # rebuild's refs/okf/preview-before/<ts>) — that ref is what makes
        # this checkout's own history recoverable independent of a reset.
        # Those refs live on the hub, not yet in this checkout, so fetch
        # them by the same glob the caller will match against. A fetch
        # failure here is not fatal — a stale but present local copy of an
        # immutable, timestamp-named preserve ref is still safe to use —
        # but it's surfaced in the detail below rather than silently
        # falling through, so a caller can tell "no preserve refs exist
        # yet" apart from "couldn't reach the hub to check".
        fetch_problems: list[str] = []
        for glob in preserve_ref_globs:
            fetched_glob = self._git("fetch", "--quiet", self.remote, f"+{glob}:{glob}")
            if not fetched_glob.ok:
                fetch_problems.append(f"{glob}: {fetched_glob.detail}")
        safe = self._diverged_commits_are_preserved(tracking, preserve_ref_globs)
        problem_suffix = (
            f" (preserve-ref fetch problems: {'; '.join(fetch_problems)})" if fetch_problems else ""
        )
        if safe is None:
            return {
                "action": "diverged",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "after": before.stdout,
                "hub_sha": hub_sha.stdout,
                "detail": (
                    "diverged; could not evaluate preserve refs, refusing to reset" + problem_suffix
                ),
            }
        if not safe:
            return {
                "action": "diverged",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "after": before.stdout,
                "hub_sha": hub_sha.stdout,
                "detail": (
                    "diverged from the hub and this checkout holds commits not reachable "
                    "from any preserve ref; refusing to reset" + problem_suffix
                ),
            }
        rescue_ref = f"{rescue_ref_prefix}/{before.stdout}"
        rescued = self._git("update-ref", rescue_ref, before.stdout)
        if not rescued.ok:
            return {
                "action": "diverged",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "after": before.stdout,
                "hub_sha": hub_sha.stdout,
                "detail": f"could not record rescue ref before reset: {rescued.detail}",
            }
        reset = self._git("reset", "--hard", "--quiet", tracking)
        if not reset.ok:
            return {
                "action": "error",
                "lane": lane,
                "branch": branch,
                "before": before.stdout,
                "hub_sha": hub_sha.stdout,
                "detail": f"reset --hard {tracking}: {reset.detail}",
                "rescue_ref": rescue_ref,
            }
        return {
            "action": "reset",
            "lane": lane,
            "branch": branch,
            "before": before.stdout,
            "after": hub_sha.stdout,
            "hub_sha": hub_sha.stdout,
            "rescue_ref": rescue_ref,
        }

    def _diverged_commits_are_preserved(
        self, tracking: str, preserve_ref_globs: tuple[str, ...]
    ) -> bool | None:
        """True if every commit unique to HEAD is reachable from some preserve ref.

        Returns ``None`` (never resets) when no globs were configured, or a
        glob resolves no refs, or the rev-list itself fails — an unproven
        "safe" never defaults to a destructive reset.
        """
        if not preserve_ref_globs:
            return None
        preserve_args: list[str] = []
        for glob in preserve_ref_globs:
            listed = self._git("for-each-ref", "--format=%(refname)", glob)
            if listed.ok and listed.stdout:
                preserve_args.extend(listed.stdout.splitlines())
        if not preserve_args:
            return None
        unreached = self._git("rev-list", "HEAD", f"^{tracking}", "--not", *preserve_args)
        if not unreached.ok:
            return None
        return unreached.stdout.strip() == ""

    def status(self, upstream_ref: str = "origin/main") -> dict[str, Any]:
        """Repository state for the staleness/provenance signal: sha, branch, dirty.

        ``branch`` is ``None`` with ``detached: true`` on a detached-HEAD
        checkout (``symbolic-ref`` fails there, unlike ``rev-parse
        --abbrev-ref`` whose literal ``"HEAD"`` answer is indistinguishable
        from a branch actually named HEAD).
        """
        sha = self._git("rev-parse", "HEAD")
        branch = self._git("symbolic-ref", "--short", "HEAD")
        porcelain = self._git("status", "--porcelain")
        upstream = self._git("rev-parse", upstream_ref)
        relationship = "unknown"
        if sha.ok and upstream.ok:
            if sha.stdout == upstream.stdout:
                relationship = "in-sync"
            else:
                served_before = self._git("merge-base", "--is-ancestor", "HEAD", upstream_ref)
                upstream_before = self._git("merge-base", "--is-ancestor", upstream_ref, "HEAD")
                if served_before.ok:
                    relationship = "behind"
                elif upstream_before.ok:
                    relationship = "ahead"
                else:
                    relationship = "diverged"
        return {
            "repo": str(self.repo_root),
            "sha": sha.stdout if sha.ok else None,
            "served_sha": sha.stdout if sha.ok else None,
            "upstream_ref": upstream_ref,
            "upstream_sha": upstream.stdout if upstream.ok else None,
            "reconciliation": relationship,
            "branch": branch.stdout if branch.ok else None,
            "detached": (not branch.ok) if sha.ok else None,
            "dirty": bool(porcelain.stdout) if porcelain.ok else None,
        }
