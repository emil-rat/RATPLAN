# RATPLAN Mathematical Model

Ändringslogg:
2026-09-20 - Skapad av Claude (session with Emil J) — split out of `architecture.md`, which had been
carrying both the system design and the underlying math together. This file is the math only: the
connectivity/coverage model (physics prior + Bayesian/kriging correction) and the mission-planner's
optimization formulation (the DP). `architecture.md` is now the system/backend design that *implements*
this — package layout, service boundaries, testing, licensing. When the two disagree, this file is
authoritative for *what is being computed*; `architecture.md` is authoritative for *where/how it runs*.
2026-09-20 - Claude (same day, separate turn) — §3.5 gained a third kernel-design option (feature-augmented
ARD kernel over relay-relative geometry, per Emil's own idea) after finding two RF-specific precedents not
in `reading_list.md`'s v4 pass (GPRT, TKL — see `reading_list.md`'s new Tier 1.6 for both, added this same
turn). §3.4 gained a pointer to coregionalization/multi-output GPs as the concrete mechanism for that
section's already-open joint-vs-independent-GP question, surfaced by the same literature pass.

Companion docs: [`architecture.md`](./architecture.md) (system/backend design), [`Goal.md`](./Goal.md)
(mission intent — the one-paragraph source of the "ITWOM as prior + kriging" idea), [`KONTEXT.md`](./KONTEXT.md)
(terms, original algorithm sketch), [`pseudocode-v2.md`](./pseudocode-v2.md) (the DP mission-planner spec —
§5 below restates its math; that file is still the authoritative spec for the algorithm's control flow),
[`research/reading_list.md`](./research/reading_list.md) (the papers §§2–4 below are drawn from, with full
citations and confidence ratings).

---

## 1. Two models, one document

RATPLAN's output rests on two distinct mathematical models, developed to different levels of maturity:

1. **The connectivity/coverage model** (§§2–4) — how a coverage posterior (expected signal strength/link
   probability, plus confidence) is produced and updated for a candidate sender position. Reasonably
   mature: Tier 0–2 of `reading_list.md` are read and the equations are settled, even though the code
   (`ITWOM/itm/`, `ITWOM/itwom/`) currently only implements the physics-prior half (§2), not the GP/kriging
   correction (§3) yet.
2. **The mission-planner optimization model** (§5) — the dynamic program that searches road positions for
   relay chains. Fully specified in `pseudocode-v2.md`; §5 here restates its value function and recurrence
   in one place alongside the other math, and adds the parts that document is deliberately silent on
   (optimality, or the lack of it, under a bounded beam width).

Two smaller, deliberately unfinished models sit downstream of both (§§6–7): `Evaluate`'s scoring function
and `BatteryModel`/`Samband`. These are documented as open, not worked out — see each section.

## 2. Connectivity model — physics prior

Per `Goal.md`: a first approach using ITWOM (or ITM) alone as the connectivity approximation is expected to
be too weak for Råttan's terrain and scale (short relay hops, complex Nordic forest terrain) — but it is
still the right **prior mean**, not something to discard. §3 is what corrects it online.

For a candidate sender position, ITM or ITWOM (`architecture.md` §3) produces a deterministic point-to-point
path-loss prediction to every cell in the area of interest, given a terrain profile (DTM elevation samples
along the great-circle path), frequency, antenna heights, ground constants, and climate. Call this surface
`m(x)` for a query point `x` — the GP's mean function in §3, not the final output.

This corresponds to the deterministic term in the standard channel decomposition (Malmirchegini & Mostofi,
Eq. 1; building on Gudmundson):

```
Υ_dB(q) = K_dB − 10·n_PL·log₁₀‖q − q_b‖ + ν(q) + ω(q)
```

where `K_dB` and `n_PL` are a fitted path-loss intercept/exponent in the general log-distance model — in
RATPLAN's case, **ITM/ITWOM's own physics-based prediction plays this role directly**, rather than fitting
`K_dB, n_PL` from data (though §3.3 notes the alternative: treating ITM/ITWOM's own calibratable inputs as
parameters fit online, the same way). `ν(q)` is the spatially correlated shadowing residual (§3) and `ω(q)`
is uncorrelated small-scale/multipath noise.

## 3. Connectivity model — Bayesian/kriging correction

**Status: designed, not yet implemented.** `ITWOM/itm/` and `ITWOM/itwom/` produce `m(x)` only; nothing in
the codebase yet computes a posterior. This section is the target design for that layer.

### 3.1 Gaussian Process formulation

Model coverage as a GP with an informative, physics-based mean rather than the usual zero mean:

```
f(x) ~ GP(m(x), k(x, x'))
```

- `m(x)`: ITM/ITWOM's predicted path loss (or its derived link-margin value, §4) at `x` — §2.
- `k(x, x')`: covariance of the residual — modeled as Gudmundson's exponential shadowing correlation plus
  an uncorrelated noise term:

  ```
  k(x, x') = α · exp(−‖x − x'‖ / β) + σ² · [x = x']
  ```

  `α` is the residual (shadowing) variance, `β` is the **decorrelation distance** — how far, physically, one
  measurement's information extends — and `σ²` is uncorrelated measurement/multipath noise.

Given a set of live measurements `X, y` (positions Råttan has driven through and their observed RSSI,
converted to the same path-loss units as `m`), the posterior at a query point `x*` is the standard GP
predictive distribution with a fixed mean function (Rasmussen & Williams, GPML Eq. 2.37–2.38):

```
μ*(x*) = m(x*) + k(x*, X) [K(X, X) + σ²I]⁻¹ (y − m(X))
σ*²(x*) = k(x*, x*) − k(x*, X) [K(X, X) + σ²I]⁻¹ k(X, x*)
```

Two properties worth stating explicitly, since they justify the whole design:

- **The variance term has no dependence on `m(·)`.** The mean function only ever affects the posterior
  *mean*, and only through the residual `(y − m(X))`. At zero measurements, `μ*(x*) = m(x*)` exactly — the
  posterior degrades gracefully to the physics prior wherever there's no data yet, rather than reverting to
  a meaningless zero.
- **Posterior variance is non-increasing as data accumulates** (GPML Ex. 4) and, more specifically for this
  channel model, **prediction error variance at an unmeasured location decreases monotonically as `β`
  increases** (Malmirchegini & Mostofi, Theorem 4, empirically validated: −29 dB error variance predicting
  unmeasured points from 5% coverage over ~16 m). This is the formal justification for "driving past a
  handful of points corrects the whole surface, not just the sampled points" — see `architecture.md` §2.

`Scan(sender, coordinates)`'s output (`architecture.md` §2, `pseudocode-v2.md`) is `(μ*(x), σ*²(x))` per
cell — mean **and** variance. Relay placement and `Evaluate` (pseudocode step 1) consume both: variance is
what should eventually drive "where should the next relay/measurement go" (Tier 3 of the reading list — not
yet designed here, since it's the next step after this correction layer exists at all).

### 3.2 Parameter estimation

`α`, `β`, `σ²` (and, optionally, `m`'s own inputs — see below) need to be estimated from data, not assumed.
The usable recipe (Malmirchegini & Mostofi, Eqs. 3–6 — geostatistics calls the same procedure variogram
fitting):

1. Fit the mean's parameters by least squares if treating them as inferred rather than fixed (see below):
   `θ̂_LS = (HᵀH)⁻¹Hᵀy`.
2. Compute residuals `ν̂ = y − m(X)` (or `y − Hθ̂` if `θ` was fit).
3. Bin residual pairs by separation distance, compute the empirical spatial correlation `r̂(l)` per bin.
4. Weighted-least-squares fit of `ln(α · exp(−l/β))` to `ln r̂(l)` to recover `α, β`.
5. `σ²` from the residual variance at zero separation (the nugget).

**Design choice, not yet decided:** GPML §2.7 treats the mean as *fixed* — plug in ITM/ITWOM's output as-is.
Malmirchegini & Mostofi instead *fit* their mean's parameters (`θ`, i.e. path-loss intercept/exponent) from
the same sparse field data, then krige the residual on top. RATPLAN could do either: treat ITM/ITWOM as
fixed, or treat its calibratable inputs (ground constants `ε, σ_g`; vegetation-attenuation coefficients —
`OPEN_ISSUES.md`'s uncalibrated-defaults gap) as parameters fit online via the same LS procedure, jointly
with the shadowing correlation. The second turns "ITM/ITWOM might be wrong for granite/pine" from a fixed
liability into something the same update loop corrects, at the cost of a harder fitting problem. Not
resolved — flagged for whoever builds this layer.

### 3.3 Online/incremental update

Råttan reports RSSI while driving; the posterior must update as each new point arrives, not refit from
scratch — a full GP refit is `O(n³)` in the number of measurements (GPML Algorithm 2.1's own Cholesky cost),
which does not scale to a continuous driving session. **No specific incremental algorithm is chosen yet** —
candidates, in increasing recency (`reading_list.md` Tier 2):

- Fink & Kumar (ICRA 2010) — closest operational match (single moving robot, GP-based radio map built
  incrementally).
- Quattrini Li et al. (Autonomous Robots 2020) — closest architectural match: a GP seeded with a
  physical/environment-map prior (their version of "start from ITM/ITWOM"), updated online, validated on a
  real robot.
- arXiv:2607.17954 (2026) — most recent, most directly on the numerical problem: a memory-based mechanism
  for updating a GP posterior from a streaming measurement history without the full `O(n³)` refit cost.

This is a genuine open implementation decision, not a placeholder — whoever builds §3 picks one of these
(or something derived from them) and should update this section with the choice and why.

### 3.4 Independent vs. joint GP across relays

Open question, carried from `reading_list.md`'s note on Ferris/Fox/Hähnel's per-access-point independence
assumption: RATPLAN needs to reason about several relay transmitters at once. The default precedent (a
separate GP fit per relay, no cross-relay correlation) is simplest and matches most of the literature, but
assumes relays' residuals are independent — false if relays share terrain/vegetation context (e.g. two
relays on the same hillside, in the same forest stand). A jointly-modeled alternative may be needed instead.
**Not decided** — needed before implementing §3.1–3.3 for more than a single relay. If joint modeling is
ever adopted, the natural mechanism is a **multi-output GP via coregionalization** — the Linear Model of
Coregionalization (LMC), or its simpler special case, the Intrinsic Coregionalization Model (ICM): treat
each relay's coverage as one output of a vector-valued GP that shares a latent spatial field (e.g. a
common terrain-driven residual) across outputs, with per-output kernels for whatever is genuinely
relay-specific (Álvarez, Rosasco & Lawrence's convolved-MOGP framework is the standard reference,
[JMLR 12](https://www.jmlr.org/papers/volume12/alvarez11a/alvarez11a.pdf); recent scalable-MOGP and
deep-coregionalization variants exist too, found in a 2026-09-20 literature pass, not independently
verified beyond search summaries). This composes with any of §3.5's kernel-design options below — it's an
answer to "how do relays share information," orthogonal to "what does one relay's own kernel look like."
Not evaluated further here; flagged as the concrete candidate for whoever picks this question back up.

### 3.5 Anisotropy / terrain-aware spatial correlation

The exponential covariance in §3.1 assumes correlation depends only on Euclidean distance — isotropic. This
is very likely wrong in forest terrain with ridges/treelines: a point 50 m away across a hill plausibly
correlates far less than a point 50 m away along open ground, and the isotropic model would be overconfident
exactly where terrain features matter most for a relay puck's placement. Three candidate mitigations exist,
at different maturity (`reading_list.md`'s Feasibility section/Appendix and its new Tier 1.6):

1. **Region-based adaptive scheme** (Malmirchegini & Mostofi §III-A) — split the workspace into regions with
   distinct `(α, β)` per region, and down-weight cross-region measurements via a forgetting-factor/distance
   weight. Simple, already fully worked out in a Tier 1 core paper, coarse (piecewise, not smooth).
2. **Locally-varying-anisotropy (LVA) kriging** (Boisvert & Deutsch, via the CCG Alberta substitute source —
   see `reading_list.md`'s confidence caveat) — replace the Euclidean distance `‖x − x'‖` in the covariance
   with a non-Euclidean distance `d_LVA(x, x')`: the length of the shortest path between the two points
   through a pre-specified anisotropy field (each grid cell carrying local orientation/strength parameters,
   e.g. derived from terrain/vegetation), found by Newton's-method path optimization. The covariance model
   applied on top of `d_LVA` stays isotropic — all directional structure is pushed into the distance
   function. Smoother than option 1, but: the anisotropy field must be specified in advance (not learned
   from RF data itself), positive-definiteness of the resulting kriging system is not guaranteed once
   distance is non-Euclidean, it costs roughly 15× a standard kriging solve, and it has **never been
   validated on RF/propagation data** — only on synthetic 2D geological fields with 4–10 conditioning
   points.
3. **Feature-augmented ARD kernel over relay-relative geometry** (Emil's own proposal, this session) —
   instead of correlating on raw position `x = (lat, lon)`, correlate on an augmented feature vector
   `z(x) = (x, extra features relative to the sending relay)` — e.g. elevation, bearing from the relay
   (as `sin θ, cos θ`, not a raw angle — see caveats), an LOS/NLOS indicator or obstruction count along the
   relay-to-`x` path, land-cover class — and apply a standard RBF/RQ kernel with **one lengthscale per
   dimension** (ARD, GPML §5.1, already in Tier 0). Mathematically this is the general and well-established
   way non-stationary spatial models get built: a stationary kernel over a transformed/augmented feature
   space induces a non-stationary kernel over the original geographic space — same family as the classical
   deformation approach (Sampson & Guttorp 1992, *JASA* 87) and kernel-convolution non-stationary covariance
   (Higdon 1998; Paciorek & Schervish, *Environmetrics* 2006), just with a hand-picked rather than fitted
   transformation. **Direct RF-specific precedent, found this session, not independently verified beyond
   search-result summaries (IEEE Xplore and its ResearchGate mirror both blocked full-text fetch — treat as
   context-tier until someone reads the primary source):**
   - **GPRT** (Chen, Liu, Zhang, Zhang, Liu & Yang, *IEEE Internet of Things Journal*, 2025) — an anisotropic
     Rational Quadratic kernel over spatial + elevation dimensions, hyperparameters fit via Adam, reported
     20–33% improvement over comparison methods in simulation and up to 20% in a real field experiment. This
     is close to exactly the option-3 mechanism, already built and field-tested for rugged-terrain radio
     maps specifically.
   - **TKL** ("Radio Environment Map Construction with Gaussian Process and Kernel Transformation," IEEE,
     2021) — learns a nonlinear input transformation to account for environmental heterogeneity before
     applying a GP; reported RMSE/CRPS improvements over prior spatial-spectrum-inference baselines. Same
     transform-then-stationary-kernel mechanism family, different specific transformation from GPRT.

   Caveats worth being deliberate about before implementing this option, beyond "expand the vector, use a
   Gaussian kernel":
   - **Avoid duplicating what `m(x)` already encodes.** ITM/ITWOM's prediction already fully depends on the
     tx–rx relative geometry (the whole terrain profile between sender and query point) — feeding raw
     distance-from-relay into the kernel again risks the residual re-learning a trend the mean already
     captures, rather than modeling genuinely unexplained structure. Prefer features orthogonal to what the
     physics model already uses — an LOS/NLOS indicator or obstruction count (a proxy for "where is
     ITM/ITWOM's own assumption likely violated"), land-cover class — over raw elevation/distance repeated
     verbatim. (GPRT's own choice of raw elevation is a partial counterexample worth scrutinizing once its
     full text is readable — plausibly their gain comes from correcting a *weaker* deterministic model than
     RATPLAN's ITM/ITWOM prior already is.)
   - **Angular features need periodic embedding.** A raw bearing-from-relay feature wraps at 360°; a plain
     RBF/RQ kernel will treat 359° and 1° as maximally dissimilar. Embed as `(sin θ, cos θ)`, not a bare
     angle.
   - **Mixed units and discrete features need more than a single shared lengthscale.** Concatenating
     metres, degrees, and a 0/1 LOS indicator into one vector under one isotropic kernel is meaningless —
     needs ARD at minimum, and a discrete/binary feature (LOS/NLOS) is better handled as a separate product
     kernel component (`k = k_spatial(x, x') × k_LOS(los(x), los(x'))`) than folded into a continuous RBF.
   - **More lengthscales compete for the same sparse per-mission data.** There isn't yet a measured Nordic-
     forest `β` for the *one-parameter* isotropic case (§3.6) — each added feature dimension is another
     hyperparameter fit from a handful of per-mission RSSI points, with real overfitting/ill-conditioning
     risk in an online marginal-likelihood fit. Mitigation, consistent with how `β` is already meant to be
     handled: pre-calibrate the extra lengthscales offline per terrain type (field trials, or synthetic
     training against ITM/ITWOM-simulated data the way GPRT's own simulation study did) and treat them as
     fixed, informative-prior hyperparameters, fitting only `α`/`σ²` (and perhaps one lengthscale) online per
     mission — not the whole augmented ARD vector fresh every drive.

**Not implemented, not chosen between.** Option 3 is the recommended near-term default if/when anisotropy
handling gets built — it changes only what feeds `k(x, x')`, so it drops into the existing posterior
equations (§3.1) and the incremental-update literature (§3.3) unchanged, unlike options 1–2 which either
need an offline-fitted region map (1) or complicate the online-update math with a non-Euclidean distance
system (2). Option 1 remains the cheaper fallback if option 3's extra hyperparameters prove too data-hungry
in practice; option 2 is now the lowest-priority of the three, since option 3 has an actual (if unverified)
RF field validation that option 2 has never had.

### 3.6 Field-measurement gaps (not reading gaps)

Two open items block *calibrating* §3.1–3.5 for Råttan's actual operating environment, independent of
whether the math above is otherwise settled:

- **No Nordic boreal-forest shadowing decorrelation distance (`β`) exists in the published literature.**
  Measured `β` values are environment-specific (Gudmundson: tens of metres in dense urban macrocells,
  larger in open terrain) — nobody has published a measurement for Swedish forest at tactical relay-hop
  distances. Needs field measurement, not more reading.
- **Ground constants and climate are uncalibrated defaults.** `ITWOM/itm/`'s `GroundConstants` (relative
  permittivity 15, conductivity 0.005 S/m) and `Climate.CONTINENTAL_TEMPERATE` are itmlogic's own example
  values, not fit to Swedish/Nordic terrain (`OPEN_ISSUES.md`).

## 4. From path loss to connectivity probability

`Scan`'s consumers (`Evaluate`, `Samband`, relay placement) need a per-cell connectivity signal, not raw
path loss in dB. The conversion (`architecture.md` §3.2 flags this as an output step, not yet specified
here as math): given a posterior `(μ*, σ*²)` on path loss at a cell, Råttan's radio TX power, and its
receiver sensitivity, define the **link margin**

```
margin(x) = TX_power_dBm − sensitivity_dBm − μ*(x)
```

and a probability-of-connectivity as the probability that margin exceeds zero under the posterior's
Gaussian uncertainty:

```
P(connected at x) = Φ( margin(x) / σ*(x) )
```

(`Φ` the standard normal CDF), rather than a hard threshold on `μ*` alone — this is what lets `σ*` (not just
the mean) matter to downstream consumers, per §3.1's point about variance driving "where's uncertain." **Not
yet implemented or validated** — a specific choice (this margin/CDF form vs. some other link-budget
convention) needs to be pinned down, and cross-checked against `itmlogic`'s own `reliability`/`confidence`
parameters (`OPEN_ISSUES.md`'s itmlogic #64 note — RATPLAN's quantile choice there feeds directly into
`μ*`, so the ambiguity there and the conversion here are coupled, not independent open items).

## 5. Mission-planner optimization model

The mission planner is a **dynamic program over road-network positions**, expanding relay-by-relay.
Restated here (see `pseudocode-v2.md` for the full algorithm, candidate-generation details, and worked
pseudocode — this section is the value function/recurrence in isolation):

- **State**: a road position `pos`.
- **Value function**: `best[pos] = (cost_seconds, battery_consumed_wh, road_ids, relay_chain, covered_raster)`
  — cheapest known time from `pos` to `target`; energy that path costs (an independent running total, never
  folded into time — the two don't trade off linearly against terrain/speed); the ordered relay positions a
  puck must be dropped at along the way; and `covered_raster`, the union of every `Scan` result along this
  specific path's own relay chain.
- **Base case**: `best[target] = (0, 0, [], [], Scan(target))`.
- **Recurrence**, for a candidate `c` found near an already-placed relay `p`:

  ```
  best[c].cost_seconds        = route(c, p).cost_seconds + best[p].cost_seconds
  best[c].battery_consumed_wh = BatteryModel(route(c, p)) + best[p].battery_consumed_wh
  best[c].road_ids            = route(c, p).road_ids ++ best[p].road_ids
  best[c].relay_chain         = [p] ++ best[p].relay_chain
  best[c].covered_raster      = best[p].covered_raster ∪ Scan(p)
  ```

  kept only if `cost_seconds ≤ max_mission_time_s` and
  `current_battery_wh − battery_consumed_wh ≥ battery_requirement_wh`.
- **Monotonicity**: `best[c] ≥ best[p]` on both budgets always, since `route()`'s time/energy cost is never
  negative — a relay chain can never loop back on itself, and progress toward the budget limits is
  monotonic by construction.
- **Eligibility vs. ranking are two different functions, not one.** A candidate `c` near relay `p` is
  *eligible* to extend the chain only if it sits near the edge of `p`'s coverage. **Re-derived 2026-09-22**
  (the archived project's version of this filter — a straight-line-distance fraction of an isotropic max
  range — was found to be wrong for a real DTM-LOS raster; see `OPEN_ISSUES.md`'s carryover-audit entry, not
  carried forward): `p`'s `Scan` result is a raster of covered/uncovered cells with a real, terrain-shaped
  boundary — not a circle. A cell is a **boundary cell** of `p`'s raster if it is covered and at least one of
  its (8-connected) neighbor cells is uncovered. `c` is *eligible* iff its containing cell is within
  `edge_tolerance_cells` raster-graph steps (BFS over covered cells, not straight-line distance) of some
  boundary cell of `p`'s raster:

  ```
  min_{b ∈ boundary_cells(Scan(p))} cell_steps(c, b) ≤ edge_tolerance_cells
  ```

  This tracks the coverage shape `Scan` actually produces — short in terrain-occluded directions, long
  along clear LOS — rather than assuming isotropic reach. `edge_tolerance_cells` is a raster-resolution-
  relative tuning parameter, not a physical distance; it should be re-derived once a real raster's cell size
  is fixed, not ported as a physical-distance constant. This is a hard filter, independent of `Evaluate`'s
  score — a point comfortably inside `p`'s coverage doesn't need this hop's puck at all. Among eligible candidates, the
  DP's beam keeps the top `K` (`beam width`) by **pure reach** — `route(c, p).distance_m` — not by
  `Evaluate`'s score; `Evaluate`, `Samband`, and retreat/resupply routes are still computed for every
  survivor (they decide the final cross-level ranking, reported in the output), but they play no role in
  *which candidates advance the search*. See `pseudocode-v2.md`'s "Promotion is ranked by reach, not
  Evaluate" for the reasoning (a puck is never manned, so cover/exposure/escape-route quality has nothing to
  say about whether a point is a good *relay*).
- **This is a beam search, not an exact DP over all road positions — no optimality guarantee.** Bounding the
  frontier to the top `K` candidates by reach at each relay level is a heuristic approximation, deliberately
  traded for tractability (`architecture.md` §10 flags that no performance budget is set yet for the
  underlying per-candidate `Scan()` cost this bounds). Worth stating plainly as a property of the
  mathematical model, not just an implementation detail: a wider beam (`K`) approaches optimality at higher
  cost; the current spec does not attempt to characterize the optimality gap at any given `K`.

## 6. Evaluate scoring model — open

`Evaluate(position, raster) -> (score, description)` (`pseudocode-v2.md`; real spec lives in
`evaluate.py` once written, not further defined here). The quantitative `score ∈ [0, 1]` combines:

- a **cover/exposure sub-score** — enemy line-of-sight via DTM + land cover, with `min_enemy_standoff_m`
  entering as a soft penalty that grows as a candidate nears a known enemy position (never a hard filter);
- an **assistance sub-score** — path time to `supply_unit`.

**Not yet specified as math**: the exposure-penalty function's shape (e.g. a distance-based decay — not
given anywhere in the source docs), and the combination rule for the two sub-scores (weighted sum? product?
something else?) — both TBD, to be pinned down when `evaluate.py` is actually written. The `description`
field is LLM-generated qualitative text and is explicitly outside the quantitative model — never used for
ranking, only carried through to output.

## 7. BatteryModel and Samband — stubs, no math yet

Both are named and given a signature in `pseudocode-v2.md`, deliberately not modeled further there or here:

- **`BatteryModel(leg) -> wh_consumed`** — energy cost of one route leg. Likely form: a function of leg
  distance, terrain, and speed profile (Wh per meter, or Wh per second at a given speed) — not decided; see
  `requirements-central-server.md` §4 (archived project, not this repo) for the last discussion of this.
- **`Samband(road_ids, covered_raster) -> probability`** — probability of maintaining comms the *entire*
  route, not just at candidate endpoints. Needs a leg-level (not just point-level) coverage check that
  doesn't exist yet on the `ratmap` side (`requirements-ratmap.md` §2, archived project) — today's
  `covered_raster.covers(point)` only proves a single point is covered.

Neither has a mathematical model to document yet — they're placeholders in the DP (§5), not implemented
approximations of one.

## 8. Open modeling questions — summary

Consolidated from §§3–7 above, for a quick scan:

- Which incremental-GP-update algorithm (§3.3) — Fink & Kumar, Quattrini Li et al., or the 2026
  memory-based method, or something derived from them.
- Independent vs. jointly-modeled GP across relays (§3.4) — coregionalization/multi-output GP is the
  concrete candidate mechanism if joint modeling is adopted, not yet evaluated further than that pointer.
- Anisotropic/terrain-aware spatial correlation — three options now (§3.5): region-based (option 1,
  pragmatic fallback), LVA kriging (option 2, lowest priority — never validated for RF), feature-augmented
  ARD kernel over relay-relative geometry (option 3, recommended near-term default, precedented by GPRT/TKL
  but neither confirmed beyond abstract-level search summaries yet).
- Nordic boreal-forest `β` and calibrated ground constants/climate — field-measurement gaps, not modeling
  gaps (§3.6).
- Path-loss-to-connectivity-probability conversion (§4) — the margin/Φ form proposed here is a starting
  point, not validated or cross-checked against itmlogic's `reliability` semantics (itmlogic #64).
- `Evaluate`'s exposure-penalty shape and sub-score combination rule (§6).
- `BatteryModel` and `Samband` have no model at all yet (§7).
- Beam width `K`'s effect on solution quality (§5) — no optimality-gap characterization exists.

## References

Full citations, links, and confidence ratings for everything above: [`research/reading_list.md`](./research/reading_list.md).
Load-bearing sources, by tier: Rasmussen & Williams *GPML* Ch. 2 (GP regression fundamentals); Gudmundson
(exponential shadowing correlation); Malmirchegini & Mostofi (the channel decomposition, LS fitting recipe,
Theorem 4, §III-A anisotropy mitigation); Ferris, Fox & Hähnel (RSS-as-GP, per-relay independence
precedent); Fink & Kumar, Quattrini Li et al., arXiv:2607.17954 (online/incremental update candidates);
Boisvert, Manchuk & Deutsch via the CCG Alberta report (LVA kriging); Hengl, Heuvelink & Rossiter
(regression-kriging, the geostatistics-side framing of the same math). Added 2026-09-20, for §3.4–3.5:
Sampson & Guttorp (spatial deformation); Paciorek & Schervish (kernel-convolution non-stationary
covariance); GPRT and TKL (RF-specific feature-augmented/transformed kernels — see `reading_list.md`'s
Tier 1.6 for confidence caveats); Álvarez, Rosasco & Lawrence (multi-output GP/coregionalization).
