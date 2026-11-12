"""Free market data: Yahoo Finance chart API (no key). 5m bars go back 60 days."""
from __future__ import annotations

import time as _t

import pandas as pd
import requests

from tjr import ET

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) tjr-signal-desk/1.0"}


def yahoo(symbol: str, interval: str = "5m", rng: str = "60d", tries: int = 3) -> pd.DataFrame:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    last = None
    for k in range(tries):
        try:
            r = requests.get(url, params={"interval": interval, "range": rng, "includePrePost": "true"},
                             headers=UA, timeout=20)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            df = pd.DataFrame({k2: q[k2] for k2 in ("open", "high", "low", "close")},
                              index=pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert(ET))
            df = df.dropna()
            # Yahoo appends a live "current price" row with an odd timestamp: keep real bars only
            step_s = int(pd.Timedelta(interval.replace("m", "min")).total_seconds())
            secs = ((df.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1s")).astype("int64")
            df = df[secs % step_s == 0]
            df = df[~df.index.duplicated(keep="last")].sort_index()
            # drop the bar that is still forming
            step = pd.Timedelta(interval.replace("m", "min"))
            now = pd.Timestamp.now(tz=ET)
            df = df[df.index + step <= now]
            return df
        except Exception as e:  # noqa: BLE001
            last = e
            _t.sleep(2 * (k + 1))
    raise RuntimeError(f"Yahoo fetch failed for {symbol}: {last}")


def twelvedata(key: str, interval: str = "5min", size: int = 1500) -> pd.DataFrame:
    """Spot XAU/USD from Twelve Data (free key: 800 calls/day). Optional upgrade."""
    r = requests.get("https://api.twelvedata.com/time_series",
                     params=dict(symbol="XAU/USD", interval=interval, outputsize=size, timezone="UTC",
                                 apikey=key, order="ASC"), timeout=20)
    r.raise_for_status()
    j = r.json()
    if j.get("status") != "ok":
        raise RuntimeError(j.get("message", "twelvedata error"))
    df = pd.DataFrame(j["values"])
    df.index = pd.DatetimeIndex(pd.to_datetime(df["datetime"], utc=True)).tz_convert(ET)
    df = df[["open", "high", "low", "close"]].astype(float)
    now = pd.Timestamp.now(tz=ET)
    return df[df.index + pd.Timedelta(minutes=5) <= now]


def binance_paxg(interval: str = "5m", limit: int = 6000) -> pd.DataFrame:
    """Real-time tokenised gold (1 PAXG = 1 oz) from Binance's public market-data API. No key, no delay.
    Pages back in 1,000-candle chunks: the strategies need ~200 thirty-minute candles of warm-up (6,000 x 5m = ~3 weeks)."""
    rows, end = [], None
    while len(rows) < limit:
        params = dict(symbol="PAXGUSDT", interval=interval, limit=1000)
        if end is not None:
            params["endTime"] = end
        r = requests.get("https://data-api.binance.vision/api/v3/klines", params=params, headers=UA, timeout=15)
        r.raise_for_status()
        k = r.json()
        if not k:
            break
        rows = k + rows
        end = k[0][0] - 1
        if len(k) < 1000:
            break
    df = pd.DataFrame([[x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4]), x[6]] for x in rows],
                      columns=["t", "open", "high", "low", "close", "close_t"]).drop_duplicates("t").sort_values("t")
    df.index = pd.DatetimeIndex(pd.to_datetime(df["t"], unit="ms", utc=True)).tz_convert(ET)
    now_ms = pd.Timestamp.now(tz="UTC").value // 10**6
    df = df[df["close_t"] < now_ms]          # closed candles only
    return df[["open", "high", "low", "close"]]


def spot_gold() -> float | None:
    """Live spot XAU/USD (what MT5 brokers quote), free, no key."""
    for url, path in (("https://api.gold-api.com/price/XAU", ("price",)),
                      ("https://data-asg.goldprice.org/dbXRates/USD", ("items", 0, "xauPrice"))):
        try:
            j = requests.get(url, headers=UA, timeout=10).json()
            for k in path:
                j = j[k]
            v = float(j)
            if 500 < v < 20000:
                return v
        except Exception:  # noqa: BLE001
            continue
    return None


def _anchor(df: pd.DataFrame, spot: float | None) -> tuple[pd.DataFrame, float]:
    """Shift candles so the last price equals live spot (removes PAXG premium / futures basis)."""
    if spot is None or df.empty:
        return df, 0.0
    off = spot - float(df["close"].iloc[-1])
    if abs(off) > 60:
        return df, 0.0
    return df + off, off


def gold_live() -> tuple[pd.DataFrame, str]:
    """Best free real-time gold feed. Returns (closed 5m candles in spot-gold terms, feed name)."""
    import os
    errors = []
    key = os.getenv("TWELVEDATA_KEY")
    if key:
        try:
            return twelvedata(key), "spot XAU/USD (Twelve Data, real-time)"
        except Exception as e:  # noqa: BLE001
            errors.append(f"twelvedata: {e}")
    spot = spot_gold()
    try:
        df = binance_paxg("5m", 6000)
        fresh = (pd.Timestamp.now(tz=ET) - df.index[-1]) < pd.Timedelta(minutes=15)
        if len(df) > 300 and fresh:
            df, off = _anchor(df, spot)
            return df, f"real-time gold (PAXG, matched to spot {'%+.2f' % off})"
        errors.append(f"paxg stale: last {df.index[-1]}")
    except Exception as e:  # noqa: BLE001
        errors.append(f"paxg: {e}")
    try:
        df = yahoo("GC=F", "5m", "5d")
        df, off = _anchor(df, spot)
        return df, f"COMEX futures (Yahoo, ~10-15 min delayed, matched to spot {'%+.2f' % off})"
    except Exception as e:  # noqa: BLE001
        errors.append(str(e))
    raise RuntimeError(" | ".join(errors))
