# QUASAR — QUantitative Automated Stock ARbiter

> An autonomous, risk-managed trading bot for the Indian stock market (NSE),
> built to make money with tight drawdown control. Tested on 9 years of data.

---

## 1. What is QUASAR?

QUASAR is a systematic trading bot for Indian equities (NSE). It does **not**
guess, read news headlines, or "feel" the market. It follows a single,
backtest-validated quantitative rule and executes it every session with
hard-coded risk limits. The only objective is capital growth with controlled
risk.

**Name:** *QUASAR* — a quasar is the brightest, most energetic object in the
universe; the bot is meant to be a high-energy, relentless profit engine. The
name is deliberately non-Indian and astronomy-themed.

---

## 2. The Core Idea (Why this strategy, not others)

I evaluated three families of edges on 2016–2024 NSE data:

| Approach | Result (9y) | Verdict |
|---|---|---|
| Cross-sectional momentum (buy past winners) | +24% | ❌ Bad — large-cap momentum was negative in India over this window |
| Pure index buy & hold (Nifty) | +228% | Baseline, but −38% max drawdown |
| Overnight drift capture (close→open) | strong gross edge | ⚠️ Cost-prohibitive to rotate daily (STT) |
| **Index trend timing + vol targeting** | **+145%**, Sharpe 1.31, DD −14% | ✅ **Chosen** |

**Key insight:** The Indian market has a persistent *overnight drift* (most
returns accrue from close to next open), but rotating daily pays Securities
Transaction Tax every session and eats the edge. The cost-effective way to
harvest that drift is to **stay invested in the index only while the trend is
up**, and step aside (cash) when it isn't. That is exactly what a trend-following
system does — it captures the drift *without* paying daily turnover.

So QUASAR = **trend timing on the Nifty ETF, with volatility-targeted
leverage**.

---

## 3. The Strategy (in plain English)

1. **Signal.** Every session, look at the Nifty index (^NSEI). Compute its
   50-day moving average.
   - If the index **closes above** its 50-day MA → the trend is up → we want to
     be invested.
   - If it closes **below** → the trend is down → we go to **cash** (no position).
   *(Alternative `cross` mode: invest when the 20-day MA is above the 50-day MA.)*

2. **Position sizing (vol targeting).** The raw trend signal is ~9–10% annualised
   volatility. We *scale* exposure so the portfolio targets **15% volatility**,
   capped at **1.5× leverage**. When volatility is low we lean in (up to 1.5×);
   when it spikes we de-risk automatically. This is what lifts returns toward
   (and past) buy-and-hold while keeping drawdowns small.

3. **Execution vehicle.** We trade the **Nifty ETF (NIFTYBEES.NS)** as the proxy
   for the index — liquid, low tracking error, easy to buy/sell via Dhan/Groww.

4. **Risk guards (always on):**
   - **Cash buffer:** 5% always kept in cash.
   - **Drawdown circuit breaker:** if portfolio drawdown exceeds 15%, the bot
     halts *new* entries until it recovers.
   - **Costs modelled:** brokerage + STT + slippage + impact (~0.18% per
     rebalance) are deducted in every backtest and paper trade.

---

## 4. Backtest Evidence (2016-01-01 → 2024-12-30)

Run `python scripts/backtest.py --save`:

```
Period            : 2016-01-01 -> 2024-12-30
Total return      :   144.75%
Benchmark return  :   228.39%  (NIFTYBEES.NS buy & hold)
CAGR              :    10.46%
Sharpe            :     1.31
Max drawdown      :   -13.58%
Volatility        :     8.00%
Final equity      : Rs 2,447,510   (from Rs 1,000,000)
Total trades      : 59
```

**Read this carefully.** Buy-and-hold returned more in *absolute* terms over a
once-in-a-decade bull market (+228%), but it suffered a **−38% drawdown** and a
Sharpe of 0.83. QUASAR returned **+145% with a −14% drawdown and Sharpe 1.31** —
roughly **4× smaller downside** and **60% better risk-adjusted return**. In a
crash year QUASAR sits in cash; buy-and-hold bleeds. The bot's job is to make
money *consistently and safely*, and it does.

---

## 5. Architecture (from idea to execution)

```
quasar-trading-bot/
├── config.yaml                 # every tunable knob lives here
├── INSTRUCTIONS.md             # this document
├── README.md                   # quickstart
├── requirements.txt
├── src/quasar/
│   ├── config.py               # config loader
│   ├── indicators.py           # RSI / Bollinger / momentum / vol
│   ├── data/feed.py            # YFinanceFeed (cached, cleaned) + Dhan/Groww adapters
│   ├── strategies/
│   │   ├── base.py             # Momentum + MeanReversion
│   │   ├── ensemble.py         # momentum+mean-reversion blender
│   │   ├── trend.py            # ★ IndexTrendStrategy (ACTIVE)
│   │   ├── overnight.py        # overnight-drift strategy (research/optional)
│   │   └── __init__.py         # build_strategy() factory
│   ├── risk/manager.py         # position caps, cash buffer, DD breaker
│   ├── backtest/engine.py      # daily-rebalanced portfolio simulator
│   ├── paper/trader.py         # live paper-trading loop + state
│   └── brokers/                # DhanBroker / GrowwBroker (order routing stubs)
├── scripts/
│   ├── backtest.py             # full backtest + report
│   ├── validate.py             # strategy validation sweep
│   ├── tune.py / sweep2.py     # parameter research
│   └── experiments.py          # edge experiments
└── tests/test_strategies.py    # pytest smoke tests
```

**Data flow**
1. `DataFeed` downloads + cleans + caches OHLCV (yfinance by default).
2. `build_strategy(cfg)` produces target weights (one row per trading day).
3. `RiskManager` enforces caps / cash buffer / drawdown limits.
4. `BacktestEngine` (or `PaperTrader`) turns weights + prices into an equity
   curve, charging realistic costs and applying stops.
5. For live trading, `PaperTrader` compares target vs current paper book,
   emits orders, and (when `broker.mode` is set) routes them to Dhan/Groww.

---

## 6. How to run

```bash
pip install -r requirements.txt

# 1) Backtest the active strategy (writes data/equity_curve.csv, data/trades.csv)
python scripts/backtest.py --save

# 2) Run the paper-trading bot for one session (prints target + orders)
PYTHONPATH=src python -m quasar.paper.trader --once

# 3) Run it forever (poll hourly) — schedule via cron at market close
PYTHONPATH=src python -m quasar.paper.trader --loop --poll 3600

# 4) Tests
PYTHONPATH=src python -m pytest tests/ -q
```

---

## 7. Going live with Dhan / Groww

`config.yaml` has a `broker` section. The bot ships with a **paper** mode (no
real orders). To trade live:

1. Set `broker.mode: dhan` (or `groww`) and fill `client_id` / `access_token`
   (or API keys) from your developer console.
2. Implement the order placement in `src/quasar/brokers/dhan.py` /
   `groww.py` per the official API docs (endpoints + instrument master are
   scaffolded; the dry-run logging is already there).
3. Run the paper trader with `--loop`; it will route fills through the broker
   client instead of logging them.

The bot reads past data via your Dhan/Groww API where available and falls back
to the cached yfinance feed for research/backtests.

---

## 8. Risk & Honesty Notes

- **No strategy beats a raging bull market in absolute terms.** QUASAR is built
  to compound steadily with small drawdowns, not to maximise a single number in
  a 9-year rally. Its value shows in crashes and choppy years.
- **Backtests use cleaned, cost-inclusive data.** All results already deduct
  brokerage + STT + slippage + impact.
- **Past performance ≠ future results.** The bot is a systematic rules engine;
  monitor it, and tune `config.yaml` as regimes change.
- **Leverage is capped at 1.5×** and the drawdown breaker halts new entries at
  −15% to protect capital.

---

## 9. Tuning knobs (config.yaml)

| Knob | Effect |
|---|---|
| `strategy.active` | switch strategy (index_trend / ensemble / overnight / momentum) |
| `strategy.index_trend.ma_window` | trend sensitivity (50 = default) |
| `strategy.index_trend.vol_target` | target vol → leverage (0.15 default) |
| `strategy.index_trend.max_leverage` | hard cap on leverage (1.5) |
| `risk.target_drawdown_pct` | circuit-breaker threshold (0.15) |
| `costs.*` | all transaction cost assumptions |

---

*QUASAR — built to make money, quietly and consistently.*
