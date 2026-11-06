"""
Gold Desk live engine (GitHub Actions).

LOOP mode (default on Actions): one job runs for ~5h45m. It wakes ~20s after every 5-minute candle
closes, scans, manages open calls, answers Telegram commands every minute, then hands over to a fresh
job by dispatching itself. A cron every 30 min restarts the chain if it ever breaks. Nobody has to prompt it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time as _time
from datetime import timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(__file__))
from tjr import ET, INSTRUMENTS, Context, Setup, simulate  # noqa: E402
from strategies import STRATEGIES  # noqa: E402
from data import gold_live, spot_gold  # noqa: E402
import news as newsmod  # noqa: E402
import briefs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state.json"
FEED = ROOT / "docs" / "signals.json"
CONFIG = ROOT / "config.json"
UK = "Europe/London"

LOT = 0.01
LOT_OZ = 1.0               # 0.01 lot XAUUSD = 1 oz -> $1 per $1 move
STRATEGY_NAMES = {
    "pdbreak": "Unger previous-day breakout",
    "compress": "Unger compression breakout",
    "channel": "Unger 5m channel breakout",
    "cci": "Unger CCI momentum",
    "tjr": "TJR liquidity sweep",
    "rsi2": "Connors RSI(2) pullback",
}


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


_CHAT = {}


def read_updates(state) -> list[str]:
    """Learn the chat from whoever pressed Start, and collect commands (/price, /levels, /news, /status)."""
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    if os.getenv("TELEGRAM_CHAT_ID"):
        state["tg_chat"] = os.getenv("TELEGRAM_CHAT_ID")
    cmds = []
    if not tok:
        return cmds
    try:
        resp = requests.get(f"https://api.telegram.org/bot{tok.strip()}/getUpdates",
                            params={"offset": state.get("tg_offset", 0), "timeout": 0}, timeout=15).json()
        ups = resp.get("result", [])
        print("telegram getUpdates ok=", resp.get("ok"), "updates=", len(ups), resp.get("description", ""))
        for u in ups:
            state["tg_offset"] = u["update_id"] + 1
            m = u.get("message") or {}
            cid = (m.get("chat") or {}).get("id")
            if cid and not state.get("tg_chat"):
                state["tg_chat"] = str(cid)
            txt = (m.get("text") or "").strip().lower()
            if cid and str(cid) == state.get("tg_chat") and txt.startswith("/"):
                parts = txt.split()
                cmds.append(" ".join([parts[0].split("@")[0]] + parts[1:2]))
    except Exception as e:  # noqa: BLE001
        print("getUpdates failed", e)
    return cmds


def tg(text: str):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), _CHAT.get("id")
    print("TG>", text.replace("\n", " | "))
    if not tok or not chat:
        return
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok.strip()}/sendMessage",
                      json={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                      timeout=15)
        if not r.ok:
            print("telegram send failed", r.status_code, r.text[:200])
    except Exception as e:  # noqa: BLE001
        print("telegram failed", e)


def fmt(x, dp):
    return f"{x:,.{dp}f}"


def unit(inst, d):
    if inst in ("EURUSD", "GBPUSD"):
        return f"{d * 10000:.1f} pips"
    if inst == "XAUUSD":
        return f"${d:.2f}"
    return f"{d:.1f} pts"


def entry_zone(s: dict) -> tuple[float, float]:
    w = max(1.0, round(0.05 * abs(s["entry"] - s["stop"]), 0))
    return s["entry"] - w, s["entry"] + w


def signal_msg(s: dict, last: float) -> str:
    cfg = INSTRUMENTS["XAUUSD"]
    buy = s["side"] == "BUY"
    lots = s.get("lots", LOT)
    fx = s.get("gbpusd", 1.30)
    risk = abs(s["entry"] - s["stop"])
    rew = abs(s["target"] - s["entry"])
    risk_gbp = (risk + cfg["cost"]) * lots * CONTRACT_OZ / fx
    rew_gbp = (rew - cfg["cost"]) * lots * CONTRACT_OZ / fx
    bal = s.get("account_gbp", 2000)
    lo, hi = entry_zone(s)
    t = pd.Timestamp(s["confirm_time"]).tz_convert(UK).strftime("%H:%M")
    if s.get("strategy") == "rsi2":
        manage = "If price snaps back to its 5-bar average before TP, I'll message you CLOSE NOW (take the profit)."
    elif s.get("strategy") == "cci":
        manage = "If momentum dies before stop or TP, I'll message you CLOSE NOW."
    else:
        manage = "Closed by end of day if neither is hit."
    head = "🟢🟢 <b>BUY XAUUSD NOW</b> 🟢🟢" if buy else "🔴🔴 <b>SELL XAUUSD NOW</b> 🔴🔴"
    return (
        f"{head}\n\n"
        f"📍 <b>ENTER BETWEEN {lo:,.2f} – {hi:,.2f}</b>\n"
        f"<i>(signal price {s['entry']:,.2f} · don't chase outside this range)</i>\n\n"
        f"🎯 <b>SET YOUR TAKE PROFIT TO {s['target']:,.2f}</b>  (+${rew:.2f} · ≈ +£{rew_gbp:,.2f})\n"
        f"🛑 <b>SET YOUR STOP LOSS TO {s['stop']:,.2f}</b>  (−${risk:.2f} · ≈ −£{risk_gbp:,.2f})\n\n"
        f"📦 <b>LOT SIZE: {lots:.2f}</b>  ({risk_gbp / bal * 100:.1f}% of £{bal:,.2f}; max 2%)\n\n"
        f"<b>Why:</b> {s.get('why') or s['level_name']}\n"
        f"<b>Strategy:</b> {STRATEGY_NAMES.get(s.get('strategy'), s.get('strategy'))} · {rew / risk:.1f}R\n"
        + news_line(s) +
        f"Signal {t} UK (candle close). {manage}\n#paper"
    )


def news_line(s: dict) -> str:
    n = s.get("news") or {}
    risk = {"normal": "🟢 normal", "elevated": "🟠 elevated", "high": "🔴 HIGH — be careful"}.get(n.get("risk"), "⚪ unknown")
    nxt = n.get("next")
    nx = f" · next red folder: {nxt['title']} {pd.Timestamp(nxt['time']).tz_convert('Europe/London'):%a %H:%M} UK" if nxt else ""
    return f"News: ✅ no red folder within 30 min{nx}\nHeadline risk: {risk}\n"


def update_msg(s: dict) -> str:
    dp = INSTRUMENTS[s["instrument"]]["dp"]
    head = f"{s['side']} XAUUSD @ {fmt(s['entry'], dp)}"
    notes = " ".join(s.get("notes", []))
    if s["status"] == "open":
        return f"✅ FILLED — {head}. Stop {fmt(s['stop'], dp)}, take profit {fmt(s['target'], dp)}."
    if s["status"] in ("win", "loss"):
        g = pnl_gbp(s)
        money = f"{'+' if g >= 0 else '-'}£{abs(g):,.2f} on {s.get('lots', LOT):.2f} lots, {'+' if s['r'] > 0 else ''}{s['r']}R"
        if "closed at" in notes:
            why = ("momentum faded" if s.get("strategy") == "cci" else "back at its 5-bar average, job done" if s.get("strategy") == "rsi2"
                   else "end of day" if "end of day" in notes else "time limit")
            return f"🚪 <b>CLOSE NOW</b> — {head}. Exit at market ({why}). Last price {fmt(s['exit_price'], dp)}  ({money})"
        if s["status"] == "win":
            return f"💰 TAKE PROFIT HIT — {head} → {fmt(s['exit_price'], dp)}  ({money})"
        return f"❌ STOPPED — {head} → {fmt(s['exit_price'], dp)}  ({money})"
    if s["status"] == "expired":
        return f"⌛ CANCELLED — {head} never filled. Delete the limit order."
    return head


CONTRACT_OZ = 100      # CoMarkets standard XAUUSD: 1.00 lot = 100 oz, so 0.01 lot = 1 oz = $1 per $1 move
LOT_STEP, LOT_MIN = 0.01, 0.01


def lot_size(balance_gbp, risk_pct, stop_usd, fx, cost):
    """Largest lot (in 0.01 steps) whose stop loss costs no more than risk_pct of the balance. Never rounds up."""
    risk_usd = balance_gbp * risk_pct / 100 * fx
    per_lot = (stop_usd + cost) * CONTRACT_OZ
    lots = int(risk_usd / per_lot / LOT_STEP + 1e-9) * LOT_STEP
    return round(lots, 2) if lots >= LOT_MIN else 0.0


def pnl_gbp(c) -> float:
    cost = INSTRUMENTS[c["instrument"]]["cost"]
    move = (c["exit_price"] - c["entry"]) if c["side"] == "BUY" else (c["entry"] - c["exit_price"])
    return (move - cost) * c.get("lots", LOT) * CONTRACT_OZ / c.get("gbpusd", 1.30)


def stats(closed, start, adjust=None):
    rs = [c["r"] for c in closed]
    wins = [r for r in rs if r > 0]
    bal, curve = start, []
    adj = sorted(adjust or [], key=lambda a: a["t"])
    for c in closed:
        while adj and adj[0]["t"] <= c["exit_time"]:
            bal = adj.pop(0)["balance"]
        c["pnl_gbp"] = round(pnl_gbp(c), 2)
        bal += c["pnl_gbp"]
        curve.append(dict(t=c["exit_time"], balance=round(bal, 2)))
    for a in adj:
        bal = a["balance"]
    return dict(trades=len(rs), wins=len(wins), win_rate=round(100 * len(wins) / len(rs), 1) if rs else None,
                total_r=round(sum(rs), 2), avg_r=round(sum(rs) / len(rs), 3) if rs else None,
                balance=round(bal, 2), start_balance=start, curve=curve)


def gbpusd() -> float:
    try:
        from data import yahoo
        return float(yahoo("GBPUSD=X", "5m", "1d")["close"].iloc[-1])
    except Exception:  # noqa: BLE001
        return 1.30


PIP = 0.10   # gold pip on MT5 (XAUUSD): $0.10 move = 1 pip


def _pips(d):
    if d.get("exit_price") is None:
        return 0.0
    move = (d["exit_price"] - d["entry"]) if d["side"] == "BUY" else (d["entry"] - d["exit_price"])
    return move / PIP


def rsi2_diag(df, cfg, day):
    """Why were there no calls? Look at today's 30m candles (07:00-20:00 UK) the way the strategy does."""
    import strategies as S
    p = cfg.get("strategy_params", {})
    try:
        ctx = Context(df, "XAUUSD")
        b, _ = S._bars(ctx, p.get("tf", "30min"))
        c = b["close"]; r2 = S._rsi(c, 2); e200 = c.ewm(span=200, adjust=False).mean()
        uk = b.index.tz_convert(UK)
        m = (uk.date == day) & (uk.hour >= 7) & (uk.hour < 20)
        if not m.any():
            return "No 30-minute candles in the trading window today."
        up = (c > e200)[m]
        trend = "up" if up.mean() > 0.66 else "down" if up.mean() < 0.34 else "mixed (flipping above/below the 200 EMA)"
        lo_up = r2[m][up].min() if up.any() else None
        hi_dn = r2[m][~up].max() if (~up).any() else None
        parts = [f"30m trend was <b>{trend}</b>."]
        if lo_up is not None:
            parts.append(f"In the uptrend the deepest dip was RSI(2) {lo_up:.0f} (needs below {p.get('lo', 20)}).")
        if hi_dn is not None:
            parts.append(f"In the downtrend the strongest rally was RSI(2) {hi_dn:.0f} (needs above {p.get('hi', 80)}).")
        if (lo_up is not None and lo_up < p.get("lo", 20)) or (hi_dn is not None and hi_dn > p.get("hi", 80)):
            parts.append("The trigger was touched, but the setup was filtered out (red-folder news window, or a stop wider than 2% allows), "
                         "or it came while a trade was already open.")
        return " ".join(parts)
    except Exception as e:  # noqa: BLE001
        return f"(diagnostics unavailable: {e})"


def daily_summary(state, cfg, df, now, account, max_risk_pct):
    ukd = now.tz_convert(UK).date()
    sig = list(state["signals"].values())
    def uk_day(t):
        return pd.Timestamp(t).tz_convert(UK).date() if t else None
    called = [d for d in sig if uk_day(d["confirm_time"]) == ukd and d["status"] != "skipped" and not str(d.get("id", "")).startswith("demo")]
    closed_today = [d for d in sig if d["status"] in ("win", "loss") and uk_day(d.get("exit_time")) == ukd]
    skipped = [d for d in sig if uk_day(d["confirm_time"]) == ukd and d["status"] == "skipped"]
    still_open = [d for d in sig if d["status"] in ("open", "pending")]
    done_all = sorted([d for d in sig if d["status"] in ("win", "loss")], key=lambda x: x["exit_time"])
    st = stats(done_all, account, state.get("balance_adjust"))
    bal = st["balance"]

    def kind(d):
        n = " ".join(d.get("notes", []))
        if "closed at" in n:
            return "close"
        return "tp" if d["status"] == "win" else "sl"
    tp = [d for d in closed_today if kind(d) == "tp"]
    sl = [d for d in closed_today if kind(d) == "sl"]
    cl = [d for d in closed_today if kind(d) == "close"]
    pips = [_pips(d) for d in closed_today]
    gained = sum(x for x in pips if x > 0); lost = -sum(x for x in pips if x < 0)
    gbp = sum(pnl_gbp(d) for d in closed_today)

    def period(start):
        ds = [d for d in done_all if pd.Timestamp(d["exit_time"]).tz_convert(UK).date() >= start]
        return sum(pnl_gbp(d) for d in ds), sum(_pips(d) for d in ds), len(ds)
    wk = period(ukd - timedelta(days=ukd.weekday()))
    mo = period(ukd.replace(day=1))

    L = [f"🌙 <b>DAILY WRAP — {pd.Timestamp(ukd):%A %d %b}</b>", ""]
    if not called and not closed_today:
        L += ["📭 <b>No trades today.</b>", "<b>Why:</b> " + rsi2_diag(df, cfg, ukd),
              "No A+ setup = no trade. Sitting out is part of the strategy."]
        if skipped:
            L.append(f"⏭ {len(skipped)} setup(s) skipped: " + "; ".join(" ".join(d.get('notes', [])) for d in skipped))
    else:
        L += [f"📊 <b>Calls today: {len(called)}</b>  ·  closed today: {len(closed_today)}", ""]
        for d in sorted(closed_today, key=lambda x: x["exit_time"]):
            k = kind(d); pp = _pips(d); g = pnl_gbp(d)
            tag = {"tp": "💰 TP HIT", "sl": "❌ SL HIT", "close": "🚪 CLOSED EARLY"}[k]
            L.append(f"{tag} · {d['side']} @ {d['entry']:,.2f} → {d['exit_price']:,.2f} · {d.get('lots', LOT):.2f} lots · "
                     f"{pp:+.0f} pips · {'+' if g >= 0 else '-'}£{abs(g):,.2f}")
        for d in still_open:
            L.append(f"⏳ STILL OPEN · {d['side']} @ {d['entry']:,.2f} · TP {d['target']:,.2f} · SL {d['stop']:,.2f} · {d.get('lots', LOT):.2f} lots")
        for d in skipped:
            L.append(f"⏭ SKIPPED · {d['side']} · {' '.join(d.get('notes', []))}")
        L += ["",
              f"✅ Take profits hit: <b>{len(tp)}</b>   ❌ Stop losses hit: <b>{len(sl)}</b>   🚪 Closed early: <b>{len(cl)}</b>",
              f"📈 Pips gained: <b>+{gained:,.0f}</b>   📉 Pips lost: <b>−{lost:,.0f}</b>",
              f"🧮 <b>Net: {gained - lost:+,.0f} pips · {'+' if gbp >= 0 else '-'}£{abs(gbp):,.2f}</b>"]
        if (gained - lost) * gbp < 0:
            L.append("<i>Pips and £ point different ways because each trade's lot size is set by its stop (2% risk): "
                     "tight-stop trades use bigger lots, wide-stop trades smaller ones.</i>")
        L.append("")
        good, bad = [], []
        if tp:
            good.append(f"{len(tp)} trade(s) ran all the way to target: the dip/rally snapped back as the strategy expects.")
        if cl:
            w = [d for d in cl if pnl_gbp(d) > 0]
            if w:
                good.append(f"{len(w)} early exit(s) banked profit when price returned to its average.")
            if len(w) < len(cl):
                bad.append(f"{len(cl) - len(w)} early exit(s) closed slightly red: price reverted without making progress.")
        if sl:
            bad.append(f"{len(sl)} stop(s) hit: the move kept going instead of snapping back (trend push or news).")
        if not good and not bad:
            good.append("No trades closed yet today.")
        L += ["<b>What went well:</b> " + (" ".join(good) or "Nothing closed in profit today."),
              "<b>What went wrong:</b> " + (" ".join(bad) or "Nothing. No losing trades today.")]
    L += ["",
          f"💷 <b>Balance: £{bal:,.2f}</b>  ({'+' if bal >= account else ''}{(bal / account - 1) * 100:.1f}% since start) · next trade risks 2% = £{bal * max_risk_pct / 100:,.2f}",
          f"📅 Week: {'+' if wk[0] >= 0 else '-'}£{abs(wk[0]):,.2f} ({wk[1]:+,.0f} pips, {wk[2]} trades) · "
          f"Month: {'+' if mo[0] >= 0 else '-'}£{abs(mo[0]):,.2f} ({mo[1]:+,.0f} pips, {mo[2]} trades)",
          f"<i>Strategy unchanged: {STRATEGY_NAMES.get(cfg.get('strategy'), cfg.get('strategy'))}, 2% risk, same rules every scan. 1 pip = $0.10.</i>"]
    return "\n".join(L)


def folder_msg(nws: dict, now: pd.Timestamp) -> str:
    ev = nws.get("today", [])
    ukd = now.tz_convert(UK)
    if not nws.get("ok_calendar"):
        return "📁 <b>News folders today</b>\n⚠️ Calendar feed unreachable — check ForexFactory manually."
    icon = {"High": "🔴", "Medium": "🟠", "Low": "🟡", "Holiday": "⚪"}
    lines = [f"📁 <b>News folders — {ukd:%A %d %b}</b> (USD, UK times)"]
    if not ev:
        lines.append("No USD events today. Clean day for gold.")
    for e in ev:
        t = pd.Timestamp(e["time"]).tz_convert(UK)
        extra = " · ".join(x for x in (f"forecast {e['forecast']}" if e.get("forecast") else "",
                                        f"prev {e['previous']}" if e.get("previous") else "") if x)
        lines.append(f"{icon.get(e['impact'], '•')} {t:%H:%M} {briefs.esc(e['title'])}" + (f"  <i>{briefs.esc(extra)}</i>" if extra else ""))
    reds = [e for e in ev if e["impact"] == "High"]
    if reds:
        lines.append("\n⛔ No new trades from 30 min before to 30 min after each 🔴.")
    lines.append("🔴 high · 🟠 medium · 🟡 low impact")
    return "\n".join(lines)


def strategy_setups(ctx, cfg, cap):
    name = cfg.get("strategy", "tjr")
    params = dict(cfg.get("strategy_params", cfg.get("params", {})))
    return STRATEGIES[name](ctx, cap=cap, **params)


def scan_once(state, cfg, mode="scan"):
    """One full pass: data, news, new calls, manage calls, commands, briefs, save."""
    account = float(cfg.get("account_gbp", 2000))
    max_risk_pct = float(cfg.get("max_risk_pct", 2.0))
    fx = state.get("_fx") or gbpusd()
    state["_fx"] = fx
    cap = round(account * max_risk_pct / 100 * fx / LOT_OZ, 2)
    now = pd.Timestamp.now(tz=ET)
    cmds = read_updates(state)
    _CHAT["id"] = state.get("tg_chat")
    cost = INSTRUMENTS["XAUUSD"]["cost"]

    # news: full refresh every 15 min, cheap otherwise
    if True:
        if not state.get("_news") or now - pd.Timestamp(state["_news_t"]) > timedelta(minutes=15):
            state["_news"] = newsmod.snapshot(now)
            state["_news_t"] = now.isoformat()
    nws = state["_news"]
    if nws.get("events"):
        nws["blackout"] = newsmod.blackout(nws["events"], now)
        nws["next"] = newsmod.next_events(nws["events"], now)

    df, feed, mmap = None, "none", None
    try:
        df, feed = gold_live()
        mmap = briefs.market_map(df)
    except Exception as e:  # noqa: BLE001
        print("data error", e)
    last = float(df["close"].iloc[-1]) if df is not None else None

    if mode == "scan" and df is not None:
        ctx = Context(df, "XAUUSD")
        print(f"{now:%H:%M:%S} feed: {feed} | last 5m {df.index[-1]:%H:%M} ET close {last:,.2f} | blackout {(nws.get('blackout') or {}).get('title')}")
        for s in strategy_setups(ctx, cfg, cap):
            if s.id in state["signals"]:
                old = state["signals"][s.id]
                if old["status"] == "open" and s.hold_until and s.hold_until != old.get("hold_until"):
                    old["hold_until"] = s.hold_until      # momentum exit now known (CCI back through 0)
                continue
            if pd.Timestamp(s.confirm_time) < now - timedelta(minutes=15):
                continue
            d = s.to_dict()
            done_ = sorted([x for x in state["signals"].values() if x["status"] in ("win", "loss")], key=lambda x: x["exit_time"])
            bal_now = stats(done_, account, state.get("balance_adjust"))["balance"]
            lots = lot_size(bal_now, max_risk_pct, abs(s.entry - s.stop), fx, cost)
            d.update(sent_at=now.isoformat(), initial_status=s.status, feed=feed, gbpusd=round(fx, 5),
                     account_gbp=round(bal_now, 2), lots=lots, risk_pct=max_risk_pct)
            if lots <= 0:
                d.update(status="skipped", notes=["stop too wide for 2% even at 0.01 lots"])
                state["signals"][s.id] = d
                tg(f"⏭ Setup skipped — {s.side} XAUUSD needs a ${abs(s.entry - s.stop):.0f} stop; even 0.01 lots would risk more than {max_risk_pct:g}% of £{bal_now:,.0f}.")
                continue
            if nws.get("blackout"):
                e = nws["blackout"]
                d.update(status="skipped", notes=[f"news blackout: {e['title']}"])
                state["signals"][s.id] = d
                tg(f"⛔ Setup skipped — {s.side} XAUUSD. 🔴 {briefs.esc(e['title'])} at "
                   f"{pd.Timestamp(e['time']).tz_convert(UK):%H:%M} UK. No new trades ±30 min around red folders.")
                continue
            d["news"] = dict(risk=(nws.get("risk") or {}).get("level"), next=(nws.get("next") or [None])[0])
            state["signals"][s.id] = d
            tg(signal_msg(d, last))
        # manage open calls
        for sid, d in state["signals"].items():
            if d["status"] not in ("pending", "open"):
                continue
            base = {k: d[k] for k in Setup.__dataclass_fields__ if k in d}
            base.update(status=d["initial_status"], fill_time=None if d["initial_status"] == "pending" else d["confirm_time"],
                        exit_time=None, exit_price=None, r=None, notes=[])
            s = simulate(Setup(**base), ctx.df, cost)
            if s.status != d["status"]:
                prev = d["status"]
                d.update(status=s.status, fill_time=s.fill_time, exit_time=s.exit_time, exit_price=s.exit_price, r=s.r, notes=s.notes)
                if prev == "pending" and s.status in ("win", "loss"):
                    tg(update_msg(dict(d, status="open")))
                extra = ""
                if s.status in ("win", "loss"):
                    done_ = sorted([x for x in state["signals"].values() if x["status"] in ("win", "loss")], key=lambda x: x["exit_time"])
                    b_ = stats(done_, account, state.get("balance_adjust"))["balance"]
                    extra = f"\n💷 Balance now ≈ <b>£{b_:,.2f}</b> → next trade risks 2% = £{b_ * max_risk_pct / 100:,.2f}"
                tg(update_msg(d) + extra)

    sigs = sorted(state["signals"].values(), key=lambda d: d["confirm_time"], reverse=True)
    closed = sorted([d for d in sigs if d["status"] in ("win", "loss")], key=lambda d: d["exit_time"])
    st = stats(closed, account, state.get("balance_adjust"))
    open_n = sum(d["status"] in ("pending", "open") for d in sigs)
    label = f"{cfg.get('strategy')} {json.dumps(cfg.get('strategy_params', {}))}"

    def send(kind):
        if kind == "price":
            spot = spot_gold()
            tg(f"💰 <b>XAUUSD {(spot or last or 0):,.2f}</b> (live spot {pd.Timestamp.now(tz=UK):%H:%M:%S} UK)\n"
               + (f"Last closed 5m candle {mmap['time'].tz_convert(UK):%H:%M} UK · {briefs.esc(feed)}" if mmap else ""))
        elif kind == "levels" and mmap:
            tg(briefs.map_msg(mmap))
        elif kind == "news":
            tg(briefs.news_msg(nws, now))
        elif kind == "folders":
            tg(folder_msg(nws, now))
        elif kind == "status":
            tg(briefs.status_msg(account, max_risk_pct, cap, label, now, open_n, st,
                                 strategy=STRATEGY_NAMES.get(cfg.get("strategy"), cfg.get("strategy"))))
        elif kind == "wrap":
            tg(daily_summary(state, cfg, df, now, account, max_risk_pct))
        elif kind == "test" and mmap:
            px = mmap["price"]; sl = 28.0
            demo = dict(side="BUY", entry=px, stop=px - sl, target=px + sl, rr=1.0, strategy=cfg.get("strategy"),
                        why="Sharp dip (RSI(2) 14) inside the 30min uptrend: buy it back to the 5-bar average",
                        level_name="", confirm_time=now.isoformat(), gbpusd=fx, account_gbp=st["balance"],
                        lots=lot_size(st["balance"], max_risk_pct, sl, fx, cost), news={"risk": "normal", "next": None})
            tg("🧪 <b>TEST — NOT A TRADE</b>\n\n" + signal_msg(demo, px).replace("#paper", "#test"))

    if os.getenv("SELFTEST") and not state.get("_selftest_done"):
        tg("🔧 <b>Self-test</b> — this is the bot confirming it can see live price, charts and news right now.")
        for k in ("price", "levels", "folders", "news", "test", "status"):
            send(k)
        state["_selftest_done"] = True
        ukn = now.tz_convert(UK)
        for key, hh in (("london", 6), ("folders", 8), ("ny", 13)):
            if ukn.hour >= hh:
                state[f"brief_{key}"] = str(ukn.date())   # self-test already covered today's briefs
    for c in dict.fromkeys(cmds):
        head, _, arg = c.partition(" ")
        if head == "/balance":
            try:
                v = float(arg.replace("£", "").replace(",", ""))
                state.setdefault("balance_adjust", []).append(dict(t=now.isoformat(), balance=v))
                tg(f"✅ Balance set to <b>£{v:,.2f}</b>. Next call is sized at 2% of that = £{v * max_risk_pct / 100:,.2f} risk.")
            except ValueError:
                tg(f"💷 Current balance (as I track it): <b>£{st['balance']:,.2f}</b>. To correct it send e.g. /balance 2150")
            continue
        send({"/price": "price", "/levels": "levels", "/map": "levels", "/news": "news", "/folders": "folders",
              "/status": "status", "/test": "test", "/start": "status", "/summary": "wrap", "/wrap": "wrap"}.get(head, "status"))

    # automatic briefs, Mon-Fri (UK time)
    ukt = now.tz_convert(UK)
    if ukt.dayofweek < 5:
        for key, hh, mm, kinds, title in (("folders", 8, 30, ("folders",), None),
                                          ("london", 6, 45, ("price", "levels"), "London session brief"),
                                          ("ny", 13, 15, ("price", "levels", "news"), "New York session brief"),
                                          ("wrap", 22, 0, ("wrap",), None)):
            k = f"brief_{key}"
            if state.get(k) != str(ukt.date()) and (ukt.hour, ukt.minute) >= (hh, mm) and ukt.hour < hh + 2:
                if title:
                    tg(f"☀️ <b>{title}</b>")
                for kd in kinds:
                    send(kd)
                state[k] = str(ukt.date())

    state["updated"] = now.isoformat()
    save(state, cfg, now, {"XAUUSD": dict(price=last, feed=feed, time=df.index[-1].isoformat() if df is not None else None)},
         st, nws, cap, account, max_risk_pct, fx, label, sigs)


def save(state, cfg, now, prices, st, nws, cap, account, max_risk_pct, fx, label, sigs):
    STATE.parent.mkdir(exist_ok=True)
    keep = {k: v for k, v in state.items() if not k.startswith("_")}
    STATE.write_text(json.dumps(keep, indent=1, default=str))
    FEED.parent.mkdir(exist_ok=True)
    FEED.write_text(json.dumps(dict(
        updated=now.isoformat(), params=label, prices=prices, stats=st,
        news=dict(blackout=nws.get("blackout"), next=nws.get("next"), risk=nws.get("risk"), today=nws.get("today"),
                  ok_calendar=nws.get("ok_calendar"), ok_headlines=nws.get("ok_headlines")),
        account=dict(gbp=account, max_risk_pct=max_risk_pct, lot=LOT, stop_cap_usd=cap, gbpusd=round(fx, 5)),
        backtest=load_json(ROOT / "reports" / "summary.json", None), signals=sigs[:200]), indent=1, default=str))


def git_save(msg):
    """Save the paper account on top of whatever is on GitHub now. The bot owns these two files,
    so a soft reset onto the latest remote can never conflict."""
    if not os.getenv("GITHUB_ACTIONS"):
        return
    files = ["data/state.json", "docs/signals.json"]
    steps = [["git", "fetch", "-q", "--depth", "1", "origin", "main"],
             ["git", "reset", "-q", "--soft", "FETCH_HEAD"],
             ["git", "add"] + files,
             ["git", "-c", "user.name=gold-desk-bot", "-c", "user.email=gold-desk-bot@users.noreply.github.com",
              "commit", "-q", "-m", msg],
             ["git", "push", "-q", "origin", "HEAD:main"]]
    for c in steps:
        try:
            r = subprocess.run(c, cwd=ROOT, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print("git timeout", c[1]); return
        if r.returncode:
            if c[1] == "commit" or "-c" in c and "commit" in c:
                return  # nothing new to save
            print("git step failed", c[1:3], r.stderr.strip()[:200]); return
    print("saved", msg)


def dispatch_next():
    tok, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not tok or not repo:
        return
    r = requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/scan.yml/dispatches",
                      headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"},
                      json={"ref": os.getenv("GITHUB_REF_NAME", "main")}, timeout=20)
    print("handover dispatch", r.status_code, r.text[:120])


def market_open(now_et: pd.Timestamp) -> bool:
    wd, h = now_et.dayofweek, now_et.hour
    return not (wd == 5 or (wd == 4 and h >= 17) or (wd == 6 and h < 18))


def main():
    cfg = load_json(CONFIG, {})
    state = load_json(STATE, {"signals": {}, "created": pd.Timestamp.now(tz="UTC").isoformat()})
    if not os.getenv("LOOP"):
        scan_once(state, cfg, "scan")
        print("ok", len(state["signals"]), "signals tracked")
        return
    budget = float(os.getenv("LOOP_MINUTES", "345")) * 60
    t0 = _time.time()
    last_scan_bar = None
    if not state.get("tg_loop_hello"):
        _CHAT["id"] = state.get("tg_chat")
    while _time.time() - t0 < budget:
        now = pd.Timestamp.now(tz=ET)
        bar = now.floor("5min")
        if os.getenv("GITHUB_ACTIONS"):
            subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", "main"], cwd=ROOT, capture_output=True, timeout=60)
            subprocess.run(["git", "checkout", "FETCH_HEAD", "--", "config.json"], cwd=ROOT, capture_output=True, timeout=30)
        cfg = load_json(CONFIG, cfg)   # settings changes apply on the next candle, no restart needed
        if market_open(now) and bar != last_scan_bar and now - bar >= pd.Timedelta(seconds=20):
            try:
                scan_once(state, cfg, "scan")
            except Exception as e:  # noqa: BLE001
                print("scan error", repr(e))
            last_scan_bar = bar
            git_save(f"scan {now:%Y-%m-%d %H:%M} ET")
        else:
            try:
                scan_once(state, cfg, "commands")   # answer /price etc. and run timed briefs
            except Exception as e:  # noqa: BLE001
                print("cmd error", repr(e))
        # sleep until the next 20s-past-candle mark or 60s, whichever first
        nxt = (bar + pd.Timedelta(minutes=5) + pd.Timedelta(seconds=20) - pd.Timestamp.now(tz=ET)).total_seconds()
        _time.sleep(max(5, min(60, nxt)))
    git_save("handover")
    dispatch_next()


if __name__ == "__main__":
    main()
