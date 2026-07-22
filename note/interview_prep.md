# Interview prep — the hardest questions on this note

Each answer comes from the repo (code, DECISIONS.md, or the note's
provenance table). Numbers are as of the 2026-07-22 cache. Questions 1–15
cover the note; 16–21 cover the working paper's robustness section
(`src/robustness.py`, paper Section 5).

**1. Your Brazil curve is retail Tesouro Direto data. Why should I trust a
slope signal from a retail window?**
Because I quantified the bias instead of assuming it away. On the one date
ANBIMA's public window allowed a cross-check, my fit sits −7.6bp (1y),
−23.1bp (5y), −19.3bp (10y) against their interbank curve. That is a level
effect; z-scores compare the source against its own 5-year history, so it
cancels. What does not cancel is the 5y–10y differential (+3.8bp) — I carry
it as the third "what kills it" bullet, and it is why the note treats
carry-per-vol of 0.06 as indicative rather than precise. The honest
alternative — DI futures — is not free data; that is the first line of
"with desk data I'd extend by".

**2. Why fit Nelson-Siegel instead of bootstrapping zeros?**
Three reasons. The BR input is an irregular, changing set of bond
maturities — a bootstrap needs a fixed grid and interpolation choices that
add hidden knobs, while NS/NSS handles any grid and gives me a stored
6-parameter time series. Second, comparability: DE and (originally) BR
publish Svensson parameters, so one functional family spans all markets.
Third, auditability for exactly this kind of conversation: gridded-τ +
OLS has no optimizer state — rerunning the repo reproduces every beta
bit-for-bit. The cost is fit error, which I publish per curve (3.4bp
median RMSE for BR) rather than hide.

**3. Your fitting uses a τ grid with OLS betas. Why not full nonlinear
least squares?**
The problem is linear in the betas conditional on τ, so a bounded grid
(40 points, geometric, 0.15–5y; 12 more for the second Svensson decay)
plus OLS finds the same optimum a nonlinear solver would, without
convergence failures on bad days. On 1,500 daily refits per country,
robustness beats the third decimal of RMSE.

**4. US and MX are par curves, BR and DE zero curves. You mixed them.**
Stated, not hidden (DECISIONS "Common basis", note Appendix B). At
2s10s/5s10s granularity the par-zero difference is a few bp of level and
much less in slope changes, which is what z-scores and vol consume. It
cannot reorder a carry-per-vol ranking whose top two entries differ by
0.05. With desk data I would bootstrap zeros from the same inputs and
show the ranking is unchanged.

**5. Mexico's curve mixes auction vintages up to six weeks old. Isn't the
whole MX row fiction?**
The staleness is real and bounded (45 business days, then the date drops
out — nothing interpolates). The measurable worry is that stale fills damp
measured vol and flatter carry-per-vol. I tested it: weekly-sampled slope
vol is 71.1bp vs 70.8bp daily-based — no damping, because auction-week
jumps carry the variance. The residual worry is timing: MX's "today" is
really "latest auction", so its entry levels are softer than BR's. The
note's trade is BR precisely because its data is daily and clean.

**6. Why is "cuts priced" the 3m rate 9m forward? That is term premium,
not expectation.**
Correct, and the note says so twice (p.1, Appendix C). Any curve-implied
path carries term premium; at the 1y point it is small relative to the
cross-market spread I am trading on (BR −8bp vs MX +105bp). The ranking
is robust unless BR's 1y term premium exceeds its peers' by ~50bp+ — the
wrong sign, given BR's level of rates. I replaced my first metric,
2×(1y−policy), because it was worse: it read BR at −62bp by linearly
extrapolating the 1y dip. Both are in Appendix C.

**7. Funding at the policy rate is generous. Where is repo?**
A stated simplification (DECISIONS "Carry and rolldown"). For BR the
carry number funds at the effective Selic target; actual GC trades near
it, and the trade's carry is a spread of two legs funded identically, so
leg-funding error largely cancels in the DV01-neutral combination. The
residual bias is level, not sign. A funding curve is on the desk-data
list.

**8. Your DV01s are zero-coupon approximations, but you trade NTN-Fs.**
Yes — DV01 = P·T/(1+y)·1e-4 on a zero of the same tenor. For the sizing
ratio this is defensible (at 14.7% yields it lands at 1.00 notional of 5y
per 1.00 of 10y — heavy discounting equalizes the DV01s), and per-unit-
DV01 quoting makes the P&L independent of the approximation's absolute
level. Coupon-exact DV01s shift the notional ratio, not the bp-per-DV01
economics.

**9. Why 5s10s and not 2s10s, if the story is the front repricing?**
Two reasons in the numbers. BR 2s10s enters z +0.29 — already above its
mean — while 5s10s enters z −0.56 with a nearly identical path readout, so
the mean-reversion cushion is only in the belly trade. Second, the 2y
sector of a retail curve is where the basis vs interbank is least stable
(cross-check: −7.6bp at 1y vs −23.1bp at 5y). The 5y leg is the cleanest
expression of "cuts get priced".

**10. Your invalidation rule is arbitrary. Why 1σ of 5y levels?**
It is the z-score's own denominator, so the entry logic and the exit
logic use the same yardstick: I enter because the slope is 0.56σ below
its mean; I exit if it moves another full σ against me (to −17.0bp,
−20.9bp of P&L per unit DV01, 7.4 quarters of carry). Any rule is a
choice; this one is at least internally consistent and cheap to state.

**11. Realized vol over 1y, scaled by √66 — no autocorrelation
adjustment, no vol-of-vol. Why should the ratio mean anything?**
It is a sizing heuristic, not a risk model, and every trade in the
ranking uses the identical estimator, so the cross-section is fair. The
one place estimator choice could flip a conclusion — MX's forward-filled
panel — I cross-checked with weekly sampling. Option-implied vol is on
the desk-data list for exactly this weakness.

**12. The worst 3m flattening you quote is −83.2bp (Nov 2021). Your vol
says 1σ ≈ 50bp per 3m. Reconcile.**
That is the reconciliation: the tail is 1.7× the current-vol σ because
2021 was a hiking shock and vol is regime-dependent. It is in the note to
make the point that the position's loss distribution is fatter than the
sizing vol suggests — hence "repricing trade, not a carry trade" and a
hard exit rather than averaging down.

**13. Six months ago your own chart shows cuts were priced — and they got
un-priced. Why is now different?**
The chart (Fig 3) is deliberately honest about that: the market moved the
cycle out rather than pricing it in, and anyone on this trade in January
lost the front-end leg. The note's answer is construction, not timing:
the 5s10s expression pays +2.8bp/3m to wait, exits mechanically at 1σ,
and does not require the cuts to be delivered — only re-priced. The
macro judgment of *why now* is the owner's section of the note, not the
machinery's.

**14. Where could the data itself be wrong, and how would you know?**
Every fetcher raises on missing or non-numeric data — nothing silently
interpolates (the design caught Banxico returning a term-in-days series
where documentation implied a yield, and ANBIMA's scientific-notation
decimal commas, which would have been a 1000× error). Residual risks:
Tesouro Direto repricing conventions changing (would show as a level
break against the Selic anchor), Banxico auction calendar changes (shows
up as dropped dates via the 45-day fill cap), and treasury.gov/FRED
revisions (immaterial at slope granularity). DECISIONS.md is the audit
trail; the RMSE table is the daily tripwire.

**15. Why should I believe any number in this PDF matches the code?**
Because none of them are typed. Every inline stat, table cell, and figure
regenerates from `scripts/build_report.py` → `report/includes/`, and
Appendix D prints the variable-to-source mapping. Change the cache,
rebuild, and the note is correct again — or the build fails loudly. The
only recorded (not recomputed) numbers are the three ANBIMA cross-check
constants, flagged as such in the provenance table with their date.

---

## Working-paper robustness (Section 5)

**16. Your own mean-reversion check says flat slopes revert only 49% of the
time — a coin flip. Doesn't that kill the Brazil trade?**
It kills the *lazy* version of the trade — "it's flat, it'll steepen" — and
I put that finding in the paper rather than bury it. Pooling all eight
trades, steep slopes (z > +1) flatten 63% of the time over the next 66
days across 1,450 events, but flat slopes (z < −1) steepen only 49% across
3,258 events. So mean reversion is asymmetric and I do not lean on it. The
Brazil 5s10s is a flat-slope position (z −0.56), so its edge is the
forward-implied path mispricing (−8.4bp priced against a 14.25% Selic) and
the +2.8bp/quarter carry — the z-score is context and the invalidation
level is risk management, not expected alpha. The trade pays you to hold a
repricing option; it does not depend on the slope reverting on a timer.

**17. You pooled all eight trades across four countries for that reversion
count. Isn't that mixing regimes and double-counting overlapping windows?**
Both are fair limitations and neither flatters or damns the result
selectively. Overlapping 66-day windows make the 1,450/3,258 event counts
statistically dependent, so I read them as a directional tendency, not an
i.i.d. sample — which is exactly why I report a hit rate and a median move,
not a t-statistic or a P&L. Pooling across countries is deliberate: any one
market has too few |z|>1 episodes in five years to say anything, and the
asymmetry (reversion from rich, not from cheap) holds in the pooled set,
which is the general claim. A per-country breakdown is a one-line change if
a desk wanted it.

**18. Your λ-sensitivity table shows Mexico's carry swinging from 26 to 13
bp as you pin the decay. If the carry isn't robust to the fit, why trust the
ranking?**
Because the trade I am recommending is Brazil, whose 5s10s carry is nearly
invariant — 1.6 to 1.8 bp across the full 10th-to-90th-percentile decay
range. Mexico's 2s10s is decay-sensitive precisely because its short leg
sits at 2y, where the Nelson-Siegel curvature term is largest, so pinning
the decay away from its fitted value re-shapes the front and moves the
carry. That is an argument for reading MX's absolute carry with caution, and
I do — the note already flags MX as the trade whose carry and z-score
disagree. It does not touch the Brazil conclusion.

**19. Rolling RMSE hits 14.3 bp for Brazil in Feb 2021 — four times the
median. Your fit breaks exactly when a trader would want it most.**
Correct, and stated in the paper. The Feb 2021 blow-up is the COVID-recovery
repricing, when the front of the BR curve was moving violently and a smooth
four-parameter fit cannot track a kinked curve. Two responses: first, the
current reading (July 2026) is in a calm window at the 3.4bp median, so
today's slope is well-measured; second, the invalidation rule and the
"repricing trade, not carry trade" framing exist precisely because the
loss distribution has these fat episodes. If I were trading through a stress
like that, I would widen the fit (add tenors, shorten the window) or switch
to raw benchmark bonds — the RMSE series is the tripwire that tells me when.

**20. Weekly and daily vol are identical for Mexico (ratio 1.00) but the
daily is higher than weekly for the clean sources. Explain the direction.**
For Mexico the 45-day forward-fill could in principle inject stale zeros
that damp daily changes; the 1.00 ratio shows it does not, because auction
weeks deliver the moves in jumps that both samplings capture. For the daily
sources (US 0.68–0.71, BR 0.70–0.84) the daily series has more high-frequency
mean-reverting noise than the weekly, so daily-sampled vol sits above
weekly — standard microstructure. I size on the daily number, so if anything
I am using the more conservative (larger) vol in the denominator, making the
reported carry-per-vol a floor, not a flattering ceiling.

**21. Why a count-based reversion check instead of a proper backtest with
P&L, transaction costs, and Sharpe ratios?**
Because a backtest is a different, heavier claim than this note makes, and a
bad one would be worse than none. The note's claim is a point-in-time
relative-value observation plus a mechanical risk frame; the reversion check
tests one property behind it — do slopes at extremes tend to revert — with
event counts and directional hit rates that cannot be curve-fit. A full
backtest needs an execution model, a funding curve, a rebalancing rule, and
survivorship-clean history, none of which I have from free retail data, and
each of which is a place to accidentally manufacture a Sharpe. I list the
desk data that would support a real backtest in the paper's discussion; I do
not pretend the free-data version is one.
