# Mission planning — pseudocode (v2)

> **NON-AUTHORITATIVE — historical reference only, 2026-09-22.** This document is not the DP spec. It was
> restored verbatim from the archived `rattfallan` implementation and had already been superseded by that
> archived project's own final code by the time it was restored — e.g. its `Evaluate`/`Scan` split doesn't
> match the archive's actual `dp.py`/`evaluate.py`, and at least one restated formula (candidate eligibility/
> `near_edge`) encodes an assumption the archive's own code comments flagged as wrong for a real terrain-shaped
> coverage raster (see `OPEN_ISSUES.md`'s carryover-audit entry). Per Emil's 2026-09-22 instruction, the
> archived project (`../arkiv/RATPLAN - gammal/`, `../arkiv/rattfallan/`) is not to be used as a source for
> this restart at all — the DP is being re-derived from scratch from `KONTEXT.md` and the real `ITWOM`/
> `ratplan_terrain` primitives. Kept on disk for historical context only; do not cite it as spec.
>
> Original restoration note, kept for provenance: restored 2026-09-19 from the archived `rattfallan`
> implementation (`arkiv/rattfallan/pseudocode-v2.md`), verbatim below — this fresh `RATPLAN/` restart had
> lost the file even though `KONTEXT.md`'s own "Algoritm" section already pointed to it.

`Scan` and `route()` below run against a local snapshot of the mission area, not live calls into `ratmap` —
see `requirements-ratmap.md` §0 for what gets pulled and when, and `routing.py` for the (not yet decided)
local routing algorithm this implies for `route()`.

## Functions

- `Scan(position) -> CoverageRaster`
  RF/LOS coverage grid around `position`, out to sender max range (DTM
  line-of-sight; land-cover attenuation later). **Only called for the
  target and for relay-sender positions already chosen** — never per
  raw candidate.
  Every result is theoretical — a "what would this cover if a sender
  sat here" test. Nothing here is ever a real placement; only the UGV
  physically driving to a position and dropping a puck during mission
  execution makes one real (planning happens before that, entirely on
  paper). A `Scan` result belongs to exactly one candidate path: it
  gets folded into that path's own `covered_raster` (see "Dynamic
  programming structure") and is never pooled or shared with a
  different candidate path's coverage. Only one path's relays will
  ever actually get placed, so a point counting as covered for one
  candidate must never make a *different* candidate's search cheaper
  or exclude its candidates — each path has to earn its own coverage
  from its own hypothetical relay chain.
- `Evaluate(position, raster) -> (score, description)`
  Implemented in `evaluation.py` — that file is this function's real
  spec, not further defined here. Two parts:
  - **Quantitative** `score` (0–1): cover/exposure (enemy LOS via DTM +
    land-cover — `min_enemy_standoff_m` factors in here as a soft
    penalty that grows as a candidate gets closer to a known enemy
    position, not a hard filter; a candidate is never excluded purely
    for proximity to the enemy) combined with assistance (path time to
    `supply_unit`, via `/api/route`). Computed for every surviving
    candidate, whether or not it also ends up used as a relay for a
    deeper candidate — **not** what decides which candidates advance to
    become the next relay level's search frontier (see "Promotion is
    ranked by reach, not `Evaluate`"); it's what the final output is
    ranked and compared by.
  - **Qualitative** `description` (text, LLM-generated): the narrative
    output fields from `KONTEXT.md` — flygskyddstyp (cover type:
    buildings/trees) and route description (protection,
    trafficability). Never used for ranking or candidate selection,
    only carried through to the final output for the commander to read.
- `BatteryModel(leg) -> wh_consumed`
  Separate model estimating energy consumed traversing one route leg
  (Wh/meter or Wh/second at a given speed/terrain — model itself TBD,
  see `requirements-central-server.md` §4). Feeds the battery-budget
  filter in the DP recurrence below; `Evaluate` never sees it directly,
  the two are independent.
- `Samband(road_ids, covered_raster) -> probability`
  Stub for now, to be revised — probability of maintaining comms the
  *entire* route, not just at candidate endpoints. Depends on the
  leg/path-level coverage check from `requirements-ratmap.md` §2 (in
  progress on the `ratmap` side); today's `covered_raster.covers(point)`
  only proves a single point is covered, not the road between hops.
  Signature is a placeholder, deliberately not specified further yet.

## Inputs

- `target`, `supply_unit` (doubles as the resupply point for the
  maintenance-feasibility route, see "Retreat and resupply routes"),
  `enemy_locations`
- `relay_count_max` (R) — the operator-supplied puck count
  (`KONTEXT.md`'s "antalet puckar tillgängligt"); one relay level costs
  exactly one puck.
- `min_start_distance_m`
- `min_enemy_standoff_m` — "hur nära fienden vi vågar vara"; feeds
  `Evaluate`'s exposure score as a soft penalty, not a candidate filter
  (see `Evaluate` above).
- `max_mission_time_s`
- `battery_requirement_wh` — required battery remaining at `target`
  (`KONTEXT.md`'s "krav på batteri vid mål").
- `current_battery_wh` — the assigned UGV's charge level at plan time,
  read from `central-server`, not navigator-entered.
- `retreat_point` — known safe rally point for withdrawal. Assumed
  given/already known for now; this algorithm doesn't search for or
  choose it.
- `sampling_step_m` — candidate spacing along roads
- `K` — max candidates kept per relay level (beam width)
- `edge_tolerance_fraction` — how close to a relay's max `Scan` range a
  candidate must sit to count as a legitimate puck-placement point,
  expressed as a fraction of that relay's range (e.g. `0.1` = must fall
  within the outer 10% of range), see "Puck placement must sit at the
  coverage edge" below.

Not yet inputs — present in `KONTEXT.md` as planning inputs from C2/`ratmap` but not wired into this
algorithm yet:

- `sidoförband` (friendly unit positions) — data source undecided (`ratmap` or `central-server`), see
  `requirements-central-server.md` §6.
- User-drawn routes ("användarinlagda vägar") — see `requirements-central-server.md` §11.

Other rats and their planned routes ("andra råttor och deras planerade vägar") are out of scope for the
current plan — deliberately not modeled here at all, not even as a deferred input.

Mined/closed roads ("mineringar/avstängda vägar") are the exception — not a DP input at all, since a closed
road is excluded transparently at the road-graph level (`ratmap`'s `enabled` flag), before candidate
generation ever sees it. See `requirements-ratmap.md` §8. Left out until that's settled.

## Dynamic programming structure

A placed relay sender is a position whose best path **to the target** is
already fully known — it was computed once, when the relay was chosen.
Every candidate discovered near that relay can reach the target via the
relay's already-known path, so its own best-path-to-target never needs a
fresh search all the way to `target` — only a short local search to the
relay, plus the relay's memoized cost.

- **State**: a road position `pos`.
- **Value**: `best[pos] = (cost_seconds, battery_consumed_wh, road_ids, relay_chain, covered_raster)`
  — the cheapest known way from `pos` to `target` in time; the energy
  that path would cost, accumulated leg by leg via `BatteryModel` (kept
  as an independent running total from `cost_seconds`, not folded into
  it — time and energy don't trade off linearly against terrain/speed);
  the ordered list of relay positions a puck has to be dropped at along
  that way (nearest `pos` first, i.e. in the order the rat actually
  drives past them); and `covered_raster`, the union of every `Scan`
  result along *this specific path's own* chain (`target`'s raster plus
  `Scan(p)` for every `p` in `relay_chain`). This union is private to
  `pos`'s own lineage — never merged with any other candidate's
  coverage, since only one path's relays would ever really exist.
- **Base case**: `best[target] = (0, 0, [], [], Scan(target))` — the
  target never has a puck placed on it (see `pseudocode.md`'s
  `Scan(sender, ...)`: the sender placed at the target is a hypothetical
  stand-in for computing reciprocal coverage, not a real placement).
  `Scan(target)` is the one piece of state every path starts from in
  common; it isn't a relay any particular path is placing, so reusing
  it across paths isn't the kind of sharing the rest of this section
  rules out.
- **Recurrence**: for a candidate `c` found near an already-placed relay `p`
  (which has a known `best[p]`):
  `best[c] = route(c, p).cost_seconds + best[p].cost_seconds` for time,
  `BatteryModel(route(c, p)) + best[p].battery_consumed_wh` for energy,
  with `road_ids = route(c, p).road_ids + best[p].road_ids`,
  `relay_chain = [p] + best[p].relay_chain`, and
  `covered_raster = best[p].covered_raster ∪ Scan(p)` — `c`'s own
  path's coverage, and nothing borrowed from any other candidate's. `c`
  is only kept if it clears **both** budgets: `cost_seconds <=
  max_mission_time_s` and `current_battery_wh - battery_consumed_wh >=
  battery_requirement_wh`.
- **Memoize on placement**: `best[p]` is computed once, the moment `p` is
  kept into the frontier — not recomputed for every candidate that later
  routes through it. `p` surviving the beam only means it's a live
  search branch: none of this is real until the UGV actually drives the
  chosen path and drops a puck at each `relay_chain` position in turn,
  during mission execution, not during planning.

This replaces the earlier `cumulative_time(c, p)` placeholder with an exact
definition, turns every deeper-level path query into a short local `route`
call instead of a long search to `target`, and gives monotonic progress for
free: `best[c] >= best[p]` on both budgets always, since `route(c, p)`'s
time and energy cost are never negative, so a chain can never loop back on
itself.

## Puck placement must sit at the coverage edge

From relay level 1 onward, a candidate `c` generated near an already-placed
relay `p` is only a legitimate next puck-placement point if it sits near
the *edge* of `raster_p` — within the outer `edge_tolerance_fraction` of
`p`'s max `Scan` range — not merely anywhere inside it. A point comfortably
inside `raster_p`
doesn't actually need this hop's puck to be reachable from `p`; treating it
as a placement point anyway would spend one of a limited number of pucks
(`relay_count_max`) on a hop that didn't need to exist. This is independent
of `Evaluate`'s score — a candidate can score well on cover and assistance
while still being a poor relay choice if it isn't extending reach.

This only constrains which candidates are eligible to be carried forward as
relay-chain-extending points (both reported at that level and used to spawn
the next level's search); it doesn't touch the 0-relay frontier generated
directly from `Scan(target)` — `target` is fixed and isn't itself a puck
placement, so those candidates keep their existing filter (covered by
`Scan(target)`, no edge requirement).

## Promotion is ranked by reach, not `Evaluate`

`near_edge` above decides *eligibility* — whether a candidate is close
enough to the range boundary to count as a legitimate puck placement at
all. Ranking *among* eligible candidates, when more of them pass than the
beam width `K` allows, uses pure reach — distance from the candidate to
the relay that reaches it (`p`, or `target` at level 0; assumes `route()`'s
leg result carries a `distance_m` alongside `cost_seconds`/`road_ids`) —
not `Evaluate`'s score. A puck is never manned: nobody stands next to it,
and it never needs an escape route of its own, so cover/exposure and
withdrawal feasibility have nothing to say about whether a point is a
*good relay*. What makes a relay good is purely how much ground it lets
the search cover next.

That doesn't mean cover/exposure and escape routes go unevaluated for
these points, though — every point that survives into the frontier plays
a dual role: it's simultaneously a candidate *relay* for whatever gets
discovered beyond it, **and** a reported *starting position* in its own
right, since nothing stops the operator from choosing to stop exactly
there and use fewer relays. So `Evaluate`, `Samband`, and the per-candidate
retreat/resupply routes (see "Retreat and resupply routes") are still
computed for every survivor, regardless of whether it also gets used as a
relay one level deeper — that's what the final cross-level comparison in
"Output" ranks by. Reach picks who advances the search; `Evaluate` picks
who wins the comparison.

## Algorithm

```
best = { target: (0, 0, [], [], Scan(target)) }
# memo: position -> (cost_seconds, battery_consumed_wh, road_ids, relay_chain, covered_raster)

def report(candidates):
    # attaches everything Output needs, for every survivor regardless of
    # whether it also gets used as a relay one level deeper — see
    # "Promotion is ranked by reach, not Evaluate"
    return [(c, best[c], Evaluate(c, best[c].covered_raster),
             Samband(best[c].road_ids, best[c].covered_raster),
             route(c, retreat_point), route(c, supply_unit))
            for c in candidates]

frontier = generate_candidates(target, min_start_distance_m, sampling_step_m)
           # on-road, outside min-distance annulus, discretized every
           # sampling_step_m, deduplicated
frontier = [c for c in frontier if best[target].covered_raster.covers(c)]   # O(1) lookup
frontier = [c for c in frontier if route(c, target).cost_seconds <= max_mission_time_s]
frontier = [c for c in frontier
            if current_battery_wh - BatteryModel(route(c, target)) >= battery_requirement_wh]
frontier = top_K(frontier, key=lambda c: route(c, target).distance_m, K)
                                              # pure reach, farthest first — not Evaluate, see
                                              # "Promotion is ranked by reach, not Evaluate"

for p in frontier:
    leg = route(p, target)
    best[p] = (leg.cost_seconds, BatteryModel(leg), leg.road_ids, [], best[target].covered_raster)
    # p is now a known point, 0 relays, coverage = just the target's

results = [report(frontier)]   # results[0] = 0-relay candidates, fully evaluated for reporting

for n in 1..relay_count_max:
    next_frontier = []
    for p in frontier:                      # p already has a known best[p], own covered_raster
        raster_p = Scan(p)                  # theoretical: what a relay at p would add to THIS path
        candidates = generate_candidates(p, min_start_distance_m, sampling_step_m)
        candidates = [c for c in candidates
                      if raster_p.covers(c) and not best[p].covered_raster.covers(c)
                      and raster_p.near_edge(c, edge_tolerance_fraction)]
                      # "already covered" checks only p's own path history — never another
                      # candidate's hypothetical relays. near_edge rejects points that would
                      # already be reachable without this hop's puck — see "Puck placement
                      # must sit at the coverage edge"
        for c in candidates:
            leg = route(c, p)                                   # short local search, not to target
            cost_c = leg.cost_seconds + best[p].cost_seconds
            battery_c = BatteryModel(leg) + best[p].battery_consumed_wh
            if cost_c <= max_mission_time_s and current_battery_wh - battery_c >= battery_requirement_wh:
                relay_chain = [p] + best[p].relay_chain
                covered_raster = best[p].covered_raster | raster_p   # c's own coverage, no one else's
                best[c] = (cost_c, battery_c, leg.road_ids + best[p].road_ids, relay_chain, covered_raster)
                next_frontier.append((c, leg.distance_m))  # memoize c, keep this hop's reach for ranking

    if not next_frontier:
        break                                # frontier fully covered, stop
    frontier = [c for c, _ in top_K(next_frontier, key=lambda pair: pair[1], K)]
                                              # pure reach again — global beam (candidate selection
                                              # only), not per-branch, not Evaluate
    results.append(report(frontier))

output = flatten(results)   # each entry: best[c], relay_count = level, Evaluate(c, best[c].covered_raster)
                             # = (score, description), Samband(...), and this candidate's own
                             # retreat_route / resupply_route (route(c, retreat_point) / route(c, supply_unit))
```

## Coverage stays private to each path

Every `covered_raster` above belongs to exactly one path through
`best[]` — the union of `Scan(target)` and `Scan(p)` for each `p` in
that specific candidate's own `relay_chain`, and nothing else. A "set
amount" of alternative paths (`K` per level) are built up and compared
side by side, but only one of them will ever actually be executed, and
during execution only *that* path's relays get physically placed. If
one candidate's hypothetical relay were allowed to extend or shorten a
*different* candidate's search, that different candidate's proposal
would silently depend on a puck that, in the scenario where it's the
one actually chosen, was never dropped. Nothing in this algorithm
writes coverage anywhere shared or persistent — every `CoverageRaster`
here stays scoped to the single path that produced it, and stays
theoretical until the UGV actually drives that specific path and drops
a puck at each `relay_chain` position in turn, during mission execution.

`top_K` pooling candidates from different parents `p` into one
`next_frontier` before reselecting is only about which candidates
advance — it never merges their `covered_raster`s. Each kept candidate
carries its own, inherited only from its own parent.

## Retreat and resupply routes

Both "fria tillbakaryckningsvägar" (free withdrawal routes) and
"möjlighet till underhåll" (maintenance/resupply feasibility) reduce to
the same computation — one `route()` call from a candidate's own position
to a known point — just aimed at a different destination:

- **Withdrawal**: `route(c, retreat_point)`. `retreat_point` is a new
  input, assumed already known/given, not searched for or chosen by this
  algorithm.
- **Resupply/maintenance**: `route(c, supply_unit)` — reuses the existing
  `supply_unit` input rather than adding a new one, since the resupply
  point is already modeled as known.

Computed per candidate, not once per mission. These describe the
*operator's* escape/resupply routes, from wherever they're actually
standing (the starting position `c`) — not the rat's own path to
`target`. `KONTEXT.md` lists both as part of what gets evaluated for
*each* proposal, and a candidate far from `retreat_point`/`supply_unit`
has a materially different withdrawal/resupply story than one close by;
collapsing this to a single target-rooted computation would have hidden
that difference. See "Promotion is ranked by reach, not `Evaluate`" for
why this only applies to reported starting positions, never to a
candidate's own relay chain — nobody stands at a puck, so a puck doesn't
get its own withdrawal route.

Deliberately plain road-time routes, unrelated to `covered_raster` or
`Samband` — withdrawal/resupply are "is there a road and how long does
it take," not scored for comms continuity along the way.

## Output

Per candidate — every survivor at every relay level, whether or not it
also ends up used as a relay for a deeper candidate (see "Promotion is
ranked by reach, not `Evaluate`"): road path to target (`best[c].road_ids`),
`best[c].cost_seconds`, `best[c].battery_consumed_wh` (and battery
remaining at target = `current_battery_wh - best[c].battery_consumed_wh`),
number of relay senders used, the relay positions to drop pucks at in
drive order (`best[c].relay_chain`), that path's own coverage
(`best[c].covered_raster` — private to this candidate, see "Coverage
stays private to each path"), `Evaluate(c, best[c].covered_raster)` —
both the quantitative `score` (used for ranking) and the qualitative
LLM `description` (flygskyddstyp, route protection/trafficability),
`Samband(best[c].road_ids, best[c].covered_raster)` (stub, to be
revised), and this candidate's own `retreat_route`/`resupply_route`
(`route(c, retreat_point)`/`route(c, supply_unit)`, see "Retreat and
resupply routes"). Ranked by quantitative score across all relay counts
(0..R) combined.

Not yet modeled: `sidoförband` (friendly unit positions) — data source
undecided, see `requirements-central-server.md` §6.
