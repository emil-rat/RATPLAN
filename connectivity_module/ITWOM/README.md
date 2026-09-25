# ITWOM

RATPLAN's prior-mean implementations for the connectivity module
(architecture.md §2/§3) — both candidate physics models that feed the GP's
mean surface `m(x)`, kept under one parent folder per Emil's request.

| Folder | What | License | Runs |
|---|---|---|---|
| [`itm/`](./itm/) | ITM (Longley-Rice), via `itmlogic` | MIT (public-domain-equivalent lineage) | In-process |
| [`itwom/`](./itwom/) | ITWOM v3.0, via unmodified upstream SPLAT! | **GPL-2.0 — third-party, not RATPLAN's own code** | Own Docker container, called via subprocess |
| [`itwom_client/`](./itwom_client/) | RATPLAN's own client for `itwom/` | (RATPLAN's own) | In-process, talks to the container over stdin/stdout |

**Why `itwom/` isn't just merged into the Python code like `itm/` is:**
ITWOM's upstream (SPLAT!, bundling `itwom3.0.cpp`) is GPL-2.0, and its
licensing chain is murkier than ITM's (see architecture.md §4.2). Keeping
it as a genuinely separate program — own Dockerfile, own dependency
footprint, called only via subprocess with JSON over pipes, never imported
or linked — is what keeps RATPLAN's own code out of GPL-2.0 scope, per the
FSF's own GPL FAQ on arm's-length program separation (architecture.md
§3.1). `itwom_client/` is the thin, RATPLAN-owned side of that boundary;
everything under `itwom/` itself is licensed GPL-2.0 and should be treated
as third-party code, not edited as if it were RATPLAN's own.

Each of the three subfolders is independently installable/testable (own
`pyproject.toml`/`.venv`, or own `Dockerfile`) — see each one's own
`README.md`. Open questions and known gaps for all three are tracked
together in [`../OPEN_ISSUES.md`](../OPEN_ISSUES.md), not per-folder.
