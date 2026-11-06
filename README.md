# Gold Desk — TJR model, paper trading

Watches XAUUSD every 5 minutes (GitHub Actions, free) and sends Telegram calls when the TJR setup prints:
liquidity sweep (PDH/PDL, Asia, London) in the London or New York killzone → 5m break of structure with displacement → FVG retrace entry, stop past the sweep.

- `scanner/tjr.py` — the model (same code for backtest and live, no look-ahead)
- `scanner/live.py` — the 5-minute scanner + paper account + Telegram alerts
- `scanner/backtest.py` — multi-year backtest on Dukascopy spot gold, picked in-sample, judged out-of-sample
- `docs/` — live dashboard (GitHub Pages)
- `config.json` — the settings the live scanner uses

Secrets (Settings → Secrets → Actions): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, optional `TWELVEDATA_KEY` for a spot-gold live feed.

Paper trading only.
