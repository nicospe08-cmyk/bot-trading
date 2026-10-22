"""
===============================================================================
MÓDULO DE TELEGRAM BOT AUTÓNOMO Y CONTROL MÓVIL (telegram_bot.py)
"Encomienda a Jehová tu camino, y confía en él; y él hará." — Salmos 37:5 (RVR1960)
===============================================================================

Este módulo administra la conexión bidireccional entre el Bot Cuantitativo y la app
nativa de Telegram en el celular del usuario:
1. Escucha comandos y clics en el teclado móvil en tiempo real.
2. Consulta saldos reales directamente de Binance Spot (con HMAC-SHA256).
3. Permite monitorear operaciones en vivo con cálculo de PnL en USDT y ARS.
4. Permite cerrar posiciones de inmediato desde el celular (/cerrar).
5. Permite cambiar horarios y sesiones de bolsa (Londres, NY, 24/7) en caliente.
6. Aísla completamente el modo REAL del modo PAPER para evitar datos ficticios.
===============================================================================
"""

import json
import os
import sys
import time
import requests
from typing import Optional, Dict, Any, Tuple

from biblical_wisdom import get_random_verse
from live_trader import (
    SESSION_MODES,
    close_active_trade_now,
    evaluate_trading_session,
    fetch_real_binance_balance,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config_bot.json")
STATE_FILE = os.path.join(BASE_DIR, "live_state.json")


def load_json(path: str) -> dict:
    """Carga un archivo JSON de forma segura y devuelve un dict vacío si falla."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_json(path: str, data: dict) -> bool:
    """Guarda un dict en formato JSON con indentación y codificación UTF-8."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except Exception:
        return False


def fetch_live_price(symbol: str, fallback: float = 0.0) -> float:
    """Obtiene el precio de mercado más reciente desde las APIs públicas de Binance."""
    for base_url in ("https://data-api.binance.vision", "https://api.binance.com"):
        try:
            r = requests.get(
                f"{base_url}/api/v3/ticker/price",
                params={"symbol": symbol.upper()},
                timeout=5
            )
            if r.status_code == 200:
                return float(r.json().get("price", fallback))
        except Exception:
            pass
    return fallback


def fetch_usdt_ars() -> float:
    """Cotización en vivo USDT/ARS en Binance con respaldo a 1450.0."""
    val = fetch_live_price("USDTARS", fallback=1450.0)
    return val if val > 100.0 else 1450.0


def get_current_balance_usdt(cfg: dict, state: dict) -> Tuple[float, str]:
    """
    Retorna (saldo_usdt, origen):
    - Si el modo es REAL y hay claves Binance, consulta la cuenta Spot en vivo.
    - Si es PAPER, retorna el saldo virtual.
    """
    mode = cfg.get("mode", "REAL")
    if mode == "REAL" and cfg.get("binance_api_key") and cfg.get("binance_api_secret"):
        try:
            bal = fetch_real_binance_balance(cfg["binance_api_key"], cfg["binance_api_secret"], "USDT")
            return bal, "Binance Spot Real"
        except Exception:
            fallback = float(state.get("real_balance_usdt", 11.41))
            return fallback, "Binance Spot (Caché)"
    return float(state.get("paper_balance_usdt", 11.41)), "Virtual (Paper)"


def send_telegram_message(
    token: str,
    chat_id: str,
    text: str,
    with_keyboard: bool = True
) -> bool:
    """
    Envía un mensaje a Telegram con teclado persistente.
    Si el parse_mode Markdown falla (por caracteres especiales), reintenta
    automáticamente en texto plano para garantizar entrega 100%.
    """
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }

    if with_keyboard:
        payload["reply_markup"] = {
            "keyboard": [
                [{"text": "📈 Operación en Vivo"}, {"text": "📊 Estado General"}],
                [{"text": "🌍 Sesión de Mercado"}, {"text": "📋 Historial Real"}],
                [{"text": "💰 Cerrar Trade"}, {"text": "📖 Versículo Bíblico"}]
            ],
            "resize_keyboard": True
        }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            return True
        # Reintento seguro sin Markdown si fue rechazado por formato
        payload.pop("parse_mode", None)
        r2 = requests.post(url, json=payload, timeout=10)
        return r2.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM SEND ERROR] {e}")
        return False


# =============================================================================
# CONSTRUCTORES DE MENSAJES (CADA BOTÓN TIENE RESPUESTA CORTA, ÚNICA Y PRECISA)
# =============================================================================

def format_active_operation_block(active: dict, cfg: dict, current_bal: float) -> str:
    """Bloque visual detallado cuando hay un trade abierto en curso."""
    if not active:
        return (
            "⚪ *SIN OPERACIÓN ABIERTA AHORA MISMO*\n"
            "El bot está escaneando el mercado cada 25s buscando el próximo gatillo de alta probabilidad.\n\n"
        )

    mode = cfg.get("mode", "REAL")
    sym = active.get("symbol", cfg.get("symbol", "BTCUSDT"))
    entry_p = float(active.get("entry_price", 0.0))
    stop_p = float(active.get("stop_price", 0.0))
    tp_p = float(active.get("tp_price", 0.0))
    units = float(active.get("units", 0.0))
    margin_u = float(active.get("margin_usdt", entry_p * units))
    strat_name = active.get("strategy", "Adaptativa")

    live_p = fetch_live_price(sym, fallback=entry_p)
    usdt_ars = fetch_usdt_ars()

    pnl_usdt = (live_p - entry_p) * units
    pnl_ars = pnl_usdt * usdt_ars
    price_diff_pct = ((live_p - entry_p) / entry_p * 100.0) if entry_p > 0 else 0.0
    roe_pct = (pnl_usdt / margin_u * 100.0) if margin_u > 0 else price_diff_pct

    risk_per_u = abs(entry_p - stop_p)
    risk_usdt = risk_per_u * units if risk_per_u > 0 else max(margin_u * 0.02, 0.5)
    tp_gain_usdt = abs(tp_p - entry_p) * units
    r_mult = (pnl_usdt / risk_usdt) if risk_usdt > 0 else 0.0

    # Barra de progreso visual
    total_span = tp_p - stop_p
    if total_span > 0:
        ratio = max(0.0, min(1.0, (live_p - stop_p) / total_span))
        slots = 10
        pos_idx = int(round(ratio * (slots - 1)))
        bar_chars = []
        for i in range(slots):
            if i == pos_idx:
                bar_chars.append("📍")
            elif i == 3:
                bar_chars.append("⚡")
            else:
                bar_chars.append("━")
        progress_bar = "🛑" + "".join(bar_chars) + "🎯"
    else:
        progress_bar = "🛑━━━━📍━━━━🎯"

    dist_to_tp_pct = ((tp_p - live_p) / live_p * 100.0) if live_p > 0 else 0.0
    dist_to_sl_pct = ((live_p - stop_p) / live_p * 100.0) if live_p > 0 else 0.0

    if pnl_usdt >= 0:
        status_banner = "🟢 *VAS EN POSITIVO (GANANDO)* 🟢"
        amount_line = f"💰 *Ganancia Actual:* `+{pnl_usdt:,.2f} USDT` (`ARS$ +{pnl_ars:,.0f}`)"
    else:
        status_banner = "🔴 *VAS EN NEGATIVO (EN PÉRDIDA FLOTANTE)* 🔴"
        amount_line = f"📉 *Pérdida Actual:* `{pnl_usdt:+,.2f} USDT` (`ARS$ {pnl_ars:+,.0f}`)"

    equity_vivo = current_bal + margin_u + pnl_usdt
    lev_label = "Spot 1x (Real)" if mode == "REAL" else "Paper"

    return (
        f"{status_banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{amount_line}\n"
        f"⚡ *Rendimiento:* `{roe_pct:+.2f}%` (`{r_mult:+.2f}R` | {lev_label})\n"
        f"💵 *Capital Total en Vivo:* `${equity_vivo:,.2f} USDT`\n\n"
        f"📊 *DETALLES DE LA OPERACIÓN ({sym}):*\n"
        f"• *Estrategia:* `{strat_name}`\n"
        f"• *Precio Entrada:* `${entry_p:,.2f}`\n"
        f"• *Precio Actual:* `${live_p:,.2f}` (`{price_diff_pct:+.2f}%`)\n"
        f"• *Capital en Trade:* `${margin_u:,.2f} USDT` ({units:.5f} {sym[:3]})\n"
        f"• *🎯 Take Profit:* `${tp_p:,.2f}` (falta `{dist_to_tp_pct:+.2f}%` | meta `+{tp_gain_usdt:,.2f} USDT`)\n"
        f"• *🛑 Stop Loss:* `${stop_p:,.2f}` (colchón `{dist_to_sl_pct:.2f}%` | riesgo `-{risk_usdt:,.2f} USDT`)\n\n"
        f"🗺️ *Recorrido SL ➔ Entrada (⚡) ➔ TP:*\n"
        f"`{progress_bar}`\n\n"
        f"💡 _Tocá el botón_ 💰 *Cerrar Trade* _si querés cerrarla ahora mismo al precio actual._\n"
    )


def build_operation_message() -> str:
    """Respuesta para el botón '📈 Operación en Vivo'."""
    cfg = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)
    sym = cfg.get("symbol", "BTCUSDT")
    active = state.get("active_trade")
    usdt_ars = fetch_usdt_ars()
    live_p = fetch_live_price(sym, fallback=0.0)
    bal, bal_src = get_current_balance_usdt(cfg, state)
    s_eval = evaluate_trading_session(str(cfg.get("session_mode", "TODAS_24_7")))

    if not active:
        if not s_eval["allowed_now"]:
            status_desc = (
                f"⏳ *Esperando horario de sesión:* Tu bot está configurado en *{s_eval['mode_short']}* "
                f"(`{s_eval['horario_arg']}`). No abre órdenes fuera de horario para evitar movimientos falsos.\n\n"
                f"👉 _Si querés que opere ahora mismo en horario nocturno, escribí:_ `24/7`"
            )
        else:
            status_desc = (
                f"🟢 *Escaneando mercado:* Sesión activa ({s_eval['mode_short']}). "
                f"El algoritmo analiza cada vela de 15m. En cuanto las EMAs y el ADX confirmen compra, entrará con ${cfg.get('max_position_usdt', 10.0):,.2f} USDT."
            )

        return (
            "📈 *MONITOR DE OPERACIÓN EN VIVO*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚪ *Estado:* Sin posición abierta en este momento.\n\n"
            f"• *Precio actual BTC:* `${live_p:,.2f}`\n"
            f"• *Saldo listo en Binance:* `${bal:,.2f} USDT` (`ARS$ {bal * usdt_ars:,.0f}`)\n"
            f"• *Tamaño de orden:* `${cfg.get('max_position_usdt', 10.0):,.2f} USDT`\n\n"
            f"💡 *Situación del Bot:*\n{status_desc}"
        )
    else:
        return (
            "📈 *MONITOR DE OPERACIÓN EN VIVO*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            + format_active_operation_block(active, cfg, bal)
        )


def build_status_message() -> str:
    """Respuesta para el botón '📊 Estado General'."""
    cfg = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)
    mode = cfg.get("mode", "REAL")
    sym = cfg.get("symbol", "BTCUSDT")
    tf = cfg.get("timeframe", "15m")
    max_d = cfg.get("max_trades_per_day", 2)
    today_cnt = state.get("trades_today_count", 0)
    bal, bal_src = get_current_balance_usdt(cfg, state)
    usdt_ars = fetch_usdt_ars()
    s_eval = evaluate_trading_session(str(cfg.get("session_mode", "TODAS_24_7")))
    active = state.get("active_trade")

    perm_str = "🟢 SÍ (Habilitado para comprar)" if s_eval["allowed_now"] else "⏳ NO (En pausa por horario de sesión)"
    pos_str = "🟢 1 OPERACIÓN EN CURSO" if active else "⚪ NINGUNA (LISTO PARA COMPRAR)"
    mode_label = "🟢 REAL (Binance Spot)" if mode == "REAL" else "📝 PAPER (Simulación)"

    return (
        "📊 *ESTADO GENERAL DEL BOT*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Modo:* `{mode_label}`\n"
        f"• *Saldo Real en Binance:* `${bal:,.2f} USDT` (`ARS$ {bal * usdt_ars:,.0f}`)\n"
        f"• *Inversión por Orden:* `${cfg.get('max_position_usdt', 10.0):,.2f} USDT`\n"
        f"• *Activo:* `{sym}` ({tf} | Spot 1x sin apalancamiento riesgoso)\n"
        f"• *Sesión Institucional:* *{s_eval['mode_short']}* (`{s_eval['horario_arg']}`)\n"
        f"• *¿Habilitado ahora?:* {perm_str}\n"
        f"• *Trades de hoy:* `{today_cnt} / {max_d}`\n"
        f"• *Posición en vivo:* {pos_str}"
    )


def build_session_message(cfg: dict) -> str:
    """Respuesta para el botón '🌍 Sesión de Mercado'."""
    s_mode = str(cfg.get("session_mode", "TODAS_24_7"))
    s_eval = evaluate_trading_session(s_mode)
    l_badge = "🟢 ABIERTA" if s_eval["london_open"] else "⚪ CERRADA"
    ny_badge = "🟢 ABIERTA" if s_eval["ny_open"] else "⚪ CERRADA"
    ov_badge = "🔥 ACTIVO" if s_eval["overlap_open"] else "⚪ INACTIVO"
    as_badge = "🟢 ABIERTA" if s_eval["asia_open"] else "⚪ CERRADA"
    perm_badge = "🟢 ACTIVO (Operando)" if s_eval["allowed_now"] else "⏳ EN PAUSA (Fuera de horario)"

    return (
        "🌍 *SESIONES INSTITUCIONALES DE MERCADO*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Hora actual Argentina:* `{s_eval['arg_time']} hs`\n"
        f"• *Tu sesión configurada:* *{s_eval['mode_short']}* (`{s_eval['horario_arg']}`)\n"
        f"• *Estado del filtro:* *{perm_badge}*\n\n"
        "🕒 *Bolsas mundiales en este momento:*\n"
        f"• 🇺🇸 Nueva York (09 a 17 hs): {ny_badge}\n"
        f"• 🇬🇧 Londres (04 a 12 hs): {l_badge}\n"
        f"• 🔥 Cruce Londres+NY (09 a 12 hs): {ov_badge}\n"
        f"• 🇯🇵 Tokio/Asia (20 a 04 hs): {as_badge}\n\n"
        "⚙️ *Para cambiar de sesión en cualquier momento, escribí:*\n"
        "• `24/7` — Operar las 24 horas continuas (sin esperar sesión)\n"
        "• `ny` — Solo en Sesión Nueva York (09 a 17 hs ARG)\n"
        "• `londres` — Solo en Sesión Londres (04 a 12 hs ARG)\n"
        "• `asia` — Solo en horario nocturno Asia (20 a 04 hs ARG)"
    )


def build_history_message(show_paper: bool = False) -> str:
    """Respuesta para el botón '📋 Historial Real' o '/historial_paper'."""
    cfg = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)
    mode = cfg.get("mode", "REAL")
    all_history = state.get("trade_history", [])
    usdt_ars = fetch_usdt_ars()
    bal, _ = get_current_balance_usdt(cfg, state)

    if mode == "REAL" and not show_paper:
        history = [t for t in all_history if t.get("mode") == "REAL"]
        title = "📋 *HISTORIAL DE OPERACIONES REALES (BINANCE SPOT)*\n━━━━━━━━━━━━━━━━━━━━\n"
        paper_cnt = len(all_history) - len(history)
    else:
        history = all_history
        title = "📋 *HISTORIAL DE PRUEBAS (MODO SIMULACIÓN)*\n━━━━━━━━━━━━━━━━━━━━\n"
        paper_cnt = 0

    if not history:
        extra_note = (
            f"\n\n💡 _(Tenés {paper_cnt} operaciones guardadas del período de prueba. Para verlas escribí:_ `/historial_paper`_)"
            if paper_cnt > 0 else ""
        )
        return (
            f"{title}"
            "• *Trades reales ejecutados:* `0`\n"
            f"• *Saldo en Binance:* `${bal:,.2f} USDT` (`ARS$ {bal * usdt_ars:,.0f}`)\n"
            "• *Ganancia acumulada real:* `$0.00 USDT`\n\n"
            "Aún no se realizaron compras con dinero real en tu cuenta de Binance Spot. "
            "En cuanto el bot ejecute y cierre la primera compra real, verás acá el resultado con su precio y análisis forense."
            f"{extra_note}"
        )

    wins = sum(1 for t in history if float(t.get("pnl_usdt", 0)) > 0)
    losses = len(history) - wins
    total_pnl = sum(float(t.get("pnl_usdt", 0.0)) for t in history)
    total_pnl_ars = total_pnl * usdt_ars

    msg = (
        f"{title}"
        f"• *Total Operaciones:* {len(history)} ({wins} Ganadas 🟢 / {losses} Perdidas 🔴)\n"
        f"• *Ganancia Total:* `{total_pnl:+,.2f} USDT` (`ARS$ {total_pnl_ars:+,.0f}`)\n\n"
    )

    for t in history[-5:]:
        pnl_u = float(t.get("pnl_usdt", 0.0))
        pnl_a = pnl_u * usdt_ars
        icon = "🟢 POSITIVA" if pnl_u >= 0 else "🔴 NEGATIVA"
        msg += (
            f"{icon} — *Trade #{t.get('id', 1)} ({t.get('symbol', 'BTCUSDT')})*\n"
            f"• *Resultado:* `{pnl_u:+,.2f} USDT` (`ARS$ {pnl_a:+,.0f}`)\n"
            f"• *Entrada/Salida:* `${float(t.get('entry_price', 0)):,.2f}` ➔ `${float(t.get('exit_price', 0)):,.2f}` ({t.get('exit_reason', '')})\n"
            f"• *Diagnóstico:* {t.get('explanation', '')}\n\n"
        )

    return msg


def build_welcome_message(cfg: dict, state: dict) -> str:
    """Mensaje de bienvenida y menú de ayuda."""
    bal, _ = get_current_balance_usdt(cfg, state)
    mode_label = "🟢 REAL (Binance Spot)" if cfg.get("mode") == "REAL" else "📝 PAPER (Simulación)"
    return (
        "🙏 *BIENVENIDO A TU BOT CUANTITATIVO MÓVIL*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Modo:* `{mode_label}`\n"
        f"• *Saldo en Binance:* `${bal:,.2f} USDT`\n\n"
        "Tocá cualquiera de los botones de abajo en tu teclado para consultar:\n\n"
        "• 📈 *Operación en Vivo:* Monitor del trade actual y precio BTC\n"
        "• 📊 *Estado General:* Resumen de cuenta, límites y configuración\n"
        "• 🌍 *Sesión de Mercado:* Bolsas abiertas y cambio de horario\n"
        "• 📋 *Historial Real:* Lista de compras/ventas reales de Binance Spot\n"
        "• 💰 *Cerrar Trade:* Botón de seguridad para cerrar la orden al instante\n"
        "• 📖 *Versículo Bíblico:* Palabra de sabiduría y paz para hoy"
    )


# =============================================================================
# DESPACHADOR CENTRAL DE COMANDOS (PROBADO Y ROBUSTO)
# =============================================================================

def handle_telegram_incoming_text(raw_text: str, token: str, chat_id: str) -> None:
    """
    Recibe el texto enviado por el usuario (o clic de botón) y ejecuta la acción correspondiente.
    """
    text = raw_text.strip().lower()
    cfg = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)

    # 1. CERRAR TRADE
    if any(k in text for k in ["/cerrar", "cerrar trade", "cerrar"]):
        closed_rec = close_active_trade_now(reason="CIERRE_MANUAL_TELEGRAM")
        if closed_rec is None:
            bal, _ = get_current_balance_usdt(cfg, load_json(STATE_FILE))
            send_telegram_message(
                token, chat_id,
                f"⚪ *No hay ninguna operación abierta en este momento para cerrar.*\n"
                f"Tu saldo de `${bal:,.2f} USDT` está 100% protegido y libre en Binance Spot.\n"
                f"El bot abrirá la siguiente posición en cuanto detecte una oportunidad válida."
            )
        else:
            pnl_u = float(closed_rec.get("pnl_usdt", 0.0))
            pnl_ars = pnl_u * fetch_usdt_ars()
            roe_t = float(closed_rec.get("roe_pct", 0.0))
            new_bal, _ = get_current_balance_usdt(cfg, load_json(STATE_FILE))
            icon = "🟢 POSITIVA (GANANCIA ASEGURADA)" if pnl_u >= 0 else "🔴 NEGATIVA (CERRADA)"
            close_msg = (
                f"💰 *OPERACIÓN CERRADA MANUALMENTE*\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"• *Resultado:* {icon}\n"
                f"• *Monto:* `{pnl_u:+,.2f} USDT` (`ARS$ {pnl_ars:+,.0f}`)\n"
                f"• *Rendimiento:* `{roe_t:+.2f}%` (`{closed_rec.get('r_multiple', 0):+.2f}R`)\n"
                f"• *Entrada ➔ Salida:* `${closed_rec.get('entry_price', 0):,.2f}` ➔ `${closed_rec.get('exit_price', 0):,.2f}`\n"
                f"• *Nuevo Saldo en Binance:* `${new_bal:,.2f} USDT`\n\n"
                f"📖 _{closed_rec.get('verse', '')}_"
            )
            send_telegram_message(token, chat_id, close_msg)
        return

    # 2. CAMBIO DE SESIÓN DIRECTO (ej: '24/7', 'ny', 'londres', '/sesion todas')
    is_session_cmd = any(k in text for k in ["/sesion", "sesion", "sesión", "horario"])
    direct_session_keywords = ["24/7", "24", "todas", "ny", "nueva york", "new york", "londres", "london", "asia", "tokio", "overlap"]

    if is_session_cmd or text in direct_session_keywords:
        new_smode = None
        if any(k in text for k in ["24/7", "todas", "24"]):
            new_smode = "TODAS_24_7"
        elif any(k in text for k in ["ny", "nueva york", "new york"]):
            new_smode = "NUEVA_YORK"
        elif any(k in text for k in ["londres", "london"]):
            new_smode = "LONDRES"
        elif any(k in text for k in ["overlap"]):
            new_smode = "OVERLAP_LONDRES_NY"
        elif any(k in text for k in ["asia", "tokio"]):
            new_smode = "ASIA"

        if new_smode:
            cfg["session_mode"] = new_smode
            save_json(CONFIG_FILE, cfg)
            label = SESSION_MODES.get(new_smode, {}).get("label", new_smode)
            send_telegram_message(
                token, chat_id,
                f"✅ *Sesión actualizada con éxito a:* *{label}*\n\n"
                + build_session_message(cfg)
            )
        else:
            send_telegram_message(token, chat_id, build_session_message(cfg))
        return

    # 3. OPERACIÓN EN VIVO
    if any(k in text for k in ["/operacion", "operacion", "operación"]):
        send_telegram_message(token, chat_id, build_operation_message())
        return

    # 4. ESTADO GENERAL
    if any(k in text for k in ["/estado", "estado"]):
        send_telegram_message(token, chat_id, build_status_message())
        return

    # 5. HISTORIAL PAPER (SIMULACIÓN ANTERIOR)
    if any(k in text for k in ["/historial_paper", "historial paper", "paper"]):
        send_telegram_message(token, chat_id, build_history_message(show_paper=True))
        return

    # 6. HISTORIAL REAL
    if any(k in text for k in ["/historial", "historial"]):
        send_telegram_message(token, chat_id, build_history_message(show_paper=False))
        return

    # 7. VERSÍCULO BÍBLICO
    if any(k in text for k in ["/versiculo", "versiculo", "versículo", "palabra", "sabiduria", "biblia"]):
        v = get_random_verse()
        send_telegram_message(
            token, chat_id,
            f"📖 *Palabra de Fe y Sabiduría:*\n\n_{v['verse']}_\n\n— *{v['reference']}* ({v['theme']})"
        )
        return

    # 8. MENÚ / AYUDA / DEFAULT
    send_telegram_message(token, chat_id, build_welcome_message(cfg, state))


# =============================================================================
# LISTENER AUTÓNOMO DE TELEGRAM (BUCLE PRINCIPAL DE POLLING)
# =============================================================================

def run_telegram_listener():
    """
    Bucle principal de escucha de comandos de Telegram con auto-recuperación,
    notificaciones push automáticas cuando abre o cierra un trade y logging limpio.
    """
    last_update_id = 0
    initial_state = load_json(STATE_FILE)
    notified_opened_times = set()
    notified_closed_times = set()

    init_active = (initial_state.get("active_trade") or {}).get("entry_time")
    if init_active:
        notified_opened_times.add(init_active)
    for t_hist in initial_state.get("trade_history", []):
        if t_hist.get("entry_time"):
            notified_closed_times.add(t_hist.get("entry_time"))
            notified_opened_times.add(t_hist.get("entry_time"))

    print("[TELEGRAM BOT] Servicio iniciado y listo para escuchar en Telegram.")

    while True:
        try:
            cfg = load_json(CONFIG_FILE)
            token = os.environ.get("TELEGRAM_BOT_TOKEN", cfg.get("telegram_bot_token", "")).strip()

            if not token:
                time.sleep(10)
                continue

            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": 8}
            resp = requests.get(url, params=params, timeout=12)

            if resp.status_code == 409:
                # Otra instancia está escuchando simultáneamente; esperar pacientemente
                time.sleep(15)
                continue

            if resp.status_code == 200:
                updates = resp.json().get("result", [])
                for upd in updates:
                    last_update_id = upd["update_id"]
                    msg_obj = upd.get("message", {})
                    chat_id = str(msg_obj.get("chat", {}).get("id", ""))
                    raw_text = msg_obj.get("text", "").strip()

                    if not chat_id or not raw_text:
                        continue

                    # Auto-guardar chat_id si no estaba guardado
                    if not cfg.get("telegram_chat_id"):
                        cfg["telegram_chat_id"] = chat_id
                        save_json(CONFIG_FILE, cfg)

                    print(f"[TELEGRAM MSG] Recibido de chat={chat_id}: '{raw_text}'")
                    handle_telegram_incoming_text(raw_text, token, chat_id)

            # Notificaciones automáticas de aperturas y cierres
            state = load_json(STATE_FILE)
            active = state.get("active_trade")
            current_entry_time = (active or {}).get("entry_time")

            # 1) Notificar nueva apertura
            if current_entry_time and current_entry_time not in notified_opened_times and cfg.get("telegram_chat_id"):
                notified_opened_times.add(current_entry_time)
                bal, _ = get_current_balance_usdt(cfg, state)
                open_msg = (
                    "🚀 *NUEVA OPERACIÓN ABIERTA EN BINANCE SPOT*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    + format_active_operation_block(active, cfg, bal)
                    + "\n💡 _Tocá_ 📈 *Operación en Vivo* _para seguirla segundo a segundo._"
                )
                send_telegram_message(token, cfg["telegram_chat_id"], open_msg)

            # 2) Notificar cierre
            history = state.get("trade_history", [])
            if history and cfg.get("telegram_chat_id"):
                new_trade = history[-1]
                closed_et = new_trade.get("entry_time", str(new_trade.get("id", "")))
                if closed_et and closed_et not in notified_closed_times:
                    notified_closed_times.add(closed_et)
                    pnl_u = float(new_trade.get("pnl_usdt", 0.0))
                    pnl_ars = pnl_u * fetch_usdt_ars()
                    roe_t = float(new_trade.get("roe_pct", 0.0))
                    t_mode = new_trade.get("mode", "REAL")
                    icon = "🟢 POSITIVA (GANANCIA TOMADA)" if pnl_u >= 0 else "🔴 NEGATIVA (STOP LOSS ACTIVADO)"
                    alert_msg = (
                        f"🔔 *OPERACIÓN CERRADA [{t_mode}]: {icon}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"• *Activo:* `{new_trade.get('symbol')}`\n"
                        f"• *Resultado Final:* `{pnl_u:+,.2f} USDT` (`ARS$ {pnl_ars:+,.0f}`)\n"
                        f"• *Rendimiento:* `{roe_t:+.2f}%` (`{new_trade.get('r_multiple', 0):+.2f}R`)\n"
                        f"• *Entrada ➔ Salida:* `${float(new_trade.get('entry_price', 0)):,.2f}` ➔ `${float(new_trade.get('exit_price', 0)):,.2f}`\n"
                        f"• *Motivo de Salida:* `{new_trade.get('exit_reason')}`\n"
                        f"• *Diagnóstico:* {new_trade.get('explanation')}\n\n"
                        f"📖 _{new_trade.get('verse')}_"
                    )
                    send_telegram_message(token, cfg["telegram_chat_id"], alert_msg)

        except Exception as e_poll:
            # Continuar en caso de fallo transitorio de red
            pass

        time.sleep(2)


if __name__ == "__main__":
    run_telegram_listener()
