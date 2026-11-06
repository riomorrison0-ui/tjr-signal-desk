"""
Andrea Unger's published gold systems (Unger Academy, 2025-2026), made mechanical, plus TJR as a benchmark.

Unger only publishes the logic, not his exact parameters, so each system is tested over a small,
sensible grid and judged out-of-sample. Every entry is "market on the close of the signal candle",
which is exactly what a Telegram alert lets you do by hand.

  pdbreak   Breakout of the previous day's high/low, fixed $ stop and target, held up to N days
  compress  Same breakout, only after daily AND weekly volatility compression, 15m closes, out by session end
  channel   5m price-channel breakout (highest high / lowest low of N candles) with trend + candle filters
  cci       CCI(20) on 1H beyond +/-300 = ride the explosive move, out when CCI returns to 0 (backtest only)

All entries are restricted to UK waking hours (07:00-20:00 UK) because signals are taken by hand.
"""
from __future__ import annotations

from datetime import time, timedelta

import numpy as np
import pandas as pd

from tjr import ET, INSTRUMENTS, Context, Params, Setup, find_setups as tjr_find

UK = "Europe/London"
COST = INSTRUMENTS["XAUUSD"]["cost"]


def _uk_ok(ts: pd.Timestamp, start=7, end=20) -> bool:
    h = ts.tz_convert(UK).hour
    return start <= h < end


def _daily(ctx: Context) -> pd.DataFrame:
    if not hasattr(ctx, "_daily"):
        d = ctx.df.groupby(ctx.day).agg(open=("open", "first"), high=("high", "max"),
                                        low=("low", "min"), close=("close", "last"))
        d["range"] = d["high"] - d["low"]
        d["atr20"] = d["range"].rolling(20).mean().shift(1)          # known before the day starts
        d["prev_range"] = d["range"].shift(1)
        hi5 = d["high"].rolling(5).max(); lo5 = d["low"].rolling(5).min()
        d["wk_range"] = (hi5 - lo5).shift(1)                         # last 5 sessions' range
        d["wk_avg"] = (hi5 - lo5).rolling(20).mean().shift(1)
        d["pdh"], d["pdl"] = d["high"].shift(1), d["low"].shift(1)
        ctx._daily = d
    return ctx._daily


def _mk(ctx, i, side, entry, stop, target, name, why, hold_until=None, extra="") -> Setup:
    idx = ctx.df.index
    t = idx[i] + timedelta(minutes=5)       # signal = candle close
    risk = abs(entry - stop)
    return Setup(id=f"XAUUSD-{name}-{idx[i]:%Y%m%d-%H%M}-{side}", instrument="XAUUSD", side=side,
                 level_name=name, level=round(float(entry), 2), sweep_time=t.isoformat(), confirm_time=t.isoformat(),
                 entry=round(float(entry), 2), stop=round(float(stop), 2), target=round(float(target), 2),
                 rr=round(abs(target - entry) / risk, 2), bias="", killzone=extra, valid_until=t.isoformat(),
                 status="open", fill_time=t.isoformat(), strategy=name, entry_type="market",
                 hold_until=hold_until.isoformat() if hold_until is not None else None, why=why)


def _bracket(side, entry, sl, tp_mult):
    stop = entry - sl if side == "BUY" else entry + sl
    tgt = entry + sl * tp_mult if side == "BUY" else entry - sl * tp_mult
    return stop, tgt


# ------------------------------------------------------------------ Unger 1: previous-day breakout
def pdbreak(ctx: Context, sl_usd=12.0, tp_mult=2.0, hold_days=3, window_end_uk=17, cap=None) -> list[Setup]:
    if cap and sl_usd + COST > cap:
        return []
    d = _daily(ctx)
    c, idx, day = ctx.df["close"].values, ctx.df.index, ctx.day
    out, done = [], set()
    for i in range(1, len(c)):
        dy = day[i]
        if dy in done or not _uk_ok(idx[i], 7, window_end_uk):
            continue
        pdh, pdl = d.at[dy, "pdh"], d.at[dy, "pdl"]
        if np.isnan(pdh):
            continue
        side = "BUY" if c[i] > pdh and c[i - 1] <= pdh else "SELL" if c[i] < pdl and c[i - 1] >= pdl else None
        if not side:
            continue
        stop, tgt = _bracket(side, c[i], sl_usd, tp_mult)
        why = f"5m close {'above previous-day high' if side == 'BUY' else 'below previous-day low'} {pdh if side == 'BUY' else pdl:,.2f}"
        out.append(_mk(ctx, i, side, c[i], stop, tgt, "pdbreak", why, idx[i] + timedelta(days=hold_days)))
        done.add(dy)
    return out


# ------------------------------------------------------------------ Unger 2: compression breakout (15m)
def compress(ctx: Context, sl_usd=10.0, tp_mult=2.0, squeeze=0.8, cap=None) -> list[Setup]:
    if cap and sl_usd + COST > cap:
        return []
    d = _daily(ctx)
    df = ctx.df
    m15 = df.resample("15min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    day15 = (m15.index + timedelta(hours=6)).date
    pos = df.index.get_indexer(m15.index + timedelta(minutes=10))   # last 5m bar inside each 15m candle
    out, done = [], set()
    c15 = m15["close"].values
    for q in range(1, len(m15)):
        dy = day15[q]
        if dy in done or dy not in d.index or pos[q] < 0 or not _uk_ok(m15.index[q] + timedelta(minutes=15), 7, 20):
            continue
        r = d.loc[dy]
        if np.isnan(r["atr20"]) or np.isnan(r["wk_avg"]):
            continue
        if not (r["prev_range"] < squeeze * r["atr20"] and r["wk_range"] < squeeze * r["wk_avg"]):
            continue
        side = "BUY" if c15[q] > r["pdh"] and c15[q - 1] <= r["pdh"] else "SELL" if c15[q] < r["pdl"] and c15[q - 1] >= r["pdl"] else None
        if not side:
            continue
        i = pos[q]
        stop, tgt = _bracket(side, c15[q], sl_usd, tp_mult)
        close_t = pd.Timestamp.combine(pd.Timestamp(dy).date(), time(16, 50)).tz_localize(ET)
        why = (f"daily + weekly volatility squeeze, then 15m close {'above' if side == 'BUY' else 'below'} "
               f"previous-day {'high' if side == 'BUY' else 'low'}")
        out.append(_mk(ctx, i, side, c15[q], stop, tgt, "compress", why, close_t))
        done.add(dy)
    return out


# ------------------------------------------------------------------ Unger 3: 5m channel breakout
def channel(ctx: Context, n=96, sl_atr=2.0, tp_mult=2.0, max_per_day=2, cap=None) -> list[Setup]:
    df = ctx.df
    h, l, c, o = (df[k].values for k in ("high", "low", "close", "open"))
    hh = pd.Series(h).rolling(n).max().shift(1).values
    ll = pd.Series(l).rolling(n).min().shift(1).values
    trend = ctx.bias("ema")                    # 1H EMA50 side, closed candles only
    a, idx, day = ctx.atr, df.index, ctx.day
    out, per_day, busy_until = [], {}, None
    for i in range(n + 1, len(c)):
        if busy_until is not None and idx[i] < busy_until:
            continue
        if np.isnan(hh[i]) or np.isnan(a[i]) or not _uk_ok(idx[i], 7, 20):
            continue
        if per_day.get(day[i], 0) >= max_per_day:
            continue
        side = None
        if c[i] > hh[i] and trend[i] == "bull" and (c[i] - o[i]) > 0.5 * a[i]:
            side = "BUY"
        elif c[i] < ll[i] and trend[i] == "bear" and (o[i] - c[i]) > 0.5 * a[i]:
            side = "SELL"
        if not side:
            continue
        sl = sl_atr * a[i]
        if cap and sl + COST > cap:
            continue
        stop, tgt = _bracket(side, c[i], sl, tp_mult)
        why = f"5m close through the {n * 5 // 60}h price channel {'high' if side == 'BUY' else 'low'}, with the 1H trend, strong candle"
        s = _mk(ctx, i, side, c[i], stop, tgt, "channel", why, None)
        out.append(s)
        per_day[day[i]] = per_day.get(day[i], 0) + 1
        busy_until = idx[i] + timedelta(hours=2)   # one idea at a time
    return out


# ------------------------------------------------------------------ Unger 4: CCI +/-300 (backtest only)
def cci(ctx: Context, level=300, sl_usd=15.0, tp_mult=None, tf="1h", sl_atr=None, cap=None) -> list[Setup]:
    if cap and sl_usd + COST > cap and not sl_atr:
        return []
    h1 = ctx.df.resample(tf, label="right", closed="left").agg(
        {"high": "max", "low": "min", "close": "last"}).dropna()
    tp = (h1["high"] + h1["low"] + h1["close"]) / 3
    ma = tp.rolling(20).mean()
    md = tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    cc = ((tp - ma) / (0.015 * md)).values
    out = []
    t1 = h1.index
    i5 = ctx.df.index.get_indexer(t1 - timedelta(minutes=5))
    k = 21
    while k < len(cc):
        side = "BUY" if cc[k] > level and cc[k - 1] <= level else "SELL" if cc[k] < -level and cc[k - 1] >= -level else None
        if not side or i5[k] < 0 or not _uk_ok(t1[k], 7, 20):
            k += 1; continue
        e = k + 1
        while e < len(cc) and ((side == "BUY" and cc[e] > 0) or (side == "SELL" and cc[e] < 0)):
            e += 1
        # momentum exit = first 1H close where CCI is back through 0. Not happened yet (live) -> open-ended.
        exit_t = t1[e] if e < len(cc) else t1[k] + timedelta(days=30)
        entry = h1["close"].values[k]
        sl = sl_usd
        if sl_atr:
            sl = sl_atr * _atr_s(h1).iat[k]
            if cap and sl + COST > cap:
                k = e; continue
        stop, tgt = _bracket(side, entry, sl, tp_mult or 50)
        why = (f"{tf.upper()} CCI(20) broke {'above +' if side == 'BUY' else 'below -'}{level}: explosive momentum, ride it")
        out.append(_mk(ctx, i5[k], side, entry, stop, tgt, "cci", why, exit_t))
        k = e
    return out


def tjr(ctx: Context, cap=None, **kw) -> list[Setup]:
    p = Params(**kw); p.max_stop_usd = cap
    return tjr_find(ctx.df, "XAUUSD", p, ctx)


STRATEGIES = dict(pdbreak=pdbreak, compress=compress, channel=channel, cci=cci, tjr=tjr)

GRIDS = dict(
    pdbreak=[dict(sl_usd=s, tp_mult=t, hold_days=h, window_end_uk=w)
             for s in (5, 8, 12, 20) for t in (1.5, 2.0, 3.0) for h in (1, 3) for w in (12, 17)],
    compress=[dict(sl_usd=s, tp_mult=t, squeeze=q) for s in (5, 8, 12, 20) for t in (1.5, 2.0, 3.0) for q in (0.7, 0.9)],
    channel=[dict(n=n, sl_atr=a, tp_mult=t) for n in (48, 96, 192) for a in (1.0, 2.0) for t in (1.5, 2.0, 3.0)],
    cci=[dict(level=lv, sl_usd=s, tp_mult=t) for lv in (250, 300, 350) for s in (8, 12, 15, 20, 25) for t in (None, 1.5, 2.0, 3.0)],
    tjr=[dict(entry=e, target=t, bias=b, m15=m, accept_atr=1.5, confirm_bars=24, zones="both")
         for e in ("fvg", "market") for t in ("1.5R", "2R") for b in ("htf", "none") for m in (True, False)],
)


# ================================================================== DAILY SESSION STRATEGIES
# Independent tests (2026): most daily gold setups lose after costs. These three published ones held up:
#   london   London range breakout (MQL5 blog, Oct 2026: 715 trades, ~49% win, PF 1.38, DD 17%)
#   orb      15-minute opening-range breakout, target 3R (Aurum: 2,003 trades, PF 1.77, walk-forward)
#   ibretr   Initial Balance retracement (Trade That Swing: ~70% win rate)

def _uk(ctx):
    if not hasattr(ctx, "_ukt"):
        u = ctx.df.index.tz_convert(UK)
        ctx._ukt = (np.array(u.hour * 60 + u.minute), np.array(u.date))
    return ctx._ukt


def _day_slices(ctx):
    """start/end positions of each UK calendar day."""
    if not hasattr(ctx, "_ukdays"):
        mins, dates = _uk(ctx)
        cuts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1], True])
        ctx._ukdays = [(cuts[k], cuts[k + 1]) for k in range(len(cuts) - 1)]
    return ctx._ukdays


def _at(ctx, i, hhmm):
    """Timestamp of the same UK day at hh:mm."""
    t = ctx.df.index[i].tz_convert(UK)
    return pd.Timestamp.combine(t.date(), time(hhmm // 100, hhmm % 100)).tz_localize(UK).tz_convert(ET)


def london(ctx: Context, stop="range", tp_mult=1.0, lo=0.5, hi=1.5, end_uk=1100, cap=None) -> list[Setup]:
    """Asian range 00:00-07:00 UK. First 5m close outside it between 07:00 and end_uk -> trade the break.
    Stop: opposite side of the range ('range') or the range midpoint ('mid'). Out by 16:00 UK."""
    df = ctx.df
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    mins, _ = _uk(ctx)
    out, widths = [], []
    for a, b in _day_slices(ctx):
        m = mins[a:b]
        asia = np.flatnonzero(m < 7 * 60)
        if len(asia) < 60:
            continue
        rh, rl = h[a + asia].max(), l[a + asia].min()
        w = rh - rl
        avg = np.mean(widths[-20:]) if len(widths) >= 10 else None
        widths.append(w)
        if avg is None or not (lo * avg <= w <= hi * avg):
            continue
        end = end_uk // 100 * 60 + end_uk % 100
        for q in range(a, b):
            if not (7 * 60 <= mins[q] < end):
                continue
            side = "BUY" if c[q] > rh else "SELL" if c[q] < rl else None
            if not side:
                continue
            e = c[q]
            st = (rl if side == "BUY" else rh) if stop == "range" else (rl + rh) / 2
            risk = abs(e - st)
            if risk <= 0 or (cap and risk + COST > cap):
                break
            tgt = e + tp_mult * risk if side == "BUY" else e - tp_mult * risk
            why = f"London broke the Asian range ({rl:,.2f}–{rh:,.2f}, ${w:.0f} wide) to the {'upside' if side == 'BUY' else 'downside'}"
            out.append(_mk(ctx, q, side, e, st, tgt, "london", why, _at(ctx, q, 1600)))
            break
    return out


def orb(ctx: Context, open_uk=1430, minutes=15, stop="range", tp_mult=3.0, cap=None) -> list[Setup]:
    """Opening range of the first `minutes` after open_uk (14:30 UK = NY stock open, 13:30 = US data).
    First 5m close outside it within 2h -> trade the break. Out by 20:00 UK."""
    df = ctx.df
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    mins, _ = _uk(ctx)
    o = open_uk // 100 * 60 + open_uk % 100
    out = []
    for a, b in _day_slices(ctx):
        m = mins[a:b]
        rng = np.flatnonzero((m >= o) & (m < o + minutes))
        if len(rng) < minutes // 5:
            continue
        rh, rl = h[a + rng].max(), l[a + rng].min()
        for q in range(a + rng[-1] + 1, b):
            if mins[q] >= o + 120:
                break
            side = "BUY" if c[q] > rh else "SELL" if c[q] < rl else None
            if not side:
                continue
            e = c[q]
            st = (rl if side == "BUY" else rh) if stop == "range" else (rl + rh) / 2
            risk = abs(e - st)
            if risk <= 0 or (cap and risk + COST > cap):
                break
            tgt = e + tp_mult * risk if side == "BUY" else e - tp_mult * risk
            why = f"5m close {'above' if side == 'BUY' else 'below'} the {minutes}-min opening range ({rl:,.2f}–{rh:,.2f}) from {open_uk // 100:02d}:{open_uk % 100:02d} UK"
            out.append(_mk(ctx, q, side, e, st, tgt, "orb", why, _at(ctx, q, 2000)))
            break
    return out


def ibretr(ctx: Context, open_uk=1430, entry_in=0.25, tgt_out=0.5, stop_in=0.6, cap=None) -> list[Setup]:
    """Initial Balance = first hour after open_uk. After a 5m close beyond it, LIMIT entry entry_in x IB back
    inside, target tgt_out x IB beyond the IB edge, stop stop_in x IB inside. Out by 20:00 UK."""
    df = ctx.df
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    mins, _ = _uk(ctx)
    o = open_uk // 100 * 60 + open_uk % 100
    out = []
    for a, b in _day_slices(ctx):
        m = mins[a:b]
        ib = np.flatnonzero((m >= o) & (m < o + 60))
        if len(ib) < 10:
            continue
        hi_, lo_ = h[a + ib].max(), l[a + ib].min()
        w = hi_ - lo_
        if w <= 0:
            continue
        for q in range(a + ib[-1] + 1, b):
            if mins[q] >= o + 240:
                break
            side = "BUY" if c[q] > hi_ else "SELL" if c[q] < lo_ else None
            if not side:
                continue
            if side == "BUY":
                e, st, tgt = hi_ - entry_in * w, hi_ - stop_in * w, hi_ + tgt_out * w
            else:
                e, st, tgt = lo_ + entry_in * w, lo_ + stop_in * w, lo_ - tgt_out * w
            risk = abs(e - st)
            if cap and risk + COST > cap:
                break
            s = _mk(ctx, q, side, e, st, tgt, "ibretr",
                    f"New York broke its first-hour range ({lo_:,.2f}–{hi_:,.2f}); buying the pullback into it" if side == "BUY"
                    else f"New York broke its first-hour range ({lo_:,.2f}–{hi_:,.2f}); selling the pullback into it",
                    _at(ctx, q, 2000))
            s.entry_type, s.status, s.fill_time = "limit", "pending", None
            s.valid_until = _at(ctx, q, 1900).isoformat()
            out.append(s)
            break
    return out


STRATEGIES.update(london=london, orb=orb, ibretr=ibretr)
GRIDS.update(
    london=[dict(stop=s, tp_mult=t, lo=lo, hi=hi, end_uk=e) for s in ("range", "mid") for t in (0.75, 1.0, 1.5, 2.0)
            for lo, hi in ((0.5, 1.5), (0.0, 9.0)) for e in (1100, 1300)],
    orb=[dict(open_uk=o, minutes=mn, stop=s, tp_mult=t) for o in (1330, 1430, 800) for mn in (15, 30)
         for s in ("range", "mid") for t in (1.0, 2.0, 3.0)],
    ibretr=[dict(open_uk=o, entry_in=e, tgt_out=g, stop_in=s) for o in (1430, 800) for e in (0.1, 0.25)
            for g in (0.3, 0.5) for s in (0.6, 1.0)],
)


# ================================================================== MORE DAILY FAMILIES
def _bars(ctx, rule):
    k = "_bars_" + rule
    if not hasattr(ctx, k):
        b = ctx.df.resample(rule, label="right", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        # position of the last 5m bar inside each higher-tf candle (signal = its close)
        pos = ctx.df.index.get_indexer(b.index - timedelta(minutes=5))
        b = b[pos >= 0]; pos = pos[pos >= 0]
        setattr(ctx, k, (b, pos))
    return getattr(ctx, k)


def _atr_s(b, n=14):
    pc = b["close"].shift()
    tr = pd.concat([b["high"] - b["low"], (b["high"] - pc).abs(), (b["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _adx(b, n=14):
    up, dn = b["high"].diff(), -b["low"].diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = _atr_s(b, 1)
    atr_ = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=b.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    ndi = 100 * pd.Series(ndm, index=b.index).ewm(alpha=1 / n, adjust=False).mean() / atr_
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi)
    return dx.ewm(alpha=1 / n, adjust=False).mean(), pdi, ndi


def _rsi(x, n):
    d = x.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    ls = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + g / ls)


def _uk_ok_t(t, a=7, b=20):
    h = t.tz_convert(UK).hour
    return a <= h < b


def holygrail(ctx: Context, tf="15min", adx_min=30, sl_atr=1.5, tp_mult=1.5, cap=None) -> list[Setup]:
    """Raschke/Connors Holy Grail: ADX(14) > adx_min and rising, price pulls back to the 20 EMA,
    enter on the close that turns back with the trend. Stop sl_atr x ATR, target tp_mult x stop. Out by 20:00 UK."""
    b, pos = _bars(ctx, tf)
    adx, pdi, ndi = _adx(b)
    ema = b["close"].ewm(span=20, adjust=False).mean()
    at = _atr_s(b)
    o, h, l, c = (b[k].values for k in ("open", "high", "low", "close"))
    out, last_day = [], None
    for k in range(40, len(b)):
        t = b.index[k]
        if not _uk_ok_t(t) or np.isnan(adx.iat[k]) or adx.iat[k] < adx_min or adx.iat[k] < adx.iat[k - 3]:
            continue
        d = t.tz_convert(UK).date()
        if d == last_day:
            continue
        up = pdi.iat[k] > ndi.iat[k]
        touched = (l[k - 1] <= ema.iat[k - 1]) if up else (h[k - 1] >= ema.iat[k - 1])
        resume = (c[k] > h[k - 1] and c[k] > ema.iat[k]) if up else (c[k] < l[k - 1] and c[k] < ema.iat[k])
        if not (touched and resume):
            continue
        sl = sl_atr * at.iat[k]
        if cap and sl + COST > cap:
            continue
        side = "BUY" if up else "SELL"
        stop, tgt = _bracket(side, c[k], sl, tp_mult)
        close_t = pd.Timestamp.combine(d, time(20, 0)).tz_localize(UK).tz_convert(ET)
        out.append(_mk(ctx, pos[k], side, c[k], stop, tgt, "holygrail",
                       f"Strong {tf} trend (ADX {adx.iat[k]:.0f}) pulled back to the 20 EMA and turned back {'up' if up else 'down'}", close_t))
        last_day = d
    return out


def rsi2(ctx: Context, tf="1h", lo=10, hi=90, sl_atr=2.0, tp_mult=None, cap=None) -> list[Setup]:
    """Connors RSI(2): in an uptrend (close > 200 EMA) buy when RSI(2) < lo; in a downtrend sell when RSI(2) > hi.
    Exit when price closes back through the 5-period average (or at tp_mult x stop if set). Stop sl_atr x ATR."""
    b, pos = _bars(ctx, tf)
    c = b["close"]
    r2, e200, s5, at = _rsi(c, 2), c.ewm(span=200, adjust=False).mean(), c.rolling(5).mean(), _atr_s(b)
    out, k = [], 201
    cv = c.values
    while k < len(b):
        t = b.index[k]
        side = None
        if cv[k] > e200.iat[k] and r2.iat[k] < lo:
            side = "BUY"
        elif cv[k] < e200.iat[k] and r2.iat[k] > hi:
            side = "SELL"
        if not side or not _uk_ok_t(t):
            k += 1; continue
        sl = sl_atr * at.iat[k]
        if cap and sl + COST > cap:
            k += 1; continue
        e = k + 1
        while e < len(b) and ((side == "BUY" and cv[e] <= s5.iat[e]) or (side == "SELL" and cv[e] >= s5.iat[e])):
            e += 1
        exit_t = b.index[e] if e < len(b) else t + timedelta(days=10)
        stop, tgt = _bracket(side, cv[k], sl, tp_mult or 50)
        out.append(_mk(ctx, pos[k], side, cv[k], stop, tgt, "rsi2",
                       f"Sharp {'dip' if side == 'BUY' else 'rally'} (RSI(2) {r2.iat[k]:.0f}) against the {tf} trend: fade it back to the 5-bar average", exit_t))
        k = e
    return out


def bbfade(ctx: Context, tf="15min", dev=2.0, adx_max=20, sl_atr=1.5, cap=None) -> list[Setup]:
    """Quiet-market fade: ADX(14) < adx_max, a candle closes back inside the Bollinger band after poking outside
    -> trade back to the middle band (20 SMA). Stop sl_atr x ATR beyond. Out by 20:00 UK."""
    b, pos = _bars(ctx, tf)
    c, h, l = b["close"], b["high"].values, b["low"].values
    mid, sd = c.rolling(20).mean(), c.rolling(20).std()
    upb, lob = mid + dev * sd, mid - dev * sd
    adx, _, _ = _adx(b)
    at = _atr_s(b)
    cv = c.values
    out, busy = [], None
    for k in range(40, len(b)):
        t = b.index[k]
        if busy is not None and t < busy:
            continue
        if not _uk_ok_t(t) or np.isnan(adx.iat[k]) or adx.iat[k] > adx_max:
            continue
        side = None
        if h[k - 1] > upb.iat[k - 1] and cv[k] < upb.iat[k]:
            side = "SELL"
        elif l[k - 1] < lob.iat[k - 1] and cv[k] > lob.iat[k]:
            side = "BUY"
        if not side:
            continue
        ext = max(h[k - 1], h[k]) if side == "SELL" else min(l[k - 1], l[k])
        stop = ext + sl_atr * at.iat[k] if side == "SELL" else ext - sl_atr * at.iat[k]
        risk = abs(cv[k] - stop)
        tgt = mid.iat[k]
        if risk <= 0 or (cap and risk + COST > cap) or (side == "SELL" and tgt >= cv[k]) or (side == "BUY" and tgt <= cv[k]):
            continue
        d = t.tz_convert(UK).date()
        close_t = pd.Timestamp.combine(d, time(20, 0)).tz_localize(UK).tz_convert(ET)
        out.append(_mk(ctx, pos[k], side, cv[k], stop, tgt, "bbfade",
                       f"Quiet market (ADX {adx.iat[k]:.0f}); price rejected the {'upper' if side == 'SELL' else 'lower'} Bollinger band, target the middle", close_t))
        busy = t + timedelta(hours=2)
    return out


def session(ctx: Context, enter_uk=1300, exit_uk=2000, side="SELL", sl_usd=15.0, cap=None) -> list[Setup]:
    """Time-of-day drift: every weekday take `side` at enter_uk, close at exit_uk. Fixed $ stop."""
    if cap and sl_usd + COST > cap:
        return []
    mins, dates = _uk(ctx)
    c = ctx.df["close"].values
    em = enter_uk // 100 * 60 + enter_uk % 100
    out = []
    for a, b2 in _day_slices(ctx):
        hit = np.flatnonzero(mins[a:b2] == em - 5)
        if not len(hit):
            continue
        q = a + hit[0]
        stop, tgt = _bracket(side, c[q], sl_usd, 50)
        out.append(_mk(ctx, q, side, c[q], stop, tgt, "session",
                       f"Gold's time-of-day drift: {side.lower()} {enter_uk // 100:02d}:{enter_uk % 100:02d} → {exit_uk // 100:02d}:{exit_uk % 100:02d} UK",
                       _at(ctx, q, exit_uk)))
    return out


STRATEGIES.update(holygrail=holygrail, rsi2=rsi2, bbfade=bbfade, session=session)
GRIDS.update(
    holygrail=[dict(tf=tf, adx_min=a, sl_atr=s, tp_mult=t) for tf in ("15min", "30min", "1h") for a in (25, 30)
               for s in (1.0, 1.5) for t in (1.0, 1.5, 2.0)],
    rsi2=[dict(tf=tf, lo=lo, hi=100 - lo, sl_atr=s, tp_mult=t) for tf in ("30min", "1h") for lo in (5, 10, 20)
          for s in (1.5, 2.5) for t in (None, 1.0)],
    bbfade=[dict(tf=tf, dev=d, adx_max=a, sl_atr=s) for tf in ("15min", "30min") for d in (2.0, 2.5)
            for a in (20, 25) for s in (0.5, 1.0)],
    session=[dict(enter_uk=e, exit_uk=x, side=sd, sl_usd=sl) for e, x in ((700, 1200), (800, 1330), (1300, 1600),
             (1330, 2000), (1500, 2000), (1600, 2100)) for sd in ("BUY", "SELL") for sl in (10, 20)],
)


def imom(ctx: Context, from_uk=800, to_uk=1330, thresh_atr=1.0, hold_to_uk=1700, sl_atr=1.0, tp_mult=None, cap=None) -> list[Setup]:
    """Intraday momentum: if gold moved more than thresh_atr x daily ATR between from_uk and to_uk,
    trade the same direction at to_uk, out at hold_to_uk (or TP). Stop sl_atr x 1H ATR."""
    d = _daily(ctx)
    mins, dates = _uk(ctx)
    c = ctx.df["close"].values
    b1, _ = _bars(ctx, "1h")
    a1 = _atr_s(b1)
    f = from_uk // 100 * 60 + from_uk % 100
    t = to_uk // 100 * 60 + to_uk % 100
    out = []
    for a, b2 in _day_slices(ctx):
        m = mins[a:b2]
        i0 = np.flatnonzero(m == f - 5); i1 = np.flatnonzero(m == t - 5)
        if not len(i0) or not len(i1):
            continue
        q0, q1 = a + i0[0], a + i1[0]
        dy = ctx.day[q1]
        if dy not in d.index or np.isnan(d.at[dy, "atr20"]):
            continue
        move = c[q1] - c[q0]
        if abs(move) < thresh_atr * d.at[dy, "atr20"] * 0.25:
            continue
        side = "BUY" if move > 0 else "SELL"
        k = b1.index.searchsorted(ctx.df.index[q1])
        sl = sl_atr * a1.iat[max(0, k - 1)]
        if np.isnan(sl) or (cap and sl + COST > cap):
            continue
        stop, tgt = _bracket(side, c[q1], sl, tp_mult or 50)
        out.append(_mk(ctx, q1, side, c[q1], stop, tgt, "imom",
                       f"Strong London move ({move:+.0f} $ since {from_uk // 100:02d}:00 UK): ride it into New York", _at(ctx, q1, hold_to_uk)))
    return out


def nr7(ctx: Context, sl_mult=0.5, tp_mult=1.5, cap=None) -> list[Setup]:
    """Raschke NR7: yesterday was the narrowest range of the last 7 days -> trade today's first 5m close beyond
    yesterday's high/low (07:00-17:00 UK). Stop sl_mult x yesterday's range. Out by 20:00 UK."""
    d = _daily(ctx)
    nr = d["range"].rolling(7).apply(lambda x: float(x[-1] == x.min()), raw=True).shift(1)
    c = ctx.df["close"].values
    mins, _ = _uk(ctx)
    out, done = [], set()
    for i in range(1, len(c)):
        dy = ctx.day[i]
        if dy in done or dy not in d.index or nr.get(dy, 0) != 1 or not (7 * 60 <= mins[i] < 17 * 60):
            continue
        pdh, pdl, pr = d.at[dy, "pdh"], d.at[dy, "pdl"], d.at[dy, "prev_range"]
        side = "BUY" if c[i] > pdh and c[i - 1] <= pdh else "SELL" if c[i] < pdl and c[i - 1] >= pdl else None
        if not side:
            continue
        sl = sl_mult * pr
        if cap and sl + COST > cap:
            done.add(dy); continue
        stop, tgt = _bracket(side, c[i], sl, tp_mult)
        out.append(_mk(ctx, i, side, c[i], stop, tgt, "nr7", f"Yesterday was the quietest day in 7 (NR7); breakout {'up' if side == 'BUY' else 'down'}",
                       _at(ctx, i, 2000)))
        done.add(dy)
    return out


STRATEGIES.update(imom=imom, nr7=nr7)
GRIDS.update(
    cci_fast=[dict(tf=tf, level=lv, sl_usd=0, sl_atr=sa, tp_mult=t) for tf in ("15min", "30min") for lv in (200, 250, 300)
              for sa in (1.0, 2.0) for t in (None, 1.5, 2.0)],
    imom=[dict(from_uk=f, to_uk=t, thresh_atr=th, hold_to_uk=hz, sl_atr=sa, tp_mult=tp) for f, t in ((700, 1300), (800, 1330))
          for th in (0.5, 1.0, 1.5) for hz in (1700, 2000) for sa in (1.0, 2.0) for tp in (None, 1.5)],
    nr7=[dict(sl_mult=s, tp_mult=t) for s in (0.3, 0.5, 1.0) for t in (1.0, 1.5, 2.0)],
)
STRATEGIES["cci_fast"] = cci
