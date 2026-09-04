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
`src/quasar/brokers/`. Secrets are read from **environment variables** so they
never sit in the repo:
```bash
export DHAN_CLIENT_ID=... DHAN_CLIENT_SECRET=... DHAN_ACCESS_TOKEN=...
export GROWW_API_KEY=... GROWW_API_SECRET=...
```
(`config.yaml` references them as `${DHAN_ACCESS_TOKEN}`, etc.)

## Dashboard
A clean Streamlit view of bot health — backtest equity + drawdown, live paper
book, per-instrument long/flat/short signals, recent trades, and config:
```bash
pip install streamlit
streamlit run dashboard/app.py
```
Sidebar buttons: **Run paper step** (refresh signals) and **Re-run backtest**.

See **[INSTRUCTIONS.md](INSTRUCTIONS.md)** for the full idea-to-execution design,
architecture, backtest evidence, and risk notes.

> ⚠️ F&O is leveraged and risky. For research/paper-trading. Not financial advice.
