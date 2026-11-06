# Gold strategy shoot-out: Andrea Unger's gold systems vs TJR

Data: **binance_paxg** 5m, 2020-08-28 → 2026-11-05. Settings picked on data before 2025-01-01, judged on data after it. 0.01 lots, max 2% risk, spread $0.3 per trade, entries at signal-candle close, UK hours 07–20.

## £200 account (stop ≤ $5.2)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pdbreak | — not enough trades within this risk limit | | | | | | | | | | |
| compress | — not enough trades within this risk limit | | | | | | | | | | |
| channel | `{"n": 192, "sl_atr": 2.0, "tp_mult": 3.0}` | 656 | 26.7 | -0.163 | 137 | 24.8 | -0.119 | 0.85 | £-35.84 | 10.7 | 19 |
| cci | — not enough trades within this risk limit | | | | | | | | | | |
| tjr | — not enough trades within this risk limit | | | | | | | | | | |

**Pick for £200:** nothing profitable in-sample

## £500 account (stop ≤ $13.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pdbreak | `{"sl_usd": 12, "tp_mult": 3.0, "hold_days": 3, "window_end_uk": 17}` | 654 | 28.0 | -0.153 | 251 | 29.5 | 0.105 | 1.15 | £242.88 | 12.2 | 14 |
| compress | `{"sl_usd": 12, "tp_mult": 1.5, "squeeze": 0.9}` | 233 | 41.6 | -0.053 | 95 | 44.2 | 0.021 | 1.04 | £18.08 | 4.5 | 11 |
| channel | `{"n": 192, "sl_atr": 2.0, "tp_mult": 3.0}` | 965 | 24.6 | -0.261 | 491 | 28.3 | -0.012 | 0.98 | £-53.14 | 19.6 | 16 |
| cci | `{"level": 300, "sl_usd": 8}` | 121 | 33.1 | 0.069 | 39 | 23.1 | 1.431 | 2.79 | £343.55 | 2.2 | 9 |
| tjr | `{"entry": "fvg", "target": "2R", "bias": "none", "m15": true, "accept_atr": 1.5, "confirm_bars": 24, "zones": "both"}` | 62 | 50.0 | 0.209 | 12 | 25.0 | -0.293 | 0.63 | £-7.58 | 1.0 | 7 |

**Pick for £500:** tjr `{"entry": "fvg", "target": "2R", "bias": "none", "m15": true, "accept_atr": 1.5, "confirm_bars": 24, "zones": "both"}`

## £1000 account (stop ≤ $26.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pdbreak | `{"sl_usd": 20, "tp_mult": 2.0, "hold_days": 1, "window_end_uk": 17}` | 654 | 44.5 | -0.064 | 251 | 39.0 | 0.019 | 1.03 | £73.62 | 12.2 | 10 |
| compress | `{"sl_usd": 20, "tp_mult": 3.0, "squeeze": 0.9}` | 233 | 45.9 | -0.002 | 95 | 41.1 | 0.074 | 1.15 | £108.53 | 4.5 | 6 |
| channel | `{"n": 192, "sl_atr": 2.0, "tp_mult": 3.0}` | 980 | 24.8 | -0.255 | 567 | 28.7 | -0.002 | 1.0 | £102.62 | 20.9 | 16 |
| cci | `{"level": 300, "sl_usd": 8}` | 121 | 33.1 | 0.069 | 39 | 23.1 | 1.431 | 2.79 | £343.55 | 2.2 | 9 |
| tjr | `{"entry": "fvg", "target": "2R", "bias": "none", "m15": true, "accept_atr": 1.5, "confirm_bars": 24, "zones": "both"}` | 66 | 50.0 | 0.191 | 25 | 32.0 | -0.15 | 0.78 | £-18.93 | 1.2 | 7 |

**Pick for £1000:** tjr `{"entry": "fvg", "target": "2R", "bias": "none", "m15": true, "accept_atr": 1.5, "confirm_bars": 24, "zones": "both"}`
