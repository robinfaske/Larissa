"""Data fetchers: one per source, common interface, cache-first.

Curve frames:  columns [date, tenor_yrs, yield_pct]   yield = effective annual, %
Policy frames: columns [date, rate_pct]
Param frames:  columns [date, b0, b1, b2, b3, t1, t2] (published Svensson fits)

Every fetcher either returns real data or raises — a dead endpoint or a
changed series ID must never degrade into a silently empty frame (see
DECISIONS.md). `load(name)` reads the committed cache so the whole repo
reproduces offline; `--refresh` re-pulls and rewrites the cache.
"""

from __future__ import annotations

import io
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
HISTORY_YEARS = 6  # 5y z-score window + 6m-ago curve comparison
STD_GRID = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0]

MX_SERIES = {  # Banxico SIE weekly-auction yields (verified via cuadro CF107 titles)
    28 / 365: "SF43936", 91 / 365: "SF43939", 182 / 365: "SF43942", 364 / 365: "SF43945",
    3.0: "SF43883", 5.0: "SF43886", 7.0: "SF44946", 10.0: "SF44071",
    20.0: "SF45384", 30.0: "SF60696",
}
US_TENORS = {"1 Mo": 1 / 12, "3 Mo": 0.25, "6 Mo": 0.5, "1 Yr": 1.0, "2 Yr": 2.0,
             "3 Yr": 3.0, "5 Yr": 5.0, "7 Yr": 7.0, "10 Yr": 10.0, "20 Yr": 20.0, "30 Yr": 30.0}
DE_PARAM_KEYS = {  # Bundesbank BBSIS flow; parameter dimension codes: verify on first refresh.
    "b0": "B0", "b1": "B1", "b2": "B2", "b3": "B3", "t1": "T1", "t2": "T2",
}


def _get(url: str, **kwargs) -> requests.Response:
    """GET with a sane timeout; raises on any non-2xx status."""
    resp = requests.get(url, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp


def _start_date() -> date:
    return date.today() - timedelta(days=int(HISTORY_YEARS * 365.25))


def semiannual_to_effective(y_pct: pd.Series) -> pd.Series:
    """Semiannual bond-equivalent yield (%) -> effective annual (%)."""
    return ((1 + y_pct / 200.0) ** 2 - 1) * 100.0


def simple_360_to_effective(y_pct: pd.Series, days: int) -> pd.Series:
    """Simple annualized act/360 rate (%) for a `days` term -> effective annual (%)."""
    period = y_pct / 100.0 * days / 360.0
    return ((1 + period) ** (365.0 / days) - 1) * 100.0


def overnight_360_to_effective(r_pct: pd.Series) -> pd.Series:
    """Overnight simple act/360 policy quote (%) -> effective annual (%).

    Applies to the Banxico target, fed funds bounds, and the ECB deposit
    rate; the Selic target is already effective annual (DECISIONS.md).
    """
    return ((1 + r_pct / 100.0 / 360.0) ** 365 - 1) * 100.0


def load(name: str) -> pd.DataFrame:
    """Read a cached CSV (offline path). Raises if the cache is missing."""
    path = CACHE_DIR / f"{name}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} missing — run `python scripts/run_all.py --refresh` on an "
            "open network to populate the cache (see DECISIONS.md)."
        )
    return pd.read_csv(path, parse_dates=["date"])


def refresh(name: str, fetch_fn: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    """Fetch fresh data and rewrite the cache."""
    frame = fetch_fn()
    if frame.empty:
        raise ValueError(f"fetcher for '{name}' returned no rows — refusing to cache")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_csv(CACHE_DIR / f"{name}.csv", index=False)
    return frame


# --- Mexico: Banxico SIE ----------------------------------------------------

def fetch_mx_curve() -> pd.DataFrame:
    """Cetes + Bonos M yields from the Banxico SIE API, normalized to effective annual %."""
    token = os.environ.get("BANXICO_TOKEN")
    if not token:
        raise RuntimeError("BANXICO_TOKEN not set (see .env.example)")
    ids = ",".join(MX_SERIES.values())
    url = (f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/{ids}/datos/"
           f"{_start_date():%Y-%m-%d}/{date.today():%Y-%m-%d}")
    payload = _get(url, headers={"Bmx-Token": token}).json()
    by_id = {t: s for t, s in MX_SERIES.items()}
    rows = []
    for serie in payload["bmx"]["series"]:
        tenor = next(t for t, s in by_id.items() if s == serie["idSerie"])
        for obs in serie.get("datos", []):
            if obs["dato"] in ("N/E", ""):
                continue
            # SIE uses commas as thousands separators (e.g. term-in-days series)
            rows.append((pd.to_datetime(obs["fecha"], dayfirst=True), tenor,
                         float(str(obs["dato"]).replace(",", ""))))
    frame = pd.DataFrame(rows, columns=["date", "tenor_yrs", "yield_pct"])
    cetes = frame["tenor_yrs"] < 1.5
    for tenor in frame.loc[cetes, "tenor_yrs"].unique():
        mask = frame["tenor_yrs"] == tenor
        frame.loc[mask, "yield_pct"] = simple_360_to_effective(
            frame.loc[mask, "yield_pct"], days=round(tenor * 365))
    frame.loc[~cetes, "yield_pct"] = semiannual_to_effective(frame.loc[~cetes, "yield_pct"])
    return frame.sort_values(["date", "tenor_yrs"]).reset_index(drop=True)


def ffill_panel(curve: pd.DataFrame, limit_bdays: int = 45) -> pd.DataFrame:
    """Weekly-auction observations (MX) -> business-daily curve panel.

    Each tenor is forward-filled at most `limit_bdays`; dates still missing
    any tenor are dropped, never interpolated across tenors (DECISIONS.md).
    """
    wide = (curve.pivot_table(index="date", columns="tenor_yrs",
                              values="yield_pct", aggfunc="last")
            .reindex(pd.bdate_range(curve["date"].min(), curve["date"].max()))
            .ffill(limit=limit_bdays).dropna())
    long = wide.rename_axis("date").reset_index().melt(
        "date", var_name="tenor_yrs", value_name="yield_pct")
    return long.sort_values(["date", "tenor_yrs"]).reset_index(drop=True)


def fetch_mx_policy() -> pd.DataFrame:
    """Banxico overnight target rate (SIE series SF61745)."""
    token = os.environ.get("BANXICO_TOKEN")
    if not token:
        raise RuntimeError("BANXICO_TOKEN not set (see .env.example)")
    url = (f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF61745/datos/"
           f"{_start_date():%Y-%m-%d}/{date.today():%Y-%m-%d}")
    datos = _get(url, headers={"Bmx-Token": token}).json()["bmx"]["series"][0]["datos"]
    out = pd.DataFrame(
        [(pd.to_datetime(o["fecha"], dayfirst=True), float(o["dato"]))
         for o in datos if o["dato"] not in ("N/E", "")],
        columns=["date", "rate_pct"])
    out["rate_pct"] = overnight_360_to_effective(out["rate_pct"])
    return out


# --- Brazil: Tesouro Direto prefixado bonds + BCB SGS policy ----------------

BR_TD_URL = ("https://www.tesourotransparente.gov.br/ckan/dataset/"
             "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
             "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv")


def fetch_br_curve() -> pd.DataFrame:
    """Prefixado curve from the Tesouro Direto daily rates file (LTN + NTN-F).

    One ~14MB CSV with full history — chosen after ANBIMA's public download
    proved to be a rolling 5-business-day window and B3's legacy vertex page
    is dead server-side (DECISIONS.md). Mid of morning buy/sell rates;
    252-business-day effective annual, so no compounding conversion. Tenors
    are each bond's actual time to maturity, which NS/NSS fitting handles.
    """
    raw = pd.read_csv(io.StringIO(_get(BR_TD_URL).text), sep=";", decimal=",")
    pre = raw[raw["Tipo Titulo"].isin(
        ["Tesouro Prefixado", "Tesouro Prefixado com Juros Semestrais"])]
    out = pd.DataFrame({
        "date": pd.to_datetime(pre["Data Base"], dayfirst=True),
        "tenor_yrs": (pd.to_datetime(pre["Data Vencimento"], dayfirst=True)
                      - pd.to_datetime(pre["Data Base"], dayfirst=True)).dt.days / 365.25,
        "yield_pct": (pre["Taxa Compra Manha"] + pre["Taxa Venda Manha"]) / 2,
    })
    out = out[(out["date"] >= pd.Timestamp(_start_date()))
              & out["tenor_yrs"].between(0.08, 11.0)]
    return out.sort_values(["date", "tenor_yrs"]).reset_index(drop=True)


def fetch_br_policy() -> pd.DataFrame:
    """Selic target rate, BCB SGS series 432 (open API, no key)."""
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados?formato=json"
           f"&dataInicial={_start_date():%d/%m/%Y}&dataFinal={date.today():%d/%m/%Y}")
    data = _get(url).json()
    return pd.DataFrame(
        [(pd.to_datetime(o["data"], dayfirst=True), float(o["valor"])) for o in data],
        columns=["date", "rate_pct"])


# --- United States: treasury.gov + FRED public CSV --------------------------

def fetch_us_curve() -> pd.DataFrame:
    """Daily Treasury par yields (no key), semiannual BEY -> effective annual %."""
    frames = []
    for year in range(_start_date().year, date.today().year + 1):
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
               f"daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
               f"&field_tdr_date_value={year}&_format=csv")
        frames.append(pd.read_csv(io.StringIO(_get(url).text)))
    raw = pd.concat(frames)
    raw["date"] = pd.to_datetime(raw["Date"])
    long = raw.melt(id_vars="date", value_vars=[c for c in US_TENORS if c in raw.columns],
                    var_name="label", value_name="yield_pct").dropna()
    long["tenor_yrs"] = long["label"].map(US_TENORS)
    long["yield_pct"] = semiannual_to_effective(long["yield_pct"])
    return (long[["date", "tenor_yrs", "yield_pct"]]
            .sort_values(["date", "tenor_yrs"]).reset_index(drop=True))


def _fredgraph(series_id: str) -> pd.DataFrame:
    """Daily series via FRED's public fredgraph CSV (no key), effective annual %."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    raw = pd.read_csv(io.StringIO(_get(url).text)).rename(
        columns={"DATE": "date", "observation_date": "date", series_id: "rate_pct"})
    raw["date"] = pd.to_datetime(raw["date"])
    raw["rate_pct"] = pd.to_numeric(raw["rate_pct"], errors="coerce")
    raw = raw.dropna()
    raw["rate_pct"] = overnight_360_to_effective(raw["rate_pct"])
    return raw[raw["date"] >= pd.Timestamp(_start_date())].reset_index(drop=True)


def fetch_us_policy() -> pd.DataFrame:
    """Fed funds target upper bound (FRED DFEDTARU)."""
    return _fredgraph("DFEDTARU")


# --- Germany: Bundesbank published Svensson coefficients --------------------

def fetch_de_params() -> pd.DataFrame:
    """Daily Svensson parameters for listed Federal securities (flow BBSIS).

    Parameter dimension codes are the one unverified piece of the DE spec
    (DECISIONS.md); if the API rejects them, fall back to fetch_de_yield_grid
    and refit with src.curves.
    """
    frames = {}
    for name, code in DE_PARAM_KEYS.items():
        key = f"D.I.ZST.{code}.EUR.S1311.B.A604._Z.R.A.A._Z._Z.A"
        url = (f"https://api.statistiken.bundesbank.de/rest/data/BBSIS/{key}"
               f"?format=csv&lang=en&startPeriod={_start_date():%Y-%m-%d}")
        raw = pd.read_csv(io.StringIO(_get(url).text))
        frames[name] = _parse_bbk_csv(raw, value_name=name)
    out = frames["b0"]
    for name in ("b1", "b2", "b3", "t1", "t2"):
        out = out.merge(frames[name], on="date", how="inner")
    return out.sort_values("date").reset_index(drop=True)


def fetch_de_yield_grid() -> pd.DataFrame:
    """Fallback: Bundesbank fitted yields at annual maturities 1-15y (confirmed keys)."""
    rows = []
    for years in range(1, 16):
        key = f"D.I.ZAR.ZI.EUR.S1311.B.A604.R{years:02d}XX.R.A.A._Z._Z.A"
        url = (f"https://api.statistiken.bundesbank.de/rest/data/BBSIS/{key}"
               f"?format=csv&lang=en&startPeriod={_start_date():%Y-%m-%d}")
        raw = _parse_bbk_csv(pd.read_csv(io.StringIO(_get(url).text)), value_name="yield_pct")
        raw["tenor_yrs"] = float(years)
        rows.append(raw)
    return (pd.concat(rows)[["date", "tenor_yrs", "yield_pct"]]
            .sort_values(["date", "tenor_yrs"]).reset_index(drop=True))


def fetch_de_policy() -> pd.DataFrame:
    """ECB deposit facility rate via FRED's ECBDFR mirror (no key).

    The canonical source (ECB data portal, FM.D.U2.EUR.4F.KR.DFR.LEV) was
    returning 504s at build time — see DECISIONS.md.
    """
    return _fredgraph("ECBDFR")


def _parse_bbk_csv(raw: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """Bundesbank SDMX CSV -> [date, value] with non-numeric flag rows dropped."""
    date_col = next((c for c in raw.columns if c.upper().startswith(("TIME", "DATE"))),
                    raw.columns[0])  # Bundesbank CSV: unnamed first column, metadata rows
    value_col = next(c for c in raw.columns if c.upper().startswith(("OBS_VALUE", "VALUE", "BBSIS")))
    out = raw[[date_col, value_col]].copy()
    out.columns = ["date", value_name]
    out["date"] = pd.to_datetime(out["date"], format="%Y-%m-%d", errors="coerce")
    out[value_name] = pd.to_numeric(out[value_name], errors="coerce")
    return out.dropna().reset_index(drop=True)
