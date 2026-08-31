"""Git commit/push backend for MCP-authored bundle writes (eejd eco#11).

When ``okf-mcp`` runs with ``--git-commit``, every successful write tool
(``create_concept``, ``init_bundle``) commits the written file into the git
repository containing the bundle and pushes to its default remote. The
intended deployment is the "local hub" pattern: the serving checkout's
``origin`` is a file-path bare repository on the same host, so no network
credentials ever exist inside the serving process/container.

Design rules, in order of importance:

1. **A git failure never loses a write and never fails the tool call.** The
   concept file is already on disk by the time this module runs; any git
   problem degrades to a structured warning in the tool result (and the
   stderr tool-call log), not an exception.
2. **No global git config dependence.** Author identity is passed with
   ``-c user.name``/``-c user.email`` per invocation, and the repository is
   whitelisted with ``-c safe.directory=<root>`` so a uid mismatch between
   the checkout owner and the serving user does not disable git.
3. **Push is best-effort and separate from commit.** A commit that lands
   locally but fails to push reports ``pushed: false`` with the reason; the
   next successful push carries it.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_GIT_TIMEOUT_S = 30
_DEFAULT_AUTHOR_NAME = "okf-mcp"
_DEFAULT_AUTHOR_EMAIL = "okf-mcp@hive.local"


@dataclass(frozen=True)
class GitResult:
    """Outcome of one git plumbing call (never an exception)."""

    ok: bool
    stdout: str = ""
    detail: str = ""


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
            return GitResult(ok=False, stdout=proc.stdout.strip(), detail=detail[:500])
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
        probe = cls(Path(bundle_root), push=push)
        result = probe._git("rev-parse", "--show-toplevel")
        if not result.ok or not result.stdout:
            return None
        return cls(Path(result.stdout), push=push)

    # -- operations -------------------------------------------------------

    def commit_and_push(self, paths: list[Path], message: str) -> dict[str, Any]:
        """``git add`` the paths, commit, and (optionally) push to the remote.

        Returns a structured dict — ``{committed, sha?, pushed, detail?}`` —
        and never raises. An empty diff (e.g. ``init_bundle`` rewriting an
        identical index.md) reports ``committed: false`` with detail
        ``"nothing to commit"``; that is a no-op, not a failure.
        """
        rels: list[str] = []
        outside: list[str] = []
        for path in paths:
            try:
                rels.append(str(Path(path).resolve().relative_to(self.repo_root.resolve())))
            except ValueError:
                outside.append(str(path))
        if outside:
            return {
                "committed": False,
                "pushed": False,
                "detail": f"path(s) outside repository {self.repo_root}: {', '.join(outside)}",
            }
        added = self._git("add", "--", *rels)
        if not added.ok:
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
        committed = self._git("commit", "--only", "-m", message, "--", *rels)
        if not committed.ok:
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
        pushed = self._git("push", self.remote, "HEAD")
        if pushed.ok:
            result["pushed"] = True
        else:
            result["detail"] = f"git push: {pushed.detail}"
        return result

    def status(self) -> dict[str, Any]:
        """Repository state for the staleness/provenance signal: sha, branch, dirty.

        ``branch`` is ``None`` with ``detached: true`` on a detached-HEAD
        checkout (``symbolic-ref`` fails there, unlike ``rev-parse
        --abbrev-ref`` whose literal ``"HEAD"`` answer is indistinguishable
        from a branch actually named HEAD).
        """
        sha = self._git("rev-parse", "HEAD")
        branch = self._git("symbolic-ref", "--short", "HEAD")
        porcelain = self._git("status", "--porcelain")
        return {
            "repo": str(self.repo_root),
            "sha": sha.stdout if sha.ok else None,
            "branch": branch.stdout if branch.ok else None,
            "detached": (not branch.ok) if sha.ok else None,
            "dirty": bool(porcelain.stdout) if porcelain.ok else None,
        }
