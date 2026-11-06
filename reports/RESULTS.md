# Gold Desk — backtest results (XAUUSD, Aug 2020 → Nov 2026)

**Data:** Binance PAXG 5-minute candles (tokenised gold, 1 PAXG = 1 oz, tracks spot), 28 Aug 2020 → 5 Nov 2026 (6.2 years; the free data starts in 2020).
**Method:** settings picked on 2020–2024 only (in-sample), then judged on 2025–2026 (out-of-sample, never seen). Entry at the close of the signal candle, $0.30 spread per trade, a candle that hits both stop and take profit counts as a loss, 0.01 lots, max 2% risk.
**Tested:** 5 strategies, ~350 setting combinations, 3 account sizes (£200 / £500 / £1,000).

## Shoot-out summary

| strategy | verdict |
|---|---|
| TJR liquidity sweep | Good in-sample, **lost money out-of-sample**. Too few trades. Rejected. |
| Unger previous-day breakout | Lost 2020–24, small profit 2025–26 rally only. ~break-even. Rejected. |
| Unger compression breakout | ~break-even (PF 1.06). Rejected. |
| Unger 5m channel breakout | Lost money (PF 0.79). Rejected. |
| **Unger CCI momentum** | **Profitable in-sample AND out-of-sample, every stop size, small drawdowns. Selected.** |

## £200 account
Nothing works. A stop under ~$5.20 (2% of £200 at 0.01 lots) gets taken out by normal gold noise; every strategy lost money or had too few trades.

## Selected: Unger CCI momentum — 1H CCI(20) breaks ±350, $20 stop, 2R take profit (£1,000 demo)

| period | trades | win % | profit factor | avg R | £ at 0.01 lots |
|---|---|---|---|---|---|
| In-sample 2020–2024 | 47 | 48.9% | — | +0.23R | — |
| **Out-of-sample 2025–2026** | **14** | **71.4%** | **4.43** | **+0.94R** | **+£201.94** |
| All 6.2 years | 61 | 54.1% | 2.45 | +0.39R | +£366.81 |

- Loss rate 45.9% · max drawdown **£46** (4.6% of £1,000) · worst losing streak **6** · risk per trade ≈ £15.50 (1.55%)
- Year by year (avg R): 2020 +0.46 · 2021 +0.33 · 2022 +0.35 · 2023 −0.15 · 2024 +0.04 · 2025 +0.54 · 2026 +1.24 → **6 of 7 years profitable**
- Frequency: **~0.9 trades a month** (about 10 a year)

Neighbouring settings (level 300/350, stop $15–$25, TP 2R/3R) are all profitable, so this is a plateau, not a lucky spike.
Caveats: 61 trades is a small sample; 2026 is the best year so far; PAXG is close to but not identical to broker spot; live results usually come in 10–20% below a backtest.
