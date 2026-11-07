# Gold strategy shoot-out: Andrea Unger's gold systems vs TJR

Data: **binance_paxg** 5m, 2020-08-28 → 2026-11-06. Settings picked on data before 2025-01-01, judged on data after it. 0.01 lots, max 2% risk, spread $0.3 per trade, entries at signal-candle close, UK hours 07–20.

## £200 account (stop ≤ $5.2)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pdbreak | — not enough trades within this risk limit | | | | | | | | | | |
| compress | — not enough trades within this risk limit | | | | | | | | | | |
| channel | `{"n": 192, "sl_atr": 2.0, "tp_mult": 3.0}` | 656 | 26.7 | -0.163 | 137 | 24.8 | -0.119 | 0.85 | £-35.84 | 10.7 | 19 |
| cci | — not enough trades within this risk limit | | | | | | | | | | |
| tjr | — not enough trades within this risk limit | | | | | | | | | | |
| london | `{"stop": "mid", "tp_mult": 1.0, "lo": 0.5, "hi": 1.5, "end_uk": 1100}` | 78 | 51.3 | -0.053 | 1 | 0.0 | -1.065 | 0.0 | £-3.79 | 1.4 | 10 |
| orb | `{"open_uk": 1430, "minutes": 30, "stop": "range", "tp_mult": 1.0}` | 157 | 52.9 | -0.035 | 9 | 22.2 | -0.652 | 0.23 | £-17.25 | 2.4 | 7 |
| ibretr | `{"open_uk": 1430, "entry_in": 0.25, "tgt_out": 0.5, "stop_in": 1.0}` | 106 | 50.0 | -0.048 | 7 | 42.9 | -0.196 | 0.57 | £-5.25 | 1.8 | 5 |
| holygrail | `{"tf": "15min", "adx_min": 30, "sl_atr": 1.5, "tp_mult": 1.0}` | 86 | 43.0 | -0.202 | 1 | 100.0 | 0.152 | None | £0.54 | 1.6 | 9 |
| rsi2 | `{"tf": "1h", "lo": 20, "hi": 80, "sl_atr": 1.5, "tp_mult": null}` | 99 | 60.6 | 0.111 | 1 | 100.0 | 3.529 | None | £10.78 | 2.2 | 4 |
| bbfade | `{"tf": "30min", "dev": 2.0, "adx_max": 20, "sl_atr": 0.5}` | 626 | 57.5 | 0.082 | 41 | 39.0 | -0.012 | 0.98 | £-6.96 | 9.9 | 8 |
| session | — not enough trades within this risk limit | | | | | | | | | | |
| cci_fast | `{"tf": "15min", "level": 300, "sl_usd": 0, "sl_atr": 2.0, "tp_mult": 2.0}` | 99 | 36.4 | -0.018 | 5 | 40.0 | 0.112 | 1.17 | £3.36 | 1.6 | 7 |
| imom | `{"from_uk": 800, "to_uk": 1330, "thresh_atr": 1.0, "hold_to_uk": 1700, "sl_atr": 1.0, "tp_mult": null}` | 74 | 21.6 | -0.266 | 3 | 66.7 | 2.379 | 7.7 | £22.25 | 1.6 | 13 |
| nr7 | `{"sl_mult": 0.3, "tp_mult": 1.5}` | 63 | 33.3 | -0.229 | 2 | 50.0 | 0.179 | 1.34 | £1.26 | 1.1 | 6 |

**Pick for £200:** bbfade `{"tf": "30min", "dev": 2.0, "adx_max": 20, "sl_atr": 0.5}`

## £1000 account (stop ≤ $26.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pdbreak | `{"sl_usd": 20, "tp_mult": 2.0, "hold_days": 1, "window_end_uk": 17}` | 654 | 44.5 | -0.064 | 251 | 39.0 | 0.019 | 1.03 | £73.62 | 12.2 | 10 |
| compress | `{"sl_usd": 20, "tp_mult": 3.0, "squeeze": 0.9}` | 233 | 45.9 | -0.002 | 95 | 41.1 | 0.074 | 1.15 | £108.53 | 4.5 | 6 |
| channel | `{"n": 192, "sl_atr": 2.0, "tp_mult": 3.0}` | 980 | 24.8 | -0.255 | 567 | 28.7 | -0.002 | 1.0 | £102.62 | 20.9 | 16 |
| cci | `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}` | 121 | 37.2 | 0.211 | 39 | 25.6 | -0.087 | 0.89 | £-20.87 | 2.2 | 8 |
| tjr | `{"entry": "fvg", "target": "2R", "bias": "none", "m15": true, "accept_atr": 1.5, "confirm_bars": 24, "zones": "both"}` | 66 | 50.0 | 0.191 | 25 | 32.0 | -0.15 | 0.78 | £-18.93 | 1.2 | 7 |
| london | `{"stop": "range", "tp_mult": 0.75, "lo": 0.0, "hi": 9.0, "end_uk": 1300}` | 726 | 48.3 | -0.089 | 101 | 58.4 | 0.047 | 1.14 | £61.95 | 11.3 | 8 |
| orb | `{"open_uk": 1430, "minutes": 30, "stop": "range", "tp_mult": 1.0}` | 922 | 46.2 | -0.105 | 320 | 49.1 | -0.026 | 0.94 | £-80.02 | 16.7 | 12 |
| ibretr | `{"open_uk": 1430, "entry_in": 0.25, "tgt_out": 0.5, "stop_in": 1.0}` | 411 | 54.0 | 0.033 | 135 | 50.4 | 0.019 | 1.05 | £25.48 | 7.4 | 8 |
| holygrail | `{"tf": "1h", "adx_min": 30, "sl_atr": 1.0, "tp_mult": 1.0}` | 62 | 56.5 | 0.041 | 9 | 22.2 | -0.582 | 0.27 | £-53.79 | 1.0 | 6 |
| rsi2 | `{"tf": "30min", "lo": 20, "hi": 80, "sl_atr": 1.5, "tp_mult": 1.0}` | 2232 | 63.2 | 0.07 | 904 | 61.4 | 0.038 | 1.13 | £133.75 | 42.4 | 7 |
| bbfade | `{"tf": "15min", "dev": 2.0, "adx_max": 20, "sl_atr": 0.5}` | 1703 | 64.3 | 0.058 | 547 | 56.3 | 0.038 | 1.09 | £-85.14 | 30.3 | 7 |
| session | `{"enter_uk": 1300, "exit_uk": 1600, "side": "SELL", "sl_usd": 20}` | 1131 | 48.2 | -0.006 | 483 | 44.3 | 0.043 | 1.1 | £318.98 | 21.7 | 15 |
| cci_fast | `{"tf": "30min", "level": 300, "sl_usd": 0, "sl_atr": 2.0, "tp_mult": 1.5}` | 239 | 36.0 | -0.095 | 60 | 40.0 | -0.044 | 0.92 | £-105.99 | 4.2 | 9 |
| imom | `{"from_uk": 700, "to_uk": 1300, "thresh_atr": 1.5, "hold_to_uk": 2000, "sl_atr": 2.0, "tp_mult": null}` | 123 | 45.5 | -0.002 | 25 | 32.0 | -0.356 | 0.42 | £-131.78 | 2.1 | 9 |
| nr7 | `{"sl_mult": 1.0, "tp_mult": 1.0}` | 130 | 43.8 | -0.077 | 12 | 50.0 | -0.001 | 1.0 | £2.85 | 2.2 | 6 |

**Pick for £1000:** cci `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}`

## £2000 account (stop ≤ $52.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pdbreak | `{"sl_usd": 20, "tp_mult": 2.0, "hold_days": 1, "window_end_uk": 17}` | 654 | 44.5 | -0.064 | 251 | 39.0 | 0.019 | 1.03 | £73.62 | 12.2 | 10 |
| compress | `{"sl_usd": 20, "tp_mult": 3.0, "squeeze": 0.9}` | 233 | 45.9 | -0.002 | 95 | 41.1 | 0.074 | 1.15 | £108.53 | 4.5 | 6 |
| channel | `{"n": 192, "sl_atr": 2.0, "tp_mult": 3.0}` | 982 | 24.7 | -0.257 | 578 | 28.7 | -0.013 | 0.98 | £-57.4 | 21.0 | 16 |
| cci | `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}` | 121 | 37.2 | 0.211 | 39 | 25.6 | -0.087 | 0.89 | £-20.87 | 2.2 | 8 |
| tjr | `{"entry": "fvg", "target": "2R", "bias": "none", "m15": true, "accept_atr": 1.5, "confirm_bars": 24, "zones": "both"}` | 68 | 51.5 | 0.194 | 29 | 37.9 | -0.084 | 0.86 | £11.48 | 1.3 | 7 |
| london | `{"stop": "range", "tp_mult": 1.0, "lo": 0.0, "hi": 9.0, "end_uk": 1100}` | 663 | 44.6 | -0.076 | 230 | 55.7 | 0.093 | 1.31 | £610.15 | 12.1 | 11 |
| orb | `{"open_uk": 1430, "minutes": 30, "stop": "range", "tp_mult": 1.0}` | 931 | 46.1 | -0.105 | 411 | 47.0 | -0.034 | 0.92 | £-209.61 | 18.0 | 12 |
| ibretr | `{"open_uk": 1430, "entry_in": 0.25, "tgt_out": 0.5, "stop_in": 1.0}` | 416 | 53.8 | 0.03 | 161 | 52.8 | 0.055 | 1.16 | £182.43 | 7.8 | 8 |
| holygrail | `{"tf": "1h", "adx_min": 30, "sl_atr": 1.0, "tp_mult": 1.0}` | 62 | 56.5 | 0.041 | 9 | 22.2 | -0.582 | 0.27 | £-53.79 | 1.0 | 6 |
| rsi2 | `{"tf": "30min", "lo": 20, "hi": 80, "sl_atr": 1.5, "tp_mult": 1.0}` | 2253 | 63.3 | 0.072 | 980 | 61.3 | 0.037 | 1.12 | £243.57 | 43.6 | 7 |
| bbfade | `{"tf": "15min", "dev": 2.0, "adx_max": 20, "sl_atr": 0.5}` | 1713 | 64.4 | 0.059 | 560 | 57.3 | 0.04 | 1.1 | £-54.48 | 30.6 | 7 |
| session | `{"enter_uk": 1300, "exit_uk": 1600, "side": "SELL", "sl_usd": 20}` | 1131 | 48.2 | -0.006 | 483 | 44.3 | 0.043 | 1.1 | £318.98 | 21.7 | 15 |
| cci_fast | `{"tf": "30min", "level": 300, "sl_usd": 0, "sl_atr": 2.0, "tp_mult": 1.5}` | 245 | 36.3 | -0.084 | 84 | 40.5 | -0.006 | 0.99 | £-10.45 | 4.6 | 9 |
| imom | `{"from_uk": 700, "to_uk": 1300, "thresh_atr": 1.5, "hold_to_uk": 2000, "sl_atr": 2.0, "tp_mult": null}` | 135 | 46.7 | -0.011 | 59 | 49.2 | 0.023 | 1.05 | £116.93 | 2.7 | 10 |
| nr7 | `{"sl_mult": 1.0, "tp_mult": 1.0}` | 142 | 43.7 | -0.075 | 37 | 40.5 | -0.107 | 0.67 | £-117.76 | 2.5 | 10 |

**Pick for £2000:** cci `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}`

## Portfolio £200: rsi2 + bbfade

- 767 trades, 0.53 per trading day, a trade on 32.9% of days
- win 57.0% · PF 1.2 · avg 0.085R · £173.62 · max DD £111.48 · worst streak 8 · green months 60.3%
- in-sample avg 0.086R (725) · out-of-sample avg 0.073R (42), win 40.5%, PF 1.12, £3.82
- years: 2020 +0.78R/17 · 2021 +0.28R/156 · 2022 -0.12R/198 · 2023 +0.03R/242 · 2024 +0.20R/112 · 2025 +0.10R/41 · 2026 -1.06R/1

## Portfolio £1000: cci + tjr + ibretr + holygrail + rsi2 + bbfade

- 6254 trades, 3.87 per trading day, a trade on 97.9% of days
- win 60.6% · PF 1.17 · avg 0.057R · £1734.8 · max DD £527.75 · worst streak 10 · green months 71.1%
- in-sample avg 0.068R (4595) · out-of-sample avg 0.027R (1659), win 57.3%, PF 1.08, £-19.5
- years: 2020 +0.19R/362 · 2021 +0.09R/1206 · 2022 -0.01R/962 · 2023 +0.04R/951 · 2024 +0.09R/1114 · 2025 +0.06R/949 · 2026 -0.01R/710

## Portfolio £2000: cci + tjr + ibretr + holygrail + rsi2 + bbfade

- 6411 trades, 3.97 per trading day, a trade on 98.7% of days
- win 60.8% · PF 1.18 · avg 0.058R · £2167.45 · max DD £401.38 · worst streak 10 · green months 71.1%
- in-sample avg 0.068R (4633) · out-of-sample avg 0.032R (1778), win 57.9%, PF 1.09, £308.34
- years: 2020 +0.19R/365 · 2021 +0.09R/1226 · 2022 -0.01R/967 · 2023 +0.04R/953 · 2024 +0.09R/1122 · 2025 +0.06R/969 · 2026 -0.00R/809
