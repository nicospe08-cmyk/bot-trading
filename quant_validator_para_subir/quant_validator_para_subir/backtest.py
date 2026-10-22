"""
Motor de Backtesting Cuantitativo Realista (Bar-by-Bar).
Reglas fundamentales:
1. Cero look-ahead bias: la señal calculada al CIERRE de i-1 se ejecuta en la APERTURA de i.
2. Stop Loss (N x ATR) y Take Profit (RR x Stop) evaluados intrabar.
3. Si en la misma vela se tocan Stop Loss y Take Profit, se asume que se tocó el STOP primero.
4. Si hay gap más allá del stop, se sale al precio de apertura (ejecución desfavorable).
5. No reentrada tras un stop mientras la señal continúe en la misma dirección.
6. Comisiones y slippage configurables por lado.
7. Tamaño de posición por % de riesgo del capital con límite de apalancamiento.
8. Equity marcada a mercado vela a vela.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from indicators import calc_atr


@dataclass
class Trade:
    entry_idx: int
    entry_date: Any
    entry_price: float
    direction: int  # +1 Largo, -1 Corto
    units: float
    stop_price: float
    tp_price: float
    initial_risk_dollars: float  # Valor de 1R inicial

    exit_idx: Optional[int] = None
    exit_date: Optional[Any] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # 'STOP_LOSS', 'TAKE_PROFIT', 'SIGNAL', 'END_OF_DATA'
    pnl: float = 0.0
    pnl_pct: float = 0.0
    r_multiple: float = 0.0
    commission_paid: float = 0.0
    bars_held: int = 0


@dataclass
class BacktestResult:
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    cash_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    initial_capital: float = 10000.0
    final_capital: float = 10000.0


def run_backtest(
    df: pd.DataFrame,
    signals: pd.Series,
    initial_capital: float = 10000.0,
    risk_pct: float = 0.01,
    stop_atr_mult: float = 2.0,
    rr_ratio: float = 2.0,
    commission_pct: float = 0.0005,  # 0.05% por lado
    slippage_pct: float = 0.0002,    # 0.02% por lado
    max_leverage: float = 1.0,
    atr_period: int = 14
) -> BacktestResult:
    """
    Ejecuta el backtest vela a vela respetando estrictamente la cronología y causalidad.
    """
    n = len(df)
    if n < 2:
        return BacktestResult(initial_capital=initial_capital, final_capital=initial_capital)

    # Calcular ATR necesario para el stop loss
    atr_series = calc_atr(df, period=atr_period)

    # Convertir a arrays de numpy para máxima velocidad y evitar sobrecargas de pandas
    opens = df['open'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    dates = df.index
    sig_vals = signals.values
    atr_vals = atr_series.values

    # Variables de estado del portafolio
    cash = float(initial_capital)
    active_trade: Optional[Trade] = None
    completed_trades: List[Trade] = field(default_factory=list)
    completed_trades = []

    # Control de no reentrada tras stop loss
    blocked_direction: Optional[int] = None

    # Series para registrar la curva de equity vela a vela
    equity_records = np.zeros(n, dtype=float)
    cash_records = np.zeros(n, dtype=float)

    for i in range(n):
        # ----------------------------------------------------------------------
        # FASE 1: GESTIÓN DE ORDENES AL INICIO DE LA VELA (APERTURA)
        # ----------------------------------------------------------------------
        # Las señales generadas al cierre de la vela i-1 se ejecutan en la apertura de la vela i
        if i > 0:
            prev_signal = sig_vals[i - 1]
            current_open = opens[i]

            # Si la señal anterior cambió respecto a la dirección bloqueada, desbloquear
            if blocked_direction is not None and prev_signal != blocked_direction:
                blocked_direction = None

            # Si hay una posición abierta, verificar si la señal de i-1 manda salir
            if active_trade is not None:
                # Salida por señal si la señal es opuesta o 0
                if prev_signal != active_trade.direction:
                    # Salir al precio de apertura de la vela i (con slippage)
                    if active_trade.direction == 1:
                        fill_price = current_open * (1.0 - slippage_pct)
                        gross_pnl = (fill_price - active_trade.entry_price) * active_trade.units
                    else:
                        fill_price = current_open * (1.0 + slippage_pct)
                        gross_pnl = (active_trade.entry_price - fill_price) * active_trade.units

                    exit_comm = fill_price * active_trade.units * commission_pct
                    net_pnl = gross_pnl - exit_comm
                    active_trade.commission_paid += exit_comm

                    active_trade.exit_idx = i
                    active_trade.exit_date = dates[i]
                    active_trade.exit_price = fill_price
                    active_trade.exit_reason = 'SIGNAL'
                    active_trade.pnl = net_pnl
                    active_trade.pnl_pct = (net_pnl / (active_trade.entry_price * active_trade.units)) * 100.0
                    active_trade.r_multiple = (
                        net_pnl / active_trade.initial_risk_dollars
                        if active_trade.initial_risk_dollars > 0 else 0.0
                    )
                    active_trade.bars_held = i - active_trade.entry_idx

                    cash += net_pnl
                    completed_trades.append(active_trade)
                    active_trade = None

            # Si no hay posición activa, verificar si la señal de i-1 manda ENTRAR
            if active_trade is None and prev_signal in [1, -1]:
                # Verificar que la dirección no esté bloqueada por un stop reciente
                if prev_signal != blocked_direction and cash > 10.0:
                    current_atr = atr_vals[i - 1]
                    if np.isnan(current_atr) or current_atr <= 0:
                        current_atr = current_open * 0.02

                    # Distancia de Stop en dólares por unidad
                    stop_distance = stop_atr_mult * current_atr

                    # Precio base de entrada al Open con slippage
                    if prev_signal == 1:
                        fill_entry = current_open * (1.0 + slippage_pct)
                        stop_level = fill_entry - stop_distance
                        tp_level = fill_entry + (rr_ratio * stop_distance)
                    else:
                        fill_entry = current_open * (1.0 - slippage_pct)
                        stop_level = fill_entry + stop_distance
                        tp_level = fill_entry - (rr_ratio * stop_distance)

                    # Dimensionamiento de posición basado en riesgo fijo del capital
                    desired_risk = cash * risk_pct
                    units = desired_risk / stop_distance

                    # Limitar por apalancamiento máximo permitido
                    max_units = (cash * max_leverage) / fill_entry
                    units = min(units, max_units)

                    if units > 0:
                        entry_comm = fill_entry * units * commission_pct
                        cash -= entry_comm
                        initial_risk = units * stop_distance

                        active_trade = Trade(
                            entry_idx=i,
                            entry_date=dates[i],
                            entry_price=fill_entry,
                            direction=prev_signal,
                            units=units,
                            stop_price=stop_level,
                            tp_price=tp_level,
                            initial_risk_dollars=initial_risk,
                            commission_paid=entry_comm
                        )

        # ----------------------------------------------------------------------
        # FASE 2: GESTIÓN INTRABAR DE STOP LOSS Y TAKE PROFIT EN LA VELA i
        # ----------------------------------------------------------------------
        if active_trade is not None:
            c_open = opens[i]
            c_high = highs[i]
            c_low = lows[i]

            stop_hit = False
            tp_hit = False
            exit_price = 0.0
            exit_reason = ""

            if active_trade.direction == 1:  # LARGO
                # Verificación de Gap en apertura más allá de niveles
                if c_open <= active_trade.stop_price:
                    # Gap bajista superó el stop: salir a la apertura (desfavorable)
                    stop_hit = True
                    exit_price = c_open * (1.0 - slippage_pct)
                    exit_reason = 'STOP_LOSS'
                elif c_open >= active_trade.tp_price:
                    # Gap alcista superó el target: salir a la apertura
                    tp_hit = True
                    exit_price = c_open * (1.0 - slippage_pct)
                    exit_reason = 'TAKE_PROFIT'
                else:
                    # Verificación dentro de la vela
                    hit_sl_range = c_low <= active_trade.stop_price
                    hit_tp_range = c_high >= active_trade.tp_price

                    if hit_sl_range and hit_tp_range:
                        # REGLA TIE-BREAKER: Si se tocan ambos, asumir STOP LOSS primero
                        stop_hit = True
                        exit_price = active_trade.stop_price * (1.0 - slippage_pct)
                        exit_reason = 'STOP_LOSS'
                    elif hit_sl_range:
                        stop_hit = True
                        exit_price = active_trade.stop_price * (1.0 - slippage_pct)
                        exit_reason = 'STOP_LOSS'
                    elif hit_tp_range:
                        tp_hit = True
                        exit_price = active_trade.tp_price * (1.0 - slippage_pct)
                        exit_reason = 'TAKE_PROFIT'

                if stop_hit or tp_hit:
                    gross_pnl = (exit_price - active_trade.entry_price) * active_trade.units
                    exit_comm = exit_price * active_trade.units * commission_pct
                    net_pnl = gross_pnl - exit_comm
                    active_trade.commission_paid += exit_comm

                    active_trade.exit_idx = i
                    active_trade.exit_date = dates[i]
                    active_trade.exit_price = exit_price
                    active_trade.exit_reason = exit_reason
                    active_trade.pnl = net_pnl
                    active_trade.pnl_pct = (net_pnl / (active_trade.entry_price * active_trade.units)) * 100.0
                    active_trade.r_multiple = (
                        net_pnl / active_trade.initial_risk_dollars
                        if active_trade.initial_risk_dollars > 0 else 0.0
                    )
                    active_trade.bars_held = i - active_trade.entry_idx

                    cash += net_pnl
                    completed_trades.append(active_trade)

                    # Si salió por stop, bloquear reentrada en la misma dirección
                    if exit_reason == 'STOP_LOSS':
                        blocked_direction = active_trade.direction

                    active_trade = None

            else:  # CORTO
                if c_open >= active_trade.stop_price:
                    # Gap alcista superó el stop: salir a la apertura
                    stop_hit = True
                    exit_price = c_open * (1.0 + slippage_pct)
                    exit_reason = 'STOP_LOSS'
                elif c_open <= active_trade.tp_price:
                    # Gap bajista superó el target: salir a la apertura
                    tp_hit = True
                    exit_price = c_open * (1.0 + slippage_pct)
                    exit_reason = 'TAKE_PROFIT'
                else:
                    hit_sl_range = c_high >= active_trade.stop_price
                    hit_tp_range = c_low <= active_trade.tp_price

                    if hit_sl_range and hit_tp_range:
                        # REGLA TIE-BREAKER: Asumir Stop Loss primero
                        stop_hit = True
                        exit_price = active_trade.stop_price * (1.0 + slippage_pct)
                        exit_reason = 'STOP_LOSS'
                    elif hit_sl_range:
                        stop_hit = True
                        exit_price = active_trade.stop_price * (1.0 + slippage_pct)
                        exit_reason = 'STOP_LOSS'
                    elif hit_tp_range:
                        tp_hit = True
                        exit_price = active_trade.tp_price * (1.0 + slippage_pct)
                        exit_reason = 'TAKE_PROFIT'

                if stop_hit or tp_hit:
                    gross_pnl = (active_trade.entry_price - exit_price) * active_trade.units
                    exit_comm = exit_price * active_trade.units * commission_pct
                    net_pnl = gross_pnl - exit_comm
                    active_trade.commission_paid += exit_comm

                    active_trade.exit_idx = i
                    active_trade.exit_date = dates[i]
                    active_trade.exit_price = exit_price
                    active_trade.exit_reason = exit_reason
                    active_trade.pnl = net_pnl
                    active_trade.pnl_pct = (net_pnl / (active_trade.entry_price * active_trade.units)) * 100.0
                    active_trade.r_multiple = (
                        net_pnl / active_trade.initial_risk_dollars
                        if active_trade.initial_risk_dollars > 0 else 0.0
                    )
                    active_trade.bars_held = i - active_trade.entry_idx

                    cash += net_pnl
                    completed_trades.append(active_trade)

                    if exit_reason == 'STOP_LOSS':
                        blocked_direction = active_trade.direction

                    active_trade = None

        # ----------------------------------------------------------------------
        # FASE 3: MARCADO A MERCADO (MARK-TO-MARKET) AL CIERRE DE LA VELA i
        # ----------------------------------------------------------------------
        current_close = closes[i]
        if active_trade is not None:
            if active_trade.direction == 1:
                unrealized_pnl = (current_close - active_trade.entry_price) * active_trade.units
            else:
                unrealized_pnl = (active_trade.entry_price - current_close) * active_trade.units
            equity = cash + unrealized_pnl
        else:
            equity = cash

        equity_records[i] = equity
        cash_records[i] = cash

    # ----------------------------------------------------------------------
    # FASE 4: LIQUIDACIÓN AL FINAL DEL DATASET (SI QUEDA POSICIÓN ABIERTA)
    # ----------------------------------------------------------------------
    if active_trade is not None:
        last_idx = n - 1
        last_close = closes[last_idx]
        if active_trade.direction == 1:
            fill_price = last_close * (1.0 - slippage_pct)
            gross_pnl = (fill_price - active_trade.entry_price) * active_trade.units
        else:
            fill_price = last_close * (1.0 + slippage_pct)
            gross_pnl = (active_trade.entry_price - fill_price) * active_trade.units

        exit_comm = fill_price * active_trade.units * commission_pct
        net_pnl = gross_pnl - exit_comm
        active_trade.commission_paid += exit_comm

        active_trade.exit_idx = last_idx
        active_trade.exit_date = dates[last_idx]
        active_trade.exit_price = fill_price
        active_trade.exit_reason = 'END_OF_DATA'
        active_trade.pnl = net_pnl
        active_trade.pnl_pct = (net_pnl / (active_trade.entry_price * active_trade.units)) * 100.0
        active_trade.r_multiple = (
            net_pnl / active_trade.initial_risk_dollars
            if active_trade.initial_risk_dollars > 0 else 0.0
        )
        active_trade.bars_held = last_idx - active_trade.entry_idx

        cash += net_pnl
        equity_records[last_idx] = cash
        completed_trades.append(active_trade)

    equity_series = pd.Series(equity_records, index=dates)
    cash_series = pd.Series(cash_records, index=dates)

    return BacktestResult(
        trades=completed_trades,
        equity_curve=equity_series,
        cash_curve=cash_series,
        initial_capital=initial_capital,
        final_capital=float(equity_series.iloc[-1])
    )
