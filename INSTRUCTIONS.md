# QUASAR — QUantitative Automated Stock ARbiter (F&O Edition)

> An autonomous, risk-managed **F&O (Futures & Options) trading bot** for the
> Indian market (NSE). It trades **Nifty / Bank Nifty index futures** with
> volatility-targeted leverage, following one backtest-validated trend rule.
> The only objective: grow capital, with hard risk limits.
>
> (An equity mode — buy/hold the Nifty ETF on the same trend rule — also ships
> as a selectable alternative; see `strategy.active` in `config.yaml`.)

**Name:** *QUASAR* — a quasar is the brightest, most energetic object in the
universe; the bot is built as a high-energy, relentless profit engine. The name
is deliberately non-Indian and astronomy-themed.

---

## 1. Why F&O, and why this strategy

F&O lets a relatively small margin control a large notional, so a modest index
move becomes a large P&L. The edge we harvest is the same one proven in the
equity research: **the Indian index trends**, and most of its return accrues
while the trend is up. We express that edge through **index futures** with
leverage, instead of buying the cash ETF.

We stress-tested three ideas (2016–2024):

| Approach | Result (9y) | Verdict |
|---|---|---|
| Cross-sectional momentum (cash stocks) | +24% | ❌ weak in India |
| Cash ETF trend timing + vol target | +145%, DD −14% | ✅ good, but no leverage |
| **Index futures trend, long/short, vol-targeted** | **+298%, DD −20%** | ✅✅ **Chosen** |

The futures version **beats buy-and-hold Nifty (+203%)** in both absolute
return *and* risk: Sharpe **1.13** vs ~0.83, and max drawdown **−20%** vs −38%.

---

## 2. The Strategy (plain English)

1. **Instrument.** Trade the **Nifty 50 index futures** (default; set
   `index: ^NSEBANK` for Bank Nifty). Each lot ≈ ₹index × lot-size notional.
2. **Direction (trend filter).** Close above the 50-day MA → **LONG**. Close
   below → **FLAT** (no position). (Set `long_only: false` to also SHORT below
   the MA — we found long/flat slightly better, so it is the default.)
3. **Leverage (vol targeting).** Exposure is scaled so the portfolio targets
   **18% annualised volatility**, capped at **3× notional**. Low-volitility
   regimes → lean in (up to 3×); high volatility → de-risk automatically.
4. **Stops & breaker (always on).**
   - **Trade stop:** exit a position if the index moves **6% against entry**.
   - **Account circuit breaker:** if the account drawdown hits **25%**, flatten
     and halt all new entries until it recovers past half the breach.
   - **Costs:** ~0.02% round-trip (STT 0.01% + exchange + brokerage) is charged
     on every rebalance in backtests and paper trades.

Net effect: a leveraged trend-follower that rides up-trends, steps aside in
downtrends, and can never lose more than the breaker allows.

---

## 3. Backtest Evidence (2016-01-01 → 2024-12-30)

```
Period            : 2016-01-01 -> 2024-12-30
Total return      :   297.90%
Benchmark return  :   203.48%  (^NSEI buy & hold)
Excess return     :    94.42%
CAGR              :    16.59%
Sharpe            :     1.13
Max drawdown      :   -20.31%
Volatility        :    14.79%
Final equity      : Rs 3,979,026   (from Rs 1,000,000)
Total trades      : 59
```

59 trades over 9 years — infrequent, trend-driven entries; sits in cash through
chop and crashes. **Beats the index on return, risk-adjusted return, and
drawdown.**

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

## 6. Going live with Dhan / Groww (F&O)

`config.yaml → broker`: the bot ships in **paper** mode (no real orders). To
trade F&O live:

1. Set `broker.mode: dhan` (or `groww`) and fill `client_id` / `access_token`
   (or API keys) from your developer console.
2. Implement order placement in `src/quasar/brokers/dhan.py` / `groww.py` per
   the official API docs — instrument master + futures order endpoints are
   scaffolded, with dry-run logging already in place.
3. Translate the bot's *signed leverage* signal into lots:
   `lots = floor( target_leverage × capital / (index_price × lot_size) )`,
   rounded to the exchange lot size (Nifty ≈ 50, Bank Nifty ≈ 15). Go LONG the
   futures when signal > 0, SHORT when < 0, FLAT when 0.

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
| `strategy.active` | `futures_trend` (F&O) / `index_trend` (equity) / others |
| `strategy.futures_trend.index` | `^NSEI` (Nifty) or `^NSEBANK` (Bank Nifty) |
| `strategy.futures_trend.ma_window` | trend sensitivity (50 default) |
| `strategy.futures_trend.vol_target` | target vol → leverage (0.18) |
| `strategy.futures_trend.max_leverage` | hard cap (3.0) |
| `strategy.futures_trend.long_only` | flat-when-down (true) vs short-when-down (false) |
| `costs_futures.stop_pct` | per-trade stop (0.06 = 6%) |
| `costs_futures.account_dd` | circuit-breaker (0.25) |
| `costs_futures.cost_pct` | round-trip cost assumption (0.0002) |

---

*QUASAR — built to make money in Indian F&O, quietly and with limits.*
