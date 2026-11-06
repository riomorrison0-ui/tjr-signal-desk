# Gold strategy shoot-out: Andrea Unger's gold systems vs TJR

Data: **binance_paxg** 5m, 2020-08-28 → 2026-11-05. Settings picked on data before 2025-01-01, judged on data after it. 0.01 lots, max 2% risk, spread $0.3 per trade, entries at signal-candle close, UK hours 07–20.

## £1000 account (stop ≤ $26.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| holygrail | `{"tf": "1h", "adx_min": 30, "sl_atr": 1.0, "tp_mult": 1.0}` | 62 | 56.5 | 0.041 | 9 | 22.2 | -0.582 | 0.27 | £-53.79 | 1.0 | 6 |
| rsi2 | `{"tf": "30min", "lo": 20, "hi": 80, "sl_atr": 1.5, "tp_mult": 1.0}` | 2232 | 63.2 | 0.07 | 902 | 61.4 | 0.039 | 1.13 | £144.22 | 42.3 | 7 |
| bbfade | `{"tf": "15min", "dev": 2.0, "adx_max": 20, "sl_atr": 0.5}` | 1703 | 64.3 | 0.058 | 546 | 56.4 | 0.04 | 1.1 | £-81.32 | 30.3 | 7 |
| session | `{"enter_uk": 1300, "exit_uk": 1600, "side": "SELL", "sl_usd": 20}` | 1131 | 48.2 | -0.006 | 482 | 44.2 | 0.042 | 1.1 | £314.45 | 21.7 | 15 |
| ibretr | `{"open_uk": 1430, "entry_in": 0.25, "tgt_out": 0.5, "stop_in": 1.0}` | 411 | 54.0 | 0.033 | 135 | 50.4 | 0.019 | 1.05 | £25.48 | 7.4 | 8 |

**Pick for £1000:** rsi2 `{"tf": "30min", "lo": 20, "hi": 80, "sl_atr": 1.5, "tp_mult": 1.0}`

## £2000 account (stop ≤ $52.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| holygrail | `{"tf": "1h", "adx_min": 30, "sl_atr": 1.0, "tp_mult": 1.0}` | 62 | 56.5 | 0.041 | 9 | 22.2 | -0.582 | 0.27 | £-53.79 | 1.0 | 6 |
| rsi2 | `{"tf": "30min", "lo": 20, "hi": 80, "sl_atr": 1.5, "tp_mult": 1.0}` | 2253 | 63.3 | 0.072 | 978 | 61.3 | 0.038 | 1.13 | £254.03 | 43.6 | 7 |
| bbfade | `{"tf": "15min", "dev": 2.0, "adx_max": 20, "sl_atr": 0.5}` | 1713 | 64.4 | 0.059 | 559 | 57.4 | 0.042 | 1.1 | £-50.67 | 30.6 | 7 |
| session | `{"enter_uk": 1300, "exit_uk": 1600, "side": "SELL", "sl_usd": 20}` | 1131 | 48.2 | -0.006 | 482 | 44.2 | 0.042 | 1.1 | £314.45 | 21.7 | 15 |
| ibretr | `{"open_uk": 1430, "entry_in": 0.25, "tgt_out": 0.5, "stop_in": 1.0}` | 416 | 53.8 | 0.03 | 161 | 52.8 | 0.055 | 1.16 | £182.43 | 7.8 | 8 |

**Pick for £2000:** rsi2 `{"tf": "30min", "lo": 20, "hi": 80, "sl_atr": 1.5, "tp_mult": 1.0}`

## Portfolio £1000: holygrail + rsi2 + bbfade + ibretr

- 6000 trades, 3.72 per trading day, a trade on 97.2% of days
- win 61.6% · PF 1.17 · avg 0.054R · £1608.42 · max DD £575.89 · worst streak 10 · green months 67.1%
- in-sample avg 0.062R (4408) · out-of-sample avg 0.034R (1592), win 58.5%, PF 1.1, £34.58
- years: 2020 +0.20R/340 · 2021 +0.09R/1152 · 2022 -0.03R/927 · 2023 +0.04R/912 · 2024 +0.09R/1077 · 2025 +0.06R/920 · 2026 -0.00R/672

## Portfolio £2000: holygrail + rsi2 + bbfade + ibretr

- 6151 trades, 3.81 per trading day, a trade on 98.0% of days
- win 61.7% · PF 1.18 · avg 0.055R · £1998.66 · max DD £416.66 · worst streak 10 · green months 67.1%
- in-sample avg 0.062R (4444) · out-of-sample avg 0.038R (1707), win 59.1%, PF 1.11, £332.0
- years: 2020 +0.20R/343 · 2021 +0.09R/1170 · 2022 -0.04R/932 · 2023 +0.04R/914 · 2024 +0.09R/1085 · 2025 +0.06R/940 · 2026 +0.01R/767
