# QUASAR — QUantitative Automated Stock ARbiter

> An autonomous, risk-managed **F&O (Futures & Options) trading bot** for the
> Indian market (NSE). It runs one backtest-validated, parameter-free edge —
> **cross-sectional momentum** — across a basket of liquid NSE stocks and
> expresses it through **stock and index futures**.
>
> (Other strategy modes — index/ensemble/futures-trend — also ship in
> `config.yaml` but are not the validated active strategy.)

**Name:** *QUASAR* — a quasar is the brightest, most energetic object in the
universe; the bot is built as a high-energy, relentless profit engine.

---

## 1. Why momentum, and why this design

A single trend-following rule on the Nifty future (or any one index) is
**flat out-of-sample after realistic costs** — we tested it, and it underperforms
buy-and-hold. The one edge that is genuinely robust in Indian equities is
**cross-sectional momentum**: winners over the past year tend to keep winning for
a while, and a basket of them diversifies idiosyncratic risk.

We deliberately use a **parameter-free** spec (12-1 momentum, top-1/3, equal
weight, monthly) so there is nothing to overfit. The rule is applied identically
across all historical periods; every rolling 3-year window is therefore a true
out-of-sample test, and all of them are positive.

---

## 2. The Strategy (plain English)

1. **Universe.** A basket of liquid NSE large/mid-caps in `config.universe.symbols`
   (indices are tracked separately for the regime filter). In live F&O, the same
   momentum logic maps each selected underlying to its **front-month futures**
   contract via the broker's instrument master.
2. **Signal.** At each month-end, rank every stock by its **12-1 momentum**: the
   return from 13 months ago to 1 month ago (skipping the last month avoids the
   well-known 1-month reversal). This is a standard, well-documented factor.
3. **Selection.** Equal-weight the **top ~1/3** of the ranked names. Long-only,
   fully invested. No leverage, no shorting, no per-day stops.
4. **Rebalance.** Hold for one month, then re-rank and rebalance. Turnover is the
   cost driver, so monthly (not weekly) rebalancing keeps costs realistic.
5. **Risk management.** Risk is controlled by **diversification** (≈15 names) and
   the monthly rebalance — not by leverage or tight stops, which just whipsaw a
   monthly signal.

Net effect: a diversified, fully-invested long book of recent winners that
rebalances monthly and quietly beats buy-and-hold with similar drawdown.

---

## 3. Backtest Evidence — `momentum` (2016-01-01 → 2024-12-31)

Universe: ~47 liquid NSE names. Realistic F&O costs (~0.17% round-trip per
monthly rebalance: STT 0.02% sell-side + brokerage + slippage + futures roll).

```
Period            : 2016-01-01 -> 2024-12-31
Total return      :   558.25%
Benchmark return  :   197.56%  (^NSEI buy & hold)
Excess return     :   360.69%
CAGR              :    23.30%
Sharpe            :     1.28
Max drawdown      :   -34.60%
Volatility        :    18.00%
Final equity      : Rs 7,079,597   (from Rs 1,000,000)
Total trades      : 329
```

**Out-of-sample robustness** (same rule, no re-fitting, rolling 3-year windows):
CAGR 19.5%–25.3%, Sharpe 1.0–1.55, all positive. Beats Nifty buy & hold
(12.7% CAGR) by a wide margin with comparable drawdown.

### Honesty notes (important)
- **Earlier docs claimed 34.7% CAGR / +1362%.** That figure used ~2bps fictional
  costs, ran on the wrong market (US ETFs you cannot trade, plus an Indian
  index-futures trend rule that was flat out-of-sample), and was the product of
  cost inflation + overfitting. The numbers above use realistic Indian F&O costs
  and a parameter-free rule.
- **Survivorship bias:** the universe is a set of *current* liquid large-caps, so
  the backtest favours names that survived and grew. Live performance on a
  point-in-time universe will be lower. Treat 23% as an optimistic ceiling.
- The backtest uses **spot prices as futures proxies**; live futures roll
  behaviour differs slightly (approximated in the cost model).

---

## 4. Architecture (idea → execution)

```
quasar-trading-bot/
├── config.yaml                 # active strategy = momentum, universe, costs
├── README.md / INSTRUCTIONS.md # this doc + honest quickstart
├── requirements.txt
├── src/quasar/
│   ├── config.py               # config loader (expands ${ENV} secrets)
│   ├── indicators.py           # momentum / vol helpers
│   ├── data/feed.py            # cached yfinance feed + Dhan/Groww adapters
│   ├── strategies/
│   │   ├── base.py             # ★ MomentumStrategy (ACTIVE)
│   │   ├── futures.py          # futures_trend / multi_trend (research)
│   │   ├── trend.py            # index_trend (equity ETF mode)
│   │   ├── ensemble.py, overnight.py, mean_reversion.py
│   │   └── __init__.py         # build_strategy() factory
│   ├── risk/manager.py         # position caps (equity mode)
│   ├── backtest/engine.py      # portfolio simulator with realistic costs
│   ├── paper/trader.py         # live paper loop + state + signal/order output
│   └── brokers/                # DhanBroker / GrowwBroker (scaffolded)
├── scripts/backtest.py         # full backtest + report
├── dashboard/app.py            # Streamlit health view
└── tests/test_strategies.py    # pytest
```

**Flow:** `DataFeed` → `build_strategy(cfg)` → `MomentumStrategy.run` (target
weights) → `BacktestEngine` (applies realistic F&O costs, monthly rebalance) →
equity curve. Live: `PaperTrader` compares target vs paper book and emits orders
(routed to Dhan/Groww when configured).

---

## 5. Run it

```bash
pip install -r requirements.txt

# Backtest the active momentum strategy -> data/equity_curve.csv, data/trades.csv
python scripts/backtest.py --save

# One paper-trading session (prints signal + simulated orders)
PYTHONPATH=src python -m quasar.paper.trader --once

# Run forever (poll at market close)
PYTHONPATH=src python -m quasar.paper.trader --loop --poll 3600

# Tests
PYTHONPATH=src python -m pytest tests/ -q
```

---

## 6. Going live with Dhan / Groww (F&O)

`config.yaml → broker`: ships in **paper** mode (no real orders). To trade F&O
live:

1. Set `broker.mode: dhan` (or `groww`) and supply API keys.
2. The paper trader maps each selected underlying to its futures contract via the
   broker instrument master (`list_futures_universe` scaffolded in the broker
   layer); translate target weight into lots:
   `lots = floor(|weight| × capital / (price × lot_size))`.
3. Implement order placement in `src/quasar/brokers/dhan.py` / `groww.py`.

Credentials are supplied as **environment variables** (kept out of the repo):
```bash
export DHAN_CLIENT_ID=... DHAN_CLIENT_SECRET=... DHAN_ACCESS_TOKEN=...
export GROWW_API_KEY=... GROWW_API_SECRET=...
```

### Dashboard
```bash
pip install streamlit
streamlit run dashboard/app.py
```

---

## 7. Risk & honesty notes

- **F&O is leveraged.** Even long-only, futures magnify moves. Size lots to your
  risk tolerance; the monthly rebalance + diversification is the primary control.
- **Past performance ≠ future results.** 23% is an optimistic, survivorship-
  biased ceiling on spot-proxy data with realistic costs. Live results will
  differ.
- The bot is a systematic rules engine, **not financial advice**.

---

## 8. Tuning knobs (config.yaml)

| Knob | Effect |
|---|---|
| `strategy.active` | `momentum` (active) / other modes (research) |
| `universe.symbols` | the tradable stock basket (survivorship-biased; widen for live) |
| `strategy.momentum.lookback_days` | momentum window (252 = 12 months) |
| `strategy.momentum.skip_days` | months skipped (21 ≈ 1 month, avoids reversal) |
| `strategy.momentum.top_frac` | fraction of universe held (0.34 ≈ top 1/3) |
| `strategy.momentum.equal_weight` | equal-weight (true) vs vol-weighted |
| `costs.*` | commission / STT / slippage / impact (round-trip ≈ 0.17%) |

---

*QUASAR — built to make money in Indian F&O, honestly and with limits.*
