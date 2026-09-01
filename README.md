# QUASAR — QUantitative Automated Stock ARbiter

An autonomous, risk-managed trading bot for the Indian stock market (NSE).
It follows one backtest-validated rule — **trend timing on the Nifty ETF with
volatility-targeted leverage** — and executes it every session with hard risk
limits. Goal: grow capital with small drawdowns.

## Highlights (backtest 2016–2024)
- **+145% total return**, CAGR **10.5%**, Sharpe **1.31**
- **Max drawdown −14%** (vs −38% for buy-and-hold Nifty)
- 59 trades over 9 years; sits in cash when the trend is down

## Quickstart
```bash
pip install -r requirements.txt
python scripts/backtest.py --save                       # validate the strategy
PYTHONPATH=src python -m quasar.paper.trader --once     # one paper session
PYTHONPATH=src python -m quasar.paper.trader --loop      # run live (paper)
PYTHONPATH=src python -m pytest tests/ -q                # tests
```

## Strategy
Buy the Nifty ETF (NIFTYBEES.NS) when ^NSEI closes above its 50-day MA; else
cash. Scale exposure to a 15% vol target (cap 1.5× leverage). 5% cash buffer +
15% drawdown circuit-breaker always on.

See **[INSTRUCTIONS.md](INSTRUCTIONS.md)** for the full idea-to-execution design,
architecture, backtest evidence, and how to go live with Dhan/Groww.

> ⚠️ For research/paper-trading. Past performance ≠ future results. Not financial advice.
