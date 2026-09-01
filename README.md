# QUASAR — QUantitative Automated Stock ARbiter (F&O Edition)

An autonomous, risk-managed **F&O trading bot** for the Indian market (NSE) that
trades **everything**: all liquid indices (Nifty, Bank Nifty, Fin Nifty, Midcap
Nifty) **and all listed stocks**, combined into one diversified, risk-parity
portfolio with volatility-targeted leverage. The trend rule runs on every
instrument; no opportunity is left unused.

## Highlights (backtest 2016–2024, 54 instruments)
- **+1362% total return**, CAGR **34.7%**, Sharpe **1.79**
- **Max drawdown −19%** (vs −38% for buy-and-hold Nifty); **beats the index by +1158%**
- 3454 trades across the whole book over 9 years

## Quickstart
```bash
pip install -r requirements.txt
python scripts/backtest.py --save                       # validate the multi-instrument strategy
PYTHONPATH=src python -m quasar.paper.trader --once     # one paper session (trades a basket)
PYTHONPATH=src python -m quasar.paper.trader --loop      # run live (paper)
PYTHONPATH=src python -m pytest tests/ -q                # tests
```

## Strategy
For each instrument: **LONG above its 50-day MA, else FLAT** (optionally short).
Weights are risk-parity (∝ 1/vol) and the whole book is vol-targeted to 15%
with a 3× gross cap. 6% per-trade stop + 25% account drawdown breaker always on.

## Live trading
Set `broker.mode: dhan|groww` and `multi_trend.instruments: null` (pulls the
broker's full F&O instrument master); fill API keys; implement order routing in
`src/quasar/brokers/`. Convert each instrument's signed-leverage signal to lots.

See **[INSTRUCTIONS.md](INSTRUCTIONS.md)** for the full idea-to-execution design,
architecture, backtest evidence, and risk notes.

> ⚠️ F&O is leveraged and risky. For research/paper-trading. Not financial advice.
