# QUASAR — QUantitative Automated Stock ARbiter (F&O Edition)

An autonomous, risk-managed **F&O trading bot** for the Indian market (NSE).
It trades **Nifty / Bank Nifty index futures** with volatility-targeted
leverage on a single backtest-validated trend rule — long above the 50-day MA,
flat below — with a 6% trade stop and a 25% account drawdown breaker.

## Highlights (backtest 2016–2024)
- **+298% total return**, CAGR **16.6%**, Sharpe **1.13**
- **Max drawdown −20%** (vs −38% for buy-and-hold Nifty); **beats the index by +94%**
- 59 trades over 9 years; sits in cash through downturns

## Quickstart
```bash
pip install -r requirements.txt
python scripts/backtest.py --save                       # validate the F&O strategy
PYTHONPATH=src python -m quasar.paper.trader --once     # one paper session
PYTHONPATH=src python -m quasar.paper.trader --loop      # run live (paper)
PYTHONPATH=src python -m pytest tests/ -q                # tests
```

## Strategy
Trade Nifty futures: **LONG when ^NSEI closes above its 50-day MA, else FLAT**.
Scale exposure to an 18% vol target (cap 3× leverage). 6% per-trade stop + 25%
account drawdown circuit breaker always on.

## Live trading
Set `broker.mode: dhan|groww` in `config.yaml` and fill your API keys; implement
order routing in `src/quasar/brokers/`. Convert the signed-leverage signal to
lots: `lots = floor(leverage × capital / (index × lot_size))`.

See **[INSTRUCTIONS.md](INSTRUCTIONS.md)** for the full idea-to-execution design,
architecture, backtest evidence, and risk notes.

> ⚠️ F&O is leveraged and risky. For research/paper-trading. Not financial advice.
