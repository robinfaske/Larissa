# DECISIONS

Data quirks, conventions, and fallbacks. Anything surprising about the data
lives here, not in code comments.

## Environment constraint (2026-07-22)

This repo was built in a sandboxed session whose network policy blocks all
data hosts (Banxico, BCB, treasury.gov, Bundesbank, ANBIMA all returned
proxy-level 403). Endpoints below were therefore verified against current
documentation, not against live responses. **No cache CSVs are committed yet
— nothing was fabricated to fill the gap.** First run of
`python scripts/run_all.py --refresh` on an open network populates
`data/cache/`; commit those CSVs so everything reproduces offline afterwards.
Items marked *verify on first refresh* may need a series-ID correction; every
fetcher fails loudly (no silent empty frames) so a wrong ID cannot slip
through as missing data.

## Sources and endpoints

| Country | Source | Endpoint | Auth | Status |
|---|---|---|---|---|
| MX | Banxico SIE API | `https://www.banxico.org.mx/SieAPIRest/service/v1/series/{ids}/datos/{start}/{end}` | free token, `Bmx-Token` header | series IDs: verify on first refresh |
| BR | ANBIMA ETTJ (daily NSS params) | `https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp` (POST, one business day per request) | none | verify on first refresh |
| BR policy | BCB SGS | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados?formato=json` (432 = Selic target) | none | documented, standard |
| US | treasury.gov daily par yields CSV | `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&_format=csv` | none | documented, standard |
| US policy | FRED public CSV (no key): `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU` (target upper bound) | none | documented, standard |
| DE policy | ECB data portal SDMX CSV (no key): `https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV?format=csvdata` (deposit facility rate) | none | documented, standard |
| DE | Bundesbank SDMX REST, flow `BBSIS` | `https://api.statistiken.bundesbank.de/rest/data/BBSIS/{key}?format=csv` | none | par-yield keys confirmed in docs; param keys: verify on first refresh |
| PL/HU/TR | deferred to M5 | see "Deferred countries" | — | blocked, see below |

### Mexico (Banxico SIE)

- Cetes secondary/auction yield series `SF43936` (28d), `SF43939` (91d),
  `SF43942` (182d), `SF43945` (364d) are widely documented. Bonos M
  fixed-rate tenor series IDs (3/5/10/20/30y) are set in
  `src/fetchers.py:MX_SERIES` from the SIE catalogue (cuadro CF107,
  "Valores gubernamentales, mercado secundario") — *verify on first
  refresh*; a wrong ID returns an SIE error which the fetcher raises.
- Quoting: Cetes are discount-paper yields quoted as simple annual rates on
  actual/360 for their term; converted to effective annual. Bonos M pay
  semiannual coupons, secondary-market yield quoted semiannual
  bond-equivalent; converted to effective annual: `(1 + y/2)^2 - 1`.
- Weekly auction frequency for some series → forward-filled to business
  days only for z-score history, never for the "today" curve snapshot.

### Brazil (ANBIMA + BCB)

- The old BM&F DI×pré swap referential series on BCB SGS (7805–7827) were
  **discontinued in 2019** — confirmed during endpoint research. Do not use.
- Primary source: ANBIMA publishes daily fitted **Svensson parameters** for
  the prefixado (nominal) curve — we use their β/τ directly, same approach
  as Bundesbank for DE, no fitting on our side. Historical depth requires
  one request per business day; the fetcher loops and caches incrementally.
- Fallback if ANBIMA blocks scripted access: B3 "Taxas referenciais" daily
  vertex page (HTML, parseable). Second fallback: reduced tenor set from
  LTN/NTN-F indicative rates.
- Quoting: Brazilian rates are exponential on a **252-business-day** basis,
  `(1+i)^(du/252)`. The annualized number is already an effective annual
  rate; no compounding conversion needed, only the day-count note. ANBIMA
  curve is zero-coupon — the cleanest of the four.

### United States (treasury.gov)

- Chose treasury.gov over FRED: no API key, so the note reproduces without
  registration. Par yields, constant maturity, semiannual bond-equivalent →
  converted to effective annual like MX Bonos.

### Germany (Bundesbank)

- Bundesbank publishes daily Svensson coefficients for listed Federal
  securities (flow `BBSIS`); we use them directly instead of fitting
  (spec requirement). Confirmed key pattern for fitted yields:
  `D.I.ZAR.ZI.EUR.S1311.B.A604.R{MM}XX.R.A.A._Z._Z.A` (e.g. `R10XX` = 10y).
  The six parameter series keys (β0..β3, τ1, τ2) follow the same dimension
  structure with the parameter in place of the maturity code — *verify on
  first refresh*. Fallback (implemented): pull the fitted par-yield grid
  1y–15y from the confirmed keys above and refit NSS; result is
  numerically near-identical for our tenors and is flagged in the fit-RMSE
  table when used.
- Bundesbank/ANBIMA Svensson yields are effective annual — no conversion.

## Common basis

All yields normalized to **effective annual rate, in percent**, ACT/365F
tenor grid in years. Conversions above; implemented and unit-tested in
`src/fetchers.py`. Mixed par (US, MX bonos) vs zero (BR, DE) curves: we fit
NS/NSS to the observed grid per country and state the object we fitted. At
2s10s/5s10s granularity the carry/roll ranking is robust to par-vs-zero;
this is a stated approximation, not a silent one.

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

## Deferred countries (M5 gate)

PL: NBP API has no bond yields; plan is MF/GPW benchmark fixings with
Stooq daily CSV (`https://stooq.com/q/d/l/?s=10yply.b&i=d`, also 2y/5y
symbols) as the free fallback. HU: ÁKK benchmark fixings, Stooq fallback
(`10yhuy.b` etc.). TR: TCMB EVDS (free key) — endpoint blocked in this
sandbox. All three enter only after their sanity table passes; sparse
3–4-tenor grids get NS with λ fixed by the MX/BR fitted range, flagged.
