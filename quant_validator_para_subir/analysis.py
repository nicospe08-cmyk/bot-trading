"""
Módulo de Métricas, Validación Estadística Fuera de Muestra y Detección de Régimen.
Implementa:
1. Cálculo de métricas cuantitativas completas (múltiplos R, t-stat, Sharpe, Drawdown, etc.)
2. Puntaje de ranking: score = t_stat(R) * (1 - MaxDrawdown)
3. Validación cruzada Train / Test (In-Sample / Out-of-Sample) sin look-ahead
4. Clasificación de estado: OK, Pocas operaciones, Pierde fuera de muestra, Posible sobreoptimización
5. Detección de Régimen de Mercado (ADX > 25) y evaluación de coherencia
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from backtest import BacktestResult, Trade, run_backtest
from indicators import calc_adx, calc_atr
from strategies import BaseStrategy, get_all_strategies


@dataclass
class PerformanceMetrics:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    expectancy_r: float = 0.0
    avg_win_r: float = 0.0
    avg_loss_r: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_consecutive_losses: int = 0
    total_return_pct: float = 0.0
    t_stat_r: float = 0.0
    ranking_score: float = -999.0


@dataclass
class StrategyEvaluation:
    strategy_name: str
    display_name: str
    strategy_type: str  # 'TENDENCIA' o 'RANGO'
    best_params: Dict[str, Any]
    train_metrics: PerformanceMetrics
    test_metrics: PerformanceMetrics
    train_result: BacktestResult
    test_result: BacktestResult
    status: str  # 'OK', 'Pocas operaciones', 'Pierde fuera de muestra', 'Posible sobreoptimización'
    status_reason: str
    ranking_score: float  # Score en test (OOS)


def calculate_metrics(result: BacktestResult, min_trades: int = 10) -> PerformanceMetrics:
    """
    Calcula el conjunto completo de métricas cuantitativas para un resultado de backtest.
    """
    trades = result.trades
    n_trades = len(trades)

    if n_trades == 0:
        return PerformanceMetrics(
            total_trades=0,
            ranking_score=-999.0
        )

    # Separar ganancias y pérdidas
    pnls = np.array([t.pnl for t in trades])
    r_mults = np.array([t.r_multiple for t in trades])

    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    n_wins = len(wins)
    n_losses = len(losses)

    win_rate = (n_wins / n_trades) * 100.0 if n_trades > 0 else 0.0

    # Profit Factor
    sum_wins = np.sum(wins) if n_wins > 0 else 0.0
    sum_losses = np.abs(np.sum(losses)) if n_losses > 0 else 0.0
    if sum_losses > 0:
        profit_factor = float(sum_wins / sum_losses)
    else:
        profit_factor = 999.0 if sum_wins > 0 else 0.0

    # Múltiplos R
    expectancy_r = float(np.mean(r_mults))
    r_wins = r_mults[r_mults > 0]
    r_losses = r_mults[r_mults <= 0]
    avg_win_r = float(np.mean(r_wins)) if len(r_wins) > 0 else 0.0
    avg_loss_r = float(np.mean(r_losses)) if len(r_losses) > 0 else 0.0

    # t-statistic de los múltiplos R: t = mean(R) / (std(R) / sqrt(N))
    if n_trades >= 2:
        std_r = float(np.std(r_mults, ddof=1))
        if std_r > 1e-9:
            t_stat_r = expectancy_r / (std_r / np.sqrt(n_trades))
        else:
            t_stat_r = 0.0
    else:
        t_stat_r = 0.0

    # Máxima racha de pérdidas consecutivas
    max_streak = 0
    current_streak = 0
    for p in pnls:
        if p <= 0:
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 0

    # Drawdown y Retorno de la curva de equity
    eq = result.equity_curve
    if len(eq) > 1:
        peak = eq.cummax()
        dd_series = (peak - eq) / (peak + 1e-12)
        max_dd_pct = float(dd_series.max()) * 100.0

        # Retorno total
        tot_return_pct = float(((eq.iloc[-1] - result.initial_capital) / result.initial_capital) * 100.0)

        # Sharpe ratio anualizado (asumiendo rendimientos vela a vela)
        returns = eq.pct_change().dropna()
        if len(returns) > 5 and returns.std() > 1e-9:
            # Factor de anualización aproximado diario (252)
            sharpe = float((returns.mean() / returns.std()) * np.sqrt(252))
        else:
            sharpe = 0.0
    else:
        max_dd_pct = 0.0
        tot_return_pct = 0.0
        sharpe = 0.0

    # Puntaje para Rankear:
    # puntaje = t-stat de la esperanza en R x (1 - max drawdown en fracción)
    # Si hay menos operaciones que el mínimo configurado, puntaje muy bajo (-999.0)
    dd_fraction = min(1.0, max(0.0, max_dd_pct / 100.0))
    if n_trades < min_trades:
        ranking_score = -999.0
    else:
        ranking_score = float(t_stat_r * (1.0 - dd_fraction))

    return PerformanceMetrics(
        total_trades=n_trades,
        winning_trades=n_wins,
        losing_trades=n_losses,
        win_rate_pct=win_rate,
        profit_factor=profit_factor,
        expectancy_r=expectancy_r,
        avg_win_r=avg_win_r,
        avg_loss_r=avg_loss_r,
        max_drawdown_pct=max_dd_pct,
        sharpe_ratio=sharpe,
        max_consecutive_losses=max_streak,
        total_return_pct=tot_return_pct,
        t_stat_r=t_stat_r,
        ranking_score=ranking_score
    )


def determine_validation_status(
    train_m: PerformanceMetrics,
    test_m: PerformanceMetrics,
    min_trades: int
) -> Tuple[str, str]:
    """
    Clasifica el estado de robustez estadística de la estrategia fuera de muestra:
    1. 'Pocas operaciones': Menos trades en test que el mínimo exigido.
    2. 'Pierde fuera de muestra': Retorno <= 0 o esperanza en R <= 0 en test.
    3. 'Posible sobreoptimización': Test rinde menos de la mitad que Train.
    4. 'OK': Validación superada satisfactoriamente.
    """
    if test_m.total_trades < min_trades:
        return "Pocas operaciones", f"Solo {test_m.total_trades} operaciones en validación (mínimo requerido: {min_trades})."

    if test_m.total_return_pct <= 0 or test_m.expectancy_r <= 0:
        return "Pierde fuera de muestra", f"Esperanza en R negativa ({test_m.expectancy_r:+.2f}R) o retorno total negativo ({test_m.total_return_pct:+.2f}%)."

    # Verificar si el rendimiento cayó drásticamente respecto al entrenamiento (sobreajuste / curve-fitting)
    if train_m.expectancy_r > 0 and test_m.expectancy_r < (0.5 * train_m.expectancy_r):
        return (
            "Posible sobreoptimización",
            f"La esperanza fuera de muestra ({test_m.expectancy_r:.2f}R) cayó a menos del 50% del entrenamiento ({train_m.expectancy_r:.2f}R)."
        )

    return "OK", "Desempeño positivo y estadísticamente consistente fuera de muestra."


def optimize_and_validate_strategy(
    strategy: BaseStrategy,
    df: pd.DataFrame,
    train_idx: int,
    initial_capital: float,
    risk_pct: float,
    stop_atr_mult: float,
    rr_ratio: float,
    commission_pct: float,
    slippage_pct: float,
    max_leverage: float,
    allow_short: bool,
    min_trades: int,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> StrategyEvaluation:
    """
    Optimiza los parámetros de una estrategia EXCLUSIVAMENTE en el tramo de entrenamiento.
    Luego valida la mejor combinación en el tramo de prueba (Out-of-Sample).
    """
    df_train = df.iloc[:train_idx]
    df_test = df.iloc[train_idx:]

    param_grid = strategy.get_param_grid()
    best_params = param_grid[0] if param_grid else {}
    best_train_score = -9999.0
    best_train_result: Optional[BacktestResult] = None
    best_train_metrics: Optional[PerformanceMetrics] = None

    # 1. OPTIMIZACIÓN EXCLUSIVAMENTE EN TRAIN
    # Se calculan las señales sobre df completo para mantener indicadores calientes,
    # pero el backtest se evalúa únicamente en el tramo df_train.
    for p_idx, params in enumerate(param_grid):
        full_signals = strategy.generate_signals(df, params, allow_short=allow_short)
        train_signals = full_signals.iloc[:train_idx]

        train_res = run_backtest(
            df=df_train,
            signals=train_signals,
            initial_capital=initial_capital,
            risk_pct=risk_pct,
            stop_atr_mult=stop_atr_mult,
            rr_ratio=rr_ratio,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
            max_leverage=max_leverage
        )

        metrics = calculate_metrics(train_res, min_trades=min_trades)

        # Criterio de optimización en entrenamiento: ranking_score
        if metrics.ranking_score > best_train_score:
            best_train_score = metrics.ranking_score
            best_params = params
            best_train_result = train_res
            best_train_metrics = metrics

    # En caso de que ninguna combinación alcance el mínimo de trades en train
    if best_train_result is None or best_train_metrics is None:
        best_params = param_grid[0]
        full_signals = strategy.generate_signals(df, best_params, allow_short=allow_short)
        best_train_result = run_backtest(
            df_train, full_signals.iloc[:train_idx],
            initial_capital, risk_pct, stop_atr_mult, rr_ratio, commission_pct, slippage_pct, max_leverage
        )
        best_train_metrics = calculate_metrics(best_train_result, min_trades=min_trades)

    # 2. VALIDACIÓN FUERA DE MUESTRA (TEST) CON LOS MEJORES PARÁMETROS FIJADOS
    best_full_signals = strategy.generate_signals(df, best_params, allow_short=allow_short)
    test_signals = best_full_signals.iloc[train_idx:]

    test_result = run_backtest(
        df=df_test,
        signals=test_signals,
        initial_capital=initial_capital,
        risk_pct=risk_pct,
        stop_atr_mult=stop_atr_mult,
        rr_ratio=rr_ratio,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
        max_leverage=max_leverage
    )

    test_metrics = calculate_metrics(test_result, min_trades=min_trades)
    status, status_reason = determine_validation_status(best_train_metrics, test_metrics, min_trades)

    return StrategyEvaluation(
        strategy_name=strategy.name,
        display_name=strategy.display_name,
        strategy_type=strategy.strategy_type,
        best_params=best_params,
        train_metrics=best_train_metrics,
        test_metrics=test_metrics,
        train_result=best_train_result,
        test_result=test_result,
        status=status,
        status_reason=status_reason,
        ranking_score=test_metrics.ranking_score
    )


def detect_market_regime(df: pd.DataFrame, window: int = 14) -> Tuple[str, float]:
    """
    Detecta el régimen de mercado actual usando ADX(14):
    - Si ADX > 25 -> 'TENDENCIA'
    - Si ADX <= 25 -> 'RANGO'
    Retorna: (régimen, valor_actual_adx)
    """
    adx_series, _, _ = calc_adx(df, period=window)
    current_adx = float(adx_series.iloc[-1])
    regime = "TENDENCIA" if current_adx > 25.0 else "RANGO"
    return regime, current_adx


def evaluate_regime_performance(
    evaluations: List[StrategyEvaluation],
    df_test: pd.DataFrame,
    current_regime: str
) -> Dict[str, Any]:
    """
    Evalúa cómo rindieron las estrategias según el régimen de mercado y si su tipo
    coincide con el régimen actual del activo.
    """
    adx_series, _, _ = calc_adx(df_test, period=14)
    # Crear máscara booleana de qué velas del tramo test correspondieron al régimen actual
    if current_regime == "TENDENCIA":
        regime_mask = (adx_series > 25.0).values
    else:
        regime_mask = (adx_series <= 25.0).values

    regime_stats = {}
    for ev in evaluations:
        test_trades = ev.test_result.trades
        trades_in_regime = []
        for t in test_trades:
            # Evaluar régimen en la vela de entrada del trade
            if t.entry_idx < len(regime_mask) and regime_mask[t.entry_idx]:
                trades_in_regime.append(t)

        n_reg = len(trades_in_regime)
        if n_reg > 0:
            exp_reg = float(np.mean([t.r_multiple for t in trades_in_regime]))
            win_reg = (sum(1 for t in trades_in_regime if t.pnl > 0) / n_reg) * 100.0
        else:
            exp_reg = 0.0
            win_reg = 0.0

        regime_stats[ev.strategy_name] = {
            'trades_count': n_reg,
            'expectancy_r': exp_reg,
            'win_rate_pct': win_reg,
            'is_congruent': (ev.strategy_type == current_regime)
        }

    return regime_stats


def run_full_pipeline(
    df: pd.DataFrame,
    train_pct: float = 0.70,
    initial_capital: float = 10000.0,
    risk_pct: float = 0.01,
    stop_atr_mult: float = 2.0,
    rr_ratio: float = 2.0,
    commission_pct: float = 0.0005,
    slippage_pct: float = 0.0002,
    max_leverage: float = 1.0,
    allow_short: bool = True,
    min_trades: int = 10,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Dict[str, Any]:
    """
    Ejecuta el pipeline completo de análisis, optimización y validación cuantitativa.
    """
    n = len(df)
    train_idx = int(n * train_pct)

    strategies = get_all_strategies()
    evaluations: List[StrategyEvaluation] = []

    total_strats = len(strategies)
    for idx, strat in enumerate(strategies):
        if progress_callback:
            progress = (idx + 1) / total_strats
            progress_callback(progress, f"Optimizando y validando: {strat.display_name}...")

        ev = optimize_and_validate_strategy(
            strategy=strat,
            df=df,
            train_idx=train_idx,
            initial_capital=initial_capital,
            risk_pct=risk_pct,
            stop_atr_mult=stop_atr_mult,
            rr_ratio=rr_ratio,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
            max_leverage=max_leverage,
            allow_short=allow_short,
            min_trades=min_trades
        )
        evaluations.append(ev)

    # Ordenar por puntaje de validación fuera de muestra (de mayor a menor)
    evaluations.sort(key=lambda x: x.ranking_score, reverse=True)

    # Régimen actual del mercado sobre las últimas velas
    current_regime, current_adx = detect_market_regime(df)

    # Desempeño en régimen
    df_test = df.iloc[train_idx:]
    regime_stats = evaluate_regime_performance(evaluations, df_test, current_regime)

    # Calcular Buy and Hold en el tramo de prueba (Out-of-Sample)
    test_close_start = float(df_test['close'].iloc[0])
    test_close_end = float(df_test['close'].iloc[-1])
    buy_and_hold_return_pct = ((test_close_end - test_close_start) / test_close_start) * 100.0

    # Curva normalizada de Buy and Hold
    buy_and_hold_curve = (df_test['close'] / test_close_start) * initial_capital

    # Determinar si hay alguna estrategia válida que pasó todos los filtros
    valid_strategies = [ev for ev in evaluations if ev.status == "OK"]
    best_strategy = valid_strategies[0] if valid_strategies else None

    # Advertencias sobre régimen para la mejor estrategia
    regime_warning = None
    if best_strategy is not None:
        best_reg_data = regime_stats.get(best_strategy.strategy_name, {})
        if not best_reg_data.get('is_congruent', True):
            regime_warning = (
                f"El mercado actual está en régimen de **{current_regime}** (ADX = {current_adx:.1f}), "
                f"mientras que la estrategia ganadora ({best_strategy.display_name}) es de tipo **{best_strategy.strategy_type}**."
            )
        elif best_reg_data.get('expectancy_r', 0) < 0:
            regime_warning = (
                f"La estrategia {best_strategy.display_name} tiene esperanza negativa ({best_reg_data.get('expectancy_r', 0):.2f}R) "
                f"durante períodos de {current_regime}."
            )

    # Señal actual de mercado con los parámetros óptimos de la mejor estrategia
    current_signal_info = None
    if best_strategy is not None:
        full_signals = get_all_strategies()[0]  # dummy
        for s in strategies:
            if s.name == best_strategy.strategy_name:
                best_s_inst = s
                break
        else:
            best_s_inst = strategies[0]

        signals_series = best_s_inst.generate_signals(df, best_strategy.best_params, allow_short=allow_short)
        last_signal = int(signals_series.iloc[-1])
        last_close = float(df['close'].iloc[-1])
        last_atr = float(calc_atr(df, 14).iloc[-1])

        stop_dist = stop_atr_mult * last_atr
        if last_signal == 1:
            direction_str = "LARGO (COMPRA)"
            stop_price = last_close - stop_dist
            tp_price = last_close + (rr_ratio * stop_dist)
        elif last_signal == -1:
            direction_str = "CORTO (VENTA)"
            stop_price = last_close + stop_dist
            tp_price = last_close - (rr_ratio * stop_dist)
        else:
            direction_str = "FUERA (NEUTRAL / SIN POSICIÓN)"
            stop_price = 0.0
            tp_price = 0.0

        # Dimensionamiento sugerido
        if last_signal != 0:
            desired_risk = initial_capital * risk_pct
            units = desired_risk / stop_dist
            max_units = (initial_capital * max_leverage) / last_close
            units = min(units, max_units)
            pos_value = units * last_close
        else:
            units = 0.0
            pos_value = 0.0

        current_signal_info = {
            'direction': last_signal,
            'direction_str': direction_str,
            'reference_price': last_close,
            'stop_price': stop_price,
            'tp_price': tp_price,
            'stop_distance': stop_dist,
            'suggested_units': units,
            'suggested_position_value': pos_value,
            'current_atr': last_atr
        }

    return {
        'evaluations': evaluations,
        'valid_strategies': valid_strategies,
        'best_strategy': best_strategy,
        'current_regime': current_regime,
        'current_adx': current_adx,
        'regime_stats': regime_stats,
        'regime_warning': regime_warning,
        'buy_and_hold_return_pct': buy_and_hold_return_pct,
        'buy_and_hold_curve': buy_and_hold_curve,
        'current_signal_info': current_signal_info,
        'train_pct': train_pct,
        'df_train': df.iloc[:train_idx],
        'df_test': df_test
    }
