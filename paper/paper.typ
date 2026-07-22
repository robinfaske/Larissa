// Working paper — layout and wiring. Data numbers come from
// /report/includes/vars.typ and *.csv (shared with the desk note); nothing
// data-derived is hand-typed. OWNER-scaffolded sections marked in accent.
#import "/report/includes/vars.typ": n

#let ink = rgb("#0b0b0b")
#let muted = rgb("#52514e")
#let hair = rgb("#c3c2b7")
#let accent = rgb("#b5541f")

#set page("a4", margin: (x: 2.2cm, top: 2.2cm, bottom: 2.0cm),
  footer: context [
    #set text(size: 8pt, fill: muted)
    #h(1fr) #counter(page).display("1") #h(1fr)
  ])
#set text(size: 10.5pt, font: "STIX Two Text", fill: ink)
#show math.equation: set text(font: "STIX Two Math")
#set par(justify: true, leading: 0.62em, first-line-indent: 1.2em, spacing: 0.65em)
#set heading(numbering: "1.1")
#show heading: set block(above: 1.1em, below: 0.6em)
#show heading.where(level: 1): set text(size: 11.5pt)
#show heading.where(level: 2): set text(size: 10.8pt)
#set math.equation(numbering: "(1)")

#show figure.caption: it => block(width: 92%, above: 0.6em)[
  #set text(size: 9pt, fill: muted)
  #text(weight: "bold", fill: ink)[#it.supplement #context it.counter.display().] #it.body
]
#let booktabs(path, fs: 9pt) = {
  let rows = csv(path)
  set text(size: fs, number-width: "tabular")
  table(columns: rows.first().len(), align: (x, _) => if x == 0 { left } else { right },
    stroke: none, inset: (x: 5pt, y: 3pt),
    table.hline(stroke: 0.8pt),
    table.header(..rows.first().map(c => text(weight: "bold")[#c])),
    table.hline(stroke: 0.4pt), ..rows.slice(1).flatten(), table.hline(stroke: 0.8pt))
}
#let owner(body) = block(inset: (left: 8pt), stroke: (left: 1.5pt + accent), below: 0.7em)[
  #text(size: 8.4pt, fill: accent, weight: "bold", tracking: 0.3pt)[OWNER — REWRITE IN YOUR VOICE] \
  #text(style: "italic", fill: muted)[#body]]

// ===================== Title block =====================
#align(center)[
  #v(0.5em)
  #text(size: 17pt, weight: "bold")[Priced to Stand Still: The Missing Cutting \ Cycle in Brazil's Local Yield Curve]
  #v(0.6em)
  #text(size: 11pt)[Robin Faske]
  #v(0.2em)
  #text(size: 9.5pt, fill: muted)[Independent researcher · robin.faske\@outlook.de]
  #v(0.2em)
  #text(size: 9.5pt, fill: muted)[This version: #n.date]
]
#v(0.8em)

// ===================== Abstract =====================
#block(width: 100%, inset: (x: 1.4em))[
  #align(center)[#text(size: 9.6pt, weight: "bold", tracking: 0.5pt)[ABSTRACT]]
  #v(0.2em)
  #set text(size: 9.6pt)
  #set par(first-line-indent: 0em, justify: true)
  #owner[
    I fit Nelson–Siegel–Svensson curves to free public data for four
    sovereign local-currency markets (Brazil, Mexico; United States and
    Germany as anchors) and read each curve's short end as a forward-implied
    policy path. Across the set, Brazil alone prices no easing: the implied
    3-month rate nine months forward sits #n.br_path12 bp from a #n.br_policy%
    Selic, while every other curve is steep to its own five-year history. I
    express the dislocation as a DV01-neutral 5s10s steepener carrying
    #n.br_carry bp per quarter per unit of DV01, and quantify its risks — a
    retail-quote basis, a fat flattening tail, and the term-premium content
    of the path metric. The analytics, data, and this paper reproduce from a
    public repository. #text(fill: accent)[[compress to 150 words or fewer in your voice]]
  ]
  #v(0.4em)
  #text(size: 9.2pt)[*Keywords:* term structure, Nelson–Siegel–Svensson, emerging markets, local-currency sovereign bonds, monetary policy expectations, curve trades.]
  #v(0.2em)
  #text(size: 9.2pt)[*JEL classification:* E43, E52, G12, G15, C13.]
]
#v(0.6em)
#line(length: 100%, stroke: 0.4pt + hair)

// ===================== 1 Introduction =====================
= Introduction
#owner[
  Motivate the question: local-currency EM curves encode a policy path, and
  cross-market dispersion in that path is tradable. State the finding —
  Brazil prices #n.br_path12 bp of change over 12m against a #n.br_policy%
  Selic while its 5s10s is flat (z #n.br_z) — and the contribution: a
  reproducible, free-data pipeline that ranks curve trades by carry per unit
  of vol. Cite the slope-factor tradition @litterman1991common and the
  fitted-curve lineage @nelson1987parsimonious, @svensson1994estimating, and @diebold2006forecasting. [your framing and positioning]
]

= Data
I fit government curves in the tradition of @gurkaynak2007us, using only
free, public sources; each fetcher fails loudly rather than returning
partial data, and all series are cached so results reproduce offline. Brazilian prefixado yields come from the Tesouro Direto daily
rates file (LTN and NTN-F), a retail window: on the one cross-check date
the public ANBIMA interbank curve allows, the fitted retail curve sits
#n.rb_1y bp, #n.rb_5y bp, and #n.rb_10y bp below interbank at 1, 5, and 10
years. This is a level effect that cancels in z-scores; the tenor
differential is carried as a risk (Section 4). Mexican yields are Banxico
weekly auction results, so no single date holds a full curve; each tenor is
forward-filled at most 45 business days, and the resulting staleness is
tested in Section 5. US par yields are from the Treasury and German
Svensson parameters from the Bundesbank. Policy rates are normalized to the
same effective-annual basis as the curves. Appendix A details every source
and convention; Appendix B reports fit quality.

= Methodology
For each date I fit the Nelson–Siegel–Svensson (NSS) forward-rate curve.
The zero yield at maturity $tau$ is

$ y(tau) = beta_0 + beta_1 (1 - e^(-tau\/lambda_1))/(tau\/lambda_1)
  + beta_2 ((1 - e^(-tau\/lambda_1))/(tau\/lambda_1) - e^(-tau\/lambda_1))
  + beta_3 ((1 - e^(-tau\/lambda_2))/(tau\/lambda_2) - e^(-tau\/lambda_2)), $ <eq-nss>

reducing to Nelson–Siegel ($beta_3 = 0$) where fewer than six tenors are
observed. Conditional on the decay parameters $lambda_1, lambda_2$, equation
(#ref(<eq-nss>)) is linear in $beta$, so I grid the decays over a bounded
range and solve ordinary least squares at each node, selecting the fit that
minimizes root-mean-square error. The forward-implied policy path reads the
short end as expected policy. With $f(t_1, t_2)$ the implied forward between
horizons,

$ f(t_1, t_2) = ((1 + y(t_2))^(t_2) / (1 + y(t_1))^(t_1))^(1/(t_2 - t_1)) - 1, $ <eq-fwd>

I measure easing priced over twelve months as $f(0.75, 1) - r$ for policy
rate $r$, replacing the cruder $2(y(1) - r)$ linear-path proxy (compared in
Section 4). A DV01-neutral slope trade sizes the short-tenor leg by

$ N_s / N_l = ("DV01"_l) / ("DV01"_s), quad
  "DV01"(y, T) = (T P) / (1 + y) times 10^(-4), $ <eq-dv01>

with $P$ the zero price. Static 3-month carry-plus-rolldown on a leg of
tenor $T$, funded at policy rate $r$, in bp per unit DV01, is

$ c(T) = [h (y(T) - r) + (T - h)(y(T) - y(T - h))] times 10^4 / T,
  quad h = 0.25, $ <eq-carry>

and the trade value is the DV01-neutral difference of its legs. I scale each
trade by the annualized standard deviation of daily fitted-slope changes and
rank on carry per unit of vol. The slope z-score compares the current fitted
slope to its trailing five-year mean in units of that window's standard
deviation.

= Results
Table 1 reports the cross-market state. Brazil is the only market pricing
easing over the next year (#n.br_path12 bp) and the only 5s10s below its
five-year mean (z #n.br_z); Mexico's 2s10s offers the highest carry per unit
of vol (#n.mx_cv) but enters #n.mx_z standard deviations steep. Figure 1
places each trade in policy-path/z-score space; Figure 2 ranks carry per
unit of vol; Figure 3 shows the fitted curves against six months prior.

#figure(booktabs("/report/includes/summary.csv"), caption: [
  Cross-market state. C+R is 3-month carry plus rolldown for the steepener,
  per unit DV01; Exit is the one-sigma invalidation level for the
  positive-carry direction. Policy rates effective annual.]) <tab-xmkt>

#figure(image("/paper/figs/fig_z_vs_cuts.pdf"), caption: [
  Policy change priced over twelve months (forward-implied) against the
  5s10s / 2s10s slope z-score. Brazil alone occupies the no-cuts,
  flat-curve quadrant.]) <fig-scatter>

#figure(image("/paper/figs/fig_carry_per_vol.pdf", width: 88%), caption: [
  Carry plus rolldown per unit of 3-month trade vol, each trade shown in its
  positive-carry direction.]) <fig-carry>

#figure(image("/paper/figs/fig_curves.pdf", width: 100%), caption: [
  Fitted local curves today versus six months prior. Brazil un-inverted at
  the front, moving the implied cutting cycle outward.]) <fig-curves>

The naive and forward-implied path metrics diverge most for Brazil
(#n.br_naive bp versus #n.br_path12 bp); the forward metric is the curve's
statement about the policy rate a year out, and the cross-market ranking is
robust to the choice (Appendix C).

= Robustness
I run four checks; none constructs a profit-and-loss backtest.

*Decay sensitivity.* I refit each curve with the Nelson–Siegel decay pinned
at the 10th, 50th, and 90th percentiles of its own fitted-decay history and
recompute the trade quantities (Table 2). The Brazil 5s10s carry is nearly
invariant, ranging #n.rob_br_carry_lo–#n.rob_br_carry_hi bp across the full
decay range; the slope and z-score move more, since pinning the decay away
from its fitted value re-shapes the belly. The Mexico 2s10s is more
decay-sensitive, as its front leg sits where the decay term is largest.

#figure(booktabs("/report/includes/rob_lambda.csv"), caption: [
  Latest slope, z-score, and carry with the decay pinned at percentiles of
  each curve's fitted-decay history.]) <tab-lambda>

*Fit stability.* The 66-business-day rolling median RMSE (Table 3) stays
near its full-sample median outside stress. Brazil's worst window reaches
#n.rob_br_rmse_max bp in #n.rob_br_rmse_when, roughly four times its median,
so fitted-slope readings from that period carry wider error.

#figure(booktabs("/report/includes/rob_rmse.csv"), caption: [
  Full-sample median versus worst 66-day rolling-median fit RMSE, by curve.]) <tab-rmse-roll>

*Sampling frequency.* Weekly- and daily-sampled slope vols agree for Mexico
(ratio near one), confirming that the 45-day forward-fill does not damp the
daily vol estimate; for the daily sources the weekly figure is lower, so the
daily estimate is, if anything, conservative in the sizing denominator
(Table 4).

#figure(booktabs("/report/includes/rob_sampling.csv"), caption: [
  Daily- versus weekly-sampled 3-month slope vol, per trade.]) <tab-sampling>

*Mean reversion.* Pooling all eight trades, I count every date whose trailing
five-year z-score exceeds one in absolute value and ask whether the slope
moves toward its mean over the next 66 business days (Table 5). Reversion is
asymmetric: from steep levels (z > +1) the slope flattens #n.rob_rich_hit of
the time across #n.rob_rich_n events, but from flat levels (z < −1) it
steepens only #n.rob_cheap_hit of the time across #n.rob_cheap_n events, near
a coin flip. The Brazil trade is a flat-slope position, so its edge rests on
the forward-implied path mispricing and positive carry, not on z-score mean
reversion; the z-score is context, and the invalidation level is risk
management rather than expected alpha.

#figure(booktabs("/report/includes/rob_reversion.csv"), caption: [
  Count-based mean-reversion check, pooled across all trades. Hit rate is the
  fraction of dates whose slope moves toward its mean over the next 66 days;
  50% is the no-reversion benchmark.]) <tab-reversion>

= Discussion and limitations
#owner[
  Interpret the dislocation and its likely resolution; discuss the retail
  basis (#n.rb_5y bp at 5y), the term-premium content of the path metric,
  the par-versus-zero approximation, and the policy-rate funding assumption.
  State what desk data (DI futures, interbank ETTJ history, option-implied
  vol) would sharpen. [your interpretation and caveats]
]

#bibliography("/paper/refs.bib", style: "chicago-author-date", title: "References")

// ===================== Appendix =====================
#set heading(numbering: "A.1")
#counter(heading).update(0)
= Appendix: conventions and fit quality
All yields are effective annual. Brazil's 252-business-day exponential
quotes pass through unchanged; US and Mexican semiannual bond-equivalent
yields compound to effective annual; Cetes convert from simple act/360
discount quotes; overnight act/360 policy quotes convert via
$(1 + r\/360)^365 - 1$. Median fit RMSE by curve:

#figure(booktabs("/report/includes/rmse.csv"), caption: [
  Median Nelson–Siegel(–Svensson) fit RMSE by curve over the sample.]) <tab-rmse>

Appendix C of the companion desk note tabulates the forward-implied versus
naive policy-path metric; the provenance table there maps every data number
to its generating function.
