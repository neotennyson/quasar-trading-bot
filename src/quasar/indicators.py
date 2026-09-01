"""Technical indicators used by QUASAR strategies."""
from __future__ import annotations
import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    return 100 - (100 / (1 + rs))


def bollinger(series: pd.Series, period: int = 20, std: float = 2.0):
    mid = sma(series, period)
    sd = series.rolling(period).std()
    upper = mid + std * sd
    lower = mid - std * sd
    return lower, mid, upper


def returns(series: pd.Series) -> pd.Series:
    return series.pct_change().fillna(0.0)


def annualized_vol(series: pd.Series, periods_per_year: int = 252) -> float:
    return float(series.pct_change().std() * np.sqrt(periods_per_year))


def realized_vol(returns: pd.Series, window: int = 20, periods_per_year: int = 252) -> pd.Series:
    return returns.rolling(window).std() * np.sqrt(periods_per_year)


def momentum_score(prices: pd.Series, lookback: int, skip: int) -> float:
    """6-1 style momentum: return from (lookback+skip) days ago to `skip` days ago."""
    if len(prices) < lookback + skip + 1:
        return np.nan
    past = prices.iloc[-(lookback + skip)]
    recent = prices.iloc[-skip] if skip > 0 else prices.iloc[-1]
    return (recent / past) - 1.0


def max_drawdown(equity: pd.Series) -> float:
    roll_max = equity.cummax()
    dd = equity / roll_max - 1.0
    return float(dd.min())
