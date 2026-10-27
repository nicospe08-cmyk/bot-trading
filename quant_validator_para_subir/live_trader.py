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
import math
import os
import time
import urllib.parse
from typing import Any, Dict, Optional
import pandas as pd
import requests

from datetime import datetime, timezone, timedelta
from analysis import detect_market_regime
from biblical_wisdom import diagnose_trade_outcome, get_random_verse
from data import fetch_binance_data
from indicators import calc_atr, calc_rsi
from news_filter import evaluate_news_filter
from strategies import BaseStrategy, get_all_strategies

# Horarios institucionales en UTC y su equivalencia en Hora Argentina (UTC-3)
SESSION_MODES: Dict[str, Dict[str, Any]] = {
    "TODAS_24_7": {
        "label": "🌐 Todas las Sesiones (24/7 Continuo)",
        "short": "🌐 24/7 Continuo",
        "hours_utc": list(range(0, 24)),
        "horario_arg": "00:00 a 24:00 hs (ARG)"
    },
    "LONDRES": {
        "label": "🇬🇧 Sesión Londres (04:00 a 12:00 hs ARG)",
        "short": "🇬🇧 Sesión Londres",
        "hours_utc": list(range(7, 15)),  # 07:00 a 15:00 UTC = 04:00 a 12:00 ARG
        "horario_arg": "04:00 a 12:00 hs (ARG)"
    },
    "NUEVA_YORK": {
        "label": "🇺🇸 Sesión Nueva York (09:00 a 17:00 hs ARG)",
        "short": "🇺🇸 Sesión Nueva York",
        "hours_utc": list(range(12, 20)),  # 12:00 a 20:00 UTC = 09:00 a 17:00 ARG
        "horario_arg": "09:00 a 17:00 hs (ARG)"
    },
    "LONDRES_NY": {
        "label": "🇬🇧+🇺🇸 Londres y Nueva York (04:00 a 17:00 hs ARG)",
        "short": "🇬🇧+🇺🇸 Londres + NY",
        "hours_utc": list(range(7, 20)),  # 07:00 a 20:00 UTC = 04:00 a 17:00 ARG
        "horario_arg": "04:00 a 17:00 hs (ARG)"
    },
    "OVERLAP_LONDRES_NY": {
        "label": "🔥 Overlap Londres + NY (09:00 a 12:00 hs ARG)",
        "short": "🔥 Overlap Londres-NY",
        "hours_utc": list(range(12, 15)),  # 12:00 a 15:00 UTC = 09:00 a 12:00 ARG
        "horario_arg": "09:00 a 12:00 hs (ARG)"
    },
    "ASIA": {
        "label": "🇯🇵 Sesión Asia / Tokio (20:00 a 04:00 hs ARG)",
        "short": "🇯🇵 Sesión Asia",
        "hours_utc": [23, 0, 1, 2, 3, 4, 5, 6],  # 23:00 a 07:00 UTC = 20:00 a 04:00 ARG
        "horario_arg": "20:00 a 04:00 hs (ARG)"
    }
}


def evaluate_trading_session(session_mode: str = "TODAS_24_7") -> Dict[str, Any]:
    """
    Evalúa en tiempo real qué sesiones institucionales (Londres, Nueva York, Asia)
    están abiertas ahora mismo y si el modo de sesión elegido permite abrir operaciones.
    """
    now_utc = datetime.now(timezone.utc)
    now_arg = now_utc - timedelta(hours=3)
    h_utc = now_utc.hour

    london_open = 7 <= h_utc < 15
    ny_open = 12 <= h_utc < 20
    overlap_open = 12 <= h_utc < 15
    asia_open = (h_utc >= 23 or h_utc < 7)

    mode_key = session_mode if session_mode in SESSION_MODES else "TODAS_24_7"
    mode_info = SESSION_MODES[mode_key]
    allowed_now = h_utc in mode_info["hours_utc"]

    active_names = []
    if london_open:
        active_names.append("🇬🇧 Londres")
    if ny_open:
        active_names.append("🇺🇸 Nueva York")
    if asia_open:
        active_names.append("🇯🇵 Asia/Tokio")
    if not active_names:
        active_names.append("🕒 Transición NY ➔ Asia")

    return {
        "mode_key": mode_key,
        "mode_label": mode_info["label"],
        "mode_short": mode_info["short"],
        "horario_arg": mode_info["horario_arg"],
        "allowed_now": allowed_now,
        "arg_time": now_arg.strftime("%H:%M:%S"),
        "utc_time": now_utc.strftime("%H:%M:%S"),
        "london_open": london_open,
        "ny_open": ny_open,
        "overlap_open": overlap_open,
        "asia_open": asia_open,
        "active_sessions_str": " + ".join(active_names)
    }


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
        session_mode: str = "TODAS_24_7",
        market_type: str = "FUTURES",
        min_adx_filter: float = 22.0,
        allow_short: bool = True,
        state_file: str = "live_state.json",
        log_file: str = "bot_activity.log"
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.mode = mode.upper()
        self.market_type = market_type.upper() if market_type else "FUTURES"
        self.allow_short = bool(allow_short) if self.market_type == "FUTURES" else False
        self.symbol = symbol.upper().replace("/", "").replace("-", "")
        self.timeframe = timeframe
        self.risk_pct = risk_pct
        self.stop_atr_mult = stop_atr_mult
        self.rr_ratio = rr_ratio
        self.max_position_usdt = max_position_usdt
        self.max_trades_per_day = max_trades_per_day
        self.leverage = max(1.0, float(leverage))
        self.session_mode = session_mode
        self.min_adx_filter = float(min_adx_filter)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cfg_file = os.path.join(base_dir, "config_bot.json")
        self.state_file = state_file if os.path.isabs(state_file) else os.path.join(base_dir, state_file)
        self.log_file = log_file if os.path.isabs(log_file) else os.path.join(base_dir, log_file)

        # URLs según el entorno
        if self.market_type == "FUTURES":
            self.base_url = "https://fapi.binance.com"
        elif self.mode == "TESTNET":
            self.base_url = "https://testnet.binance.vision"
        else:
            self.base_url = "https://api.binance.com"

        self.state = self._load_state()

        if self.mode == "REAL" and self.market_type == "FUTURES" and self.api_key and self.api_secret:
            self._setup_futures_leverage_and_margin()

    def _setup_futures_leverage_and_margin(self):
        """Configura el apalancamiento deseado (ej: 15x) y el tipo de margen AISLADO (ISOLATED) en Binance Futuros."""
        if not self.api_key or not self.api_secret:
            return
        lev_val = int(round(self.leverage))
        try:
            # 1. Configurar apalancamiento
            lev_endpoint = f"{self.base_url}/fapi/v1/leverage"
            headers = {"X-MBX-APIKEY": self.api_key}
            p_lev = self._sign_payload({"symbol": self.symbol, "leverage": lev_val})
            r_lev = requests.post(lev_endpoint, headers=headers, params=p_lev, timeout=8)
            if r_lev.status_code == 200:
                self._log(f"[BINANCE FUTUROS] Apalancamiento fijado en {lev_val}x para {self.symbol}.")
            else:
                self._log(f"[BINANCE FUTUROS AVISO] Respuesta fijando apalancamiento: {r_lev.text}")
        except Exception as e_l:
            self._log(f"[BINANCE FUTUROS ERROR LEVERAGE] {e_l}")

        try:
            # 2. Configurar margen AISLADO (ISOLATED)
            mt_endpoint = f"{self.base_url}/fapi/v1/marginType"
            headers = {"X-MBX-APIKEY": self.api_key}
            p_mt = self._sign_payload({"symbol": self.symbol, "marginType": "ISOLATED"})
            r_mt = requests.post(mt_endpoint, headers=headers, params=p_mt, timeout=8)
            if r_mt.status_code == 200:
                self._log(f"[BINANCE FUTUROS] Margen AISLADO (ISOLATED) configurado con éxito.")
            elif "-4046" in r_mt.text:
                self._log(f"[BINANCE FUTUROS] Margen AISLADO ya activo previamente.")
        except Exception as e_m:
            self._log(f"[BINANCE FUTUROS ERROR MARGIN TYPE] {e_m}")

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

    def get_futures_position_info(self) -> Optional[Dict[str, Any]]:
        """
        Consulta la posición real abierta en Binance Futuros USD-M para el símbolo activo.
        Retorna diccionario con positionAmt, entryPrice, unRealizedProfit, leverage, etc.
        """
        if self.market_type != "FUTURES" or not self.api_key:
            return None
        endpoint = f"{self.base_url}/fapi/v2/positionRisk"
        headers = {"X-MBX-APIKEY": self.api_key}
        params = self._sign_payload({"symbol": self.symbol})
        try:
            r = requests.get(endpoint, headers=headers, params=params, timeout=8)
            if r.status_code == 200:
                for p in r.json():
                    if p.get("symbol") == self.symbol:
                        amt = float(p.get("positionAmt", 0.0))
                        return {
                            "symbol": self.symbol,
                            "positionAmt": amt,
                            "entryPrice": float(p.get("entryPrice", 0.0)),
                            "markPrice": float(p.get("markPrice", 0.0)),
                            "unRealizedProfit": float(p.get("unRealizedProfit", 0.0)),
                            "leverage": float(p.get("leverage", self.leverage)),
                            "isolatedMargin": float(p.get("isolatedMargin", 0.0)),
                            "liquidationPrice": float(p.get("liquidationPrice", 0.0))
                        }
        except Exception as e:
            print(f"[ERROR FUTURES POSITION INFO] {e}")
        return None

    def get_futures_position_amt(self) -> float:
        """Obtiene la cantidad neta de la posición abierta en Futuros (ej: 0.001 BTC)."""
        info = self.get_futures_position_info()
        return abs(info["positionAmt"]) if info else 0.0

    def get_account_balance(self, asset: str = "USDT") -> float:
        """Consulta el saldo libre en Binance Futuros, Spot o Paper."""
        if self.mode == "PAPER":
            return float(self.state.get("paper_balance_usdt", 1000.0))

        if self.market_type == "FUTURES":
            endpoint = f"{self.base_url}/fapi/v2/balance"
            headers = {"X-MBX-APIKEY": self.api_key}
            params = self._sign_payload({})
            try:
                resp = requests.get(endpoint, headers=headers, params=params, timeout=10)
                if resp.status_code == 200:
                    for b in resp.json():
                        if b.get("asset") == asset:
                            avail = float(b.get("availableBalance", b.get("balance", 0.0)))
                            if asset == "USDT":
                                self.state["real_balance_usdt"] = avail
                            return avail
            except Exception as e:
                print(f"[ERROR FUTURES BALANCE] {e}")
            return float(self.state.get("real_balance_usdt", 0.0))

        endpoint = f"{self.base_url}/api/v3/account"
        headers = {"X-MBX-APIKEY": self.api_key}
        params = self._sign_payload({})

        try:
            resp = requests.get(endpoint, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                balances = resp.json().get("balances", [])
                spot_bal = 0.0
                ld_bal = 0.0
                for b in balances:
                    a = b["asset"]
                    if a == asset:
                        spot_bal = float(b.get("free", 0.0))
                    elif a == f"LD{asset}":
                        ld_bal = float(b.get("free", 0.0))

                total_bal = spot_bal + ld_bal

                # Si el saldo Spot es menor al mínimo de $10 USDT pero hay en Earn Flexible, auto-rescatar a Spot
                if asset == "USDT" and spot_bal < 10.0 and total_bal >= 10.0:
                    self._log(f"[AUTO-RESCATE] Spot tiene ${spot_bal:.2f} USDT y Earn tiene ${ld_bal:.2f} USDT. Rescatando fondos a Spot...")
                    auto_redeem_simple_earn(self.api_key, self.api_secret, amount=min(total_bal, 11.0))
                    spot_bal = total_bal

                if asset == "USDT":
                    self.state["real_balance_usdt"] = total_bal

                return total_bal if asset == "USDT" else spot_bal
            else:
                print(f"[ERROR] Error al consultar saldo: {resp.text}")
        except Exception as e:
            print(f"[ERROR] Excepción de red: {e}")
        return float(self.state.get("real_balance_usdt", 0.0))

    def place_market_order(self, side: str, quantity: float, quote_order_qty: Optional[float] = None, reduce_only: bool = False) -> Optional[Dict[str, Any]]:
        """
        Ejecuta una orden MARKET en Binance (Spot o Futuros) o la simula en modo PAPER.
        side: 'BUY' o 'SELL'
        """
        step_dec = 3 if self.market_type == "FUTURES" else 5
        qty_formatted = round(quantity, step_dec)

        if self.mode == "PAPER":
            self._log(f"[PAPER TRADING] Orden simulada {side} de {qty_formatted} {self.symbol} ({self.leverage:.0f}x)")
            return {"status": "FILLED", "side": side, "origQty": qty_formatted, "mock": True}

        if self.market_type == "FUTURES":
            endpoint = f"{self.base_url}/fapi/v1/order"
            headers = {"X-MBX-APIKEY": self.api_key}
            params: Dict[str, Any] = {
                "symbol": self.symbol,
                "side": side,
                "type": "MARKET",
                "quantity": f"{qty_formatted:.3f}"
            }
            if reduce_only:
                params["reduceOnly"] = "true"

            signed_params = self._sign_payload(params)
            try:
                resp = requests.post(endpoint, headers=headers, params=signed_params, timeout=10)
                if resp.status_code == 200:
                    order_info = resp.json()
                    self._log(f"[BINANCE FUTUROS] Orden {side} ejecutada con exito: ID={order_info.get('orderId')} (Status: {order_info.get('status')})")
                    return order_info
                else:
                    self._log(f"[BINANCE FUTUROS ERROR] Error al ejecutar orden {side}: {resp.text}")
                    return None
            except Exception as e:
                self._log(f"[ERROR] Excepcion enviando orden a Binance Futuros: {e}")
                return None

        endpoint = f"{self.base_url}/api/v3/order"
        headers = {"X-MBX-APIKEY": self.api_key}
        params: Dict[str, Any] = {
            "symbol": self.symbol,
            "side": side,
            "type": "MARKET"
        }

        # En Binance Spot REAL SELL: intentar Binance Convert para liquidar el 100% sin polvo ni rechazo
        if side == "SELL" and self.mode == "REAL":
            base_asset = self.symbol.replace("USDT", "").replace("USDC", "").replace("BUSD", "")
            actual_free = self.get_account_balance(base_asset)

            if actual_free > 0:
                try:
                    c_quote_params = {
                        "fromAsset": base_asset,
                        "toAsset": "USDT",
                        "fromAmount": str(actual_free),
                        "timestamp": int(time.time() * 1000)
                    }
                    c_query = "&".join([f"{k}={v}" for k, v in c_quote_params.items()])
                    c_quote_params["signature"] = hmac.new(self.api_secret.encode(), c_query.encode(), hashlib.sha256).hexdigest()
                    c_q_resp = requests.post("https://api.binance.com/sapi/v1/convert/getQuote", headers=headers, params=c_quote_params, timeout=8)
                    if c_q_resp.status_code == 200:
                        c_q_data = c_q_resp.json()
                        c_qid = c_q_data.get("quoteId")
                        if c_qid:
                            c_acc_params = {
                                "quoteId": c_qid,
                                "timestamp": int(time.time() * 1000)
                            }
                            c_acc_query = "&".join([f"{k}={v}" for k, v in c_acc_params.items()])
                            c_acc_params["signature"] = hmac.new(self.api_secret.encode(), c_acc_query.encode(), hashlib.sha256).hexdigest()
                            c_acc_resp = requests.post("https://api.binance.com/sapi/v1/convert/acceptQuote", headers=headers, params=c_acc_params, timeout=8)
                            if c_acc_resp.status_code == 200:
                                self._log(f"[BINANCE CONVERT] Salida completada al 100% sin polvo: {actual_free} {base_asset} -> {c_q_data.get('toAmount')} USDT")
                                return {"status": "FILLED", "orderId": c_acc_resp.json().get("orderId"), "side": "SELL"}
                except Exception as e_conv:
                    self._log(f"[CONVERT FALLBACK] Error al usar Convert: {e_conv}. Usando Market Order normal...")

            sell_qty = math.floor(min(quantity, actual_free if actual_free > 0 else quantity) * 100000) / 100000
            params["quantity"] = f"{sell_qty:.5f}"
        # En Binance Spot REAL BUY: usar quoteOrderQty para gastar el monto exacto en USDT (ej: 10.0 USDT)
        elif side == "BUY" and quote_order_qty is not None and quote_order_qty >= 5.0:
            params["quoteOrderQty"] = round(quote_order_qty, 2)
        else:
            params["quantity"] = qty_formatted

        signed_params = self._sign_payload(params)

        try:
            resp = requests.post(endpoint, headers=headers, params=signed_params, timeout=10)
            if resp.status_code == 200:
                order_info = resp.json()
                self._log(f"[BINANCE] Orden {side} ejecutada con exito: ID={order_info.get('orderId')} (Status: {order_info.get('status')})")
                return order_info
            else:
                self._log(f"[BINANCE ERROR] Error al ejecutar orden {side}: {resp.text}")
                return None
        except Exception as e:
            self._log(f"[ERROR] Excepcion enviando orden a Binance: {e}")
            return None

    def place_futures_algo_order(self, order_type: str, side: str, trigger_price: float, quantity: float) -> Optional[Dict[str, Any]]:
        """
        Envía una orden condicional nativa (STOP_MARKET o TAKE_PROFIT_MARKET) directamente
        a los servidores de Binance (/fapi/v1/algoOrder) con reduceOnly=True.
        Esto garantiza que Binance ejecute el Stop Loss y el Take Profit 24/7 en su exchange,
        incluso si la PC del usuario se apaga, suspende o pierde conexión a internet.
        """
        if self.mode != "REAL" or self.market_type != "FUTURES" or not self.api_key:
            return None

        endpoint = f"{self.base_url}/fapi/v1/algoOrder"
        headers = {"X-MBX-APIKEY": self.api_key}
        params: Dict[str, Any] = {
            "algoType": "CONDITIONAL",
            "symbol": self.symbol,
            "side": side,
            "type": order_type,
            "triggerPrice": f"{trigger_price:.1f}",
            "quantity": f"{quantity:.3f}",
            "reduceOnly": "true",
            "workingType": "MARK_PRICE"
        }
        signed_params = self._sign_payload(params)
        try:
            resp = requests.post(endpoint, headers=headers, params=signed_params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self._log(f"[BINANCE NATIVE {order_type}] Orden algorítmica {side} creada en exchange: trigger=${trigger_price:,.2f} | ID={data.get('algoId')}")
                return data
            else:
                self._log(f"[BINANCE NATIVE {order_type} ERROR] {resp.text}")
        except Exception as e:
            self._log(f"[ERROR NATIVE {order_type}] {e}")
        return None

    def cancel_all_futures_algo_orders(self) -> bool:
        """Cancela todas las órdenes condicionales abiertas (Stop Loss / Take Profit) en Binance."""
        if self.mode != "REAL" or self.market_type != "FUTURES" or not self.api_key:
            return False
        endpoint = f"{self.base_url}/fapi/v1/algoOpenOrders"
        headers = {"X-MBX-APIKEY": self.api_key}
        params = self._sign_payload({"symbol": self.symbol})
        try:
            r = requests.delete(endpoint, headers=headers, params=params, timeout=8)
            return r.status_code == 200
        except Exception:
            return False

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

        # Recargar configuración en caliente desde config_bot.json (incluyendo Apalancamiento y Sesión de Mercado)
        self.session_mode = getattr(self, "session_mode", "TODAS_24_7")
        if os.path.exists(self.cfg_file):
            try:
                with open(self.cfg_file, "r", encoding="utf-8") as f_c:
                    dyn_cfg = json.load(f_c)
                    self.leverage = max(1.0, float(dyn_cfg.get("leverage", self.leverage)))
                    self.max_trades_per_day = int(dyn_cfg.get("max_trades_per_day", self.max_trades_per_day))
                    self.max_position_usdt = float(dyn_cfg.get("max_position_usdt", self.max_position_usdt))
                    self.session_mode = str(dyn_cfg.get("session_mode", "TODAS_24_7"))
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

        # Sincronización automática con Binance Futuros en tiempo real
        if self.mode == "REAL" and self.market_type == "FUTURES":
            pos_info = self.get_futures_position_info()
            if pos_info is not None:
                real_amt = pos_info["positionAmt"]
                if real_amt != 0.0:
                    real_side = "SHORT" if real_amt < 0 else "LONG"
                    # Si hay posición real en Binance pero active_trade es None, auto-recuperarla
                    if active_trade is None:
                        real_entry = pos_info["entryPrice"] if pos_info["entryPrice"] > 0 else current_price
                        stop_dist = max(10.0, self.stop_atr_mult * current_atr)
                        if real_side == "SHORT":
                            stop_level = real_entry + stop_dist
                            tp_level = real_entry - (self.rr_ratio * stop_dist)
                        else:
                            stop_level = real_entry - stop_dist
                            tp_level = real_entry + (self.rr_ratio * stop_dist)

                        active_trade = {
                            "entry_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "side": real_side,
                            "entry_price": round(real_entry, 2),
                            "units": abs(real_amt),
                            "stop_price": round(stop_level, 2),
                            "tp_price": round(tp_level, 2),
                            "bars_held": 1,
                            "leverage": pos_info["leverage"],
                            "market_type": "FUTURES",
                            "margin_usdt": round(max(5.0, pos_info["isolatedMargin"]), 2),
                            "strategy": getattr(strategy, "display_name", "Operación Binance Futuros"),
                            "stop_distance": round(stop_dist, 2)
                        }
                        self.state["active_trade"] = active_trade
                        self._save_state()
                        self._log(
                            f"[AUTO-SINCRONIZACIÓN BINANCE] Detectada posición real {real_side} de {abs(real_amt):.3f} {self.symbol} "
                            f"en Binance a ${real_entry:,.2f}. Vinculada exitosamente al Bot con SL ${stop_level:,.2f} y TP ${tp_level:,.2f}."
                        )
                else:
                    # Si no hay posición en Binance pero el estado local decía que sí, limpiar
                    if active_trade is not None:
                        exit_price = current_price
                        entry_price = float(active_trade.get("entry_price", current_price))
                        units = float(active_trade.get("units", 0.0))
                        side = str(active_trade.get("side", "LONG")).upper()
                        pnl = (exit_price - entry_price) * units if side == "LONG" else (entry_price - exit_price) * units
                        trade_lev = float(active_trade.get("leverage", self.leverage))
                        margin_used = float(active_trade.get("margin_usdt", (units * entry_price) / max(1.0, trade_lev)))
                        roe = (pnl / margin_used * 100.0) if margin_used > 0 else 0.0
                        stop_dist = float(active_trade.get("stop_distance", 1.0))
                        r_mult = round(pnl / max(0.01, stop_dist * units), 2)

                        trade_rec = {
                            "id": len(self.state.get("trade_history", [])) + 1,
                            "mode": self.mode,
                            "side": side,
                            "symbol": self.symbol,
                            "strategy": active_trade.get("strategy", strategy.display_name),
                            "leverage": f"{trade_lev:.0f}x",
                            "entry_time": active_trade.get("entry_time", "-"),
                            "exit_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "entry_price": round(entry_price, 2),
                            "exit_price": round(exit_price, 2),
                            "units": round(units, 4),
                            "pnl_usdt": round(pnl, 2),
                            "roe_pct": round(roe, 2),
                            "r_multiple": r_mult,
                            "exit_reason": "CIERRE_BINANCE_EXCHANGE",
                            "status": "POSITIVA (GANANCIA)" if pnl >= 0 else "NEGATIVA (PÉRDIDA)",
                            "explanation": f"Posición cerrada en exchange Binance ({'Ganancia' if pnl >= 0 else 'Pérdida'} de ${pnl:+.2f} USDT).",
                            "verse": get_random_verse()
                        }
                        if "trade_history" not in self.state:
                            self.state["trade_history"] = []
                        self.state["trade_history"].append(trade_rec)
                        self.state["total_trades"] = len(self.state["trade_history"])
                        self._log(f"[AUTO-SINCRONIZACIÓN BINANCE] Operación cerrada registrada en historial: {trade_rec['status']} ({pnl:+.2f} USDT). Limpiando estado local.")
                        self.state["active_trade"] = None
                        self._save_state()
                        active_trade = None

        same_candle = (self.state.get("last_processed_candle") == last_candle_time)

        # Si no hay posición abierta y esta vela ya fue evaluada, esperar al siguiente cierre de vela
        if active_trade is None and same_candle:
            print(f"[{time.strftime('%H:%M:%S')}] Vela actual ya procesada (${current_price:,.2f} | {self.leverage:.0f}x). Esperando siguiente cierre...")
            return

        # Generar señales (soporta LONG +1 y SHORT -1 en Futuros)
        signals = strategy.generate_signals(df, strategy_params, allow_short=self.allow_short)
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
            sig_txt = "+1=COMPRA/LONG" if current_signal == 1 else ("-1=VENTA/SHORT" if current_signal == -1 else "0=NEUTRAL")
            self._log(f"Senal de la Estrategia ({strategy.display_name}): {current_signal} ({sig_txt})")
            act_txt = f"SI ({active_trade.get('side', 'LONG')})" if active_trade else "NINGUNA"
            self._log(f"Posicion Activa: {act_txt} | Operaciones Hoy: {trades_today}/{self.max_trades_per_day}")

        # 1. GESTIÓN DE SALIDAS EN TIEMPO REAL (STOP LOSS Y TAKE PROFIT)
        if active_trade is not None:
            entry_price = active_trade["entry_price"]
            stop_price = active_trade["stop_price"]
            tp_price = active_trade["tp_price"]
            units = active_trade["units"]
            trade_lev = float(active_trade.get("leverage", self.leverage))
            margin_used = float(active_trade.get("margin_usdt", (units * entry_price) / max(1.0, trade_lev)))
            trade_side = str(active_trade.get("side", "LONG")).upper()
            stop_dist_be = float(active_trade.get("stop_distance", max(10.0, abs(entry_price - stop_price))))

            # Protección Break-Even: Si el precio avanzó al menos +0.70R a favor, blindar la entrada
            if trade_side == "SHORT":
                if current_price <= (entry_price - (0.70 * stop_dist_be)) and float(active_trade.get("stop_price", 999999.0)) > entry_price:
                    new_be_stop = round(entry_price - (0.05 * stop_dist_be), 2)
                    active_trade["stop_price"] = new_be_stop
                    stop_price = new_be_stop
                    self._save_state()
                    self._log(f"[BREAK-EVEN BLINDADO SHORT] El precio cayo +0.70R a favor. Stop Loss reducido a ${new_be_stop:,.2f} (Operación sin riesgo).")
                    if self.mode == "REAL" and self.market_type == "FUTURES":
                        self.cancel_all_futures_algo_orders()
                        self.place_futures_algo_order("STOP_MARKET", "BUY", new_be_stop, units)
                        self.place_futures_algo_order("TAKE_PROFIT_MARKET", "BUY", tp_price, units)
            else:
                if current_price >= (entry_price + (0.70 * stop_dist_be)) and float(active_trade.get("stop_price", 0.0)) < entry_price:
                    new_be_stop = round(entry_price + (0.05 * stop_dist_be), 2)
                    active_trade["stop_price"] = new_be_stop
                    stop_price = new_be_stop
                    self._save_state()
                    self._log(f"[BREAK-EVEN BLINDADO LONG] El precio avanzo +0.70R a favor. Stop Loss elevado a ${new_be_stop:,.2f} (Operación sin riesgo).")
                    if self.mode == "REAL" and self.market_type == "FUTURES":
                        self.cancel_all_futures_algo_orders()
                        self.place_futures_algo_order("STOP_MARKET", "SELL", new_be_stop, units)
                        self.place_futures_algo_order("TAKE_PROFIT_MARKET", "SELL", tp_price, units)

            exit_triggered = False
            exit_reason = ""
            bars_held_now = int(active_trade.get("bars_held", 0))

            if trade_side == "SHORT":
                if current_price >= stop_price:
                    exit_triggered = True
                    exit_reason = "STOP_LOSS"
                elif current_price <= tp_price:
                    exit_triggered = True
                    exit_reason = "TAKE_PROFIT"
                elif not same_candle and current_signal == 1:
                    exit_triggered = True
                    exit_reason = "CAMBIO_SENAL"
                elif bars_held_now >= 20 and current_price < entry_price:
                    exit_triggered = True
                    exit_reason = "TOMA_GANANCIA_POR_TIEMPO"
                elif bars_held_now >= 32:
                    exit_triggered = True
                    exit_reason = "CIERRE_MAX_TIEMPO"
            else:
                if current_price <= stop_price:
                    exit_triggered = True
                    exit_reason = "STOP_LOSS"
                elif current_price >= tp_price:
                    exit_triggered = True
                    exit_reason = "TAKE_PROFIT"
                elif not same_candle and current_signal == -1:
                    exit_triggered = True
                    exit_reason = "CAMBIO_SENAL"
                elif bars_held_now >= 20 and current_price > entry_price:
                    exit_triggered = True
                    exit_reason = "TOMA_GANANCIA_POR_TIEMPO"
                elif bars_held_now >= 32:
                    exit_triggered = True
                    exit_reason = "CIERRE_MAX_TIEMPO"

            if exit_triggered:
                if self.mode == "REAL" and self.market_type == "FUTURES":
                    self.cancel_all_futures_algo_orders()
                self._log(f"[SALIDA {trade_side}] Cerrando posicion ({trade_lev:.0f}x): Motivo {exit_reason} al precio ${current_price:,.2f}")
                if trade_side == "SHORT":
                    if self.market_type == "FUTURES":
                        pos_amt = abs(self.get_futures_position_amt())
                        buy_qty = pos_amt if pos_amt > 0 else units
                        self.place_market_order("BUY", buy_qty, reduce_only=True)
                    else:
                        self.place_market_order("BUY", units)
                    pnl = (entry_price - current_price) * units
                else:
                    if self.market_type == "FUTURES":
                        pos_amt = self.get_futures_position_amt()
                        sell_qty = pos_amt if pos_amt > 0 else units
                        self.place_market_order("SELL", sell_qty, reduce_only=True)
                    else:
                        self.place_market_order("SELL", units)
                    pnl = (current_price - entry_price) * units

                # Calcular PnL apalancado y múltiplo R
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
                    "mode": self.mode,
                    "side": trade_side,
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

                self._log(f"Resultado de la operacion ({trade_side} {trade_lev:.0f}x): {diag['status']} | PnL = ${pnl:+,.2f} (ROE: {roe_pct:+.2f}% | {r_mult:+.2f}R)")
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

        # 2. GESTIÓN DE ENTRADAS (NUEVO LARGO O CORTO CON APALANCAMIENTO Y SESIÓN DE MERCADO)
        if active_trade is None and current_signal in (1, -1):
            target_side = "LONG" if current_signal == 1 else "SHORT"

            # En SPOT no se puede abrir SHORT; y si allow_short es False, ignorar SHORT
            if target_side == "SHORT" and (self.market_type != "FUTURES" or not self.allow_short):
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                return

            # Verificar si estamos dentro de la Sesión de Mercado configurada (ej. Sesión Londres, NY, etc.)
            sess_eval = evaluate_trading_session(self.session_mode)
            if not sess_eval["allowed_now"]:
                mode_ascii = sess_eval["mode_short"].encode("ascii", "ignore").decode("ascii").strip()
                self._log(
                    f"[ESPERANDO SESION {mode_ascii}] Hora actual ARG: {sess_eval['arg_time']} "
                    f"(Horario permitido: {sess_eval['horario_arg']}). Se aguarda apertura de sesion."
                )
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                self._log("=" * 60 + "\n")
                return

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

            if target_side == "LONG" and not news_eval.get("allow_long", True):
                self._log("[ORDEN BLOQUEADA] El filtro de noticias detecto alto riesgo bajista. Se cancela la compra por seguridad.")
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                self._log("=" * 60 + "\n")
                return
            elif target_side == "SHORT" and not news_eval.get("allow_short", True):
                self._log("[ORDEN BLOQUEADA] El filtro de noticias detecto fuerte impulso alcista. Se cancela la venta en corto (SHORT) por seguridad.")
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                self._log("=" * 60 + "\n")
                return

            # Evaluar régimen de mercado con ADX: exigir fuerza direccional confirmada para no entrar en rango/chop
            regime, current_adx = detect_market_regime(df, window=14)
            self._log(f"[FILTRO DE TENDENCIA] Régimen: {regime} | Fuerza ADX(14): {current_adx:.2f} (Mínimo exigido: {self.min_adx_filter:.1f})")
            if current_adx < self.min_adx_filter:
                self._log(
                    f"[ORDEN BLOQUEADA] Mercado lateral/sin tendencia clara (ADX {current_adx:.1f} < {self.min_adx_filter:.1f}). "
                    f"Se descarta la entrada para evitar falsos quiebres en rango."
                )
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                self._log("=" * 60 + "\n")
                return

            # Filtro Anti-Agotamiento de Tendencia con RSI(14)
            rsi_series = calc_rsi(df['close'], 14)
            current_rsi = float(rsi_series.iloc[-1])
            self._log(f"[FILTRO ANTI-AGOTAMIENTO] RSI(14): {current_rsi:.1f}")

            if target_side == "SHORT" and current_rsi < 36.0:
                self._log(
                    f"[ORDEN DESCARTADA] Mercado sobrevendido (RSI {current_rsi:.1f} < 36.0). "
                    f"Alto riesgo de vender en el piso antes de un rebote alcista. Se cancela el SHORT para proteger capital."
                )
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                self._log("=" * 60 + "\n")
                return

            if target_side == "LONG" and current_rsi > 64.0:
                self._log(
                    f"[ORDEN DESCARTADA] Mercado sobrecomprado (RSI {current_rsi:.1f} > 64.0). "
                    f"Alto riesgo de comprar en el techo antes de una corrección. Se cancela el LONG para proteger capital."
                )
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                self._log("=" * 60 + "\n")
                return

            # Filtro de confirmación de acción del precio (Evitar entrar contra mechas de absorción/rechazo)
            last_open = float(df['open'].iloc[-1])
            last_close = float(df['close'].iloc[-1])
            last_high = float(df['high'].iloc[-1])
            last_low = float(df['low'].iloc[-1])
            candle_range = max(1.0, last_high - last_low)
            lower_wick = min(last_open, last_close) - last_low
            upper_wick = last_high - max(last_open, last_close)

            if target_side == "SHORT" and (last_close > last_open or (lower_wick / candle_range) > 0.45):
                self._log(
                    f"[ORDEN DESCARTADA] La vela muestra absorción de compra o cierre verde "
                    f"(Mecha inferior {(lower_wick/candle_range)*100:.0f}%). Se evita vender en soporte."
                )
                self.state["last_processed_candle"] = last_candle_time
                self._save_state()
                self._log("=" * 60 + "\n")
                return

            if target_side == "LONG" and (last_close < last_open or (upper_wick / candle_range) > 0.45):
                self._log(
                    f"[ORDEN DESCARTADA] La vela muestra presión de venta o cierre rojo "
                    f"(Mecha superior {(upper_wick/candle_range)*100:.0f}%). Se evita comprar en resistencia."
                )
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
            if target_side == "LONG":
                stop_level = current_price - stop_dist
                tp_level = current_price + (self.rr_ratio * stop_dist)
                order_side = "BUY"
            else:
                stop_level = current_price + stop_dist
                tp_level = current_price - (self.rr_ratio * stop_dist)
                order_side = "SELL"

            # Dimensionamiento de margen y orden
            if self.mode == "REAL":
                if self.market_type == "FUTURES":
                    effective_lev = self.leverage
                    margin_usdt = min(balance * 0.90, self.max_position_usdt)
                    if margin_usdt < 5.0:
                        self._log(f"[AVISO] Saldo insuficiente en Futuros (minimo $5 USDT, disponible ${balance:.2f}).")
                        return
                    notional_usdt = margin_usdt * effective_lev
                    step = 0.001
                    raw_units = notional_usdt / current_price
                    units = math.floor(raw_units / step) * step
                    if units * current_price < 50.0:
                        units = 0.001
                    units = round(units, 3)
                    actual_notional = units * current_price
                    actual_margin = actual_notional / effective_lev
                    self._log(
                        f"[ORDEN {target_side} FUTUROS REAL {effective_lev:.0f}x ISOLATED] Margen: ${actual_margin:,.2f} USDT | "
                        f"Poder de Posicion: ${actual_notional:,.2f} USDT ({units:.3f} {self.symbol})"
                    )
                    order = self.place_market_order(order_side, units)
                    margin_usdt = actual_margin
                else:
                    effective_lev = 1.0
                    margin_usdt = min(balance, self.max_position_usdt)
                    if margin_usdt < 5.0:
                        self._log(f"[AVISO] Saldo insuficiente para operar (minimo $5 USDT en Binance, disponible ${balance:.2f}).")
                        return
                    units = round(margin_usdt / current_price, 5)
                    notional_usdt = units * current_price
                    self._log(
                        f"[ORDEN COMPRA SPOT REAL] Monto: ${margin_usdt:,.2f} USDT | "
                        f"Cantidad: {units:.5f} {self.symbol} (~${notional_usdt:,.2f} USDT)"
                    )
                    order = self.place_market_order("BUY", units, quote_order_qty=margin_usdt)
            else:
                effective_lev = self.leverage
                desired_risk = balance * self.risk_pct
                base_units = desired_risk / stop_dist
                max_margin_units = min(balance, self.max_position_usdt) / current_price
                margin_units = min(base_units, max_margin_units)
                margin_usdt = margin_units * current_price
                if margin_usdt < 10.0:
                    margin_usdt = min(balance, self.max_position_usdt)
                    margin_units = margin_usdt / current_price

                units = round(margin_units * effective_lev, 5)
                notional_usdt = margin_usdt * effective_lev
                self._log(
                    f"[ORDEN {target_side} PAPER {effective_lev:.0f}x] Margen: ${margin_usdt:,.2f} USDT | "
                    f"Posicion: ${notional_usdt:,.2f} USDT ({units:.5f} {self.symbol})"
                )
                order = self.place_market_order(order_side, units)

            if order is not None:
                if self.mode == "PAPER":
                    self.state["paper_balance_usdt"] -= margin_usdt
                else:
                    exec_qty = float(order.get("executedQty", units))
                    if exec_qty > 0:
                        units = exec_qty

                    # Colocar inmediatamente órdenes nativas de Stop Loss y Take Profit en los servidores de Binance
                    if self.market_type == "FUTURES":
                        exit_side = "BUY" if target_side == "SHORT" else "SELL"
                        self.cancel_all_futures_algo_orders()
                        self.place_futures_algo_order("STOP_MARKET", exit_side, stop_level, units)
                        self.place_futures_algo_order("TAKE_PROFIT_MARKET", exit_side, tp_level, units)
                        self._log(
                            f"[PROTECCIÓN NATIVA EN BINANCE ACTIVADA] Stop Loss (${stop_level:,.2f}) y Take Profit (${tp_level:,.2f}) "
                            f"registrados en los servidores de Binance. Blindaje 24/7 incluso con la PC apagada o suspendida."
                        )

                self.state["trades_today_count"] = trades_today + 1
                self.state["active_trade"] = {
                    "entry_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "side": target_side,
                    "entry_price": current_price,
                    "units": units,
                    "stop_price": round(stop_level, 2),
                    "tp_price": round(tp_level, 2),
                    "bars_held": 0,
                    "leverage": effective_lev,
                    "market_type": self.market_type,
                    "margin_usdt": margin_usdt,
                    "strategy": strategy.display_name,
                    "stop_distance": stop_dist
                }
                lev_desc = f"Futuros {effective_lev:.0f}x Aislado ({target_side})" if (self.mode == "REAL" and self.market_type == "FUTURES") else ("Spot 1x" if self.mode == "REAL" else f"{self.leverage:.0f}x ({target_side})")
                self._log(
                    f"Posicion {target_side} abierta con exito ({lev_desc} | "
                    f"Operacion {trades_today + 1}/{self.max_trades_per_day} de hoy). "
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

    trade_side = str(active_trade.get("side", "LONG")).upper()

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

    if trade_side == "SHORT":
        pnl = (entry_price - current_price) * units
    else:
        pnl = (current_price - entry_price) * units

    roe_pct = (pnl / margin_used) * 100.0 if margin_used > 0 else 0.0
    stop_dist_orig = float(active_trade.get("stop_distance", max(1.0, abs(entry_price - stop_price))))
    initial_risk = units * stop_dist_orig
    r_mult = pnl / initial_risk if initial_risk > 0 else 0.0

    trade_mode = cfg.get("mode", "PAPER")
    mkt_t = cfg.get("market_type", "FUTURES").upper()
    if trade_mode == "PAPER":
        state["paper_balance_usdt"] = float(state.get("paper_balance_usdt", 1000.0)) + margin_used + pnl
    elif trade_mode == "REAL" and cfg.get("binance_api_key") and cfg.get("binance_api_secret"):
        try:
            trader = BinanceLiveTrader(
                api_key=cfg["binance_api_key"],
                api_secret=cfg["binance_api_secret"],
                mode="REAL",
                market_type=mkt_t,
                symbol=sym
            )
            if mkt_t == "FUTURES":
                trader.cancel_all_futures_algo_orders()
                pos_amt = abs(trader.get_futures_position_amt())
                close_qty = pos_amt if pos_amt > 0 else units
                close_side = "BUY" if trade_side == "SHORT" else "SELL"
                trader.place_market_order(close_side, close_qty, reduce_only=True)
            else:
                trader.place_market_order("SELL", units)
        except Exception as e_sell:
            print(f"[CIERRE MANUAL REAL ERROR] {e_sell}")

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
        "mode": trade_mode,
        "side": trade_side,
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


_REAL_BALANCES_CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "key": "",
    "data": {}
}


def auto_redeem_simple_earn(api_key: str, api_secret: str, amount: float = 10.5) -> bool:
    """Rescata automáticamente USDT de Simple Earn Flexible a la billetera Spot para operar."""
    if not api_key or not api_secret:
        return False
    endpoint = "https://api.binance.com/sapi/v1/simple-earn/flexible/redeem"
    ts = int(time.time() * 1000)
    params = {
        "productId": "USDT001",
        "amount": round(amount, 2),
        "type": "FAST",
        "timestamp": ts
    }
    query = urllib.parse.urlencode(params)
    sig = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {"X-MBX-APIKEY": api_key}
    try:
        r = requests.post(f"{endpoint}?{query}&signature={sig}", headers=headers, timeout=5)
        if r.status_code == 200 and r.json().get("success"):
            print(f"[BINANCE EARN] Auto-rescate exitoso de {amount} USDT a Spot.")
            return True
    except Exception as e:
        print(f"[BINANCE EARN ERROR] {e}")
    return False


def fetch_real_binance_balances_dict(api_key: str, api_secret: str, force_refresh: bool = False, market_type: str = "FUTURES") -> Dict[str, float]:
    """
    Consulta saldos reales de Binance (Futuros USD-M, Spot y Flexible Earn) usando HMAC-SHA256 con caché inteligente.
    """
    global _REAL_BALANCES_CACHE
    now = time.time()
    cache_key = f"{api_key}_{market_type}"
    if not force_refresh and (now - _REAL_BALANCES_CACHE["timestamp"] < 8.0) and _REAL_BALANCES_CACHE["key"] == cache_key:
        return dict(_REAL_BALANCES_CACHE["data"])

    if not api_key or not api_secret:
        return {}

    res: Dict[str, float] = {}

    # 1. Consultar saldo disponible en Binance Futuros USD-M
    try:
        ts_f = int(time.time() * 1000)
        p_f = {"timestamp": ts_f}
        q_f = f"timestamp={ts_f}"
        sig_f = hmac.new(api_secret.encode("utf-8"), q_f.encode("utf-8"), hashlib.sha256).hexdigest()
        p_f["signature"] = sig_f
        r_f = requests.get("https://fapi.binance.com/fapi/v2/balance", headers={"X-MBX-APIKEY": api_key}, params=p_f, timeout=5)
        if r_f.status_code == 200:
            for b in r_f.json():
                if b.get("asset") == "USDT":
                    avail_fut = float(b.get("availableBalance", b.get("balance", 0.0)))
                    res["USDT_FUTURES"] = avail_fut
                    if market_type == "FUTURES":
                        res["USDT"] = avail_fut
    except Exception as e_f:
        print(f"[FUTURES BALANCE API ERROR] {e_f}")

    # 2. Consultar Binance Spot y Flexible Earn
    endpoint = "https://api.binance.com/api/v3/account"
    ts = int(time.time() * 1000)
    params = {"timestamp": ts}
    query = f"timestamp={ts}"
    sig = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    params["signature"] = sig
    headers = {"X-MBX-APIKEY": api_key}

    try:
        r = requests.get(endpoint, headers=headers, params=params, timeout=5)
        if r.status_code == 200:
            raw_spot_usdt = 0.0
            raw_ld_usdt = 0.0

            for b in r.json().get("balances", []):
                val = float(b.get("free", 0.0))
                if val > 0:
                    asset = b["asset"]
                    if asset not in res:
                        res[asset] = val
                    if asset == "USDT":
                        raw_spot_usdt = val
                    elif asset == "LDUSDT":
                        raw_ld_usdt = val

            total_spot_usdt = raw_spot_usdt + raw_ld_usdt
            res["USDT_SPOT"] = raw_spot_usdt
            res["USDT_EARN"] = raw_ld_usdt
            if market_type != "FUTURES" or "USDT" not in res:
                res["USDT"] = total_spot_usdt
    except Exception as e:
        print(f"[BINANCE BALANCE API ERROR] {e}")

    if res:
        _REAL_BALANCES_CACHE = {
            "timestamp": now,
            "key": cache_key,
            "data": res
        }
        return dict(res)

    if _REAL_BALANCES_CACHE["data"]:
        return dict(_REAL_BALANCES_CACHE["data"])
    return {}


def fetch_real_binance_balance(api_key: str, api_secret: str, asset: str = "USDT") -> float:
    """Consulta rápida del saldo real disponible de Binance (Spot + Flexible Earn)."""
    b_dict = fetch_real_binance_balances_dict(api_key, api_secret)
    return b_dict.get(asset, 0.0)
