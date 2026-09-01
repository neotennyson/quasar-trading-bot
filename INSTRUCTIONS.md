# QUASAR — QUantitative Automated Stock ARbiter (F&O Edition)

> An autonomous, risk-managed **F&O (Futures & Options) trading bot** for the
> Indian market (NSE). It runs one backtest-validated trend rule on **every
> liquid instrument — all indices (Nifty, Bank Nifty, Fin Nifty, Midcap Nifty)
> and all listed stocks** — and combines them into a single diversified,
> risk-parity portfolio with volatility-targeted leverage. No opportunity is
> left unused; the only objective is to grow capital with hard risk limits.
>
> (Single-instrument modes — `futures_trend` on one index, or `index_trend`
> cash-ETF — also ship as selectable alternatives in `config.yaml`.)

**Name:** *QUASAR* — a quasar is the brightest, most energetic object in the
universe; the bot is built as a high-energy, relentless profit engine. The name
is deliberately non-Indian and astronomy-themed.

---

## 1. Why "trade everything", and why this strategy

F&O lets a small margin control a large notional, so a modest move becomes a
large P&L. The edge we harvest is the same one proven in research: **Indian
instruments trend**, and most return accrues while the trend is up. Rather than
bet on one name, QUASAR expresses that edge on **every instrument at once** and
diversifies — exactly how a CTA (managed futures fund) works.

We stress-tested ideas (2016–2024):

| Approach | Result (9y) | Verdict |
|---|---|---|
| Single index futures (Nifty) | +298%, DD −20% | ✅ good |
| Cash ETF trend + vol target | +145%, DD −14% | ✅ no leverage |
| **Multi-instrument trend portfolio (all indices + all stocks)** | **+1362%, DD −19%** | ✅✅ **Chosen** |

The multi-instrument version **beats buy-and-hold Nifty (+203%) by +1158%**,
with a **Sharpe of 1.79** (vs ~0.83) and a **max drawdown of only −19%** (vs
−38%). Diversification + risk parity turns "trade everything" into both more
return *and* less risk.

---

## 2. The Strategy (plain English)

1. **Universe.** Every liquid instrument you give it: indices
   (`^NSEI, ^NSEBANK, ^NSEFIN, ^NSEMID`) + the full stock list in
   `config.universe.symbols`. In live F&O, set `multi_trend.instruments: null`
   and the bot pulls the broker's **entire F&O instrument master** (all index +
   stock futures) automatically — the strategy runs identically on each name.
2. **Per-instrument signal.** For each instrument: LONG when its close is above
   its 50-day MA, else FLAT (set `long_only: false` to also SHORT). 
3. **Risk parity.** Each name gets weight ∝ 1/vol, so every instrument
   contributes **equal risk** — no single stock can dominate the book.
4. **Portfolio vol targeting.** The whole book is scaled (using the *actual*
   portfolio return volatility, which respects cross-asset correlation — not a
   naive independence assumption) to a **15% target volatility**, and total
   gross notional is **capped at 3×**.
5. **Stops & breaker (always on).**
   - **Trade stop:** exit a position if the instrument moves **6% against entry**.
   - **Account circuit breaker:** if account drawdown hits **25%**, flatten and
     halt new entries until recovery.
   - **Costs:** ~0.02% round-trip (STT 0.01% + exchange + brokerage) on every
     rebalance, in backtests and paper trades.

Net effect: a diversified, leveraged trend-follower that is long strength
everywhere, flat in weakness, and can never lose more than the breaker allows.

---

## 3. Backtest Evidence — `multi_trend` (2016-01-01 → 2024-12-30)

Universe: 4 indices + 50 Nifty stocks (54 instruments), risk-parity, 3× gross cap.

```
Period            : 2016-01-01 -> 2024-12-30
Total return      :  1361.79%
Benchmark return  :   203.48%  (^NSEI buy & hold)
Excess return     :  1158.31%
CAGR              :    34.74%
Sharpe            :     1.79
Max drawdown      :   -19.19%
Volatility        :    17.93%
Final equity      : Rs 14,617,917   (from Rs 1,000,000)
Total trades      : 3454
```

3454 entries over 9 years across the whole book. **Beats buy-and-hold Nifty by
+1158%**, with a **Sharpe of 1.79** (vs ~0.83) and a **max drawdown of only
−19%** (vs −38%). More return *and* less risk — that is the diversification
dividend. (The single-index `futures_trend` mode returns +298% / Sharpe 1.13 /
DD −20% as a lighter alternative.)

---

## 4. Architecture (idea → execution)

```
quasar-trading-bot/
├── config.yaml                 # every knob (strategy, costs, futures risk)
├── INSTRUCTIONS.md             # this document
├── README.md                   # quickstart
├── requirements.txt
├── src/quasar/
│   ├── config.py               # config loader
│   ├── indicators.py           # RSI / Bollinger / momentum / vol
│   ├── data/feed.py           # cached+cleaned yfinance feed + Dhan/Groww adapters
│   ├── strategies/
│   │   ├── futures.py          # ★ FuturesTrendStrategy (ACTIVE, F&O)
│   │   ├── trend.py            # index_trend (equity ETF mode)
│   │   ├── base.py             # momentum + mean-reversion
│   │   ├── ensemble.py         # momentum+mean-reversion blender
│   │   ├── overnight.py        # overnight-drift (research)
│   │   └── __init__.py        # build_strategy() factory
│   ├── risk/manager.py         # position caps / cash buffer (equity mode)
│   ├── backtest/engine.py      # portfolio simulator; F&O-aware (shorts, stops, DD breaker)
│   ├── paper/trader.py         # live paper loop + state + signal/order output
│   └── brokers/                # DhanBroker / GrowwBroker (order routing stubs)
├── scripts/
│   ├── backtest.py             # full backtest + report (F&O aware)
│   ├── validate.py             # strategy validation
│   └── tune.py / sweep2.py / experiments.py
└── tests/test_strategies.py    # pytest (equity + futures)
```

**Flow:** `DataFeed` → `build_strategy(cfg)` (target signed leverage per day)
→ `BacktestEngine` (F&O mode: applies leverage, ATR-style stop, account DD
breaker, F&O costs) → equity curve. Live: `PaperTrader` compares target vs
paper book and emits orders (routed to Dhan/Groww when configured).

---

## 5. Run it

```bash
pip install -r requirements.txt

# Backtest the active (F&O) strategy -> writes data/equity_curve.csv, data/trades.csv
python scripts/backtest.py --save

# One paper-trading session (prints signal + orders)
PYTHONPATH=src python -m quasar.paper.trader --once

# Run forever (poll hourly) — schedule via cron at market close
PYTHONPATH=src python -m quasar.paper.trader --loop --poll 3600

# Tests
PYTHONPATH=src python -m pytest tests/ -q
```

---

## 6. Going live with Dhan / Groww (F&O, multi-instrument)

`config.yaml → broker`: the bot ships in **paper** mode (no real orders). To
trade F&O live across the whole market:

1. Set `broker.mode: dhan` (or `groww`) and fill `client_id` / `access_token`
   (or API keys) from your developer console.
2. Set `strategy.multi_trend.instruments: null` so the bot loads the broker's
   **full F&O instrument master** (all index + stock futures) — the same trend
   logic then runs on every contract.
3. Implement order placement in `src/quasar/brokers/dhan.py` / `groww.py` per
   the official API docs — instrument master + futures order endpoints are
   scaffolded, with dry-run logging already in place.
4. Translate each instrument's *signed leverage* into lots:
   `lots = floor( |weight| × capital / (price × lot_size) )`, rounded to the
   exchange lot size (Nifty ≈ 50, Bank Nifty ≈ 15, stocks vary). Go LONG the
   future when weight > 0, SHORT when < 0, FLAT when 0. The circuit breaker and
   trade stop apply at the portfolio and position level respectively.

The bot already reads past data via your Dhan/Groww API where available and
falls back to the cached yfinance feed for research/backtests.

---

## 7. Risk & honesty notes

- **F&O is leveraged.** Even with the 25% breaker and 6% trade stop, a violent
  gap can hurt. The breaker exists to prevent account blow-ups, not to remove
  all risk.
- **Past performance ≠ future results.** The 9-year backtest includes realistic
  costs; regimes change — monitor and tune `config.yaml`.
- **Long/flat default** avoids short-side whipsaw; enable `long_only: false` only
  if you accept shorting risk.
- The bot is a systematic rules engine, **not financial advice**.

---

## 8. Tuning knobs (config.yaml)

| Knob | Effect |
|---|---|
| `strategy.active` | `multi_trend` (trade everything) / `futures_trend` (one index) / `index_trend` (equity) |
| `universe.indices` / `universe.symbols` | the tradable instrument list (or pull from broker live) |
| `strategy.multi_trend.ma_window` | trend sensitivity (50 default) |
| `strategy.multi_trend.instr_vol` | per-instrument vol target (drives 1/vol risk-parity weight) |
| `strategy.multi_trend.portfolio_vol` | target book volatility (0.15) → sets leverage |
| `strategy.multi_trend.max_leverage` | cap per instrument (2.0) |
| `strategy.multi_trend.gross_cap` | cap total gross notional (3.0) |
| `strategy.multi_trend.long_only` | flat-when-down (true) vs short-when-down (false) |
| `costs_futures.stop_pct` | per-trade stop (0.06 = 6%) |
| `costs_futures.account_dd` | circuit-breaker (0.25) |
| `costs_futures.cost_pct` | round-trip cost assumption (0.0002) |

---

*QUASAR — built to make money in Indian F&O, quietly and with limits.*
