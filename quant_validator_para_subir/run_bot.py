"""
Ejecutor Continuo 24/7 del Bot de Trading Automatizado (run_bot.py).

"Encomienda a Jehová tus obras, y tus pensamientos serán afirmados." — Proverbios 16:3 (RVR1960)
"Los pensamientos del diligente ciertamente tiertamente tienden a la abundancia;
 Mas todo el que se apresura alocadamente, de cierto va a la pobreza." — Proverbios 21:5 (RVR1960)

- Lee su configuración automáticamente desde config_bot.json (sin necesidad de activación manual).
- Limita las operaciones a un máximo de 2 trades por día (configurable).
- Re-evalúa y valida las estrategias automáticamente cada 6 horas.
- Inicia automáticamente el hilo de la App Móvil de Telegram (telegram_bot.py) para consultar desde el celular.
"""

import json
import os
import sys
import threading
import time

from analysis import run_full_pipeline
from biblical_wisdom import get_random_verse
from data import fetch_binance_data
from live_trader import BinanceLiveTrader
from strategies import get_all_strategies
from telegram_bot import run_telegram_listener

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config_bot.json")
HEARTBEAT_FILE = os.path.join(BASE_DIR, "bot_heartbeat.json")


def update_heartbeat(source: str = "standalone"):
    try:
        with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_beat": time.time(), "source": source}, f)
    except Exception:
        pass


def is_bot_recently_active(max_age_sec: float = 65.0) -> bool:
    if not os.path.exists(HEARTBEAT_FILE):
        return False
    try:
        with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (time.time() - float(data.get("last_beat", 0))) < max_age_sec
    except Exception:
        return False


def load_bot_config() -> dict:
    default_cfg = {
        "mode": "PAPER",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "max_trades_per_day": 2,
        "risk_pct": 0.01,
        "stop_atr_mult": 2.0,
        "rr_ratio": 2.0,
        "max_position_usdt": 250.0,
        "binance_api_key": "",
        "binance_api_secret": ""
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
                default_cfg.update(user_cfg)
        except Exception as e:
            print(f"[AVISO] Error leyendo config_bot.json, usando valores por defecto: {e}")
    return default_cfg


def select_best_validated_strategy(symbol: str, timeframe: str, risk_pct: float, stop_atr: float, rr_ratio: float):
    """
    Descarga datos frescos y ejecuta el validador cuantitativo para elegir la mejor estrategia.
    Si el mercado estuvo lateral en el tramo corto y ninguna pasa el filtro OOS estricto,
    selecciona de forma adaptativa la mejor estrategia con ventaja en entrenamiento y señal activa
    para que el bot no se quede congelado sin operar.
    """
    df = fetch_binance_data(symbol=symbol, interval=timeframe, limit=1000)
    val_res = run_full_pipeline(
        df=df,
        train_pct=0.70,
        initial_capital=10000.0,
        risk_pct=risk_pct,
        stop_atr_mult=stop_atr,
        rr_ratio=rr_ratio,
        commission_pct=0.0005,
        slippage_pct=0.0002,
        allow_short=False,
        min_trades=3
    )
    all_strats = get_all_strategies()
    evaluations = val_res.get("evaluations", [])
    best_strict = val_res.get("best_strategy")

    if best_strict is not None:
        return best_strict, True

    # Selección adaptativa: priorizar estrategias con señal activa (+1) y mejor esperanza combinada
    scored_candidates = []
    for ev in evaluations:
        strat_inst = next(s for s in all_strats if s.name == ev.strategy_name)
        sig_series = strat_inst.generate_signals(df, ev.best_params, allow_short=False)
        last_sig = int(sig_series.iloc[-1])
        combined_exp = (ev.train_metrics.expectancy_r * 0.6) + (ev.test_metrics.expectancy_r * 0.4)
        scored_candidates.append((last_sig == 1, combined_exp, ev))

    # Ordenar primero por tener señal activa hoy (True > False) y luego por mayor esperanza combinada
    scored_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored_candidates[0][2], False


def main():
    cfg = load_bot_config()

    # Permitir sobrescribir por variables de entorno si existen
    SYMBOL = os.environ.get("TRADING_SYMBOL", cfg["symbol"]).upper()
    TIMEFRAME = os.environ.get("TRADING_TIMEFRAME", cfg["timeframe"])
    MODE = os.environ.get("TRADING_MODE", cfg["mode"]).upper()
    MAX_TRADES_DAY = int(os.environ.get("TRADING_MAX_DAILY", cfg.get("max_trades_per_day", 2)))

    BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", cfg.get("binance_api_key", ""))
    BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET", cfg.get("binance_api_secret", ""))

    RISK_PCT = float(os.environ.get("TRADING_RISK_PCT", cfg["risk_pct"]))
    STOP_ATR_MULT = float(os.environ.get("TRADING_STOP_ATR", cfg["stop_atr_mult"]))
    RR_RATIO = float(os.environ.get("TRADING_RR_RATIO", cfg["rr_ratio"]))
    MAX_POSITION_USDT = float(os.environ.get("TRADING_MAX_USDT", cfg["max_position_usdt"]))
    LEVERAGE = float(os.environ.get("TRADING_LEVERAGE", cfg.get("leverage", 5.0)))

    trader = BinanceLiveTrader(
        api_key=BINANCE_API_KEY,
        api_secret=BINANCE_API_SECRET,
        mode=MODE,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        risk_pct=RISK_PCT,
        stop_atr_mult=STOP_ATR_MULT,
        rr_ratio=RR_RATIO,
        max_position_usdt=MAX_POSITION_USDT,
        max_trades_per_day=MAX_TRADES_DAY,
        leverage=LEVERAGE
    )

    v = get_random_verse()
    verse_ascii = f'"{v["verse"]}" - {v["reference"]}'.encode("ascii", "ignore").decode("ascii")

    trader._log("=" * 70)
    trader._log("   BOT DE TRADING AUTOMATICO 24/7 INICIADO (AUTONOMO)")
    trader._log(f"   [PALABRA DE SABIDURIA] {verse_ascii}")
    trader._log("=" * 70)
    trader._log(f" - Modo:                 {MODE} ({'DINERO VIRTUAL' if MODE == 'PAPER' else 'BINANCE REAL'})")
    trader._log(f" - Par:                  {SYMBOL} ({TIMEFRAME})")
    trader._log(f" - Apalancamiento:       {LEVERAGE:.0f}x")
    trader._log(f" - Maximo Trades / Dia:  {MAX_TRADES_DAY} operaciones por dia")
    trader._log(f" - Riesgo por Operacion: {RISK_PCT * 100:.1f}%")
    trader._log(f" - Stop / Take Profit:   {STOP_ATR_MULT}x ATR / {RR_RATIO}:1 RR")
    trader._log("=" * 70)

    # Iniciar hilo secundario para la App Movil de Telegram (sin sitio web)
    tg_thread = threading.Thread(target=run_telegram_listener, daemon=True)
    tg_thread.start()

    all_strats = get_all_strategies()
    active_strat_instance = None
    best_params = None
    last_validation_time = 0.0
    VALIDATION_INTERVAL_SECONDS = 6 * 3600  # Re-validar estrategia cada 6 horas

    sleep_interval = 25  # Segundos entre chequeos de vela

    try:
        while True:
            now = time.time()
            update_heartbeat(source="run_bot")

            # Recargar apalancamiento y límites dinámicos por si se actualizaron desde la Web
            latest_cfg = load_bot_config()
            trader.leverage = float(latest_cfg.get("leverage", trader.leverage))
            trader.max_trades_per_day = int(latest_cfg.get("max_trades_per_day", trader.max_trades_per_day))

            # Re-validar cada 15 min si no hay operación abierta (para detectar nuevas señales activas) o cada 6h si hay trade en curso
            reval_wait = VALIDATION_INTERVAL_SECONDS if trader.state.get("active_trade") is not None else 900
            if (now - last_validation_time) > reval_wait:
                try:
                    trader._log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ejecutando validacion cuantitativa de estrategias...")
                    best_eval, is_strict = select_best_validated_strategy(SYMBOL, TIMEFRAME, RISK_PCT, STOP_ATR_MULT, RR_RATIO)
                    last_validation_time = now

                    if best_eval is not None:
                        active_strat_instance = next(s for s in all_strats if s.name == best_eval.strategy_name)
                        best_params = best_eval.best_params
                        mode_tag = "VALIDADA OOS" if is_strict else "ADAPTATIVA (MEJOR RANKING)"
                        disp_ascii = best_eval.display_name.encode("ascii", "ignore").decode("ascii")
                        trader._log(
                            f"[ESTRATEGIA ACTIVA - {mode_tag}] {disp_ascii} | Params: {best_params} | "
                            f"Train: {best_eval.train_metrics.expectancy_r:+.2f}R | Test: {best_eval.test_metrics.expectancy_r:+.2f}R"
                        )
                except Exception as e:
                    trader._log(f"[ERROR EN VALIDACION] {e}")

            # Ejecutar ciclo si hay estrategia validada (o si hay un trade abierto que gestionar)
            if active_strat_instance is not None and best_params is not None:
                try:
                    trader.execute_strategy_cycle(active_strat_instance, best_params)
                except Exception as e:
                    trader._log(f"[ERROR EN CICLO] {e}")

            time.sleep(sleep_interval)

    except KeyboardInterrupt:
        trader._log("\n[BOT DETENIDO MANUALMENTE] Estado guardado en live_state.json.")


_EMBEDDED_LOCK = threading.Lock()
_EMBEDDED_STARTED = False


def start_embedded_bot_if_needed():
    """
    Si el proyecto corre en la Nube (Streamlit Cloud / Render / Railway) donde solo se ejecuta `streamlit run app.py`,
    o si en la PC no está corriendo `run_bot.py` por separado, lanza automáticamente el motor 24/7 + Telegram
    dentro de un hilo daemon para que siempre esté activo sin depender de una consola abierta.
    """
    global _EMBEDDED_STARTED
    with _EMBEDDED_LOCK:
        if _EMBEDDED_STARTED or is_bot_recently_active(max_age_sec=65.0):
            return False
        _EMBEDDED_STARTED = True
        t = threading.Thread(target=main, daemon=True, name="EmbeddedBot24x7")
        t.start()
        return True


if __name__ == "__main__":
    main()
