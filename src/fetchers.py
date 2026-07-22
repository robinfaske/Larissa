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
import re
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
HISTORY_YEARS = 6  # 5y z-score window + 6m-ago curve comparison
STD_GRID = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0]

MX_SERIES = {  # Banxico SIE, secondary/auction yields. Bonos IDs: verify on first refresh.
    28 / 365: "SF43936", 91 / 365: "SF43939", 182 / 365: "SF43942", 364 / 365: "SF43945",
    3.0: "SF44070", 5.0: "SF44071", 10.0: "SF44072", 20.0: "SF44073", 30.0: "SF44074",
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
            rows.append((pd.to_datetime(obs["fecha"], dayfirst=True), tenor, float(obs["dato"])))
    frame = pd.DataFrame(rows, columns=["date", "tenor_yrs", "yield_pct"])
    cetes = frame["tenor_yrs"] < 1.5
    for tenor in frame.loc[cetes, "tenor_yrs"].unique():
        mask = frame["tenor_yrs"] == tenor
        frame.loc[mask, "yield_pct"] = simple_360_to_effective(
            frame.loc[mask, "yield_pct"], days=round(tenor * 365))
    frame.loc[~cetes, "yield_pct"] = semiannual_to_effective(frame.loc[~cetes, "yield_pct"])
    return frame.sort_values(["date", "tenor_yrs"]).reset_index(drop=True)


def fetch_mx_policy() -> pd.DataFrame:
    """Banxico overnight target rate (SIE series SF61745)."""
    token = os.environ.get("BANXICO_TOKEN")
    if not token:
        raise RuntimeError("BANXICO_TOKEN not set (see .env.example)")
    url = (f"https://www.banxico.org.mx/SieAPIRest/service/v1/series/SF61745/datos/"
           f"{_start_date():%Y-%m-%d}/{date.today():%Y-%m-%d}")
    datos = _get(url, headers={"Bmx-Token": token}).json()["bmx"]["series"][0]["datos"]
    return pd.DataFrame(
        [(pd.to_datetime(o["fecha"], dayfirst=True), float(o["dato"]))
         for o in datos if o["dato"] not in ("N/E", "")],
        columns=["date", "rate_pct"])


# --- Brazil: ANBIMA ETTJ params + BCB SGS policy ----------------------------

def fetch_br_params() -> pd.DataFrame:
    """Daily ANBIMA Svensson parameters for the prefixado curve.

    One POST per business day; incremental — days already cached are not
    re-requested. ANBIMA rates are effective annual on a 252-business-day
    basis (DECISIONS.md), so parameters are used as published.
    """
    cached = None
    if (CACHE_DIR / "br_params.csv").exists():
        cached = load("br_params")
    have = set(cached["date"].dt.date) if cached is not None else set()
    days = pd.bdate_range(_start_date(), date.today())
    rows = []
    for day in days:
        if day.date() in have:
            continue
        resp = requests.post(
            "https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp",
            data={"Idioma": "PT", "Dt_Ref": f"{day:%d/%m/%Y}", "saida": "txt"},
            timeout=30)
        resp.raise_for_status()
        text = resp.text
        time.sleep(0.15)  # politeness: ~1.5k sequential requests on first run
        params = _parse_anbima_prefixado(text)
        if params is not None:  # holidays return an empty document
            rows.append((day, *params))
        if len(rows) % 100 == 0 and rows:  # checkpoint: first run is ~1.5k requests
            _combine_br(cached, rows).to_csv(CACHE_DIR / "br_params.csv", index=False)
    return _combine_br(cached, rows)


def _combine_br(cached: pd.DataFrame | None, rows: list[tuple]) -> pd.DataFrame:
    fresh = pd.DataFrame(rows, columns=["date", "b0", "b1", "b2", "b3", "t1", "t2"])
    out = pd.concat([cached, fresh]) if cached is not None else fresh
    return out.sort_values("date").reset_index(drop=True)


def _parse_anbima_prefixado(text: str) -> tuple[float, ...] | None:
    """Extract (b0..b3, t1, t2) from the PREFIXADOS block of ANBIMA's txt download."""
    block = re.search(r"PREFIXADOS(.*?)(?:IPCA|$)", text, flags=re.S | re.I)
    if not block:
        return None
    # decimal commas AND scientific notation, e.g. -7,28447805013511E-03
    nums = re.findall(r"-?\d+[.,]\d+(?:E[+-]?\d+)?", block.group(1))
    if len(nums) < 6:
        return None
    b1, b2, b3, b4, l1, l2 = (float(n.replace(",", ".")) for n in nums[:6])
    # ANBIMA quotes betas in decimals (0.1458 = 14.58%) and lambdas as decay
    # rates; convert to our percent basis and tau = 1/lambda.
    return 100 * b1, 100 * b2, 100 * b3, 100 * b4, 1.0 / l1, 1.0 / l2


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


def fetch_us_policy() -> pd.DataFrame:
    """Fed funds target upper bound via FRED's public fredgraph CSV (no key)."""
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU"
    raw = pd.read_csv(io.StringIO(_get(url).text)).rename(
        columns={"DATE": "date", "observation_date": "date", "DFEDTARU": "rate_pct"})
    raw["date"] = pd.to_datetime(raw["date"])
    raw["rate_pct"] = pd.to_numeric(raw["rate_pct"], errors="coerce")
    raw = raw.dropna()
    return raw[raw["date"] >= pd.Timestamp(_start_date())].reset_index(drop=True)


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
    """ECB deposit facility rate via the ECB data portal SDMX CSV (no key)."""
    url = ("https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
           f"?format=csvdata&startPeriod={_start_date():%Y-%m-%d}")
    raw = pd.read_csv(io.StringIO(_get(url).text))
    return _parse_bbk_csv(raw, value_name="rate_pct")


def _parse_bbk_csv(raw: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """Bundesbank SDMX CSV -> [date, value] with non-numeric flag rows dropped."""
    date_col = next((c for c in raw.columns if c.upper().startswith(("TIME", "DATE"))),
                    raw.columns[0])  # Bundesbank CSV: unnamed first column, metadata rows
    value_col = next(c for c in raw.columns if c.upper().startswith(("OBS_VALUE", "VALUE", "BBSIS")))
    out = raw[[date_col, value_col]].copy()
    out.columns = ["date", value_name]
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out[value_name] = pd.to_numeric(out[value_name], errors="coerce")
    return out.dropna().reset_index(drop=True)
