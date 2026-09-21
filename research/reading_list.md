

# RATPLAN — Coverage Module, Step 1: Bayesian Update — Reading List
**Draft v5 — companion to RATPLAN_discovery_summary.md §2.2/§2.2.1**
 
v4 resolves all three "not yet verified" items carried from v3: arXiv:2607.17954's author list is confirmed, Han et al. has been read in full (and downgraded — see Tier 4), and Boisvert & Deutsch's method has been read via a substitute source (see Tier 1.5 and Appendix). Two open items remain (Nordic β, RF anisotropy validation) — both are field-measurement/validation gaps, not reading gaps.

v5 adds Tier 1.6, prompted by a design discussion in `model.md` §3.4–3.5 (Emil's proposal to correlate on a
feature vector augmented with relay-relative geometry, not raw distance alone): two RF-specific
feature-augmented/transformed-kernel papers (GPRT, TKL) found via web search this session, plus the two
classical non-stationary-kernel references (Sampson & Guttorp; Paciorek & Schervish) that establish *why*
the augmented-feature-vector approach is mathematically sound, and one multi-output-GP reference
(Álvarez, Rosasco & Lawrence) relevant to the still-open joint-vs-independent-GP-per-relay question. **All
five are search-summary-level only** — GPRT and TKL specifically are behind IEEE Xplore, which blocked
full-text fetch this session (HTTP 418/403); nothing below has been read in full the way Tiers 0–1.5 have.
Treat Tier 1.6 as a pointer to chase, not settled reading, until someone gets past the paywall.
 
Scope: papers to learn the math of the Bayesian update itself — modelling RF coverage as a Gaussian Process (GP) with an informative (ITWOM/physics-based) mean, and updating that posterior online as Råttan drives. Relay-placement decision theory and traversability are separate later steps; only included here where a paper's *update mechanics* are directly reusable.
 
Confidence key: **(core)** = read this, directly on the load-bearing math. **(context)** = survey/orientation, not where the equations live. **(optional)** = go here only if a core paper's derivation is too compressed.
 
---
 
## Tier 0 — GP regression math itself
 
**Rasmussen & Williams, *Gaussian Processes for Machine Learning*** (MIT Press, 2006 — free online). **(core)**
[Book page](https://gaussianprocess.org/gpml/) · [Ch. 2, Regression, PDF](https://gaussianprocess.org/gpml/chapters/RW2.pdf)
 
The standard reference for everything downstream. Read Ch. 2 specifically: the GP posterior mean/covariance update given noisy observations, the role of the mean function (this is where "use ITWOM as the mean, not zero" gets its formal justification — see the discovery doc's flat-prior-GP-is-a-special-case argument in §2.2.1), kernel/covariance function choice, and hyperparameter fitting via marginal likelihood. Every RSS-GP paper below assumes this chapter as background without re-deriving it.
 
Note on posterior structure, confirmed by direct derivation (not just this book): for query point x*, μ*(x*) = m(x*) + k(x*,X)[K(X,X)+σ²I]⁻¹(y−m(X)) and σ*²(x*) = k(x*,x*) − k(x*,X)[K(X,X)+σ²I]⁻¹k(X,x*). The variance term has **no m(·) dependence** — the mean function only affects the posterior mean, and only affects it at all through the residual (y−m(X)). At zero measurements, μ*(x*) = m(x*) exactly.
 
---
 
## Tier 1 — RSS/channel as a Gaussian Process (the foundational applied papers)
 
**Ferris, Fox, Hähnel — "Gaussian Processes for Signal Strength-Based Location Estimation"**, RSS 2006. **(core)**
[Paper](https://www.roboticsproceedings.org/rss02/p39.pdf) — already flagged in the discovery doc §2.2.
 
First paper to model received signal strength as a GP over space rather than a deterministic path-loss surface. Confirm you can reproduce its posterior-update derivation before moving on — it's the shortest, cleanest version of the exact math RATPLAN needs, just applied to localization rather than coverage.

**Requirement note (added 2026-09-18):** RATPLAN must be able to take several relay transmitters into account simultaneously. FFH's per-access-point independence assumption (§II-B — a separate GP fit per access point) is the default precedent, but it assumes no correlation between transmitters; if RATPLAN's relays share terrain/vegetation context, a jointly-modeled alternative may be needed instead. Revisit when implementing C1–C3.
 
**Gudmundson — "Correlation model for shadow fading in mobile radio systems"**, Electronics Letters 27(23), pp. 2145–2146, Nov 1991. **(core)**
 
The foundational reference for treating shadowing as a spatially correlated random field with exponential correlation — E{ν(q₁)ν(q₂)} = α·e^(−‖q₁−q₂‖/β), where β is the **decorrelation distance**: how far, physically, a measurement's information extends. Everything below (Malmirchegini & Mostofi included) builds on this model without re-deriving it. Measured β values are environment-specific (tens of metres in dense urban macrocells, larger in open terrain) — read this to understand the parameter, not to get a Nordic-forest number, which doesn't exist in the published literature (see Feasibility note below).
 
**Malmirchegini & Mostofi — "On the Spatial Predictability of Communication Channels"**, IEEE Trans. Wireless Communications, 2012. **(core, now verified)**
[Open-access author PDF](https://web.ece.ucsb.edu/~ymostofi/papers/TWC_Chegini_Mostofi.pdf) (preferred over the paywalled IEEE Xplore/ResearchGate links)
 
Confirmed by direct read: decomposes the channel into deterministic path loss Υ_PL(q) = K_PL·‖q−q_b‖^(−n_PL) (RATPLAN's ITWOM plays this role) plus Gudmundson-style spatially-correlated shadowing plus uncorrelated multipath. Formally proves (their Theorem 4) that prediction error variance at an **unmeasured** location decreases monotonically as the correlation distance β increases, and validates it empirically (outdoor SF measurements: −29 dB error variance predicting unmeasured points from 5% coverage over ~16 m). This is the single most directly relevant paper in the list to "does the posterior get better where the rat hasn't driven" — see the Feasibility section below.
 
Correction after full read: their §III-A ("Space-varying underlying parameters and adaptive channel prediction") already proposes a **partial answer to the terrain-anisotropy gap** flagged below — split the workspace into regions with distinct (θ, α, β) and down-weight cross-region measurements via a forgetting matrix and a distance-dependent weight. Not a smooth anisotropic kernel, but a working, simpler mechanism for the same problem, already inside a Tier 1 core paper — see the Appendix.
 
**Malmirchegini — PhD thesis** (UCSB, advisor Mostofi). **(optional)**
[PDF](https://web.ece.ucsb.edu/~ymostofi/Thesis/MehrzadChegini.pdf)
 
Fuller derivations than the journal paper above; use only if you get stuck on the TWC paper's math.
 
---
 
## Tier 1.5 — Geostatistics / kriging (same math, older and more mature literature)
 
Kriging (geostatistics, since the 1960s) and GP regression (machine learning, since the 1990s–2000s) are the same mathematical framework under different vocabulary — worth deliberately cross-reading, because geostatistics has ~60 years of applied experience on exactly the open questions below (physics-informed trend + correlated residual, anisotropic correlation), often with more implementation-level guidance (variogram fitting, cross-validation practice) than the ML-GP papers give.
 
**"Explaining and Connecting Kriging with Gaussian Process Regression"**, arXiv:2408.02331. **(core)**
[arXiv](https://arxiv.org/abs/2408.02331)
 
The formal bridge between the two literatures' terminology. Read this first in this tier: it maps "ordinary kriging" → zero/constant-mean GP, and **"universal kriging" / "kriging with external drift"** → GP with an explicit deterministic mean — i.e., the 40-years-earlier geostatistics name for RATPLAN's own "ITWOM as GP mean" architecture.
 
**Hengl, Heuvelink & Rossiter — "About regression-kriging: from equations to case studies"**, Computers & Geosciences, 2007. **(core)**
[Wageningen repository](https://research.wur.nl/en/publications/about-regression-kriging-from-equations-to-case-studies/) · [Wikipedia summary](https://en.wikipedia.org/wiki/Regression-kriging)
 
The standard reference for regression-kriging: fit a deterministic trend (regression on covariates — for RATPLAN, ITWOM's output and/or terrain/vegetation features), then krige the residuals. Structurally identical to the Malmirchegini & Mostofi decomposition above, from a field that has spent decades on the practical side (how to fit and validate the residual's variogram/kernel) that the ML-GP papers mostly assume away.
 
**Boisvert & Deutsch — "Kriging in the Presence of Locally Varying Anisotropy Using Non-Euclidean Distances"**, Mathematical Geosciences, 2009. **(optional — read via substitute source, see caveat)**
[Springer](https://link.springer.com/article/10.1007/s11004-009-9229-1) (paywalled, no accessible mirror found) · substitute read: [CCG Alberta report 2007-103](https://www.ccgalberta.com/ccgresources/report09/2007-103_kriging_and_sim_with_lva.pdf), Boisvert, Manchuk & Deutsch, "Kriging and Simulation in the Presence of Locally Varying Anisotropy"
 
Candidate answer to the terrain-anisotropy gap (see Feasibility section and Appendix). **Confidence caveat:** the 2009 journal paper itself could not be obtained (paywalled). What was read instead is the CCG technical-report version — same research group, same period, almost certainly the same core method, but not confirmed textually identical to the peer-reviewed paper. Mechanism (from the report): each grid block carries local anisotropy parameters, and the distance between two points is the length of the shortest path through that anisotropy field (found by Newton's-method path optimization) rather than Euclidean distance; that non-Euclidean distance is then plugged into an otherwise-standard isotropic variogram/kriging system. Demonstrated only on synthetic 2D geological fields (5–10 conditioning points, no RF/propagation data) and requires the anisotropy field to be specified in advance (e.g. from terrain) — it does not estimate anisotropy from data. So: mechanically the right shape of fix for RATPLAN's ridge/treeline problem, but unvalidated for RF — see Appendix for the full read-through.
 
---

## Tier 1.6 — Feature-augmented / transformed kernels for RF-specific anisotropy (found post-v4, unread)

Prompted by `model.md` §3.5's third anisotropy-mitigation option: instead of a non-Euclidean *distance*
(Tier 1.5's Boisvert & Deutsch) or a piecewise region split (Tier 1's Malmirchegini & Mostofi §III-A),
correlate on a stationary kernel over an *augmented feature vector* (position plus relay-relative geometry —
elevation, bearing, LOS/NLOS, land cover). This is the standard route to non-stationary spatial models in
general (see the two classical references below); the two RF-specific papers are direct precedents for
doing it on radio maps over terrain specifically.

**GPRT** — Chen, Liu, Zhang, Zhang, Liu & Yang, *"GPRT: A Gaussian Process Regression-Based Radio Map
Construction Method for Rugged Terrain,"* IEEE Internet of Things Journal, 2025. **(context, abstract-level
only — not independently verified)**
[IEEE Xplore](https://ieeexplore.ieee.org/document/10938559/) (blocked full-text fetch, HTTP 418) ·
[ResearchGate](https://www.researchgate.net/publication/390216031_GPRT_A_Gaussian_Process_Regression-Based_Radio_Map_Construction_Method_for_Rugged_Terrain) (blocked, HTTP 403)

Per two independent web-search summaries (consistent with each other, neither a primary-source read): an
anisotropic Rational Quadratic kernel over spatial + elevation dimensions (one lengthscale per dimension —
ARD in spirit), hyperparameters fit via Adam, validated both in simulation (20–33% improvement over
comparison methods, varying numbers of emitters) and a real field experiment (up to 20% improvement). If
confirmed on a full read, this is close to exactly `model.md` §3.5 option 3's mechanism, already built and
field-tested for rugged-terrain radio maps specifically — the strongest direct precedent in this list for
that option. **Action before relying on this for a design decision: get past the IEEE paywall and read the
actual kernel formula and validation methodology**, not just the abstract-level description above.

**TKL — "Radio Environment Map Construction with Gaussian Process and Kernel Transformation"**, IEEE, 2021.
**(context, abstract-level only — not independently verified)**
[IEEE Xplore](https://ieeexplore.ieee.org/document/9639312/) ·
[ResearchGate](https://www.researchgate.net/publication/357144140_Radio_Environment_Map_Construction_with_Gaussian_Process_and_Kernel_Transformation)

"Transformed Kernel Learning": learns a nonlinear input transformation to account for environmental
heterogeneity before applying a GP to spatial spectrum inference, reporting RMSE/CRPS improvements over
prior baselines. Same transform-then-stationary-kernel mechanism family as GPRT, different specific
transformation (learned rather than hand-picked features) — a second, earlier RF-specific precedent for the
same general approach. Not read beyond the search summary.

**Sampson & Guttorp — "Nonparametric Estimation of Nonstationary Spatial Covariance Structure"**, *JASA*
87(417), 1992. **(context — classical reference, not RF-specific, not read in full)**
[Taylor & Francis](https://www.tandfonline.com/doi/abs/10.1080/01621459.1992.10475181)

The original "deformation" method: warp the geographic plane into a latent space where isotropy holds
(originally via multidimensional scaling + thin-plate splines fit from repeated observations at fixed
monitoring stations), then krige in the warped space. Establishes that GPRT/TKL's approach is a well-worn
technique, not a hack — but the original method's data assumption (repeated time series at fixed stations)
doesn't match Råttan's single-pass, non-repeated drive-through measurements; useful for the theoretical
lineage, not directly applicable as a recipe.

**Paciorek & Schervish — "Spatial Modelling Using a New Class of Nonstationary Covariance Functions"**,
*Environmetrics* 17(5), 2006. **(context — classical reference, not RF-specific, not read in full)**
[PDF](https://www.stat.berkeley.edu/~paciorek/files/environmetrics/paci.sche.2006.pdf)

Kernel-convolution approach to non-stationary covariance (building on Higdon 1998): a spatially-varying
smoothing-kernel bandwidth, with a closed-form non-stationary Matérn as the headline result. More flexible
than a fixed feature-augmentation choice (the bandwidth itself varies continuously over space rather than
being fit as a handful of ARD lengthscales), but adds meaningfully more parameters — likely too heavy for
RATPLAN's sparse per-mission, online-update data regime (`model.md` §3.3). Noted as the "escalate to this if
ARD-over-augmented-features isn't flexible enough" option, not a starting point.

**Álvarez, Rosasco & Lawrence — "Kernels for Vector-Valued Functions: A Review"** (the convolved
multi-output GP framework), *Foundations and Trends in Machine Learning* / JMLR-adjacent, 2011+ recent
extensions. **(context — not RF-specific, not read in full)**
[JMLR PDF](https://www.jmlr.org/papers/volume12/alvarez11a/alvarez11a.pdf)

Not about anisotropy directly — the standard reference for the Linear Model of Coregionalization / Intrinsic
Coregionalization Model, i.e. how to jointly model several relays' coverage as one vector-valued GP sharing
latent spatial structure. Relevant to `model.md` §3.4's still-open joint-vs-independent-GP question, not
§3.5's kernel-anisotropy question — flagged here because it surfaced in the same literature pass.

---
 
## Tier 2 — Online/incremental updating (no batch refit, matches Råttan's operating mode)
 
This is the part Tier 1 papers mostly don't cover: RATPLAN's posterior must update as new measurements stream in while driving, not recompute from scratch. Three papers do this specifically for radio/RSS maps, in increasing recency:
 
**Fink & Kumar — "Online Methods for Radio Signal Mapping with Mobile Robots"**, ICRA 2010. **(core)**
[Semantic Scholar PDF](https://www.semanticscholar.org/paper/Online-methods-for-radio-signal-mapping-with-mobile-Fink-Kumar/a4b8d7e750ee5cf296a77f16ff73a73eae8404e5) · [IEEE Xplore](https://ieeexplore.ieee.org/abstract/document/5509574)
 
GP-based radio map built incrementally by a single moving robot — operationally the closest match to "Råttan drives, coverage posterior updates live." Good second read after Ferris/Fox/Hähnel.
 
**Quattrini Li, Penumarthi, Banfi, Basilico, O'Kane, Rekleitis, Nelakuditi, Amigoni — "Multi-robot online sensing strategies for the construction of communication maps"**, Autonomous Robots 44, 2020. **(core)**
[Springer](https://link.springer.com/article/10.1007/s10514-019-09862-3) · [Open-access PDF via NSF PAR](https://par.nsf.gov/servlets/purl/10127557)
 
Architecturally the closest match found to date: a GP communication map seeded with a **prior derived from the physical/environment map** (their version of "start from ITWOM"), updated online, with real-robot validation (TurtleBot 2) rather than simulation only. Also relevant to Tier 3 (relay/next-measurement placement) since it proposes leader-follower sensing strategies — worth a second pass once you get to that step.
 
**"Radio Map Updating from Streaming Spectrum Measurements via Memory-Based Online Gaussian Processes"**, arXiv:2607.17954 (2026). **(core)**
[arXiv](https://arxiv.org/abs/2607.17954) · [HTML](https://arxiv.org/html/2607.17954)
 
Most recent of the three, and most directly on the specific numerical problem: how to update a GP posterior from a continuous measurement stream without the O(n³) cost of refitting on the full history — the "memory-based" mechanism is the part to study closely. Author list confirmed directly from arXiv (submitted 2026-07-20, v1): Yuanyuan Deng, Bo Zhou, Tian Chen, Shijian Gao, Jia Yan, Lantu Guo, Qiuming Zhu, Qihui Wu (no affiliations listed on the abstract page).
 
**Optional deeper math on the recursive-update mechanics, if the above three don't give enough derivation detail:**
- "Recursive Estimation for Sparse Gaussian Process Regression", arXiv:1905.11711. **(optional)**
- "Sequential Gaussian Processes for Online Learning of Nonstationary Functions", arXiv:1905.10003. **(optional)**
---
 
## Tier 3 — Where the posterior feeds decisions (relay placement) — next step, not this one
 
Already identified in the discovery doc (§2.2, §5) — RCAMP, HGP-RL, the "deploy-as-you-go" MDP paper, and the classic relay-placement optimisation paper. Re-read Quattrini Li et al. above when you get here — its leader-follower sensing strategy is effectively an active-learning policy over the GP's variance, i.e. exactly "place the next relay/take the next measurement where it most reduces uncertainty" from discovery doc §2.2.1.
 
Also noted for later, not now: **"Turning Bayesian Model Averaging into Bayesian Model Combination"**, IEEE IJCNN 2011 ([IEEE Xplore](https://ieeexplore.ieee.org/document/6033566/)) — relevant once you implement the discovery doc's ITWOM-vs-log-distance-model ensemble (§2.2.1's mitigation for ITWOM's short-range weakness), not to the core GP update math.
 
---
 
## Tier 4 — Orientation / survey (read anytime, not on the critical path)
 
**Han et al. — "Radio Environment Map Construction by Kriging Algorithm Based on Mobile Crowd Sensing"**, Wireless Communications and Mobile Computing, 2019. **(context, downgraded after full read)**
[Wiley/Hindawi](https://www.hindawi.com/journals/wcmc/2019/4064201/)
 
Read in full — downgraded from Tier 1.5 to here. It's ordinary kriging (ẑ(x₀) = Σλᵢz(xᵢ), Lagrange-constrained weights, power-model variogram γ(h) = αh^β fitted as 0.25·h^1.68) under an **intrinsic-stationarity assumption, i.e. a flat/zero mean** — no physics-based trend, no anisotropy, free-space path loss only, uniform grid with no terrain. No connection drawn to GP regression at all. Their own validation shows it losing to plain IDW at the sparsest density tested (ρ=0.05: 7 dBm kriging error vs. 6 dBm IDW), only overtaking IDW/NN once coverage density rises (ρ≥0.2). Keep as a negative data point — zero-mean kriging alone underperforms exactly in the sparse-data regime closest to Råttan's operating mode, reinforcing why RATPLAN's physics-informed-mean approach (Tier 0/1) matters — not as a method to emulate.
 
**Mostofi — "Communication-Aware Robotics: Exploiting Motion for Communication"**, Annual Review of Control, Robotics, and Autonomous Systems, 2021. **(context)**
[Annual Reviews](https://www.annualreviews.org/content/journals/10.1146/annurev-control-071420-080708)
 
Broad survey of exactly this subfield (channel prediction + motion planning under connectivity constraints), from the group behind the Tier 1 spatial-predictability paper. Good for vocabulary and a map of what else exists before committing to one paper's formalism.
 
**Awesome-Radio-Map-Categorized** (GitHub, curated bibliography). **(context)**
[Repo](https://github.com/UNIC-Lab/Awesome-Radio-Map-Categorized)
 
Same function for radio/channel maps as `awesome-traversability-analysis` already serves for the traversability module (discovery doc §2.3). Skews toward deep-learning radio-map-estimation methods rather than classical Bayesian GP — use to scan for anything missed here, not as primary reading.
 
**"A Tutorial on Learning-Based Radio Map Construction: Data, Paradigms, and Physics-Awareness"**, arXiv:2603.17499 (2026). **(context, lower confidence)**
[arXiv](https://arxiv.org/html/2603.17499v7)
 
Recent tutorial covering physics-based vs. data-driven vs. hybrid radio-map paradigms. Useful framing, but the field it surveys leans toward deep-learning radio map estimation (large-scale cellular/spectrum cartography) more than the small-n, incrementally-updated, physics-informed GP setting RATPLAN needs — treat as context, verify any specific claim against a primary source before relying on it.
 
**"Radio Map Estimation: A data-driven approach to spectrum cartography"**, IEEE Signal Processing Magazine, 2022. **(context)**
[arXiv version](https://arxiv.org/pdf/2202.03269)
 
Same caveat as above — good field overview (spectrum cartography / kriging / GP / deep learning approaches), not focused on the online, physics-prior-plus-GP setting specifically.
 
---
 
## Feasibility: does the posterior actually improve at unvisited locations?
 
Yes, in principle, and it's not speculative — it's what Malmirchegini & Mostofi (Tier 1) formally prove for wireless channels specifically (their Theorem 4: prediction error variance at an unmeasured point decreases monotonically with the shadowing correlation distance β), with empirical validation (−29 dB error variance predicting unmeasured points from 5% coverage over ~16 m, outdoor SF measurements). Mechanism: the residual after removing the deterministic mean (ITWOM) is modelled as spatially correlated with exponential covariance E{ν(q₁)ν(q₂)} = α·e^(−‖q₁−q₂‖/β) (Gudmundson, Tier 1) — β is literally the answer to "how far does a measurement's information reach."
 
Two open risks, not resolved by anything currently in this list:
 
1. **β for Nordic boreal terrain at tactical relay-hop distances is not in the published literature.** Gudmundson-style decorrelation distances are measured per-environment (dense urban vs. suburban etc.); nobody has measured it for Swedish forest. Same data-scarcity gap the discovery doc already flags for vegetation attenuation (§Roadblocks) — this is a field-measurement problem, not a reading problem.
2. **Isotropy.** The standard exponential model assumes correlation depends only on Euclidean distance. In forest with ridges/treelines, a point 50 m away across a hill plausibly correlates far less than a point 50 m away along open ground — the model would be overconfident exactly where terrain features matter most. Two candidate mitigations, different maturity: Malmirchegini & Mostofi §III-A's region-based adaptive scheme (piecewise-constant α, β per region, forgetting-factor down-weighting across regions — simple, already worked out, coarse) and Boisvert & Deutsch (Tier 1.5, locally-varying-anisotropy kriging via non-Euclidean distance fields — smoother, imported from mining geostatistics, not yet verified for RF use).
---
 
## Suggested reading order
 
1. GPML Ch. 2 (Tier 0) — if GP regression internals aren't already solid.
2. Ferris/Fox/Hähnel, then Gudmundson, then Malmirchegini & Mostofi (Tier 1) — the core "RSS as GP with a physics-based mean, spatially correlated residual" math, ending on the paper that directly answers the extrapolation-to-unvisited-locations question.
3. The kriging↔GP bridge paper, then Hengl/Heuvelink/Rossiter (Tier 1.5) — same math, more mature practical guidance; read once Tier 1 is solid, to pick up implementation habits (variogram fitting, cross-validation) the ML papers skip.
3.5. GPRT and TKL (Tier 1.6) — only once past the IEEE paywall; read these before committing engineering time to `model.md` §3.5 option 3, since the whole point is checking whether their validation claims hold up under a full read, not just a search summary.
4. Fink & Kumar → Quattrini Li et al. → the 2026 streaming-GP paper (Tier 2) — online updating, in that order (increasing complexity/recency).
5. Mostofi's 2021 survey (Tier 4) can be read first or in parallel for orientation — it doesn't gate anything.
6. Tier 3 once the update math is solid and the project moves to relay placement.
## Open items
 
**Resolved in v4:**
- ~~Confirm arXiv:2607.17954's author list~~ — done, see Tier 2.
- ~~Han et al. and Boisvert & Deutsch not read in full~~ — done. Han et al. read in full and downgraded to Tier 4 (context, negative data point). Boisvert & Deutsch read via a substitute source (CCG Alberta report 2007-103, same group/period, not confirmed textually identical to the 2009 journal paper) — see Tier 1.5 and Appendix.
**Still open (field-measurement/validation gaps, not reading gaps):**
- No Nordic-forest-specific shadowing decorrelation distance (β) exists in the literature.
- Anisotropic/terrain-aware spatial correlation for RF specifically now has a *candidate* validated answer,
  not yet confirmed: GPRT (Tier 1.6, added v5) reportedly field-validates a feature-augmented ARD-style
  kernel (elevation + spatial dims) on rugged-terrain radio maps, but this is search-summary-level only —
  IEEE Xplore blocked full-text fetch, so the claim is unconfirmed. Until someone reads it in full, the
  practical state is unchanged from v4: Malmirchegini & Mostofi §III-A gives a coarse, working region-based
  mechanism; Boisvert & Deutsch's non-Euclidean-distance LVA kriging gives a smoother mechanism demonstrated
  only on synthetic geological data, never RF; GPRT/TKL (Tier 1.6) suggest a third, RF-validated-in-theory
  path but need a primary-source read before that validation can be trusted (cf. tidsplan §D).
- **Next action, added v5**: get past the IEEE Xplore paywall for GPRT and TKL (Tier 1.6) — both blocked a
  direct fetch this session (HTTP 418/403). Library/institutional access or a personal IEEE login would
  resolve this; worth doing before committing to option 3 in `model.md` §3.5 as more than a design sketch.
---
 
## Appendix: Core equations, verified by direct read (GPML Ch. 2, Ferris/Fox/Hähnel, Malmirchegini & Mostofi)
 
All three papers now read in full (project files RW2.pdf, p39.pdf, TWC_Chegini_Mostofi.pdf). This section is the equation-level map between them — what's load-bearing, what to skip.
 
### GPML Ch. 2 (RW2.pdf)
 
**Load-bearing:**
- Eq. 2.13–2.14: GP definition, f(x) ~ GP(m(x), k(x,x')).
- Eq. 2.16/2.31: squared-exponential kernel, k(xp,xq) = σf²·exp(−|xp−xq|²/2l²).
- **Eq. 2.22–2.26: the core predictive equations.** f̄* = k*ᵀ(K+σn²I)⁻¹y, V[f*] = k(x*,x*) − k*ᵀ(K+σn²I)⁻¹k*.
- Eq. 2.30: log marginal likelihood — hyperparameter fitting (l, σf, σn).
- **§2.7, Eq. 2.37–2.38 (fixed deterministic mean function):** f̄* = m(X*) + K(X*,X)Ky⁻¹(y−m(X)), variance unchanged from 2.24 — the formal statement of "use ITWOM as m(x)"; confirms the mean function affects only the posterior mean, never the variance.
- Eq. 2.39–2.45 (explicit basis functions with *inferred* coefficients β, vague-prior limit B⁻¹→0): the general form Malmirchegini & Mostofi's path-loss fit is an instance of.
- Algorithm 2.1: Cholesky-based implementation, O(n³/6).
- Exercise 4: posterior variance is non-increasing as data accumulates (varₙ(f*) ≤ varₙ₋₁(f*)) — weaker than Theorem 4 below but unconditional.
- History section: states the kriging/GP equivalence directly from the primary source.
**Skip / deprioritize:** §2.1 weight-space derivation (background, function-space view in §2.2 is what's used); §2.4 decision theory/loss functions (only needed for asymmetric-loss cost functions later); §2.5 SARCOS robot-arm example (unrelated worked example); §2.6 smoothing/equivalent-kernel analysis (deeper theory, not needed for implementation).
 
### Ferris, Fox & Hähnel (p39.pdf)
 
**Load-bearing:**
- Eq. 1–6: same GP setup/posterior as GPML, renotated (μx*, σx*²).
- Eq. 7–11: explicit hyperparameter gradients — more implementation-ready than GPML's abstract treatment.
- **§II-D "Zero Mean Offset", Eq. 12: ss = m·‖x−xAP‖ + b** — their own primitive answer to RATPLAN's exact problem (GP reverts to zero far from data); a crude linear-distance precedent for "use a physics-informed mean."
- **§V-C "Dealing with Sparse Data":** stripped training data from 25/54 rooms — 9/10 test traces statistically indistinguishable from full-data performance, one failed (16 m error). Direct empirical evidence for "does the posterior improve at unvisited locations," independent of Malmirchegini & Mostofi's Theorem 4.
**Skip / not relevant:** **all of §III** (Bayesian particle filter, mixed graph/free-space representation, Eq. 13–15, motion models) — this is about using the GP as a localization likelihood to track a *person's position*, not coverage-map prediction; the largest skippable block in the paper. Also §V-B and §V-D (localization-accuracy benchmarking, GSM centroid/fingerprinting comparisons) — wrong metric for RATPLAN. Note the per-access-point independence assumption ("estimate a GP for each access point separately") as a modeling choice to revisit if RATPLAN ever models multiple relays jointly.
 
### Malmirchegini & Mostofi (TWC_Chegini_Mostofi.pdf) — richest of the three
 
**Load-bearing:**
- **Eq. 1: ΥdB(q) = KdB − 10·nPL·log₁₀‖q−qb‖ + ν(q) + ω(q)** — the master decomposition (path loss = ITWOM's role; ν = spatially correlated shadowing; ω = uncorrelated multipath).
- Exponential shadowing covariance E{ν(q₁)ν(q₂)} = α·e^(−‖q₁−q₂‖/β) (Gudmundson's model, applied).
- **Eq. 2: YQ = HQθ + ϑQ + ΩQ**, HQ = [1k, −DQ] — a concrete instance of GPML's explicit-basis-function form (h(x) = [1, −D{x}]ᵀ, θ = [KdB, nPL]ᵀ).
- Eq. 3–6: ML/LS estimators for θ, α, β, σ². **The LS route (Eq. 5–6) is the actual usable recipe** — θ̂_LS = (HQᵀHQ)⁻¹HQᵀYQ, then empirical spatial correlation r̂Q(l) binned by distance, weighted-LS fit of ln(α·e^(−l/β)) to ln r̂Q(l). This is variogram-fitting under another name — the procedure to use once Nordic field data exists.
- **Eq. 7: the prediction equations** — Υ̃dB,Q(q) = hᵀ(q)θ + φQᵀ(q)Rtot,Q⁻¹(YQ−HQθ), σ²dB,Q(q) = α+σ² − φQᵀ(q)Rtot,Q⁻¹φQ(q) — GPML Eq. 2.38 specialized to this channel model.
- Theorem 1 (error variance increasing in α, σ²) and **Theorem 4** (error variance decreasing in β) — the formal predictability results.
- Eq. 14: error propagation from path-loss parameter estimation into the final prediction variance — a refinement beyond treating ITWOM's output as noiseless.
- **§III-A** region-based adaptive extension — see correction note under Tier 1 above.
**Defer to Tier 3 / skip:**
- All of §IV (Theorems 2–3, 5–8, Euclidean-Distance-Matrix optimal-sampling-position proofs for β→0 and β→∞ extremes) — correct and eventually useful for *where Råttan should drive to calibrate the model*, i.e. relay-placement/active-sensing (Tier 3), not the update itself.
- Nakagami/Rician small-scale-fading distribution machinery — the paper's own simplification (Gaussian ω) is sufficient; no need to reproduce this.
- §VI's specific numbers (β ≈ 0.08–1.4 m indoors, one 16 m SF street) — indoor-multipath-dominated or single-street values, not Nordic-forest priors. Illustrates *why* a Nordic β measurement is needed, not what its value is.
### Boisvert, Manchuk & Deutsch — CCG report 2007-103 (substitute source for Boisvert & Deutsch 2009)
 
Read in full via the CCG Alberta report (the 2009 Mathematical Geosciences paper itself remains inaccessible — see confidence caveat under Tier 1.5).
 
**Load-bearing:**
- The core move: replace the Euclidean distance ‖q₁−q₂‖ in an otherwise-standard variogram/covariance model with a **non-Euclidean distance** d_LVA(q₁,q₂), defined as the length of the shortest path between q₁ and q₂ through a locally-varying-anisotropy (LVA) field. Each grid block in that field carries five parameters — three angles (α,β,γ) fixing local anisotropy orientation and two ratios (r1,r2) fixing anisotropy strength — and the shortest path is found by Newton's-method optimization over paths crossing the field, with total distance = the sum of the segment lengths through each block crossed.
- The covariance/variogram model applied on top of d_LVA is kept **isotropic** — i.e. all directional structure is pushed into the distance function itself, not into the covariance model, because summed path segments through varying anisotropy can't be represented as an anisotropic covariance in closed form.
- Practically: three GSLIB programs (KT3D_LVA, SGS_LVA, GAMV_LVA) are modified to accept an LVA field and compute d_LVA during kriging-matrix assembly; otherwise the kriging/SGS equations are unchanged from the standard (isotropic-distance) case.
- Worked validation: kriging and sequential Gaussian simulation on two synthetic 2D fields (a smooth-anisotropy field and a 10:1-anisotropy channel), each with only 4–5 conditioning data — the method reproduces curvilinear structure (e.g. a channel) from the LVA specification alone, not from data density.
**Caveats relevant to applying this to RATPLAN (RF over terrain, not ore bodies):**
- The LVA field itself (anisotropy orientation/ratio per location) must be **specified in advance**, e.g. derived from a terrain/vegetation map — the method does not estimate anisotropy from the RF measurements themselves.
- Positive-definiteness of the resulting kriging system is not guaranteed once distance is no longer Euclidean: the report notes 5–10 indefinite matrices per 400 kriging systems using a spherical variogram.
- Computational cost: ~15× slower than standard kriging at comparable data density (mitigated in the report via distance-hash caching).
- No RF, propagation, or any non-geological application is demonstrated anywhere in this source.
### Cross-paper synthesis: a design choice for RATPLAN
 
GPML §2.7 Eq. 2.38 treats the mean function as **fixed** (plug in ITWOM's output, done). Malmirchegini & Mostofi instead **fit** their mean's parameters (θ) from the same sparse field data via least squares, then krige the residual — closer to GPML's Eq. 2.39–2.42 (explicit basis functions, vague-prior limit). RATPLAN can do either: treat ITWOM as fixed, or treat its calibratable inputs (ground constants ε,σ; vegetation-attenuation coefficients — discovery doc §2.2.1's "what needs calibrating" table) as parameters fit online with this paper's LS procedure, jointly with the shadowing correlation. The second is more work but turns "ITWOM might be wrong for granite/pine" from a fixed liability into something the same update loop corrects.
 

