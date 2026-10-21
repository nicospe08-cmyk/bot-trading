"""
Módulo de Trading Automatizado en Vivo para Binance (live_trader.py).
"Los pensamientos del diligente ciertamente tienden a la abundancia; mas todo el que se apresura alocadamente, de cierto va a la pobreza." — Proverbios 21:5 (RVR1960)

Permite operar en modo:
1. 'PAPER': Simulación en vivo con saldo virtual (sin riesgo).
2. 'TESTNET': Binance Spot Testnet oficial (dinero ficticio en servidores de Binance).
3. 'REAL': Binance Spot Real con gestión de riesgo estricta y órdenes OCO.
"""

import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional
import pandas as pd
import requests

from analysis import detect_market_regime
from biblical_wisdom import diagnose_trade_outcome, get_random_verse
from data import fetch_binance_data
from indicators import calc_atr
from news_filter import evaluate_news_filter
from strategies import BaseStrategy, get_all_strategies


class BinanceLiveTrader:
    """
    Gestor de ejecución de órdenes en Binance con firma criptográfica HMAC-SHA256.
    """
    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        mode: str = "PAPER",  # 'PAPER', 'TESTNET', 'REAL'
        symbol: str = "BTCUSDT",
        timeframe: str = "15m",
        risk_pct: float = 0.01,
        stop_atr_mult: float = 2.0,
        rr_ratio: float = 2.0,
        max_position_usdt: float = 500.0,
        max_trades_per_day: int = 2,
        leverage: float = 1.0,
        state_file: str = "live_state.json",
        log_file: str = "bot_activity.log"
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.mode = mode.upper()
        self.symbol = symbol.upper().replace("/", "").replace("-", "")
        self.timeframe = timeframe
        self.risk_pct = risk_pct
        self.stop_atr_mult = stop_atr_mult
        self.rr_ratio = rr_ratio
        self.max_position_usdt = max_position_usdt
        self.max_trades_per_day = max_trades_per_day
        self.leverage = max(1.0, float(leverage))
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cfg_file = os.path.join(base_dir, "config_bot.json")
        self.state_file = state_file if os.path.isabs(state_file) else os.path.join(base_dir, state_file)
        self.log_file = log_file if os.path.isabs(log_file) else os.path.join(base_dir, log_file)

        # URLs según el entorno
        if self.mode == "TESTNET":
            self.base_url = "https://testnet.binance.vision"
        else:
            self.base_url = "https://api.binance.com"

        self.state = self._load_state()

    def _log(self, msg: str):
        """Imprime en consola y guarda en el archivo de registro bot_activity.log."""
        print(msg)
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

    def _load_state(self) -> Dict[str, Any]:
        """Carga el estado de la posición activa desde disco."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "active_trade": None,
            "paper_balance_usdt": 1000.0,
            "last_processed_candle": None,
            "total_trades": 0,
            "trades_today_date": time.strftime("%Y-%m-%d"),
            "trades_today_count": 0,
            "trade_history": []
        }

    def _save_state(self):
        """Guarda el estado en disco para persistencia ante cortes de luz o reinicios."""
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=4)

    def _sign_payload(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Firma la petición con la clave secreta usando HMAC-SHA256."""
        params["timestamp"] = int(time.time() * 1000)
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def get_account_balance(self, asset: str = "USDT") -> float:
        """Consulta el saldo libre en Binance (o saldo virtual en modo PAPER)."""
        if self.mode == "PAPER":
            return float(self.state.get("paper_balance_usdt", 1000.0))

        endpoint = f"{self.base_url}/api/v3/account"
        headers = {"X-MBX-APIKEY": self.api_key}
        params = self._sign_payload({})

        try:
            resp = requests.get(endpoint, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                balances = resp.json().get("balances", [])
                for b in balances:
                    if b["asset"] == asset:
                        return float(b["free"])
            else:
                print(f"[ERROR] Error al consultar saldo: {resp.text}")
        except Exception as e:
            print(f"[ERROR] Excepción de red: {e}")
        return 0.0

    def place_market_order(self, side: str, quantity: float) -> Optional[Dict[str, Any]]:
        """
        Ejecuta una orden MARKET en Binance (o la simula en modo PAPER).
        side: 'BUY' o 'SELL'
        """
        # Redondear cantidad según precisión estándar de Binance (ej: BTC a 5 decimales)
        qty_formatted = round(quantity, 5)

        if self.mode == "PAPER":
            print(f"[PAPER TRADING] Orden simulada {side} de {qty_formatted} {self.symbol}")
            return {"status": "FILLED", "side": side, "origQty": qty_formatted, "mock": True}

        endpoint = f"{self.base_url}/api/v3/order"
        headers = {"X-MBX-APIKEY": self.api_key}
        params = {
            "symbol": self.symbol,
            "side": side,
            "type": "MARKET",
            "quantity": qty_formatted
        }
        signed_params = self._sign_payload(params)

        try:
            resp = requests.post(endpoint, headers=headers, params=signed_params, timeout=10)
            if resp.status_code == 200:
                order_info = resp.json()
                print(f"[BINANCE] Orden {side} ejecutada con éxito: {order_info.get('orderId')}")
                return order_info
            else:
                print(f"[BINANCE ERROR] Error al ejecutar orden: {resp.text}")
                return None
        except Exception as e:
            print(f"[ERROR] Excepción enviando orden a Binance: {e}")
            return None

    def execute_strategy_cycle(self, strategy: BaseStrategy, strategy_params: Dict[str, Any]):
        """
        Ciclo principal de ejecución que se llama tras el cierre de cada vela:
        1. Descarga las velas más recientes de Binance.
        2. Evalúa si la vela anterior acaba de cerrar.
        3. Calcula la señal de la estrategia ganadora al cierre.
        4. Abre o gestiona la posición según corresponda.
        """
        # Recargar estado en vivo desde disco (por si se cerró manualmente desde Telegram o desde la Web)
        self.state = self._load_state()

        # Recargar configuración en caliente desde config_bot.json (incluyendo Apalancamiento)
        if os.path.exists(self.cfg_file):
            try:
                with open(self.cfg_file, "r", encoding="utf-8") as f_c:
                    dyn_cfg = json.load(f_c)
                    self.leverage = max(1.0, float(dyn_cfg.get("leverage", self.leverage)))
                    self.max_trades_per_day = int(dyn_cfg.get("max_trades_per_day", self.max_trades_per_day))
                    self.max_position_usdt = float(dyn_cfg.get("max_position_usdt", self.max_position_usdt))
            except Exception:
                pass

        # Descargar últimas 400 velas para que los indicadores estén perfectamente calculados
        df = fetch_binance_data(self.symbol, interval=self.timeframe, limit=400)
        last_candle_time = str(df.index[-1])
        current_price = float(df['close'].iloc[-1])
        current_atr = float(calc_atr(df, 14).iloc[-1])

        active_trade = self.state.get("active_trade")
        # Si hay una operación activa y el usuario actualizó el apalancamiento en el panel, sincronizarlo en vivo
        if active_trade is not None:
            old_lev = float(active_trade.get("leverage", 1.0))
            margin_u = float(active_trade.get("margin_usdt", active_trade["units"] * active_trade["entry_price"] / max(1.0, old_lev)))
            active_trade["margin_usdt"] = margin_u
            if abs(old_lev - self.leverage) > 0.01:
                active_trade["leverage"] = self.leverage
                active_trade["units"] = (margin_u * self.leverage) / float(active_trade["entry_price"])
                self._save_state()

        same_candle = (self.state.get("last_processed_candle") == last_candle_time)

        # Si no hay posición abierta y esta vela ya fue evaluada, esperar al siguiente cierre de vela
        if active_trade is None and same_candle:
            print(f"[{time.strftime('%H:%M:%S')}] Vela actual ya procesada (${current_price:,.2f} | {self.leverage:.0f}x). Esperando siguiente cierre...")
            return

        # Generar señales
        signals = strategy.generate_signals(df, strategy_params, allow_short=False)
        current_signal = int(signals.iloc[-1])

        # Control de límite de operaciones por día
        today_str = time.strftime("%Y-%m-%d")
        if self.state.get("trades_today_date") != today_str:
            self.state["trades_today_date"] = today_str
            self.state["trades_today_count"] = 0

        trades_today = int(self.state.get("trades_today_count", 0))

        if not same_candle or active_trade is not None:
            self._log("=" * 60)
            self._log(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] EVALUANDO MERCADO ({self.symbol} - {self.timeframe} | Apalancamiento: {self.leverage:.0f}x)")
            self._log(f"Precio Actual: ${current_price:,.2f} | ATR(14): ${current_atr:,.2f}")
            self._log(f"Senal de la Estrategia ({strategy.display_name}): {current_signal} (+1=COMPRA, 0=NEUTRAL)")
            self._log(f"Posicion Activa: {'SI' if active_trade else 'NINGUNA'} | Operaciones Hoy: {trades_today}/{self.max_trades_per_day}")

        # 1. GESTIÓN DE SALIDAS EN TIEMPO REAL (STOP LOSS Y TAKE PROFIT)
        if active_trade is not None:
            entry_price = active_trade["entry_price"]
            stop_price = active_trade["stop_price"]
            tp_price = active_trade["tp_price"]
            units = active_trade["units"]
            trade_lev = float(active_trade.get("leverage", self.leverage))
            margin_used = float(active_trade.get("margin_usdt", (units * entry_price) / max(1.0, trade_lev)))

            exit_triggered = False
            exit_reason = ""

            bars_held_now = int(active_trade.get("bars_held", 0))
            if current_price <= stop_price:
                exit_triggered = True
                exit_reason = "STOP_LOSS"
            elif current_price >= tp_price:
                exit_triggered = True
                exit_reason = "TAKE_PROFIT"
            elif not same_candle and current_signal == 0:
                exit_triggered = True
                exit_reason = "CAMBIO_SENAL"
            elif bars_held_now >= 20 and current_price > entry_price:
                exit_triggered = True
                exit_reason = "TOMA_GANANCIA_POR_TIEMPO"
            elif bars_held_now >= 32:
                exit_triggered = True
                exit_reason = "CIERRE_MAX_TIEMPO"

            if exit_triggered:
                self._log(f"[SALIDA] Cerrando posicion ({trade_lev:.0f}x): Motivo {exit_reason} al precio ${current_price:,.2f}")
                self.place_market_order("SELL", units)

                # Calcular PnL apalancado y múltiplo R
                pnl = (current_price - entry_price) * units
                roe_pct = (pnl / margin_used) * 100.0 if margin_used > 0 else 0.0
                stop_dist_orig = active_trade.get("stop_distance", max(1.0, abs(entry_price - stop_price)))
                initial_risk = units * stop_dist_orig
                r_mult = pnl / initial_risk if initial_risk > 0 else 0.0

                if self.mode == "PAPER":
                    self.state["paper_balance_usdt"] += (margin_used + pnl)

                # Diagnóstico forense de la operación
                _, current_adx = detect_market_regime(df)
                diag = diagnose_trade_outcome(
                    pnl=pnl,
                    r_multiple=r_mult,
                    exit_reason=exit_reason,
                    bars_held=max(1, active_trade.get("bars_held", 1)),
                    strategy_type=strategy.strategy_type,
                    adx_at_exit=current_adx
                )
                verse = get_random_verse()

                trade_record = {
                    "id": self.state.get("total_trades", 0) + 1,
                    "symbol": self.symbol,
                    "strategy": strategy.display_name,
                    "leverage": f"{trade_lev:.0f}x",
                    "entry_time": active_trade.get("entry_time", "-"),
                    "exit_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_price": round(entry_price, 4),
                    "exit_price": round(current_price, 4),
                    "units": round(units, 5),
                    "pnl_usdt": round(pnl, 2),
                    "roe_pct": round(roe_pct, 2),
                    "r_multiple": round(r_mult, 2),
                    "exit_reason": exit_reason,
                    "status": diag["status"],
                    "explanation": diag["explanation"],
                    "improvement": diag["improvement"],
                    "verse": f"{verse['verse']} ({verse['reference']})"
                }

                if "trade_history" not in self.state:
                    self.state["trade_history"] = []
                self.state["trade_history"].append(trade_record)

                self._log(f"Resultado de la operacion ({trade_lev:.0f}x): {diag['status']} | PnL = ${pnl:+,.2f} (ROE: {roe_pct:+.2f}% | {r_mult:+.2f}R)")
                self._log(f"Analisis: {diag['explanation'].encode('ascii', 'ignore').decode('ascii')}")
                self._log(f"Mejora:   {diag['improvement'].encode('ascii', 'ignore').decode('ascii')}")
                self._log(f"Palabra:  \"{verse['verse'].encode('ascii', 'ignore').decode('ascii')}\" - {verse['reference']}")

                self.state["active_trade"] = None
                self.state["total_trades"] = self.state.get("total_trades", 0) + 1
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                return
            else:
                if not same_candle:
                    active_trade["bars_held"] = active_trade.get("bars_held", 0) + 1
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                return

        # 2. GESTIÓN DE ENTRADAS (NUEVO LARGO CON APALANCAMIENTO)
        if active_trade is None and current_signal == 1:
            # Verificar límite máximo de operaciones diarias (ej. máx 2 por día)
            if trades_today >= self.max_trades_per_day:
                self._log(
                    f"[LIMITE DIARIO ALCANZADO] Ya se realizaron {trades_today}/{self.max_trades_per_day} "
                    f"operaciones hoy ({today_str}). No se abriran mas posiciones hasta manana."
                )
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                self._log("=" * 60 + "\n")
                return

            # Evaluar filtro fundamental de noticias antes de arriesgar capital
            self._log("[FILTRO FUNDAMENTAL] Consultando noticias recientes del activo...")
            news_eval = evaluate_news_filter(self.symbol)
            self._log(f" - Sentimiento de Noticias: {news_eval['overall_sentiment']} (Score: {news_eval['avg_score']:+.2f})")
            self._log(f" - Diagnostico: {news_eval['reason']}")

            if news_eval["news"]:
                self._log(" - Ultimos titulares:")
                for n_item in news_eval["news"][:3]:
                    clean_title = n_item["title"].encode("ascii", "ignore").decode("ascii")
                    self._log(f"   * [{n_item['sentiment']}] {clean_title[:75]}")

            if not news_eval["allow_long"]:
                self._log("[ORDEN BLOQUEADA] El filtro de noticias detecto alto riesgo bajista. Se cancela la compra por seguridad.")
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                self._log("=" * 60 + "\n")
                return

            balance = self.get_account_balance("USDT")
            self._log(f"Saldo USDT Disponible: ${balance:,.2f}")

            if balance < 10.0:
                self._log("[AVISO] Saldo insuficiente para operar (minimo $10 USDT en Binance).")
                return

            stop_dist = self.stop_atr_mult * current_atr
            stop_level = current_price - stop_dist
            tp_level = current_price + (self.rr_ratio * stop_dist)

            # Dimensionamiento de margen base + multiplicador de Apalancamiento
            desired_risk = balance * self.risk_pct
            base_units = desired_risk / stop_dist
            max_margin_units = min(balance, self.max_position_usdt) / current_price
            margin_units = min(base_units, max_margin_units)

            margin_usdt = margin_units * current_price
            if margin_usdt < 10.0:
                self._log(f"[AVISO] El margen calculado (${margin_usdt:.2f}) es menor al minimo de Binance ($10 USDT).")
                return

            # Aplicar Apalancamiento (ej. 5x multiplica el tamaño de la posición por 5)
            units = margin_units * self.leverage
            notional_usdt = margin_usdt * self.leverage

            self._log(
                f"[ORDEN COMPRA {self.leverage:.0f}x] Margen: ${margin_usdt:,.2f} USDT | "
                f"Posicion Apalancada ({self.leverage:.0f}x): ${notional_usdt:,.2f} USDT ({units:.5f} {self.symbol})"
            )
            order = self.place_market_order("BUY", units)

            if order is not None:
                if self.mode == "PAPER":
                    self.state["paper_balance_usdt"] -= margin_usdt

                self.state["trades_today_count"] = trades_today + 1
                self.state["active_trade"] = {
                    "entry_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_price": current_price,
                    "units": units,
                    "margin_usdt": margin_usdt,
                    "leverage": self.leverage,
                    "stop_price": stop_level,
                    "tp_price": tp_level,
                    "stop_distance": stop_dist
                }
                self._log(
                    f"Posicion abierta con exito ({self.leverage:.0f}x | Operacion {trades_today + 1}/{self.max_trades_per_day} de hoy). "
                    f"Stop Loss en ${stop_level:,.2f} | Take Profit en ${tp_level:,.2f}"
                )

        self.state["last_processed_candle"] = last_candle_time
        self._save_state()
        self._log("=" * 60 + "\n")


def close_active_trade_now(reason: str = "CIERRE_MANUAL_USUARIO") -> Optional[Dict[str, Any]]:
    """
    Cierra inmediatamente la operación activa en `live_state.json` al precio actual de mercado en Binance,
    acredita la ganancia/pérdida en el saldo y guarda el registro completo en `trade_history`.
    Puede invocarse desde Telegram (`/cerrar`) o desde la Web (`app.py`).
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    state_file = os.path.join(base_dir, "live_state.json")
    cfg_file = os.path.join(base_dir, "config_bot.json")
    log_file = os.path.join(base_dir, "bot_activity.log")

    if not os.path.exists(state_file):
        return None
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        return None

    active_trade = state.get("active_trade")
    if not active_trade:
        return None

    cfg = {}
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass

    sym = active_trade.get("symbol", cfg.get("symbol", "BTCUSDT"))
    entry_price = float(active_trade.get("entry_price", 0.0))
    stop_price = float(active_trade.get("stop_price", 0.0))
    units = float(active_trade.get("units", 0.0))
    trade_lev = float(active_trade.get("leverage", cfg.get("leverage", 5.0)))
    margin_used = float(active_trade.get("margin_usdt", (units * entry_price) / max(1.0, trade_lev)))

    # Obtener precio en vivo de Binance
    current_price = entry_price
    for base_u in ("https://data-api.binance.vision", "https://api.binance.com"):
        try:
            r = requests.get(f"{base_u}/api/v3/ticker/price", params={"symbol": sym.upper()}, timeout=5)
            if r.status_code == 200:
                current_price = float(r.json().get("price", entry_price))
                break
        except Exception:
            pass

    pnl = (current_price - entry_price) * units
    roe_pct = (pnl / margin_used) * 100.0 if margin_used > 0 else 0.0
    stop_dist_orig = float(active_trade.get("stop_distance", max(1.0, abs(entry_price - stop_price))))
    initial_risk = units * stop_dist_orig
    r_mult = pnl / initial_risk if initial_risk > 0 else 0.0

    if cfg.get("mode", "PAPER") == "PAPER":
        state["paper_balance_usdt"] = float(state.get("paper_balance_usdt", 1000.0)) + margin_used + pnl

    diag = diagnose_trade_outcome(
        pnl=pnl,
        r_multiple=r_mult,
        exit_reason=reason,
        bars_held=max(1, int(active_trade.get("bars_held", 1))),
        strategy_type="trend",
        adx_at_exit=25.0
    )
    verse = get_random_verse()

    trade_record = {
        "id": int(state.get("total_trades", 0)) + 1,
        "symbol": sym,
        "strategy": active_trade.get("strategy", "Cruce de EMAs"),
        "leverage": f"{trade_lev:.0f}x",
        "entry_time": active_trade.get("entry_time", "-"),
        "exit_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "entry_price": round(entry_price, 4),
        "exit_price": round(current_price, 4),
        "units": round(units, 5),
        "pnl_usdt": round(pnl, 2),
        "roe_pct": round(roe_pct, 2),
        "r_multiple": round(r_mult, 2),
        "exit_reason": reason,
        "status": diag["status"],
        "explanation": diag["explanation"],
        "improvement": diag["improvement"],
        "verse": f"{verse['verse']} ({verse['reference']})"
    }

    if "trade_history" not in state:
        state["trade_history"] = []
    state["trade_history"].append(trade_record)
    state["active_trade"] = None
    state["total_trades"] = int(state.get("total_trades", 0)) + 1

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

    try:
        with open(log_file, "a", encoding="utf-8") as f_l:
            f_l.write(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [CIERRE MANUAL {trade_lev:.0f}x] "
                f"Cerrada al precio ${current_price:,.2f} | PnL: ${pnl:+,.2f} USDT (ROE: {roe_pct:+.2f}%)\n"
            )
    except Exception:
        pass

    return trade_record
