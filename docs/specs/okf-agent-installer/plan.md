# Plan: OKF agent installer

- **Spec:** [`spec.md`](spec.md)
- **Status:** Done

> **Plan contract:** this is the implementation strategy. Unlike the spec, this
> document is allowed to change as you learn. When it changes substantially,
> note why in the changelog at the bottom.

## Approach

Package canonical skills under `okf_kit/agent_assets`, expose a small installer
helper outside `core`, and add `okf agent install` as a CLI presentation layer
over that helper. Start with tests for skill assets and installer ownership
behavior, then wire the CLI and docs. The riskiest part is safe update behavior:
the installer must distinguish OKF-owned files from unmanaged local files before
writing.

Tempted to add a generic plugin/pack framework; declining because RFC-0001
approved only skills. Tempted to add subagent/hook components now; declining
because they are explicitly deferred. Tempted to move existing repo-local
`.claude`/`.codex` artifacts; declining because installer assets should come
from package data, not project agent config.

## Constraints

- RFC-0001 approves skill-only installation and defers subagents/hooks.
- `okf_kit.core` remains pure and must not contain agent-environment writes.
- No new runtime dependency unless explicitly approved.
- Existing bundle commands must stay behavior-compatible.

## Construction tests

**Integration tests:** subprocess CLI tests for `okf agent install --help`,
dry-run, project install, and unmanaged-file refusal.
**Manual verification:** none. The wheel-install smoke test is mandatory because
the objective requires a wheel-installed `okf` to work without a source checkout.

## Design (LLD)

### Interfaces & contracts

The public interface is CLI-only:

```bash
okf agent install <claude-code|codex> --scope <project|user> [--dry-run] [--update]
```

Exit code `0` means the requested dry-run/install completed. Exit code `2`
means usage, target, path, or ownership errors. The command prints one line per
planned/written/skipped file.

### Data & schema

Each target writes a JSON ownership manifest:

- Claude Code project: `.claude/okf-agent-assets.json`
- Codex project: `.codex/okf-agent-assets.json`
- Claude Code user: `~/.claude/okf-agent-assets.json`
- Codex user: `~/.codex/okf-agent-assets.json`

The manifest records `target`, `scope`, `version`, and a mapping of installed
relative file paths to a content hash. A manifest entry proves ownership only
when target/scope match, the path is in the fixed OKF asset allowlist, the path
is relative and confined to the target root, and the current file digest matches
both the recorded digest and a known OKF release digest for that asset. Missing,
malformed, unknown, spoofed, or hash-mismatched entries are treated as
unmanaged and refused.

### Dependencies & integration

Skill assets are package data under `okf_kit/agent_assets/skills/<name>/`.
Installer code reads assets with `importlib.resources`, so wheel installs and
editable installs use the same path.

### Failure, edge cases & resilience

The installer preflights the complete write plan before creating directories,
files, or manifests. Every destination is canonicalized and must resolve under
the selected skill root or manifest parent; traversal, absolute paths, symlink
escapes, existing non-directory path components, or malformed asset/manifest
paths raise `ValueError` before any write. Existing unmanaged files cause a
`ValueError` and no overwrite. Existing
OKF-owned files are refreshed by default on re-run; `--update` remains accepted
for compatibility with earlier CLI usage. Refresh writes only when the current
file digest matches the manifest and a known OKF release digest for that asset;
hash mismatches are treated as user edits and refused unless a future force
mode exists. Dry-run computes the same plan but performs no writes. If a
manifest is missing, existing files are treated as unmanaged. Legacy manifests
that record prior known OKF asset digests can be migrated to the current
packaged skills.

## Tasks

### T1: Package skill assets are canonical and testable

**Depends on:** none

**Tests:**
- TDD: `test_skill.py` asserts package assets include `okf-search`,
  `okf-author`, and `okf-code`, valid frontmatter, distinct create and update
  workflow guidance in `okf-author`, current link guidance, progressive context
  workflow text, and code-indexing workflow text. Verifies the skill-content ACs.
- Goal-based: `uv build` wheel inspection contains all three `SKILL.md` files.
  Verifies the wheel asset AC.
- Goal-based: install the built wheel into a temporary environment and run the
  wheel-installed `okf agent install codex --scope project --dry-run` plus one
  project install. Verifies the wheel-install AC.

**Approach:**
- Add `okf_kit/agent_assets/skills/okf-author/SKILL.md`.
- Add `okf_kit/agent_assets/skills/okf-search/SKILL.md`.
- Add `okf_kit/agent_assets/skills/okf-code/SKILL.md`.
- Keep or adapt the legacy `okf-kit/skills/okf-author/SKILL.md` test fixture
  only if needed for backwards source-tree compatibility.
- Configure Hatchling to include the package-data files in wheels.

**Done when:** skill asset tests fail before assets/config changes and pass
after them; wheel inspection finds all three skill files; a temporary environment
installs the wheel and runs the wheel-installed installer dry-run plus one
project install.

### T2: Installer helper plans and applies skill writes safely

**Depends on:** T1

**Tests:**
- TDD: unit tests cover Claude Code/Codex project destinations, user
  destinations with a monkeypatched home, dry-run no-write behavior, manifest
  creation, skip-without-update, update with matching digest, refusal with
  hash-mismatched manifest entries, missing manifest refusal, malformed manifest
  refusal, spoofed manifest digest refusal, non-allowlisted but confined
  manifest entry refusal, legacy-manifest migration, unmanaged-file refusal, traversal/absolute
  destination refusal, non-directory component refusal, symlink escape refusal,
  OKF bundle root/subdirectory refusal, and no-side-effects refusal before parent
  directories, files, or manifests are created. Verifies
  install/update/path-safety ACs.

**Approach:**
- Add `okf_kit/agent_assets.py` or `okf_kit/agent_install.py` outside `core`.
- Model install operations as planned file actions before writing.
- Preflight the whole plan, including digest ownership and resolved-path
  confinement, before creating any parent directory or file.
- Write files atomically enough for local CLI use: create parents, write text,
  then write manifest after successful file writes.
- Use per-target manifests under `.claude` and `.codex` for project scope.

**Done when:** installer unit tests pass and no code under `okf_kit/core` is
changed for installer behavior.

### T3: CLI exposes `okf agent install`

**Depends on:** T2

**Tests:**
- TDD/subprocess: `okf agent install --help` shows target, scope, dry-run, and
  update options. Verifies the CLI-help AC.
- TDD/subprocess: dry-run and project install produce stable output and expected
  files. Verifies ACs 1, 2, 3.
- TDD/subprocess: unmanaged-file refusal exits with code 2. Verifies AC 5.

**Approach:**
- Add an `agent` subparser with an `install` subcommand.
- Delegate all installation decisions to the installer helper.
- Reuse existing CLI error handling for `ValueError`.

**Done when:** CLI tests pass and existing CLI tests remain green.

### T4: Documentation reflects the shipped skill-only installer

**Depends on:** T3

**Tests:**
- Goal-based: docs tests or grep checks confirm README, `wiki/interfaces/okf-cli.md`,
  `wiki/guides/authoring.md`, and `wiki/reference/tools.md` mention the installer
  and do not claim subagents/hooks ship. Verifies AC 9.

**Approach:**
- Update README install/use sections.
- Update the CLI wiki interface with `agent install`.
- Update authoring guide to mention `okf-author` create/update behavior and
  `okf-search`.
- Update tool reference build commands or CLI-only section for installer docs.

**Done when:** docs checks pass and the docs match CLI behavior.

### T5: Gates and final review are clean

**Depends on:** T1-T4

**Tests:**
- Goal-based: `uv run ruff check .`.
- Goal-based: `uv run mypy okf-kit/okf_kit`.
- Goal-based: `uv run pytest`.
- Review: adversarial-reviewer returns `Clean — ready to commit.`
- Security review: security-reviewer reviews file-write/path behavior or is
  explicitly unavailable.

**Approach:**
- Run gates.
- Run simplify pass on new code only.
- Run reviewers and fix findings.
- Mark accepted ACs complete only after verification.

**Done when:** all gates pass, reviewers are clean or explicitly unavailable,
and spec status reflects shipped state.

## Rollout

This ships as a CLI/package feature. No migration is needed. Users opt in by
running `okf agent install ...`; rollback is deleting installed OKF skill files
and the target-local manifest.

## Risks

- Wheel package-data rules may differ from editable installs; mitigate with a
  wheel inspection test.
- Installer ownership checks may be too strict for users who manually edited an
  OKF-owned skill; mitigate by reporting skipped/refused paths clearly and
  leaving `--force` for a future spec.
- Codex or Claude Code skill locations may change; mitigate by keeping target
  path rules isolated in installer helper functions.

## Changelog

- 2026-06-17: initial plan from accepted RFC-0001.
- 2026-06-18: amended to include refresh-by-default behavior, `okf-code` as an
  installed skill asset, and legacy OKF-owned manifest migration.
