"""Telegram message builders: price, market map (4H/1H/15m/5m), news, status, test trade."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd

from tjr import Context, KILLZONES, hourly_bias

UK = "Europe/London"


def uk(t) -> str:
    return pd.Timestamp(t).tz_convert(UK).strftime("%a %H:%M")


def esc(x) -> str:
    return html.escape(str(x))


def market_map(df: pd.DataFrame) -> dict:
    ctx = Context(df, "XAUUSD")
    i = len(ctx.df) - 1
    lv = {k: (None if np.isnan(v[i]) else round(float(v[i]), 2)) for k, v in ctx.lv.items()}
    b = {m: ctx.bias(m)[i] for m in ("structure4h", "structure", "htf")}
    b["15m"] = hourly_bias(ctx.df, "structure15m").values[i]
    last = ctx.df.iloc[-1]
    return dict(price=round(float(last["close"]), 2), time=ctx.df.index[-1], levels=lv, bias=b,
                atr5=round(float(ctx.atr[i]), 2))


def price_msg(m: dict, feed: str) -> str:
    return (f"💰 <b>XAUUSD {m['price']:,.2f}</b>\n"
            f"Last 5m close {uk(m['time'])} UK · {esc(feed)}\n"
            f"5m ATR ${m['atr5']:.2f}")


def map_msg(m: dict) -> str:
    L, p = m["levels"], m["price"]
    def row(name, key):
        v = L.get(key)
        if v is None:
            return f"{name}: —"
        d = v - p
        broken = (key.endswith("_L") or key == "PDL") and v > p or (key.endswith("_H") or key == "PDH") and v < p
        return f"{name}: <b>{v:,.2f}</b>  ({'+' if d >= 0 else ''}{d:,.2f}){' · taken' if broken else ''}"
    em = {"bull": "🟢 bullish", "bear": "🔴 bearish", "neutral": "⚪ neutral"}
    return ("🗺 <b>Market map</b> (price {:,.2f})\n".format(p) +
            "\n<b>4H</b>  bias " + em.get(m["bias"]["structure4h"], "?") + "\n" + row("Swing high", "H4_H") + "\n" + row("Swing low", "H4_L") +
            "\n\n<b>1H</b>  bias " + em.get(m["bias"]["structure"], "?") + "\n" + row("Swing high", "H1_H") + "\n" + row("Swing low", "H1_L") +
            "\n\n<b>Daily / sessions</b>\n" + row("Prev day high", "PDH") + "\n" + row("Prev day low", "PDL") + "\n" +
            row("Asia high", "Asia_H") + "\n" + row("Asia low", "Asia_L") + "\n" + row("London high", "London_H") + "\n" + row("London low", "London_L") +
            f"\n\n<b>15m</b> structure {em.get(m['bias']['15m'], '?')}\n"
            f"<b>Trade direction allowed:</b> {'BUYS only' if m['bias']['htf'] == 'bull' else 'SELLS only' if m['bias']['htf'] == 'bear' else 'none (4H and 1H disagree, stand aside)'}")


def news_msg(n: dict, now: pd.Timestamp) -> str:
    out = ["📰 <b>News check</b>"]
    if n.get("ok_calendar"):
        if n.get("blackout"):
            e = n["blackout"]
            out.append(f"⛔ <b>NEWS BLACKOUT</b>: {esc(e['title'])} at {uk(e['time'])} UK. No new trades ±30 min.")
        else:
            out.append("✅ No high-impact USD news in the next 30 min.")
        if n.get("next"):
            out.append("\n<b>Next red-folder USD events</b>")
            for e in n["next"]:
                fc = f" (f'cast {esc(e['forecast'])})" if e.get("forecast") else ""
                out.append(f"• {uk(e['time'])} UK — {esc(e['title'])}{fc}")
        else:
            out.append("No more high-impact USD events this week.")
    else:
        out.append("⚠️ Calendar feed unreachable this run (" + esc(n.get("calendar_error", "?"))[:80] + ")")
    r = n.get("risk", {})
    lvl = {"normal": "🟢 normal", "elevated": "🟠 elevated", "high": "🔴 HIGH", "unknown": "⚪ unknown"}.get(r.get("level"), "?")
    out.append(f"\n<b>Headline risk (wars, strikes, sanctions, shocks):</b> {lvl}")
    for t in r.get("examples", []):
        out.append(f"• {esc(t)[:140]}")
    for key, title in (("gold", "Gold"), ("fed", "Fed / dollar"), ("world", "World")):
        items = n.get("headlines", {}).get(key, [])[:2]
        if items:
            out.append(f"\n<b>{title}</b>")
            for it in items:
                out.append(f"• {esc(it['title'])[:140]}")
    return "\n".join(out)


def test_trade_msg(m: dict, account: float, fx: float, cost: float, stop_cap: float) -> str:
    p = m["price"]
    above = [v for k, v in m["levels"].items() if v and v > p]
    lvl = min(above) if above else p + 5
    entry = round(lvl - 1.0, 2)
    stop = round(lvl + 2.5, 2)
    risk = stop - entry
    tp = round(entry - 2 * risk, 2)
    risk_gbp = (risk + cost) / fx
    rew_gbp = (2 * risk - cost) / fx
    return ("🧪 <b>TEST — NOT A TRADE. DO NOT TAKE.</b>\nThis is exactly how a real call will look:\n\n"
            "<b>🔴 SELL XAUUSD</b>  (Gold)\n"
            f"LIMIT entry <b>{entry:,.2f}</b>  — ${entry - p:,.2f} above current price\n"
            f"Stop <b>{stop:,.2f}</b>  (${risk:.2f} risk)\n"
            f"Take profit <b>{tp:,.2f}</b>  (${2 * risk:.2f}, 2.0R)\n\n"
            f"<b>0.01 lots</b> · risk ≈ £{risk_gbp:.2f} ({risk_gbp / account * 100:.1f}% of £{account:.0f}) · profit ≈ £{rew_gbp:.2f}\n\n"
            "Why: 1H high swept → 15m rejection → 5m break of structure → FVG retrace. 4H + 1H bias bearish. NY killzone.\n"
            "News: ✅ clear · Headline risk 🟢 normal\n"
            "Signal 14:05 UK · limit valid until 14:35 UK\n"
            f"\nRules: one entry, one stop, one take profit. Stops wider than ${stop_cap:.2f} (2% of £{account:.0f}) are skipped.\n#test")


def status_msg(account, max_risk, stop_cap, params_label, last_scan, open_n, closed_stats, sched_ok=True) -> str:
    wr = closed_stats.get("win_rate")
    return ("✅ <b>Gold Desk status</b>\n"
            "• Scans XAUUSD <b>every 5 minutes</b>, Sunday 23:00 → Friday 22:00 UK (gold is shut at weekends)\n"
            "• Checks every scan: 4H + 1H structure & highs/lows, daily/Asia/London liquidity, 15m rejection, 5m break of structure + FVG entry\n"
            "• Calls trades only in killzones: London 07:00–10:00 UK, New York 13:30–16:00 UK\n"
            "• News: red-folder USD calendar (blocks new trades ±30 min) + live gold / Fed / war & world headlines on every scan\n"
            f"• Risk: 0.01 lots, max {max_risk:g}% of £{account:.0f} → stop must be ≤ ${stop_cap:.2f}, otherwise skipped\n"
            "• Expect 0–2 calls a day. Quiet days are normal: no A+ setup, no call.\n"
            "• Morning brief ~06:45 UK and New York brief ~13:15 UK, Mon–Fri\n"
            "• Commands: /price /levels /news /status\n"
            f"\nLast scan {uk(last_scan)} UK · open calls {open_n} · closed {closed_stats.get('trades', 0)}"
            + (f" · win rate {wr}%" if wr is not None else "") + f"\n<code>{esc(params_label)}</code>")
