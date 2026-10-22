"""
Aplicación Móvil en Telegram para Control y Monitoreo del Bot (telegram_bot.py).
"Encomienda a Jehová tu camino, y confía en él; y él hará." — Salmos 37:5 (RVR1960)

Permite controlar, configurar y monitorear el bot directamente desde la app nativa de Telegram en el celular.
Compatible con modo REAL (Binance Spot) y modo PAPER (Simulación).
"""

import json
import os
import time
import requests

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
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def fetch_live_price(symbol: str, fallback: float = 0.0) -> float:
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
    val = fetch_live_price("USDTARS", fallback=1450.0)
    return val if val > 100 else 1450.0


def send_telegram_message(token: str, chat_id: str, text: str, with_keyboard: bool = True):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
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
        print(f"[TELEGRAM SEND] status={r.status_code} to={chat_id}")
        # Si Telegram rechaza el parse_mode Markdown por algún carácter especial, reintentar en texto plano
        if r.status_code != 200:
            print(f"[TELEGRAM RETRY RAW] Response: {r.text}")
            payload.pop("parse_mode", None)
            r2 = requests.post(url, json=payload, timeout=10)
            print(f"[TELEGRAM RETRY RESULT] status={r2.status_code}")
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")


def format_active_operation_block(active: dict, cfg: dict, current_bal: float) -> str:
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
    lev = float(active.get("leverage", 1.0 if mode == "REAL" else 5.0))
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

    # Barra de progreso visual entre Stop Loss y Take Profit
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
    lev_label = "Spot 1x (Real)" if mode == "REAL" else f"{lev:.0f}x"

    return (
        f"{status_banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{amount_line}\n"
        f"⚡ *Rendimiento:* `{roe_pct:+.2f}%` (`{r_mult:+.2f}R` | {lev_label})\n"
        f"💵 *Capital Total en Vivo:* `${equity_vivo:,.2f} USDT`\n\n"
        f"📊 *DETALLES DE LA OPERACIÓN ({sym}):*\n"
        f"• *Modo:* `{mode}`\n"
        f"• *Estrategia:* `{strat_name}`\n"
        f"• *Precio Entrada:* `${entry_p:,.2f}`\n"
        f"• *Precio Actual:* `${live_p:,.2f}` (`{price_diff_pct:+.2f}%`)\n"
        f"• *Capital en Trade:* `${margin_u:,.2f} USDT` ({units:.5f} {sym[:3]})\n"
        f"• *🎯 Take Profit:* `${tp_p:,.2f}` (falta `{dist_to_tp_pct:+.2f}%` | meta `+{tp_gain_usdt:,.2f} USDT`)\n"
        f"• *🛑 Stop Loss:* `${stop_p:,.2f}` (colchón `{dist_to_sl_pct:.2f}%` | riesgo `-{risk_usdt:,.2f} USDT`)\n\n"
        f"🗺️ *Recorrido SL ➔ Entrada (⚡) ➔ TP:*\n"
        f"`{progress_bar}`\n\n"
        f"💡 _Tocá el botón_ 💰 *Cerrar Trade* _si querés cerrarla ahora mismo al precio actual._\n\n"
    )


def get_current_balance_usdt(cfg: dict, state: dict) -> float:
    mode = cfg.get("mode", "REAL")
    if mode == "REAL" and cfg.get("binance_api_key") and cfg.get("binance_api_secret"):
        try:
            return fetch_real_binance_balance(cfg["binance_api_key"], cfg["binance_api_secret"], "USDT")
        except Exception:
            return float(state.get("real_balance_usdt", 11.41))
    return float(state.get("paper_balance_usdt", 11.41))


def build_operation_message() -> str:
    cfg = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)
    sym = cfg.get("symbol", "BTCUSDT")
    active = state.get("active_trade")
    usdt_ars = fetch_usdt_ars()
    live_p = fetch_live_price(sym, fallback=0.0)
    bal = get_current_balance_usdt(cfg, state)
    s_eval = evaluate_trading_session(str(cfg.get("session_mode", "TODAS_24_7")))

    if not active:
        why_wait = (
            "⏳ *Esperando horario de sesión:* Tu bot está configurado en *Sesión Nueva York* (09:00 a 17:00 hs ARG). "
            "Por seguridad, no abre compras de noche salvo que actives el modo 24/7 (escribiendo `24/7`)."
            if not s_eval["allowed_now"]
            else "🔍 *Escaneando:* Esperando que las EMAs y el ADX confirmen señal de compra alcista."
        )
        return (
            "📈 *MONITOR DE OPERACIÓN*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚪ *Estado:* Sin operación abierta en este momento.\n\n"
            f"• *Precio actual BTC:* `${live_p:,.2f}`\n"
            f"• *Saldo listo en Binance:* `${bal:,.2f} USDT` (`ARS$ {bal * usdt_ars:,.0f}`)\n"
            f"• *Monto por orden:* `${cfg.get('max_position_usdt', 10.0):,.2f} USDT`\n\n"
            f"💡 *Situación actual:*\n{why_wait}\n\n"
            "_(En cuanto compre, acá verás el gráfico de ganancias en vivo y el botón para cerrarla)._"
        )
    else:
        return format_active_operation_block(active, cfg, bal)


def build_session_message(cfg: dict) -> str:
    s_mode = str(cfg.get("session_mode", "TODAS_24_7"))
    s_eval = evaluate_trading_session(s_mode)
    l_badge = "🟢 ABIERTA" if s_eval["london_open"] else "⚪ CERRADA"
    ny_badge = "🟢 ABIERTA" if s_eval["ny_open"] else "⚪ CERRADA"
    ov_badge = "🔥 ACTIVO" if s_eval["overlap_open"] else "⚪ INACTIVO"
    as_badge = "🟢 ABIERTA" if s_eval["asia_open"] else "⚪ CERRADA"
    perm_badge = "🟢 HABILITADO (Operando ahora)" if s_eval["allowed_now"] else "⏳ EN PAUSA (Fuera de horario)"

    return (
        "🌍 *SESIONES INSTITUCIONALES DE MERCADO*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Hora actual (ARG):* `{s_eval['arg_time']} hs`\n"
        f"• *Tu configuración:* *{s_eval['mode_short']}* (`{s_eval['horario_arg']}`)\n"
        f"• *Estado del bot:* *{perm_badge}*\n\n"
        "🕒 *Bolsas mundiales en este momento:*\n"
        f"• 🇺🇸 Nueva York (09 a 17 hs): {ny_badge}\n"
        f"• 🇬🇧 Londres (04 a 12 hs): {l_badge}\n"
        f"• 🔥 Cruce Londres+NY (09 a 12 hs): {ov_badge}\n"
        f"• 🇯🇵 Tokio/Asia (20 a 04 hs): {as_badge}\n\n"
        "⚙️ *Para cambiar de sesión escribí:*\n"
        "• `24/7` — Operar las 24 horas sin esperar sesión\n"
        "• `ny` — Solo en Sesión Nueva York (09 a 17 hs)\n"
        "• `londres` — Solo en Sesión Londres (04 a 12 hs)"
    )


def build_status_message() -> str:
    cfg = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)
    mode = cfg.get("mode", "REAL")
    sym = cfg.get("symbol", "BTCUSDT")
    max_d = cfg.get("max_trades_per_day", 2)
    today_cnt = state.get("trades_today_count", 0)
    bal = get_current_balance_usdt(cfg, state)
    usdt_ars = fetch_usdt_ars()
    s_eval = evaluate_trading_session(str(cfg.get("session_mode", "TODAS_24_7")))
    active = state.get("active_trade")

    perm_str = "🟢 SÍ (Buscando compras)" if s_eval["allowed_now"] else "⏳ NO (Pausado por horario de sesión)"
    pos_str = "🟢 1 OPERACIÓN EN CURSO" if active else "⚪ NINGUNA (ESPERANDO SEÑAL)"

    return (
        "📊 *ESTADO GENERAL DEL BOT*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Modo:* `{'🟢 REAL (Binance Spot)' if mode == 'REAL' else '📝 PAPER (Simulación)'}`\n"
        f"• *Saldo en Binance:* `${bal:,.2f} USDT` (`ARS$ {bal * usdt_ars:,.0f}`)\n"
        f"• *Monto por Trade:* `${cfg.get('max_position_usdt', 10.0):,.2f} USDT`\n"
        f"• *Par:* `{sym}` (Spot 1x sin deuda)\n"
        f"• *Horario Configurado:* *{s_eval['mode_short']}* (`{s_eval['horario_arg']}`)\n"
        f"• *¿Puede operar ahora?:* {perm_str}\n"
        f"• *Trades realizados hoy:* `{today_cnt} / {max_d}`\n"
        f"• *Posición actual:* {pos_str}"
    )


def build_history_message(show_paper: bool = False) -> str:
    cfg = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)
    mode = cfg.get("mode", "REAL")
    all_history = state.get("trade_history", [])
    usdt_ars = fetch_usdt_ars()

    if mode == "REAL" and not show_paper:
        history = [t for t in all_history if t.get("mode") == "REAL"]
        title = "📋 *HISTORIAL DE TRADES REALES*\n━━━━━━━━━━━━━━━━━━━━\n"
    else:
        history = all_history
        title = "📋 *HISTORIAL DE PRUEBAS (PAPER)*\n━━━━━━━━━━━━━━━━━━━━\n"

    if not history:
        return (
            f"{title}"
            "• *Trades reales ejecutados:* `0`\n"
            "• *Ganancia acumulada:* `$0.00 USDT`\n\n"
            "Aún no se realizaron compras con dinero real en tu cuenta de Binance Spot. "
            "En cuanto el bot ejecute la primera orden, verás acá el resultado detallado con su precio de compra y ganancia neta.\n\n"
            "💡 _(Para ver las pruebas simuladas anteriores escribí:_ `/historial_paper`_)"
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


def run_telegram_listener():
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

    connected_logged = False

    while True:
        try:
            cfg = load_json(CONFIG_FILE)
            token = os.environ.get("TELEGRAM_BOT_TOKEN", cfg.get("telegram_bot_token", "")).strip()

            if not token:
                time.sleep(15)
                continue

            url = f"https://api.telegram.org/bot{token}/getUpdates"
            if not connected_logged:
                print("[TELEGRAM APP] Conectado y escuchando comandos desde tu celular...")
                connected_logged = True
                try:
                    r_init = requests.get(url, params={"offset": -1, "timeout": 1}, timeout=5)
                    if r_init.status_code == 200:
                        res_init = r_init.json().get("result", [])
                        if res_init:
                            last_update_id = res_init[-1]["update_id"]
                except Exception:
                    pass

            params = {"offset": last_update_id + 1, "timeout": 8}
            resp = requests.get(url, params=params, timeout=12)

            if resp.status_code == 409:
                time.sleep(20)
                continue

            if resp.status_code == 200:
                updates = resp.json().get("result", [])
                for upd in updates:
                    last_update_id = upd["update_id"]
                    msg_obj = upd.get("message", {})
                    chat_id = str(msg_obj.get("chat", {}).get("id", ""))
                    raw_text = msg_obj.get("text", "").strip()
                    text = raw_text.lower()

                    if not chat_id:
                        continue

                    print(f"[TELEGRAM INCOMING] chat={chat_id} | text='{raw_text}'")

                    # Guardar chat_id automáticamente en config_bot.json
                    if not cfg.get("telegram_chat_id"):
                        cfg["telegram_chat_id"] = chat_id
                        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                            json.dump(cfg, f, indent=4)

                    # 1. COMANDO CERRAR TRADE
                    if any(k in text for k in ["/cerrar", "cerrar trade", "cerrar"]):
                        closed_rec = close_active_trade_now(reason="CIERRE_MANUAL_TELEGRAM")
                        if closed_rec is None:
                            curr_bal = get_current_balance_usdt(cfg, load_json(STATE_FILE))
                            send_telegram_message(
                                token, chat_id,
                                f"⚪ *No hay ninguna operación abierta en este momento para cerrar.*\n"
                                f"Tu saldo de `${curr_bal:,.2f} USDT` está 100% libre y seguro en Binance Spot.\n"
                                f"El bot abrirá la siguiente posición en cuanto detecte una oportunidad válida."
                            )
                        else:
                            if closed_rec.get("entry_time"):
                                notified_closed_times.add(closed_rec["entry_time"])
                            pnl_u = float(closed_rec.get("pnl_usdt", 0.0))
                            pnl_ars = pnl_u * fetch_usdt_ars()
                            roe_t = float(closed_rec.get("roe_pct", 0.0))
                            new_bal = get_current_balance_usdt(cfg, load_json(STATE_FILE))
                            icon = "🟢 POSITIVA (GANANCIA TOMADA)" if pnl_u >= 0 else "🔴 NEGATIVA (CERRADA)"
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

                    # 2. COMANDO CAMBIO / CONSULTA DE SESIÓN DE MERCADO
                    elif any(k in text for k in ["/sesion", "sesion", "sesión", "horario"]) or text in ["ny", "londres", "todas", "24/7", "24", "asia", "overlap"]:
                        new_smode = None
                        if any(k in text for k in ["londres_ny", "londres y", "londres+ny"]):
                            new_smode = "LONDRES_NY"
                        elif "overlap" in text:
                            new_smode = "OVERLAP_LONDRES_NY"
                        elif "londres" in text:
                            new_smode = "LONDRES"
                        elif any(k in text for k in ["ny", "nueva york", "new york"]):
                            new_smode = "NUEVA_YORK"
                        elif any(k in text for k in ["asia", "tokio"]):
                            new_smode = "ASIA"
                        elif any(k in text for k in ["todas", "24/7", "24 hs", "24h", "24"]):
                            new_smode = "TODAS_24_7"

                        if new_smode:
                            cfg["session_mode"] = new_smode
                            with open(CONFIG_FILE, "w", encoding="utf-8") as f_s:
                                json.dump(cfg, f_s, indent=4)
                            send_telegram_message(
                                token, chat_id,
                                f"✅ *Sesión actualizada con éxito a:* *{SESSION_MODES[new_smode]['label']}*\n\n"
                                + build_session_message(cfg)
                            )
                        else:
                            send_telegram_message(token, chat_id, build_session_message(cfg))

                    # 3. COMANDO OPERACIÓN EN VIVO
                    elif any(k in text for k in ["/operacion", "operacion", "operación"]):
                        send_telegram_message(token, chat_id, build_operation_message())

                    # 4. COMANDO ESTADO GENERAL
                    elif any(k in text for k in ["/estado", "estado"]):
                        send_telegram_message(token, chat_id, build_status_message())

                    # 5. COMANDO HISTORIAL PAPER (SIMULACIÓN ANTERIOR)
                    elif any(k in text for k in ["/historial_paper", "historial paper", "paper"]):
                        send_telegram_message(token, chat_id, build_history_message(show_paper=True))

                    # 6. COMANDO HISTORIAL REAL
                    elif any(k in text for k in ["/historial", "historial"]):
                        send_telegram_message(token, chat_id, build_history_message(show_paper=False))

                    # 7. COMANDO VERSÍCULO
                    elif any(k in text for k in ["/versiculo", "versiculo", "versículo", "palabra", "sabiduria"]):
                        v = get_random_verse()
                        send_telegram_message(
                            token, chat_id,
                            f"📖 *Palabra de Fe y Sabiduría:*\n\n_{v['verse']}_\n\n— *{v['reference']}* ({v['theme']})"
                        )

                    # 8. BIENVENIDA / MENÚ PRINCIPAL
                    else:
                        mode_tag = "🟢 REAL (Binance Spot)" if cfg.get("mode") == "REAL" else "📝 PAPER (Simulación)"
                        curr_b = get_current_balance_usdt(cfg, load_json(STATE_FILE))
                        welcome = (
                            f"🙏 *Bienvenido a tu Bot Cuantitativo Móvil.*\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"• *Modo:* `{mode_tag}`\n"
                            f"• *Saldo en Binance:* `${curr_b:,.2f} USDT`\n\n"
                            f"Tocá cualquiera de los botones de abajo en tu teclado para consultar:\n\n"
                            f"• 📈 *Operación en Vivo* — Mira el trade actual, precio BTC y saldo en vivo\n"
                            f"• 📊 *Estado General* — Resumen de cuenta, configuración y filtros\n"
                            f"• 🌍 *Sesión de Mercado* — Ver bolsas abiertas y cambiar de horario\n"
                            f"• 📋 *Historial Real* — Lista de trades reales ejecutados con su ganancia\n"
                            f"• 💰 *Cerrar Trade* — Cierra la orden actual inmediatamente al precio de mercado\n"
                            f"• 📖 *Versículo Bíblico* — Recibir una palabra de aliento y sabiduría"
                        )
                        send_telegram_message(token, chat_id, welcome)

            # Verificación periódica de aperturas / cierres para notificar automáticamente al celular
            state = load_json(STATE_FILE)
            active = state.get("active_trade")
            current_entry_time = (active or {}).get("entry_time")

            # 1) Notificar si se acaba de ABRIR una operación
            if current_entry_time and current_entry_time not in notified_opened_times and cfg.get("telegram_chat_id"):
                notified_opened_times.add(current_entry_time)
                bal = get_current_balance_usdt(cfg, state)
                open_msg = (
                    "🚀 *NUEVA OPERACIÓN ABIERTA EN BINANCE*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    + format_active_operation_block(active, cfg, bal)
                    + "💡 _Tocá_ 📈 *Operación en Vivo* _para seguir la evolución segundo a segundo._"
                )
                send_telegram_message(token, cfg["telegram_chat_id"], open_msg)

            # 2) Notificar si se acaba de CERRAR una operación
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
                    icon = "🟢 POSITIVA (GANANCIA ASEGURADA)" if pnl_u >= 0 else "🔴 NEGATIVA (STOP LOSS ACTIVADO)"
                    alert_msg = (
                        f"🔔 *OPERACIÓN CERRADA [{t_mode}]: {icon}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"• *Activo:* `{new_trade.get('symbol')}`\n"
                        f"• *Resultado Final:* `{pnl_u:+,.2f} USDT` (`ARS$ {pnl_ars:+,.0f}`)\n"
                        f"• *Rendimiento:* `{roe_t:+.2f}%` (`{new_trade.get('r_multiple', 0):+.2f}R`)\n"
                        f"• *Entrada ➔ Salida:* `${float(new_trade.get('entry_price', 0)):,.2f}` ➔ `${float(new_trade.get('exit_price', 0)):,.2f}`\n"
                        f"• *Motivo de Salida:* `{new_trade.get('exit_reason')}`\n"
                        f"• *Diagnóstico:* {new_trade.get('explanation')}\n"
                        f"• *Lección de mejora:* _{new_trade.get('improvement')}_\n\n"
                        f"📖 _{new_trade.get('verse')}_"
                    )
                    send_telegram_message(token, cfg["telegram_chat_id"], alert_msg)

        except Exception as e_loop:
            import traceback
            print(f"[TELEGRAM LOOP ERROR] {e_loop}")
            traceback.print_exc()

        time.sleep(3)


if __name__ == "__main__":
    run_telegram_listener()
