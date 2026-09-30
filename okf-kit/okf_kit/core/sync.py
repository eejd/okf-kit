"""Keep a serving checkout current with its hub, without restarting the process.

The hub is the source of truth; this checkout only ever converges *toward*
it (:meth:`~okf_kit.core.gitio.GitWriter.converge`). Nothing here decides
*when* the hub moved — that is an external trigger (a git
``reference-transaction`` hook on the hub, POSTing to the refresh route
this module's coordinator serves) plus a cheap self-healing check on use,
so a missed or failed trigger cannot leave a server silently stale.

Two things are deliberately NOT here:

- **No background polling thread.** ``revalidate_if_stale`` is called from
  the request path (a tool call, or the refresh route) — an idle server
  with no traffic and no refresh pings does no work at all.
- **No index to invalidate.** okf-kit's tools already re-read the checkout
  from disk on every call (search, read_concept, ...); "current" here means
  only "the checkout's HEAD is the hub's tip", nothing more.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from okf_kit.core.gitio import GitWriter

# git-sync (kubernetes/git-sync) uses a 10s poll floor and treats a signal
# (push trigger) as the primary path with poll as backstop; we borrow that
# shape but default poll off (see mcp.py --sync-poll) since the hub hook is
# expected to be present, and revalidate-on-use covers the gap when it is
# not.
DEFAULT_REVALIDATE_SECONDS = 30.0


@dataclass
class SyncOutcome:
    """One :meth:`GitWriter.converge` result, timestamped for reporting."""

    action: str
    lane: str
    branch: str
    at: float
    before: str | None = None
    after: str | None = None
    hub_sha: str | None = None
    detail: str | None = None
    rescue_ref: str | None = None

    @classmethod
    def from_converge(cls, result: dict[str, Any]) -> SyncOutcome:
        return cls(
            action=result.get("action", "error"),
            lane=result.get("lane", "stable"),
            branch=result.get("branch", ""),
            at=time.time(),
            before=result.get("before"),
            after=result.get("after"),
            hub_sha=result.get("hub_sha"),
            detail=result.get("detail"),
            rescue_ref=result.get("rescue_ref"),
        )

    def to_dict(self) -> dict[str, Any]:
        is_problem = self.action in {"error", "dirty", "diverged"}
        return {
            "sync_action": self.action,
            "sync_lane": self.lane,
            "sync_branch": self.branch,
            "last_sync_at": self.at,
            "hub_sha": self.hub_sha,
            "last_sync_error": self.detail if is_problem else None,
        }


@dataclass
class _BundleSyncState:
    # A per-bundle lock, not a global one: syncing bundle A never blocks a
    # tool call or refresh for bundle B.
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_checked: float = 0.0
    last_outcome: SyncOutcome | None = None


class SyncCoordinator:
    """Owns convergence state for every bundle a server serves.

    One instance per :func:`okf_kit.mcp.make_server` call, shared by the
    revalidate-on-use hook, the refresh route, and ``sync_status``.
    """

    def __init__(self) -> None:
        self._bundles: dict[str, _BundleSyncState] = {}

    def _state(self, bundle: str) -> _BundleSyncState:
        if bundle not in self._bundles:
            self._bundles[bundle] = _BundleSyncState()
        return self._bundles[bundle]

    def last_outcome(self, bundle: str) -> SyncOutcome | None:
        state = self._bundles.get(bundle)
        return state.last_outcome if state else None

    def sync_now(
        self,
        writer: GitWriter,
        bundle: str,
        *,
        branch: str,
        lane: str,
        preserve_ref_globs: tuple[str, ...] = (),
    ) -> SyncOutcome:
        """Converge ``bundle`` to ``branch`` now, blocking until done.

        Safe to call concurrently for the same bundle (e.g. several refresh
        pings arriving close together, or a ping racing a revalidate check):
        callers serialize on the bundle's own lock. This is not wasted work
        when several arrive together — :meth:`GitWriter.converge` starts
        with an ``ls-remote`` and does nothing further once the checkout is
        already at the hub's tip, so a second call right behind the first
        is cheap (one ref-advertisement round trip, no fetch).
        """
        state = self._state(bundle)
        with state.lock:
            result = writer.converge(branch, lane=lane, preserve_ref_globs=preserve_ref_globs)
            outcome = SyncOutcome.from_converge(result)
            state.last_outcome = outcome
            state.last_checked = time.monotonic()
            return outcome

    def revalidate_if_stale(
        self,
        writer: GitWriter,
        bundle: str,
        *,
        branch: str,
        lane: str,
        preserve_ref_globs: tuple[str, ...] = (),
        interval: float = DEFAULT_REVALIDATE_SECONDS,
    ) -> SyncOutcome | None:
        """Self-healing backstop: sync if it's been >= ``interval`` since the last check.

        Called at the top of every tool call. Cheap when nothing is stale
        (one monotonic comparison, no git invocation). ``interval <= 0``
        disables this (every call would sync; use the refresh route and/or
        an external poller instead). Never blocks a caller on a sync another
        thread is already running for this bundle: it checks the lock
        non-blocking and skips if busy, since that in-flight sync will
        update ``last_checked`` itself momentarily.
        """
        if interval <= 0:
            return None
        state = self._state(bundle)
        now = time.monotonic()
        if now - state.last_checked < interval:
            return None
        if not state.lock.acquire(blocking=False):
            return None
        try:
            result = writer.converge(branch, lane=lane, preserve_ref_globs=preserve_ref_globs)
            outcome = SyncOutcome.from_converge(result)
            state.last_outcome = outcome
            # A fresh timestamp, not the pre-acquire `now` above: converge()
            # itself can take a while (a real fetch), and staking
            # last_checked to when the check STARTED rather than when it
            # FINISHED would let the next interval start counting early.
            state.last_checked = time.monotonic()
            return outcome
        finally:
            state.lock.release()
