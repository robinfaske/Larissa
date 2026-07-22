# DECISIONS

Data quirks, conventions, and fallbacks. Anything surprising about the data
lives here, not in code comments.

## Build note (2026-07-22)

The repo was scaffolded in a sandbox that initially blocked all data hosts;
after the network was opened, every endpoint was verified against live
responses and `data/cache/` was populated and committed — the repo
reproduces offline from the cache. Every fetcher fails loudly (no silent
empty frames), so a dead endpoint or changed series ID cannot masquerade as
missing data. Live verification changed two sources from the original plan
(Brazil curve, DE policy) — both switches are documented below.

## Sources and endpoints

| Country | Source | Endpoint | Auth | Status |
|---|---|---|---|---|
| MX | Banxico SIE API, weekly auction yields | `https://www.banxico.org.mx/SieAPIRest/service/v1/series/{ids}/datos/{start}/{end}` | free token, `Bmx-Token` header | verified live 2026-07-22 |
| MX policy | Banxico SIE `SF61745` (overnight target) | same API | token | verified live |
| BR | Tesouro Direto daily rates (LTN + NTN-F) | `https://www.tesourotransparente.gov.br/ckan/dataset/.../PrecoTaxaTesouroDireto.csv` (full URL in `src/fetchers.py`) | none | verified live; see "Brazil" for why not ANBIMA/B3 |
| BR policy | BCB SGS 432 (Selic target) | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados?formato=json` | none | verified live |
| US | treasury.gov daily par yields CSV | `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&_format=csv` | none | verified live |
| US policy | FRED public CSV `DFEDTARU` (target upper bound) | `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU` | none | verified live |
| DE | Bundesbank SDMX REST, flow `BBSIS`, daily Svensson params β0–β3, τ1, τ2 | `https://api.statistiken.bundesbank.de/rest/data/BBSIS/D.I.ZST.{B0..T2}.EUR.S1311.B.A604._Z.R.A.A._Z._Z.A?format=csv` | none | param keys verified live (β0 = 4.07 on 2026-07-10) |
| DE policy | FRED public CSV `ECBDFR` (ECB deposit facility rate mirror) | `https://fred.stlouisfed.org/graph/fredgraph.csv?id=ECBDFR` | none | canonical ECB portal (`FM.D.U2.EUR.4F.KR.DFR.LEV`) returned 504s at build time, even for 5-observation windows; FRED mirror lags ≤1 day, immaterial for a policy rate |
| PL/HU/TR | deferred to M5 | see "Deferred countries" | — | pending |

### Mexico (Banxico SIE)

- Yields are the **weekly auction results** (cuadro CF107), the only free
  per-tenor source with usable frequency; the "mercado secundario" tables
  (CF114) turned out to be monthly averages. Verified series: Cetes
  `SF43936/39/42/45` (28/91/182/364d); Bonos M `SF43883` (3y), `SF43886`
  (5y), `SF44071` (10y), `SF45384` (20y), `SF60696` (30y). The 7y Bono
  series (`SF44946`) has returned nothing for 6y — 7y is out of the
  auction calendar — so the MX grid is 9 tenors. First-guess IDs from
  documentation were wrong in a subtle way (`SF44070` is the auction
  *term in days*, whence a "3,213" parse) — caught because the fetcher
  fails loudly; SIE also uses commas as thousands separators, handled
  explicitly.
- Each tenor is auctioned on its own rotation, so no single date carries a
  full curve. `ffill_panel` forward-fills each tenor at most 45 business
  days, then drops incomplete dates — stale-but-bounded beats
  interpolated. Long-end points can be up to ~6 weeks old; this smooths
  the fitted history, so MX realized vol (hence carry-per-vol) is, if
  anything, understated. Fit RMSE (~9bp median) reflects the
  auction-vintage mixing.
- Quoting: Cetes are simple annual act/360 for their term → effective
  annual. Bonos M are semiannual bond-equivalent → `(1 + y/2)^2 - 1`.

### Brazil (Tesouro Direto + BCB)

The curve source changed twice during live verification — the audit trail:

1. BM&F DI×pré swap referential series on BCB SGS (7805–7827):
   **discontinued in 2019**. Not used.
2. ANBIMA daily Svensson parameters (the original plan): the public
   `CZ-down.asp` download is a **rolling ~5-business-day window** — older
   dates return an empty document; deep history is subscriber-only. Useless
   for 5y z-scores. (The parser was validated first: parameters reproduce
   ANBIMA's own published vertices to 0.01bp, including their
   decimal-comma scientific notation and decimal-vs-percent units.)
3. B3 legacy "taxas referenciais" vertex page (`www2.bmf.com.br/...`):
   dead server-side — returns a SQL Server connection error.
4. **Adopted: Tesouro Direto daily rates file** (Tesouro Transparente CKAN,
   one ~14MB CSV, full history since 2002, no key). Prefixado universe =
   LTN ("Tesouro Prefixado", zero-coupon) + NTN-F ("com Juros Semestrais");
   yield = mid of morning buy/sell; tenor = actual time to maturity per
   bond (NS/NSS fitting handles the irregular grid).

Caveat, quantified: Tesouro Direto is a retail window, so it embeds a
spread vs the interbank curve. Cross-check on 2026-07-17 (our NSS fit vs
ANBIMA's published params): −7.6bp at 1y, −23.1bp at 5y, −19.3bp at 10y.
A level effect of that size is immaterial for slope z-scores (source is
self-consistent through time) and small for carry/roll; stated rather
than hidden.

Quoting: Brazilian rates are exponential on a **252-business-day** basis,
`(1+i)^(du/252)`; the quoted number is already an effective annual rate —
no compounding conversion, only this day-count note.

### United States (treasury.gov)

- Chose treasury.gov over FRED: no API key, so the note reproduces without
  registration. Par yields, constant maturity, semiannual bond-equivalent →
  converted to effective annual like MX Bonos.

### Germany (Bundesbank)

- Bundesbank publishes daily Svensson coefficients for listed Federal
  securities (flow `BBSIS`); we use them directly instead of fitting
  (spec requirement). Confirmed key pattern for fitted yields:
  `D.I.ZAR.ZI.EUR.S1311.B.A604.R{MM}XX.R.A.A._Z._Z.A` (e.g. `R10XX` = 10y).
  The six parameter series keys (β0..β3, τ1, τ2) were **verified live**:
  `D.I.ZST.{B0,B1,B2,B3,T1,T2}.EUR.S1311.B.A604._Z.R.A.A._Z._Z.A`.
  A fallback (implemented, unused) refits NSS from the fitted-yield grid
  1y–15y should the parameter keys ever move.
- Bundesbank quirks: the CSV ships an unnamed date column, several
  metadata rows before the data, and "." for missing values — all handled
  in one parser, which the ECB-style `TIME_PERIOD` CSVs share.
- Bundesbank Svensson yields are effective annual — no conversion.

## Common basis

All yields normalized to **effective annual rate, in percent**, ACT/365F
tenor grid in years. Conversions above; implemented and unit-tested in
`src/fetchers.py`. Mixed par (US, MX bonos) vs zero (BR, DE) curves: we fit
NS/NSS to the observed grid per country and state the object we fitted. At
2s10s/5s10s granularity the carry/roll ranking is robust to par-vs-zero;
this is a stated approximation, not a silent one.

**Policy rates share the basis**: the Banxico target, fed funds bounds, and
ECB deposit rate are quoted simple annual act/360 for an overnight term and
are converted via `(1 + r/360)^365 − 1` (≈ +20bp at MX levels — large
enough to distort "cuts priced" if ignored). The Selic target is already
effective annual on the 252 convention and passes through unchanged.

## Policy-path lens

Cuts priced over 12m ≈ `2 × (fitted 1y yield − policy rate)`, i.e. the 1y
zero read as the average expected policy rate over the next year under a
linear path, term premium ignored. Crude, but identical across countries,
which is what the cross-sectional chart needs.

## Carry and rolldown

3m static, along today's fitted curve (curve assumed unchanged). Per leg of
tenor `T`, in bp per 3m per unit DV01:
`[h·(y(T) − r_policy) + (T−h)·(y(T) − y(T−h))] × 10000 / T`, `h = 0.25`,
zero-coupon approximation. Trade number = signed sum of the two legs;
DV01-neutrality is by construction since legs are expressed per unit DV01.
Funding at the policy rate (repo proxy) — stated simplification.

## Sizing

Trade vol = stdev of daily changes in the fitted trade spread × √66 (3m,
business days). Money chart ranks carry+roll per unit of that vol.

## Deferred countries — M5 gate outcome (2026-07-22)

**PL and HU are excluded**: no free, scriptable, per-tenor daily yield
source survived verification, and this repo does not scrape around access
controls. The audit trail:

- Stooq CSV endpoints (`10yply.b`, `10yhuy.b`, …): now behind a
  proof-of-work anti-bot challenge (SHA-256 nonce + `/__verify` cookie).
  Solvable programmatically, but circumventing an explicit anti-scraper
  wall is the wrong trade for this repo. Out.
- ÁKK (HU debt agency) reference yields: the statistics section is a
  JavaScript (Vaadin) application; no public data API is documented and
  deep links 404. Out.
- BondSpot / GPW Benchmark (PL): fixing results are news-bulletin pages
  and the TBSP is an index level, not a per-tenor curve. Out.
- NBP and MNB open APIs: FX and policy rates only — no bond yields.

**TR is pending**: TCMB EVDS is a documented free API but needs a key
(`EVDS_KEY` in the environment, like `BANXICO_TOKEN`); not yet provided.
If added later: sparse 3–4-tenor grids get NS with λ fixed from the MX/BR
fitted range, flagged in the summary table, and enter only after a clean
sanity table.

## Report toolchain (Phase 2)

Typst via the `typst` PyPI package (compiles in-process, fonts bundled, no
system install) — chosen over HTML+weasyprint for deterministic layout and
a single-binary dependency. `scripts/build_report.py` regenerates every
inline number, table, and figure into `report/includes/` from the analytics
layer and compiles `report/note.typ`; nothing in the note is hand-typed, and
`includes/provenance.csv` maps each variable to its source function. The
three ANBIMA retail-basis constants are the only recorded (not recomputed)
numbers — the one-off cross-check is documented under "Brazil".

Invalidation rule (also in the note): a trade exits when its slope moves
one 5y standard deviation of levels — the z-score's own denominator —
against the position from entry.
