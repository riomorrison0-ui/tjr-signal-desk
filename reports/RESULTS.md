# Gold Desk — live strategy: Connors RSI(2) pullback, 30-minute chart

**Rules:** 30m candles. Uptrend (close above 200 EMA) and RSI(2) < 20 → BUY. Downtrend (below 200 EMA) and RSI(2) > 80 → SELL.
Stop 2.5 × ATR(14). Take profit 1R. Close early when price closes back through its 5-bar average. Entries 07:00–20:00 UK.

**Test:** Binance PAXG 5m, 28 Aug 2020 → 5 Nov 2026 (6.2 yrs). Settings picked on 2020–24, judged on unseen 2025–26.
$0.30 spread per trade, entry at signal-candle close, same-candle stop+target = loss, 0.01 lots. £2,000 demo.

| period | trades | per month | win % | profit factor | avg R | £ (0.01 lots) | max drawdown |
|---|---|---|---|---|---|---|---|
| All 6.2 yrs | 3,186 | 43 | 64.8% | 1.25 | +0.043R | +£1,445 | £182 (9.1%) |
| 2020–24 (picked on) | 2,241 | 43 | 65.1% | 1.27 | +0.044R | +£1,081 | £145 |
| **2025–26 (unseen)** | **945** | **43** | **64.2%** | **1.21** | **+0.039R** | **+£364** | £182 |

Years: 2020 +£374 · 2021 +£349 · 2022 −£38 · 2023 +£100 · 2024 +£296 · 2025 +£102 · 2026 +£262 → 6 of 7 profitable.
Worst losing streak 7. Average risk per trade ≈ 0.6% of £2,000.
Passed the fixed screen (≥8 trades/month, profitable in- and out-of-sample, PF ≥ 1.2, ≥5/7 green years, DD ≤ 15%).
Neighbouring settings (RSI 10/90, stop 1.5 ATR, momentum exit only) also pass or nearly pass — a plateau, not a spike.

Caveats: edge per trade is small (+0.04R), so spread matters; PAXG ≈ spot but not identical; live results usually come in 10–20% below a backtest.
Previous candidates (TJR, Unger breakouts, London/NY range breakouts, ORB, IB retracement, Holy Grail, Bollinger fade, time-of-day) all failed the screen. CCI momentum passed everything except frequency (~1/month).
