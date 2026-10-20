"""
Módulo de adquisición, validación y normalización de datos financieros.
Soporta:
1. Yahoo Finance (yfinance)
2. Archivos CSV locales
3. Generador de datos sintéticos con regímenes de volatilidad y tendencia
"""

from io import StringIO
from typing import Optional, Union
import numpy as np
import pandas as pd
import requests
import yfinance as yf

MIN_CANDLES_REQUIRED = 300


def clean_and_validate_dataframe(df: pd.DataFrame, source_name: str = "Datos") -> pd.DataFrame:
    """
    Normaliza y valida un DataFrame de velas OHLCV:
    - Renombra columnas a minúsculas estándar (open, high, low, close, volume).
    - Elimina zonas horarias (naive datetime).
    - Elimina duplicados en el índice de fechas y ordena cronológicamente.
    - Valida que existan al menos 300 velas.
    - Valida coherencia matemática: high >= low, high >= open, high >= close.
    """
    if df is None or df.empty:
        raise ValueError(f"[{source_name}] El conjunto de datos está vacío.")

    # Si las columnas son MultiIndex (a veces devuelto por yfinance reciente)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # Convertir nombres de columnas a minúsculas
    col_mapping = {}
    for col in df.columns:
        c_str = str(col).strip().lower()
        if c_str in ['open', 'apertura']:
            col_mapping[col] = 'open'
        elif c_str in ['high', 'maximo', 'máximo']:
            col_mapping[col] = 'high'
        elif c_str in ['low', 'minimo', 'mínimo']:
            col_mapping[col] = 'low'
        elif c_str in ['close', 'cierre', 'adj close', 'adj_close']:
            # Preferir 'close' estándar si existe, de lo contrario adj close
            if 'close' not in col_mapping.values():
                col_mapping[col] = 'close'
        elif c_str in ['volume', 'volumen', 'vol']:
            col_mapping[col] = 'volume'
        elif c_str in ['date', 'datetime', 'fecha', 'timestamp', 'time']:
            col_mapping[col] = 'datetime'

    df = df.rename(columns=col_mapping)

    # Manejar si 'datetime' o 'date' es una columna o el índice
    if 'datetime' in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.set_index('datetime')
    elif not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception as e:
            raise ValueError(f"[{source_name}] El índice no se pudo convertir a fechas válidas: {e}")

    # Verificar presencia de las columnas requeridas
    required_cols = ['open', 'high', 'low', 'close']
    for req in required_cols:
        if req not in df.columns:
            raise ValueError(f"[{source_name}] Falta la columna obligatoria '{req}'. Columnas encontradas: {list(df.columns)}")

    # Si falta volumen, crear columna con ceros
    if 'volume' not in df.columns:
        df['volume'] = 1000.0

    # Seleccionar solo las columnas necesarias en orden estándar
    df = df[['open', 'high', 'low', 'close', 'volume']].copy()

    # Convertir a valores numéricos
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Eliminar NaNs
    df = df.dropna()

    # Normalizar índice: ordenar cronológicamente y remover duplicados
    df = df.sort_index()
    df = df[~df.index.duplicated(keep='last')]

    # Remover información de zona horaria para estandarización perfecta
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    # Validar coherencia matemática básica de velas japonesas
    # Ajustar posibles anomalías en fuentes públicas
    df['high'] = df[['high', 'open', 'close']].max(axis=1)
    df['low'] = df[['low', 'open', 'close']].min(axis=1)

    # Validar mínimo de 300 velas
    if len(df) < MIN_CANDLES_REQUIRED:
        raise ValueError(
            f"[{source_name}] Se requieren al menos {MIN_CANDLES_REQUIRED} velas para un análisis estadístico robusto. "
            f"El conjunto actual solo contiene {len(df)} velas."
        )

    return df


def fetch_yahoo_data(symbol: str, interval: str = "1d", period: str = "2y") -> pd.DataFrame:
    """
    Descarga datos OHLCV desde Yahoo Finance y los valida.
    Intervalos soportados: '1d', '1h', '15m'.
    """
    ticker = symbol.strip().upper()
    try:
        raw_df = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True
        )
    except Exception as e:
        raise ValueError(f"Error de red o ticker inválido al consultar Yahoo Finance ('{ticker}'): {e}")

    if raw_df is None or raw_df.empty:
        raise ValueError(
            f"Yahoo Finance no devolvió datos para el ticker '{ticker}' "
            f"con intervalo '{interval}' y período '{period}'."
        )

    return clean_and_validate_dataframe(raw_df, source_name=f"Yahoo:{ticker}")


def fetch_binance_data(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 1000) -> pd.DataFrame:
    """
    Descarga velas OHLCV directamente desde la API pública oficial de Binance Spot.
    Sin necesidad de API keys, con datos exactos del motor de calce en milisegundos.
    Soporta intervalos: '1m', '5m', '15m', '30m', '1h', '2h', '4h', '1d'.
    """
    clean_sym = symbol.strip().upper().replace("/", "").replace("-", "").replace("_", "")
    if not clean_sym.endswith("USDT") and not clean_sym.endswith("FDUSD") and not clean_sym.endswith("BTC"):
        clean_sym += "USDT"

    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": clean_sym,
        "interval": interval,
        "limit": min(1000, max(300, limit))
    }

    try:
        resp = requests.get(url, params=params, timeout=12)
        if resp.status_code != 200:
            raise ValueError(f"Binance API devolvio error {resp.status_code}: {resp.text}")
        data = resp.json()
    except Exception as e:
        raise ValueError(f"Error al conectar con Binance API para '{clean_sym}': {e}")

    if not data or not isinstance(data, list) or len(data) == 0:
        raise ValueError(f"No se obtuvieron velas desde Binance para el par '{clean_sym}'.")

    raw_df = pd.DataFrame(data, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'
    ])

    raw_df['datetime'] = pd.to_datetime(raw_df['open_time'], unit='ms')
    raw_df = raw_df[['datetime', 'open', 'high', 'low', 'close', 'volume']].set_index('datetime')

    for col in ['open', 'high', 'low', 'close', 'volume']:
        raw_df[col] = raw_df[col].astype(float)

    return clean_and_validate_dataframe(raw_df, source_name=f"Binance:{clean_sym}")


def load_csv_data(file_input: Union[str, StringIO, bytes]) -> pd.DataFrame:
    """
    Carga un archivo CSV que contenga columnas date/datetime, open, high, low, close.
    """
    try:
        df = pd.read_csv(file_input)
    except Exception as e:
        raise ValueError(f"Error al leer el archivo CSV: {e}")

    return clean_and_validate_dataframe(df, source_name="Archivo CSV")


def generate_synthetic_data(
    n_candles: int = 1000,
    start_price: float = 100.0,
    seed: Optional[int] = 42,
    trend_type: str = "mixed"
) -> pd.DataFrame:
    """
    Genera un conjunto de datos sintéticos realista con regímenes de tendencia y rango,
    ideal para pruebas unitarias, validaciones offline y demostraciones.
    trend_type: 'mixed', 'bullish', 'bearish', 'ranging'
    """
    if seed is not None:
        np.random.seed(seed)

    if n_candles < MIN_CANDLES_REQUIRED:
        n_candles = MIN_CANDLES_REQUIRED

    dates = pd.date_range(start="2023-01-01", periods=n_candles, freq="1D")

    # Generar dinámica de precios mediante caminata aleatoria con drift cambiante
    # 4 fases para crear un ciclo de mercado completo (alcista -> rango -> bajista -> recuperación)
    phase_len = n_candles // 4
    remainder = n_candles - (phase_len * 4)

    if trend_type == "bullish":
        drifts = np.full(n_candles, 0.0012)
    elif trend_type == "bearish":
        drifts = np.full(n_candles, -0.0010)
    elif trend_type == "ranging":
        drifts = np.full(n_candles, 0.0000)
    else:  # mixed
        d1 = np.full(phase_len, 0.0018)    # Alcista
        d2 = np.full(phase_len, -0.0002)   # Rango / Distribución
        d3 = np.full(phase_len, -0.0015)   # Bajista
        d4 = np.full(phase_len + remainder, 0.0010)  # Reversión / Rango alcista
        drifts = np.concatenate([d1, d2, d3, d4])

    volatilities = 0.015 + 0.008 * np.sin(np.linspace(0, 4 * np.pi, n_candles))**2
    daily_returns = np.random.normal(drifts, volatilities)

    # Trayectoria de precios de cierre
    close_prices = start_price * np.exp(np.cumsum(daily_returns))

    # Construir Open, High, Low coherentes
    intraday_noise = np.random.uniform(0.002, 0.015, n_candles)
    high_prices = close_prices * (1 + intraday_noise)
    low_prices = close_prices * (1 - intraday_noise)

    open_prices = np.roll(close_prices, 1)
    open_prices[0] = start_price

    # Ajustar para asegurar que High sea el máximo y Low el mínimo
    for i in range(n_candles):
        high_prices[i] = max(high_prices[i], open_prices[i], close_prices[i])
        low_prices[i] = min(low_prices[i], open_prices[i], close_prices[i])

    volume = np.random.lognormal(mean=12, sigma=0.5, size=n_candles)

    df = pd.DataFrame({
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices,
        'volume': volume
    }, index=dates)

    return clean_and_validate_dataframe(df, source_name="Datos Sintéticos")
