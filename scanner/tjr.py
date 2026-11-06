"""
TJR model, made mechanical.

  1. Liquidity  : previous day high/low, Asia high/low, London high/low
  2. Killzone   : London 02:00-05:00 ET (gold/FX) and NY 08:30-11:00 ET (all)
  3. Sweep      : a 5m candle trades through a level and closes back inside it
  4. Shift      : within 12 bars, a 5m close breaks the last swing on the other side
                  (break of structure) with displacement
  5. Entry      : the fair value gap left by that displacement (50% of the gap)
                  or market on the confirmation close
  6. Stop       : beyond the sweep extreme (+ small ATR buffer)
  7. Target     : fixed R multiple, or the nearest opposite liquidity
  8. Bias       : 1H structure (HH/HL vs LH/LL) or 1H EMA50, optional

Everything uses only bars that were closed at the time (no look-ahead),
so the same code runs the backtest and the live scanner.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import time, timedelta

import numpy as np
import pandas as pd

ET = "America/New_York"

INSTRUMENTS = {
    # Gold only. cost = typical round-trip spread on a retail XAUUSD account, in $
    "XAUUSD": dict(yahoo="GC=F", name="Gold", kz=["london", "ny"], cost=0.30, dp=2),
}

KILLZONES = {
    "london": (time(2, 0), time(5, 0)),
    "ny": (time(8, 30), time(11, 0)),
}
FLAT_TIME = time(15, 55)
from collections import Counter
FUNNEL: Counter = Counter()  # anything still open is closed here (intraday only)


@dataclass
class Params:
    entry: str = "fvg"        # "fvg" (limit at 50% of the gap) | "market"
    target: str = "2R"        # "1R" | "1.5R" | "2R" | "3R" | "liq"
    bias: str = "structure"   # "structure" | "ema" | "none"
    confirm_bars: int = 12    # bars allowed between sweep and break of structure
    fill_bars: int = 6        # bars a limit order stays valid
    disp_atr: float = 0.8     # displacement candle body >= this x ATR
    stop_buf_atr: float = 0.10
    min_risk_atr: float = 0.30
    max_risk_atr: float = 4.0
    zones: str = "both"       # "both" | "ny" | "london"
    max_stop_usd: float | None = None   # skip setups whose stop+spread is wider than this ($ per 0.01 lot)

    def label(self) -> str:
        cap = f"${self.max_stop_usd:g}" if self.max_stop_usd else "none"
        return f"entry={self.entry} target={self.target} bias={self.bias} zones={self.zones} stopcap={cap}"


@dataclass
class Setup:
    id: str
    instrument: str
    side: str                 # BUY | SELL
    level_name: str           # which liquidity got swept
    level: float
    sweep_time: str
    confirm_time: str         # when the break of structure closed -> signal time
    entry: float
    stop: float
    target: float
    rr: float
    bias: str
    killzone: str
    valid_until: str
    # filled in by simulate()
    status: str = "pending"   # pending | open | win | loss | expired | flat
    fill_time: str | None = None
    exit_time: str | None = None
    exit_price: float | None = None
    r: float | None = None
    notes: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------- helpers

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n, min_periods=n).mean()


def trading_day(idx: pd.DatetimeIndex) -> np.ndarray:
    """CME-style day: starts 18:00 ET the evening before."""
    return (idx + timedelta(hours=6)).date


def confirmed_swings(df: pd.DataFrame, left: int = 2, right: int = 2):
    """Fractal swings. Returns arrays where value at bar i is the most recent swing
    high/low that is CONFIRMED by bar i (i.e. its right-hand bars have closed)."""
    h, l = df["high"].values, df["low"].values
    n = len(df)
    last_sh = np.full(n, np.nan)
    last_sl = np.full(n, np.nan)
    sh, sl = np.nan, np.nan
    for i in range(n):
        p = i - right
        if p - left >= 0:
            if h[p] == max(h[p - left:i + 1]) and h[p] > max(h[p - left:p].max(), h[p + 1:i + 1].max()):
                sh = h[p]
            if l[p] == min(l[p - left:i + 1]) and l[p] < min(l[p - left:p].min(), l[p + 1:i + 1].min()):
                sl = l[p]
        last_sh[i], last_sl[i] = sh, sl
    return last_sh, last_sl


def hourly_bias(df5: pd.DataFrame, mode: str) -> pd.Series:
    """Bias per 5m bar using only 1H candles that had closed."""
    if mode == "none":
        return pd.Series("neutral", index=df5.index)
    h1 = df5.resample("1h", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    if mode == "ema":
        ema = h1["close"].ewm(span=50, adjust=False).mean()
        b = np.where(h1["close"] > ema, "bull", "bear")
        out = pd.Series(b, index=h1.index)
    else:
        hs, ls = [], []
        vals = []
        h, l = h1["high"].values, h1["low"].values
        for i in range(len(h1)):
            p = i - 2
            if p >= 2:
                if h[p] > max(h[p - 2:p].max(), h[p + 1:i + 1].max()):
                    hs.append(h[p])
                if l[p] < min(l[p - 2:p].min(), l[p + 1:i + 1].min()):
                    ls.append(l[p])
            if len(hs) >= 2 and len(ls) >= 2:
                if hs[-1] > hs[-2] and ls[-1] > ls[-2]:
                    vals.append("bull")
                elif hs[-1] < hs[-2] and ls[-1] < ls[-2]:
                    vals.append("bear")
                else:
                    # mixed: follow the most recent break
                    vals.append("bull" if h1["close"].iloc[i] > hs[-1] else "bear" if h1["close"].iloc[i] < ls[-1] else "neutral")
            else:
                vals.append("neutral")
        out = pd.Series(vals, index=h1.index)
    # h1 index is the candle CLOSE time (label=right) -> forward fill onto 5m bars
    return out.reindex(df5.index, method="ffill").fillna("neutral")


def session_levels(df: pd.DataFrame) -> pd.DataFrame:
    """For every 5m bar: PDH/PDL, Asia H/L (20:00-00:00 ET), London H/L (02:00-05:00 ET),
    each only once that window has finished."""
    t = df.index.time
    day = trading_day(df.index)
    out = pd.DataFrame(index=df.index)
    out["day"] = day
    daily = df.groupby(day).agg(high=("high", "max"), low=("low", "min"))
    prev = daily.shift(1)
    out["PDH"] = [prev["high"].get(d, np.nan) for d in day]
    out["PDL"] = [prev["low"].get(d, np.nan) for d in day]

    def window(mask, name, ready_after):
        sub = df[mask]
        g = sub.groupby(trading_day(sub.index)).agg(high=("high", "max"), low=("low", "min"))
        hi = np.array([g["high"].get(d, np.nan) for d in day])
        lo = np.array([g["low"].get(d, np.nan) for d in day])
        ready = np.array([ready_after(x) for x in t])
        out[name + "_H"] = np.where(ready, hi, np.nan)
        out[name + "_L"] = np.where(ready, lo, np.nan)

    asia = np.array([(x >= time(20, 0)) for x in t])
    london = np.array([(time(2, 0) <= x < time(5, 0)) for x in t])
    window(asia, "Asia", lambda x: time(0, 0) <= x < time(18, 0))
    window(london, "London", lambda x: time(5, 0) <= x < time(18, 0))
    return out


def in_kz(ts, zones) -> str | None:
    tt = ts.time()
    for z in zones:
        a, b = KILLZONES[z]
        if a <= tt < b:
            return z
    return None


def _target(side, entry, risk, mode, lv_row, swing_opp):
    if mode.endswith("R"):
        m = float(mode[:-1])
        return entry + m * risk if side == "BUY" else entry - m * risk
    # liquidity: nearest opposite pool at >= 1.5R, else 2R
    cands = []
    keys = ["PDH", "Asia_H", "London_H"] if side == "BUY" else ["PDL", "Asia_L", "London_L"]
    for k in keys:
        v = lv_row.get(k)
        if v is not None and not np.isnan(v):
            cands.append(v)
    if swing_opp is not None and not np.isnan(swing_opp):
        cands.append(swing_opp)
    if side == "BUY":
        good = sorted(c for c in cands if c >= entry + 1.5 * risk)
        return good[0] if good else entry + 2 * risk
    good = sorted((c for c in cands if c <= entry - 1.5 * risk), reverse=True)
    return good[0] if good else entry - 2 * risk


# ---------------------------------------------------------------- detection

class Context:
    """Everything that doesn't depend on the settings, computed once per dataset."""
    def __init__(self, df: pd.DataFrame, inst: str):
        self.df = df.dropna(subset=["open", "high", "low", "close"]).copy()
        self.inst = inst
        self.atr = atr(self.df).values
        self.sh, self.sl = confirmed_swings(self.df)
        lv = session_levels(self.df)
        self.day = lv["day"].values
        self.lv = {k: lv[k].values for k in lv.columns if k != "day"}
        self.kz = np.array([in_kz(t, INSTRUMENTS[inst]["kz"]) for t in self.df.index], dtype=object)
        self._bias = {}

    def bias(self, mode):
        if mode not in self._bias:
            self._bias[mode] = hourly_bias(self.df, mode).values
        return self._bias[mode]


class _Row:
    def __init__(self, lv, i): self.lv, self.i = lv, i
    def __getitem__(self, k): return self.lv[k][self.i]
    def get(self, k, d=None): return self.lv[k][self.i] if k in self.lv else d
    def to_dict(self): return {k: v[self.i] for k, v in self.lv.items()}


def find_setups(df: pd.DataFrame, inst: str, p: Params, ctx: Context | None = None) -> list[Setup]:
    """df: 5m OHLC indexed by tz-aware ET timestamps, closed bars only."""
    cfg = INSTRUMENTS[inst]
    ctx = ctx or Context(df, inst)
    df = ctx.df
    if len(df) < 300:
        return []
    a, sh, sl = ctx.atr, ctx.sh, ctx.sl
    lv = ctx
    bias = ctx.bias(p.bias)
    o, h, l, c = (df[k].values for k in ("open", "high", "low", "close"))
    idx = df.index
    n = len(df)
    setups: list[Setup] = []
    used_session = set()       # (day, killzone) -> one trade per instrument per killzone
    swept_today = set()        # (day, level name)

    level_keys_hi = ["PDH", "Asia_H", "London_H"]
    level_keys_lo = ["PDL", "Asia_L", "London_L"]

    for i in range(30, n):
        if np.isnan(a[i]):
            continue
        day = ctx.day[i]
        kz = ctx.kz[i]
        if kz is not None and p.zones != "both" and kz != p.zones:
            kz = None
        row = _Row(ctx.lv, i)
        if kz is None:
            # outside the killzone a level that price closes through is spent
            for k in level_keys_hi:
                if not np.isnan(row[k]) and c[i] > row[k]:
                    swept_today.add((day, k))
            for k in level_keys_lo:
                if not np.isnan(row[k]) and c[i] < row[k]:
                    swept_today.add((day, k))
            continue
        if (day, kz) in used_session:
            continue
        events = []
        for k in level_keys_hi:
            L = row[k]
            if not np.isnan(L) and (day, k) not in swept_today and h[i] > L:
                events.append(("SELL", k, L))
        for k in level_keys_lo:
            L = row[k]
            if not np.isnan(L) and (day, k) not in swept_today and l[i] < L:
                events.append(("BUY", k, L))
        for side, k, L in events:
            swept_today.add((day, k))
            FUNNEL["sweeps"] += 1
            b = bias[i]
            if p.bias != "none" and ((side == "BUY" and b != "bull") or (side == "SELL" and b != "bear")):
                FUNNEL["bias_block"] += 1
                continue
            s = _confirm(i, side, k, L, df, a, sh, sl, o, h, l, c, idx, lv, p, inst, kz, b)
            if s:
                FUNNEL["setups"] += 1
                setups.append(s)
                used_session.add((day, kz))
                break
    return setups


def _confirm(i, side, k, L, df, a, sh, sl, o, h, l, c, idx, lv, p, inst, kz, b):
    n = len(df)
    # structure level to break: last confirmed swing on the other side at sweep time
    ref = sl[i] if side == "SELL" else sh[i]
    if np.isnan(ref):
        FUNNEL["no_swing"] += 1; return None
    extreme = h[i] if side == "SELL" else l[i]
    for j in range(i + 1, min(i + 1 + p.confirm_bars, n)):
        if side == "SELL":
            extreme = max(extreme, h[j])
            if c[j] > L + 0.5 * a[i]:             # sweep failed, price accepted above
                FUNNEL["accepted"] += 1; return None
            broke = c[j] < ref
        else:
            extreme = min(extreme, l[j])
            if c[j] < L - 0.5 * a[i]:
                FUNNEL["accepted"] += 1; return None
            broke = c[j] > ref
        if not broke:
            continue
        # fair value gap inside the displacement leg (sweep .. confirm)
        fvg = None
        for m in range(j, i + 1, -1):
            if side == "SELL" and l[m - 2] > h[m]:
                fvg = (h[m], l[m - 2]); break
            if side == "BUY" and h[m - 2] < l[m]:
                fvg = (h[m - 2], l[m]); break
        # displacement = a big-bodied break candle, or an FVG left in the leg (ICT definition)
        body = abs(c[j] - o[j])
        if body < p.disp_atr * a[j] and fvg is None:
            FUNNEL["no_displacement"] += 1; return None
        if p.entry == "fvg":
            if fvg is None:
                FUNNEL["no_fvg"] += 1; return None
            entry = (fvg[0] + fvg[1]) / 2
        else:
            entry = c[j]
        buf = p.stop_buf_atr * a[j]
        stop = extreme + buf if side == "SELL" else extreme - buf
        risk = (stop - entry) if side == "SELL" else (entry - stop)
        if risk <= 0 or risk < p.min_risk_atr * a[j] or risk > p.max_risk_atr * a[j]:
            FUNNEL["bad_risk"] += 1; return None
        if p.max_stop_usd and risk + INSTRUMENTS[inst]["cost"] > p.max_stop_usd:
            FUNNEL["stop_too_wide_for_account"] += 1; return None
        opp = sl[j] if side == "SELL" else sh[j]
        tgt = _target(side, entry, risk, p.target, _Row(lv.lv, j).to_dict(), opp)
        rr = abs(tgt - entry) / risk
        dp = INSTRUMENTS[inst]["dp"]
        valid = idx[j] + timedelta(minutes=5 * (p.fill_bars + 1))
        sid = f"{inst}-{idx[j].strftime('%Y%m%d-%H%M')}-{side}"
        return Setup(
            id=sid, instrument=inst, side=side, level_name=k, level=round(float(L), dp),
            sweep_time=idx[i].isoformat(), confirm_time=(idx[j] + timedelta(minutes=5)).isoformat(),
            entry=round(float(entry), dp), stop=round(float(stop), dp), target=round(float(tgt), dp),
            rr=round(float(rr), 2), bias=b, killzone=kz, valid_until=valid.isoformat(),
            status="pending" if p.entry == "fvg" else "open",
            fill_time=None if p.entry == "fvg" else (idx[j] + timedelta(minutes=5)).isoformat(),
        )
    FUNNEL["no_bos"] += 1
    return None


# ---------------------------------------------------------------- outcome

def simulate(s: Setup, df: pd.DataFrame, cost: float) -> Setup:
    """Walk bars after the signal. Same-bar stop+target counts as a LOSS (conservative).
    Costs (spread/commission) are taken off every filled trade."""
    after = df[df.index >= pd.Timestamp(s.confirm_time)]
    risk = abs(s.entry - s.stop)
    filled = s.status == "open"
    valid_until = pd.Timestamp(s.valid_until)
    for ts, bar in after.iterrows():
        end = ts + timedelta(minutes=5)
        if not filled:
            if ts >= valid_until:
                s.status = "expired"; s.exit_time = ts.isoformat(); return s
            # target traded before we got filled -> cancel
            if (s.side == "BUY" and bar.high >= s.target) or (s.side == "SELL" and bar.low <= s.target):
                s.status = "expired"; s.notes.append("ran to target without filling"); s.exit_time = ts.isoformat(); return s
            touched = bar.low <= s.entry if s.side == "BUY" else bar.high >= s.entry
            if not touched:
                continue
            filled = True; s.status = "open"; s.fill_time = ts.isoformat()
            # same bar: did it also hit the stop?
            hit_sl = bar.low <= s.stop if s.side == "BUY" else bar.high >= s.stop
            if hit_sl:
                return _close(s, "loss", s.stop, end, risk, cost)
            continue
        hit_sl = bar.low <= s.stop if s.side == "BUY" else bar.high >= s.stop
        hit_tp = bar.high >= s.target if s.side == "BUY" else bar.low <= s.target
        if hit_sl:
            return _close(s, "loss", s.stop, end, risk, cost)
        if hit_tp:
            return _close(s, "win", s.target, end, risk, cost)
        if ts.time() >= FLAT_TIME or ts.date() > pd.Timestamp(s.confirm_time).date():
            return _close(s, "flat", bar.close, end, risk, cost)
    return s  # still pending/open (live mode)


def _close(s, status, price, ts, risk, cost):
    pnl = (price - s.entry) if s.side == "BUY" else (s.entry - price)
    s.r = round((pnl - cost) / risk, 3)
    if status == "flat":
        status = "win" if s.r > 0 else "loss"
        s.notes.append("closed at end of day")
    s.status, s.exit_price, s.exit_time = status, round(float(price), 6), ts.isoformat()
    return s
