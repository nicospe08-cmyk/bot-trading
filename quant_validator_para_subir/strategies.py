"""
Módulo de estrategias cuantitativas de trading.
Cada estrategia implementa:
- Nombre y tipo de régimen ('TENDENCIA' o 'RANGO')
- Generación de señales (+1 Largo, -1 Corto, 0 Fuera) calculadas estrictamente al CIERRE de cada vela
- Grilla de parámetros para optimización sobre el tramo de entrenamiento
- Control de operativa en corto (allow_short)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List
import numpy as np
import pandas as pd

from indicators import (
    calc_adx,
    calc_atr,
    calc_bollinger,
    calc_ema,
    calc_macd,
    calc_rsi,
    calc_sma,
)


class BaseStrategy(ABC):
    """
    Clase base abstracta para todas las estrategias cuantitativas.
    Garantiza una interfaz unificada para el motor de backtest y optimizador.
    """
    def __init__(self, name: str, display_name: str, strategy_type: str):
        self.name = name
        self.display_name = display_name
        self.strategy_type = strategy_type  # 'TENDENCIA' o 'RANGO'

    @abstractmethod
    def get_param_grid(self) -> List[Dict[str, Any]]:
        """Devuelve la lista de combinaciones de parámetros para optimizar."""
        pass

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame, params: Dict[str, Any], allow_short: bool = True) -> pd.Series:
        """
        Calcula las señales (+1, -1, 0) al CIERRE de la vela.
        El motor de backtest ejecutará estas señales en la APERTURA de la vela siguiente.
        """
        pass

    def filter_shorts(self, signals: pd.Series, allow_short: bool) -> pd.Series:
        """Si allow_short es False, convierte cualquier señal de corto (-1) en flat (0)."""
        if not allow_short:
            return signals.clip(lower=0)
        return signals


# ==============================================================================
# 1. ESTRATEGIA: CRUCE DE EMAs
# ==============================================================================
class EmaCrossStrategy(BaseStrategy):
    """
    Estrategia de seguimiento de tendencia basada en el cruce de dos EMAs.
    - Largo (+1) cuando EMA Rápida > EMA Lenta.
    - Corto (-1) cuando EMA Rápida < EMA Lenta.
    """
    def __init__(self):
        super().__init__(
            name="ema_cross",
            display_name="Cruce de EMAs",
            strategy_type="TENDENCIA"
        )

    def get_param_grid(self) -> List[Dict[str, Any]]:
        grid = []
        for fast in [9, 13, 21]:
            for slow in [34, 55, 89]:
                if fast < slow:
                    grid.append({"fast_period": fast, "slow_period": slow})
        return grid

    def generate_signals(self, df: pd.DataFrame, params: Dict[str, Any], allow_short: bool = True) -> pd.Series:
        fast = calc_ema(df['close'], params['fast_period'])
        slow = calc_ema(df['close'], params['slow_period'])

        signals = pd.Series(0, index=df.index, dtype=int)
        signals[fast > slow] = 1
        signals[fast < slow] = -1

        return self.filter_shorts(signals, allow_short)


# ==============================================================================
# 2. ESTRATEGIA: CRUCE DE EMAs CON FILTRO ADX
# ==============================================================================
class EmaAdxStrategy(BaseStrategy):
    """
    Estrategia tendencial que exige confirmación de fuerza de tendencia mediante ADX.
    - Largo (+1): EMA Rápida > EMA Lenta Y ADX > umbral.
    - Corto (-1): EMA Rápida < EMA Lenta Y ADX > umbral.
    - Fuera (0): Mercado sin tendencia direccional suficiente (ADX <= umbral).
    """
    def __init__(self):
        super().__init__(
            name="ema_adx",
            display_name="Cruce de EMAs + Filtro ADX",
            strategy_type="TENDENCIA"
        )

    def get_param_grid(self) -> List[Dict[str, Any]]:
        grid = []
        for fast, slow in [(9, 26), (13, 34), (20, 50)]:
            for adx_th in [20, 25, 30]:
                grid.append({"fast_period": fast, "slow_period": slow, "adx_threshold": adx_th})
        return grid

    def generate_signals(self, df: pd.DataFrame, params: Dict[str, Any], allow_short: bool = True) -> pd.Series:
        fast = calc_ema(df['close'], params['fast_period'])
        slow = calc_ema(df['close'], params['slow_period'])
        adx, _, _ = calc_adx(df, period=14)

        has_trend = adx > params['adx_threshold']

        signals = pd.Series(0, index=df.index, dtype=int)
        signals[(fast > slow) & has_trend] = 1
        signals[(fast < slow) & has_trend] = -1

        return self.filter_shorts(signals, allow_short)


# ==============================================================================
# 3. ESTRATEGIA: RUPTURA DE DONCHIAN
# ==============================================================================
class DonchianBreakoutStrategy(BaseStrategy):
    """
    Canal de Donchian con control anti look-ahead:
    - Canal Superior = Máximo de los N periodos anteriores (desplazado en 1 vela).
    - Canal Inferior = Mínimo de los N periodos anteriores (desplazado en 1 vela).
    - Largo (+1) al cerrar por encima del canal superior.
    - Corto (-1) al cerrar por debajo del canal inferior.
    """
    def __init__(self):
        super().__init__(
            name="donchian",
            display_name="Ruptura de Donchian",
            strategy_type="TENDENCIA"
        )

    def get_param_grid(self) -> List[Dict[str, Any]]:
        return [{"period": p} for p in [15, 20, 30, 40, 55]]

    def generate_signals(self, df: pd.DataFrame, params: Dict[str, Any], allow_short: bool = True) -> pd.Series:
        p = params['period']
        # Desplazamiento obligatorio para evitar que la vela actual contamine el canal
        upper = df['high'].shift(1).rolling(window=p, min_periods=p).max()
        lower = df['low'].shift(1).rolling(window=p, min_periods=p).min()

        signals = np.zeros(len(df), dtype=int)
        current_state = 0
        close_vals = df['close'].values
        upper_vals = upper.values
        lower_vals = lower.values

        for i in range(len(df)):
            if np.isnan(upper_vals[i]) or np.isnan(lower_vals[i]):
                signals[i] = 0
                continue

            if close_vals[i] > upper_vals[i]:
                current_state = 1
            elif close_vals[i] < lower_vals[i]:
                current_state = -1

            signals[i] = current_state

        sig_series = pd.Series(signals, index=df.index, dtype=int)
        return self.filter_shorts(sig_series, allow_short)


# ==============================================================================
# 4. ESTRATEGIA: MACD
# ==============================================================================
class MacdStrategy(BaseStrategy):
    """
    Estrategia de momentum clásico:
    - Largo (+1): Línea MACD > Señal.
    - Corto (-1): Línea MACD < Señal.
    """
    def __init__(self):
        super().__init__(
            name="macd",
            display_name="MACD",
            strategy_type="TENDENCIA"
        )

    def get_param_grid(self) -> List[Dict[str, Any]]:
        return [
            {"fast": 8, "slow": 17, "signal": 9},
            {"fast": 12, "slow": 26, "signal": 9},
            {"fast": 15, "slow": 30, "signal": 9},
            {"fast": 19, "slow": 39, "signal": 9},
        ]

    def generate_signals(self, df: pd.DataFrame, params: Dict[str, Any], allow_short: bool = True) -> pd.Series:
        macd_line, signal_line, _ = calc_macd(
            df['close'],
            fast=params['fast'],
            slow=params['slow'],
            signal=params['signal']
        )

        signals = pd.Series(0, index=df.index, dtype=int)
        signals[macd_line > signal_line] = 1
        signals[macd_line < signal_line] = -1

        return self.filter_shorts(signals, allow_short)


# ==============================================================================
# 5. ESTRATEGIA: REVERSIÓN CON RSI
# ==============================================================================
class RsiReversionStrategy(BaseStrategy):
    """
    Estrategia de reversión a la media con RSI:
    - Entra Largo (+1) cuando el RSI cae por debajo de la zona de sobreventa.
    - Entra Corto (-1) cuando el RSI supera la zona de sobrecompra.
    - Cierra posición (0) al retornar al equilibrio central (RSI cruza el nivel 50).
    """
    def __init__(self):
        super().__init__(
            name="rsi_reversion",
            display_name="Reversión con RSI",
            strategy_type="RANGO"
        )

    def get_param_grid(self) -> List[Dict[str, Any]]:
        grid = []
        for period in [7, 10, 14]:
            for oversold in [25, 30]:
                for overbought in [70, 75]:
                    grid.append({
                        "period": period,
                        "oversold": oversold,
                        "overbought": overbought
                    })
        return grid

    def generate_signals(self, df: pd.DataFrame, params: Dict[str, Any], allow_short: bool = True) -> pd.Series:
        rsi = calc_rsi(df['close'], period=params['period']).values
        signals = np.zeros(len(df), dtype=int)
        current_state = 0

        for i in range(len(df)):
            val = rsi[i]
            if np.isnan(val):
                signals[i] = 0
                continue

            # Condiciones de entrada
            if val < params['oversold']:
                current_state = 1
            elif val > params['overbought']:
                current_state = -1
            # Condiciones de salida hacia la media (neutralidad en 50)
            elif current_state == 1 and val >= 50.0:
                current_state = 0
            elif current_state == -1 and val <= 50.0:
                current_state = 0

            signals[i] = current_state

        sig_series = pd.Series(signals, index=df.index, dtype=int)
        return self.filter_shorts(sig_series, allow_short)


# ==============================================================================
# 6. ESTRATEGIA: REVERSIÓN CON BANDAS DE BOLLINGER
# ==============================================================================
class BollingerReversionStrategy(BaseStrategy):
    """
    Estrategia de reversión a la media con Bandas de Bollinger:
    - Entra Largo (+1) al cerrar por debajo de la banda inferior.
    - Entra Corto (-1) al cerrar por encima de la banda superior.
    - Cierra posición (0) cuando el precio regresa a la media móvil central.
    """
    def __init__(self):
        super().__init__(
            name="bollinger_reversion",
            display_name="Reversión con Bandas de Bollinger",
            strategy_type="RANGO"
        )

    def get_param_grid(self) -> List[Dict[str, Any]]:
        grid = []
        for period in [15, 20, 25]:
            for num_std in [1.8, 2.0, 2.3]:
                grid.append({"period": period, "num_std": num_std})
        return grid

    def generate_signals(self, df: pd.DataFrame, params: Dict[str, Any], allow_short: bool = True) -> pd.Series:
        upper, middle, lower = calc_bollinger(df['close'], period=params['period'], num_std=params['num_std'])

        close_vals = df['close'].values
        upper_vals = upper.values
        lower_vals = lower.values
        middle_vals = middle.values

        signals = np.zeros(len(df), dtype=int)
        current_state = 0

        for i in range(len(df)):
            c = close_vals[i]
            u = upper_vals[i]
            l = lower_vals[i]
            m = middle_vals[i]

            if np.isnan(u) or np.isnan(l) or np.isnan(m):
                signals[i] = 0
                continue

            # Entradas por rechazo de extremos
            if c < l:
                current_state = 1
            elif c > u:
                current_state = -1
            # Salidas al retornar a la media móvil
            elif current_state == 1 and c >= m:
                current_state = 0
            elif current_state == -1 and c <= m:
                current_state = 0

            signals[i] = current_state

        sig_series = pd.Series(signals, index=df.index, dtype=int)
        return self.filter_shorts(sig_series, allow_short)


def get_all_strategies() -> List[BaseStrategy]:
    """Retorna la lista de todas las estrategias cuantitativas implementadas."""
    return [
        EmaCrossStrategy(),
        EmaAdxStrategy(),
        DonchianBreakoutStrategy(),
        MacdStrategy(),
        RsiReversionStrategy(),
        BollingerReversionStrategy()
    ]
