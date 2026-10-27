"""
Módulo de cálculo de indicadores técnicos cuantitativos.
Implementaciones propias con pandas y numpy, garantizando CERO look-ahead bias.
Cada valor en el índice i depende estrictamente de observaciones en t <= i.
"""

from typing import Tuple
import numpy as np
import pandas as pd


def calc_sma(series: pd.Series, period: int) -> pd.Series:
    """
    Media Móvil Simple (SMA).
    """
    return series.rolling(window=period, min_periods=period).mean()


def calc_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Media Móvil Exponencial (EMA).
    adjust=False garantiza la formulación recursiva estándar de trading:
    EMA_t = alpha * P_t + (1 - alpha) * EMA_{t-1}
    """
    return series.ewm(span=period, adjust=False).mean()


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range (ATR) de Wilder.
    TR_t = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)
    Suavizado recursivo con alpha = 1 / period.
    """
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)

    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder smoothing: alpha = 1 / period
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    return atr


def calc_rsi(close: pd.Series, period: int = 14, **kwargs) -> pd.Series:
    """
    Relative Strength Index (RSI) de Wilder.
    RSI = 100 - (100 / (1 + RS))
    Donde RS = GananciaMedia / PerdidaMedia (suavizado Wilder con alpha = 1/period)
    """
    if "window" in kwargs and kwargs["window"] is not None:
        period = int(kwargs["window"])
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)

    # Suavizado exponencial tipo Wilder
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-12)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def calc_adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Average Directional Index (ADX) de Wilder.
    Retorna: (ADX, Plus_DI, Minus_DI)
    """
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)

    # Movimientos direccionales
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

    # True Range
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Suavizado Wilder (alpha = 1 / period)
    tr_smooth = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=1.0 / period, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=1.0 / period, adjust=False).mean()

    plus_di = 100.0 * (plus_dm_smooth / (tr_smooth + 1e-12))
    minus_di = 100.0 * (minus_dm_smooth / (tr_smooth + 1e-12))

    di_diff = (plus_di - minus_di).abs()
    di_sum = plus_di + minus_di + 1e-12
    dx = 100.0 * (di_diff / di_sum)

    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()

    return adx, plus_di, minus_di


def calc_bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bandas de Bollinger.
    Retorna: (Banda Superior, Media Móvil / Banda Media, Banda Inferior)
    """
    middle = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)

    upper = middle + (num_std * std)
    lower = middle - (num_std * std)

    return upper, middle, lower


def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Moving Average Convergence Divergence (MACD).
    Retorna: (Línea MACD, Línea Señal, Histograma)
    """
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)

    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    hist = macd_line - signal_line

    return macd_line, signal_line, hist
