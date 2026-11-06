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


def gold_live() -> tuple[pd.DataFrame, str]:
    """Best free gold feed available right now. Returns (bars, feed name)."""
    import os
    errors = []
    key = os.getenv("TWELVEDATA_KEY")
    if key:
        try:
            return twelvedata(key), "spot XAU/USD (Twelve Data)"
        except Exception as e:  # noqa: BLE001
            errors.append(f"twelvedata: {e}")
    for sym, name in (("XAUUSD=X", "spot XAU/USD (Yahoo)"), ("GC=F", "COMEX gold futures (Yahoo)")):
        try:
            df = yahoo(sym, "5m", "5d")
            fresh = (pd.Timestamp.now(tz=ET) - df.index[-1]) < pd.Timedelta(minutes=40)
            if len(df) > 300 and fresh:
                return df, name
            errors.append(f"{sym}: {len(df)} bars, last {df.index[-1]}")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{sym}: {e}")
    # market closed / stale: return futures anyway so open trades can still be managed
    try:
        return yahoo("GC=F", "5m", "5d"), "COMEX gold futures (Yahoo, stale)"
    except Exception as e:  # noqa: BLE001
        errors.append(str(e))
    raise RuntimeError(" | ".join(errors))
