# Contributing to okf-kit

Thanks for contributing. This guide covers local setup, the gates every change
must pass, and the conventions the codebase enforces. The authoritative build
rules live in [`AGENTS.md`](AGENTS.md); format, architecture, and backlog docs
live in the [`wiki/`](wiki/) OKF bundle.

## Setup

```bash
uv sync --extra dev        # Python >= 3.12; installs CLI, tests, lint, typecheck
```

The dev extra also installs Tree-sitter parser dependencies used by
`okf code index`.

## The gates (must pass before a change is done)

```bash
uv run ruff check .
uv run mypy okf-kit/okf_kit              # --strict
uv run pytest
python3 .codex/skills/work-loop/scripts/lint-spec-status.py
```

These are the objective completion criteria. Don't move past a failing gate by
editing the gate. Source is held to 100 columns; the `okf-kit/tests/` tree is
exempt from E501 (test fixtures carry long inline Markdown).

## How we work: test-first

Core logic is written **TDD**: write the failing test against the format,
conformance, or design contract, confirm it is red, then implement to green. The
OKF conformance and path-handling rules are invariants and must be pinned by
tests. Bug fixes start with a failing test that reproduces the bug.

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
  description to the **`wiki/reference/tools.md`** concept inside a
  `<!-- desc:start -->` … `<!-- desc:end -->` block. The
  `test_tool_reference_synced_with_mcp_descriptions` test asserts the wiki
  reference and the server stay in sync — keep them identical.
- **A concept-type template** → add a body scaffold to `_BODY_TEMPLATES` in
  `okf_kit/core/templates.py` and the type name to `TEMPLATE_TYPES`.
- **A doc** → add a concept to the `wiki/` bundle (`okf new` / `create_concept`);
  update cross-references and regenerate indexes with `uv run okf index regen
  wiki`. Design notes, format docs, guides, and deferred work live in `wiki/`.
  Operational rules live in `AGENTS.md`.
- **A code-indexing change** → keep syntax extraction in `okf_kit/code/`,
  generated code concepts under `wiki/code*/`, and the agent workflow in
  `okf_kit/agent_assets/skills/okf-code/SKILL.md`.

## Where things live

| Concern | Location |
|---|---|
| Build rules, structure | `AGENTS.md` |
| Format and conformance | `wiki/format/` |
| Architecture | `wiki/architecture/` |
| Tool reference and guides | `wiki/reference/`, `wiki/interfaces/`, `wiki/guides/` |
| Deferred work / known gaps | `wiki/project/backlog.md` |
| Source | `okf-kit/okf_kit/` (`core/`, `cli.py`, `mcp.py`) |
| Tests | `okf-kit/tests/` |
| Agent skill assets | `okf-kit/okf_kit/agent_assets/skills/` |

## Review

Non-trivial changes run an adversarial review, and anything crossing the
security boundary runs a security review, before merge. Record deferred review
findings in the `wiki/project/backlog` concept rather than dropping them.

## License

By contributing you agree your contributions are licensed under the MIT
License (see [`LICENSE`](LICENSE)). okf-kit is an independent implementation of
the Apache-2.0 licensed Open Knowledge Format specification. Do not copy OKF
specification text, examples, schemas, sample bundles, or source files into this
repository without preserving the upstream license and attribution notices. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
