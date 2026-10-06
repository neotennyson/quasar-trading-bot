# QUASAR — QUantitative Automated Stock ARbiter

An autonomous, risk-managed **F&O (Futures & Options) trading bot** for the
Indian market (NSE). It runs one backtest-validated, parameter-free edge —
**cross-sectional momentum** — across a basket of liquid NSE stocks and
expresses it through **stock and index futures**.

> ⚠️ Research / paper-trading only. Not financial advice. F&O is leveraged and risky.

## What it actually does

At each monthly rebalance the bot ranks the universe by **12-1 momentum**
(the trailing 12-month return, skipping the most recent month to avoid the
short-term reversal) and **equal-weights the top ~1/3**. It holds that book for
the month, then rebalances. Long-only, fully invested, no leverage, no
in-sample fitting — so there is nothing to overfit.

Execution: each selected underlying is traded via its **front-month futures**
contract (indices → Nifty/Bank-Nifty futures). This is the instrument set you
actually trade through Dhan / Groww.

## Honest backtest (2016-01-01 → 2024-12-31, realistic F&O costs)

Universe: ~47 liquid NSE large/mid-caps. Costs: ~0.17% round-trip per monthly
rebalance (STT 0.02% sell-side + brokerage + slippage + futures roll).

| Metric | QUASAR (momentum) | Nifty buy & hold |
|---|---|---|
| Total return | **+558%** | +198% |
| CAGR | **23.3%** | 12.7% |
| Sharpe | **1.28** | 0.83 |
| Max drawdown | −34.6% | −38% |
| Volatility | 18.0% | ~15% |

**Out-of-sample robustness:** the same rule (no re-fitting) is positive in
*every* rolling 3-year window — CAGR 19.5%–25.3%, Sharpe 1.0–1.55 — so this is
not a single-period fluke.

### Honesty notes (read these)
- The 34.7% CAGR / +1362% figure in earlier docs was **cost-inflated** (it used
  ~2bps fictional costs) and was run on the **wrong market** (US ETFs you can't
  trade, and an Indian index-futures trend rule that was flat out-of-sample).
  This version uses realistic Indian F&O costs and a strategy that survives them.
- **Survivorship bias:** the universe is a set of *current* liquid large-caps, so
  the backtest favours names that survived and grew. Real live performance on a
  point-in-time universe will be somewhat lower. Treat 23% as an optimistic
  ceiling, not a guarantee.
- Backtest uses **spot prices as futures proxies**. Live futures have roll
  behaviour; the cost model approximates it but exact fills will differ.

## Quickstart
```bash
pip install -r requirements.txt
python scripts/backtest.py --save                 # validate -> data/equity_curve.csv
PYTHONPATH=src python -m quasar.paper.trader --once   # one paper session
PYTHONPATH=src python -m pytest tests/ -q            # tests
```

## Live trading (paper by default)
`broker.mode: paper`, `live_trading: false` — no real orders are ever sent.
To go live you wire order routing in `src/quasar/brokers/` (scaffolded) and set
`broker.mode: dhan|groww` + API keys via environment variables.

## Dashboard
```bash
pip install streamlit
streamlit run dashboard/app.py
```
Backtest equity + drawdown, live paper book, per-instrument momentum signals,
recent fills, and config.

> QUASAR · powered by Hy3
