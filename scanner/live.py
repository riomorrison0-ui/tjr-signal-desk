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
                cmds.append(txt.split()[0].split("@")[0])
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


def signal_msg(s: dict, last: float) -> str:
    cfg = INSTRUMENTS["XAUUSD"]
    arrow = "🟢 BUY" if s["side"] == "BUY" else "🔴 SELL"
    risk = abs(s["entry"] - s["stop"])
    rew = abs(s["target"] - s["entry"])
    t = pd.Timestamp(s["confirm_time"]).tz_convert(UK).strftime("%H:%M")
    gap = s["entry"] - last
    kind = {"limit": "LIMIT", "stop": "STOP"}.get(s.get("entry_type"), "MARKET")
    if kind == "MARKET":
        where = f"now (last price {last:,.2f})"
    else:
        where = f"${abs(gap):.2f} {'below' if gap < 0 else 'above'} current price"
    fx = s.get("gbpusd", 1.30)
    risk_gbp = (risk + cfg["cost"]) * LOT_OZ / fx
    rew_gbp = (rew - cfg["cost"]) * LOT_OZ / fx
    acct = s.get("account_gbp", 200)
    hold = s.get("hold_until")
    hold_txt = (f"Hold up to {pd.Timestamp(hold).tz_convert(UK):%a %H:%M} UK if neither is hit" if hold
                else "Closed by end of day if neither is hit")
    return (
        f"<b>{arrow} XAUUSD</b>  (Gold) · {STRATEGY_NAMES.get(s.get('strategy'), s.get('strategy'))}\n"
        f"{kind} entry <b>{s['entry']:,.2f}</b>  — {where}\n"
        f"Stop loss <b>{s['stop']:,.2f}</b>  (${risk:.2f})\n"
        f"Take profit <b>{s['target']:,.2f}</b>  (${rew:.2f}, {s['rr']}R)\n"
        f"\n<b>0.01 lots</b> · risk ≈ £{risk_gbp:.2f} ({risk_gbp / acct * 100:.1f}% of £{acct:.0f}) · profit ≈ £{rew_gbp:.2f}\n"
        f"\nWhy: {s.get('why') or s['level_name']}\n"
        + news_line(s) +
        f"Signal {t} UK (candle close) · {hold_txt}\n#paper"
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
    if s["status"] == "open":
        return f"✅ FILLED — {head}. Stop {fmt(s['stop'], dp)}, target {fmt(s['target'], dp)}."
    if s["status"] == "win":
        g = pnl_gbp(s)
        return f"💰 TAKE PROFIT HIT — {head} → {fmt(s['exit_price'], dp)}  (+£{g:.2f}, +{s['r']}R)" if s["r"] > 0 else f"➖ CLOSED AT END OF DAY — {head} (£{g:.2f})"
    if s["status"] == "loss":
        g = pnl_gbp(s)
        closed_eod = any("end of day" in n for n in s.get("notes", []))
        return f"{'➖ CLOSED AT END OF DAY' if closed_eod else '❌ STOPPED'} — {head} → {fmt(s['exit_price'], dp)}  (£{g:.2f}, {s['r']}R)"
    if s["status"] == "expired":
        return f"⌛ CANCELLED — {head} never filled. Delete the limit order."
    return head


def pnl_gbp(c) -> float:
    cost = INSTRUMENTS[c["instrument"]]["cost"]
    move = (c["exit_price"] - c["entry"]) if c["side"] == "BUY" else (c["entry"] - c["exit_price"])
    return (move - cost) * LOT_OZ / c.get("gbpusd", 1.30)


def stats(closed, start):
    rs = [c["r"] for c in closed]
    wins = [r for r in rs if r > 0]
    bal, curve = start, []
    for c in closed:
        c["pnl_gbp"] = round(pnl_gbp(c), 2)
        bal += c["pnl_gbp"]
        curve.append(dict(t=c["exit_time"], balance=round(bal, 2)))
    return dict(trades=len(rs), wins=len(wins), win_rate=round(100 * len(wins) / len(rs), 1) if rs else None,
                total_r=round(sum(rs), 2), avg_r=round(sum(rs) / len(rs), 3) if rs else None,
                balance=round(bal, 2), start_balance=start, curve=curve)


def gbpusd() -> float:
    try:
        from data import yahoo
        return float(yahoo("GBPUSD=X", "5m", "1d")["close"].iloc[-1])
    except Exception:  # noqa: BLE001
        return 1.30


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
    account = float(cfg.get("account_gbp", 200))
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
            if s.id in state["signals"] or pd.Timestamp(s.confirm_time) < now - timedelta(minutes=15):
                continue
            d = s.to_dict()
            d.update(sent_at=now.isoformat(), initial_status=s.status, feed=feed, gbpusd=round(fx, 5), account_gbp=account)
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
                tg(update_msg(d))

    sigs = sorted(state["signals"].values(), key=lambda d: d["confirm_time"], reverse=True)
    closed = sorted([d for d in sigs if d["status"] in ("win", "loss")], key=lambda d: d["exit_time"])
    st = stats(closed, account)
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
        elif kind == "test" and mmap:
            tg(briefs.test_trade_msg(mmap, account, fx, cost, cap))

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
        send({"/price": "price", "/levels": "levels", "/map": "levels", "/news": "news", "/folders": "folders",
              "/status": "status", "/test": "test", "/start": "status"}.get(c, "status"))

    # automatic briefs, Mon-Fri (UK time)
    ukt = now.tz_convert(UK)
    if ukt.dayofweek < 5:
        for key, hh, mm, kinds, title in (("folders", 8, 30, ("folders",), None),
                                          ("london", 6, 45, ("price", "levels"), "London session brief"),
                                          ("ny", 13, 15, ("price", "levels", "news"), "New York session brief")):
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
