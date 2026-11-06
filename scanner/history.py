"""
Download years of free 5m gold history into data/hist/xauusd_m5.csv (timestamp ms UTC, o/h/l/c).

Sources, in order:
  1. Dukascopy raw datafeed (spot XAUUSD, 1m candles per day, .bi5 = LZMA-packed records)
  2. Binance public archive, PAXGUSDT 5m (tokenised gold, 1 PAXG = 1 troy oz, tracks spot)
The source used is written to data/hist/source.txt.
"""
from __future__ import annotations

import io
import lzma
import struct
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "hist"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) gold-desk/1.0"}


def duka_day(d: date) -> pd.DataFrame | None:
    # month is zero-based in the datafeed path
    url = f"https://datafeed.dukascopy.com/datafeed/XAUUSD/{d.year}/{d.month - 1:02d}/{d.day:02d}/BID_candles_min_1.bi5"
    r = requests.get(url, headers=UA, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    if not r.content:
        return None  # weekend / holiday
    raw = lzma.decompress(r.content)
    rows = [struct.unpack(">5if", raw[i:i + 24]) for i in range(0, len(raw) - 23, 24)]
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["t", "open", "close", "low", "high", "vol"])
    base = pd.Timestamp(d, tz="UTC")
    df.index = base + pd.to_timedelta(df["t"], unit="s")
    for k in ("open", "close", "low", "high"):
        df[k] = df[k] / 1000.0
    return df[["open", "high", "low", "close"]]


def dukascopy(start: date, end: date) -> pd.DataFrame:
    probe = date(2024, 3, 5)
    for k in range(3):  # raises if blocked
        try:
            duka_day(probe); break
        except Exception:  # noqa: BLE001
            if k == 2:
                raise
    days = [start + timedelta(n) for n in range((end - start).days + 1)]
    days = [d for d in days if d.weekday() != 5]
    out, failed = [], []

    def get(d):
        for _ in range(3):
            try:
                return duka_day(d)
            except Exception:  # noqa: BLE001
                pass
        failed.append(d)
        return None

    with ThreadPoolExecutor(8) as ex:
        for i, df in enumerate(ex.map(get, days)):
            if df is not None:
                out.append(df)
            if i % 100 == 0:
                print("dukascopy", days[i], flush=True)
    if len(failed) > len(days) * 0.05:
        raise RuntimeError(f"{len(failed)} days failed")
    m1 = pd.concat(out).sort_index()
    return m1.resample("5min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def binance(start: date, end: date) -> pd.DataFrame:
    frames = []
    m = date(start.year, start.month, 1)
    while m <= end:
        url = f"https://data.binance.vision/data/spot/monthly/klines/PAXGUSDT/5m/PAXGUSDT-5m-{m:%Y-%m}.zip"
        r = requests.get(url, headers=UA, timeout=60)
        if r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            df = pd.read_csv(z.open(z.namelist()[0]), header=None, usecols=range(5),
                             names=["t", "open", "high", "low", "close"])
            if str(df["t"].iloc[0]).isdigit() is False:
                df = df.iloc[1:]
            t = df["t"].astype("int64")
            unit = "us" if t.iloc[0] > 10**14 else "ms"
            df.index = pd.to_datetime(t, unit=unit, utc=True)
            frames.append(df[["open", "high", "low", "close"]].astype(float))
            print("binance", m, len(df), flush=True)
        else:
            print("binance missing", m, r.status_code)
        m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
    # current month: daily files
    d = date(end.year, end.month, 1)
    while d <= end:
        url = f"https://data.binance.vision/data/spot/daily/klines/PAXGUSDT/5m/PAXGUSDT-5m-{d:%Y-%m-%d}.zip"
        r = requests.get(url, headers=UA, timeout=60)
        if r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            df = pd.read_csv(z.open(z.namelist()[0]), header=None, usecols=range(5), names=["t", "open", "high", "low", "close"])
            t = df["t"].astype("int64")
            df.index = pd.to_datetime(t, unit="us" if t.iloc[0] > 10**14 else "ms", utc=True)
            frames.append(df[["open", "high", "low", "close"]].astype(float))
        d += timedelta(1)
    if not frames:
        raise RuntimeError("no binance data")
    df = pd.concat(frames).sort_index()
    return df[~df.index.duplicated()]


def main():
    start = date.fromisoformat(sys.argv[1] if len(sys.argv) > 1 else "2022-01-01")
    end = date.today() - timedelta(1)
    OUT.mkdir(parents=True, exist_ok=True)
    import os
    src, df = None, None
    if os.getenv("HIST_SOURCE", "binance") == "dukascopy":
        try:
            df, src = dukascopy(start, end), "dukascopy_spot"
        except Exception as e:  # noqa: BLE001
            print("dukascopy unavailable:", e)
    if df is None:
        df, src = binance(start, end), "binance_paxg"   # fast and reliable from GitHub
    ts = ((df.index - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta("1ms")).astype("int64")
    out = df.copy()
    out.insert(0, "timestamp", ts)
    out.to_csv(OUT / "xauusd_m5.csv", index=False)
    (OUT / "source.txt").write_text(src)
    print(f"saved {len(out):,} bars from {src}: {df.index[0]} -> {df.index[-1]}")


if __name__ == "__main__":
    main()
