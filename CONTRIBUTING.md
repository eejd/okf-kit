# Contributing to okf-kit

Thanks for contributing. This guide covers local setup, the gates every change
must pass, and the conventions the codebase enforces. The authoritative build
rules live in [`AGENTS.md`](AGENTS.md); the design rationale in
[`_docs/`](_docs/).

## Setup

```bash
uv sync --extra dev        # Python ≥ 3.12; installs okf, okf-mcp, pytest, ruff, mypy, types-PyYAML
```

## The gates (must pass before a change is done)

```bash
uv run ruff check okf-kit/okf_kit okf-kit/tests
uv run mypy okf-kit/okf_kit              # --strict
uv run pytest okf-kit/tests
```

These are the objective completion criteria. Don't move past a failing gate by
editing the gate. Source is held to 100 columns; the `okf-kit/tests/` tree is
exempt from E501 (test fixtures carry long inline Markdown).

## How we work: test-first

Core logic is written **TDD** — write the failing test against the SPEC/design
contract, confirm it's red, then implement to green. The OKF conformance and
path-handling rules are the kind of invariant that must be pinned by tests; never
ship core logic without one. Bug fixes start with a failing test that reproduces
the bug.

## Architecture rules

- **The core is pure.** `okf_kit/core/` is deterministic, no network, no
  randomness. `cli` and `mcp` are *thin* wrappers — never duplicate logic between
  them. New behavior goes in `core/`, then both surfaces call it.
- **Permissive consumer (SPEC §9).** Parsing never raises on malformed input; it
  degrades and lets `validate` report. `validate` is the only judge.
- **Security boundary — paths.** Every caller-supplied concept id and every link
  target is resolved and confined to the bundle root. Do **not** reach for raw
  `root.rglob(...)` + `resolve()` on caller-supplied paths. Use the blessed
  helpers in `okf_kit/core/links.py`:
  - `resolve_cid_path(root, cid)` — read one concept by id (containment-checked).
  - `iter_concept_files(root)` — enumerate a bundle's `.md` safely (skips symlink
    escapes and dupes). Use this, not `rglob`, in validate/search/context/index/mcp.
  - `is_within(path, root)` — the containment primitive.
  - `create_concept` writes with containment + an atomic exclusive create.
  Changes that cross this boundary (file I/O, path handling, MCP/agent input) get
  a security review.
- **Progressive context is one primitive.** `read_concept(depth>0)` *is* the
  context loader — don't add a separate `context` tool. Seed always full;
  neighbors BFS within `token_budget`; deterministic ordering.

## Adding things

- **A core function** → TDD; add a test in `okf-kit/tests/`; keep the core pure.
- **A CLI command** → add a subparser in `okf_kit/cli.py`, delegate to `core/`,
  document `--help`, pick the right exit code (`0` ok / `1` conformance / `2`
  usage & IO).
- **An MCP tool** → register it in `okf_kit/mcp.py` and add its canonical
  description to **`docs/tools.md`** inside a
  `<!-- desc:start -->` … `<!-- desc:end -->` block. The
  `test_tools_md_synced_with_mcp_descriptions` test asserts the doc and the
  server stay in sync — keep them identical.
- **A concept-type template** → add a body scaffold to `_BODY_TEMPLATES` in
  `okf_kit/core/templates.py` and the type name to `TEMPLATE_TYPES`.
- **A doc** → `docs/`; update cross-references. Design decisions go in `_docs/`
  (spec) and `AGENTS.md` (operational rules).

## Where things live

| Concern | Location |
|---|---|
| Build rules, structure | `AGENTS.md` |
| Design & requirements | `_docs/` |
| Tool reference, guides | `docs/` |
| Deferred work / known gaps | `docs/backlog.md` |
| Source | `okf-kit/okf_kit/` (`core/`, `cli.py`, `mcp.py`) |
| Tests | `okf-kit/tests/` |
| The authoring skill | `okf-kit/skills/okf-author/SKILL.md` |

## Review

Non-trivial changes run an adversarial review, and anything crossing the
security boundary runs a security review, before merge. Record deferred review
findings in `docs/backlog.md` rather than dropping them.

## License

By contributing you agree your contributions are licensed under the Apache
License 2.0 (see [`LICENSE`](LICENSE)).
