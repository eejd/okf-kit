# Progressive context loading

`read_concept` is OKF's progressive-disclosure principle (index → concept →
links) applied to the **LLM context window** instead of a UI pane. An agent
loads the minimum it needs and expands on demand, always under a token budget.

## The funnel (cheap → expensive)

1. **`search`** — a hit list only: `cid, title, type, snippet, score`. No bodies.
2. **`read_concept(cid, depth=0)`** — one full concept (frontmatter + body).
3. **`read_concept(cid, depth=1..N)`** — the concept plus its N-hop neighborhood
   (concepts reachable via relative links), concatenated as Markdown.

## Token-budget semantics

- Every context-returning tool takes `token_budget` (default `8000`).
- The **seed concept is always included in full**; neighbors are added in BFS
  order by depth until the budget is reached.
- On truncation a trailing marker names what was omitted and how to get it:
  `… (3 concept(s) omitted …: metrics/arr, tables/orders — raise depth or
  token_budget, or read each).`
- **Deterministic:** BFS, then alphabetical `cid` tiebreak; char-based token
  estimate (≈4 chars/token); no randomness — reproducible across runs.

## Worked example

Bundle: `tables/users` links to `metrics/churn`, which links to `refs/def`.

```
okf read mykb tables/users                  # depth 0: just users
okf read mykb tables/users --depth 1        # users + metrics/churn
okf read mykb tables/users --depth 2        # users + churn + refs/def
okf read mykb tables/users --depth 2 --token-budget 4000   # truncate + marker
```

Start at depth 0; raise depth only when you need surrounding context. For one
concept, MCP clients can also address it as the resource
`okf://<bundle>/concepts/<id>.md`.
