"""RATPLAN's mission planner — the DP over road positions (model.md §5).

Fresh 2026-09-22, built without reference to the archived `rattfallan` project (see OPEN_ISSUES.md's
"Archive carryover audit" entry for why). Design sources are `KONTEXT.md` (mission inputs/outputs) and
`model.md` §5 (value function/recurrence, re-derived eligibility filter) — not `pseudocode-v2.md` or
`architecture.md` §§5-6, both marked non-authoritative.

Only `models/` and `primitives/protocols.py` exist so far. Still open, deliberately not decided here:
the real `Scan` grid-sampling implementation, the road-graph candidate generator, the local router, and
`Evaluate`/`BatteryModel`/`Samband` (no math yet — model.md §§6-7).
"""
