"""
Aplicación Móvil en Telegram para Control y Monitoreo del Bot (telegram_bot.py).
"Encomienda a Jehová tu camino, y confía en él; y él hará." — Salmos 37:5 (RVR1960)

Permite usar y consultar el sistema directamente desde la app nativa de Telegram en el celular
(sin necesidad de abrir ningún sitio web ni estar en la misma red Wi-Fi).
Comandos en el celular:
- /start o /menu : Muestra el panel con botones interactivos
- /estado        : Muestra saldo, operaciones hoy (máx 2/día) y posición abierta
- /historial     : Muestra las operaciones realizadas, ganancias y explicación de errores en negativas
- /versiculo     : Envía una palabra bíblica cristiana de sabiduría y paz
"""

import json
import os
import time
import requests

from biblical_wisdom import get_random_verse

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
                [{"text": "📈 /operacion"}, {"text": "📊 /estado"}],
                [{"text": "📋 /historial"}, {"text": "📖 /versiculo"}]
            ],
            "resize_keyboard": True
        }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")


def format_active_operation_block(active: dict, cfg: dict, paper_bal: float) -> str:
    if not active:
        return (
            "⚪ *SIN OPERACIÓN ABIERTA AHORA MISMO*\n"
            "El bot está escaneando el mercado cada 25s buscando el próximo gatillo de alta probabilidad.\n\n"
        )

    sym = active.get("symbol", cfg.get("symbol", "BTCUSDT"))
    entry_p = float(active.get("entry_price", 0.0))
    stop_p = float(active.get("stop_price", 0.0))
    tp_p = float(active.get("tp_price", 0.0))
    units = float(active.get("units", 0.0))
    lev = float(active.get("leverage", cfg.get("leverage", 5.0)))
    margin_u = float(active.get("margin_usdt", (entry_p * units) / max(lev, 1.0)))
    notional_u = float(active.get("notional_usdt", entry_p * units))
    strat_name = active.get("strategy", "Adaptativa")

    live_p = fetch_live_price(sym, fallback=entry_p)
    usdt_ars = fetch_usdt_ars()

    pnl_usdt = (live_p - entry_p) * units
    pnl_ars = pnl_usdt * usdt_ars
    price_diff_pct = ((live_p - entry_p) / entry_p * 100.0) if entry_p > 0 else 0.0
    roe_pct = (pnl_usdt / margin_u * 100.0) if margin_u > 0 else (price_diff_pct * lev)

    risk_per_u = abs(entry_p - stop_p)
    risk_usdt = risk_per_u * units if risk_per_u > 0 else max(paper_bal * 0.02, 1.0)
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

    equity_vivo = paper_bal + pnl_usdt

    return (
        f"{status_banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{amount_line}\n"
        f"⚡ *ROE Apalancado ({lev:.0f}x):* `{roe_pct:+.2f}%` (`{r_mult:+.2f}R`)\n"
        f"💵 *Capital Total en Vivo:* `${equity_vivo:,.2f} USDT`\n\n"
        f"📊 *DETALLES DE LA OPERACIÓN ({sym}):*\n"
        f"• *Estrategia:* `{strat_name}`\n"
        f"• *Precio Entrada:* `${entry_p:,.2f}`\n"
        f"• *Precio Actual:* `${live_p:,.2f}` (`{price_diff_pct:+.2f}%`)\n"
        f"• *Margen / Posición:* `${margin_u:,.2f}` ➔ `${notional_u:,.2f} USDT` (`{lev:.0f}x`)\n"
        f"• *🎯 Take Profit:* `${tp_p:,.2f}` (falta `{dist_to_tp_pct:+.2f}%` | meta `+{tp_gain_usdt:,.2f} USDT`)\n"
        f"• *🛑 Stop Loss:* `${stop_p:,.2f}` (colchón `{dist_to_sl_pct:.2f}%` | riesgo `-{risk_usdt:,.2f} USDT`)\n\n"
        f"🗺️ *Recorrido SL ➔ Entrada (⚡) ➔ TP:*\n"
        f"`{progress_bar}`\n\n"
    )


def build_operation_message() -> str:
    cfg = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)
    v = get_random_verse()
    paper_bal = float(state.get("paper_balance_usdt", 1000.0))
    active = state.get("active_trade")

    msg = "📈 *MONITOR EN VIVO DE TU OPERACIÓN*\n━━━━━━━━━━━━━━━━━━━━\n"
    msg += format_active_operation_block(active, cfg, paper_bal)
    msg += f"📖 _{v['verse']}_\n— *{v['reference']}*"
    return msg


def build_status_message() -> str:
    cfg = load_json(CONFIG_FILE)
    state = load_json(STATE_FILE)
    v = get_random_verse()

    mode = cfg.get("mode", "PAPER")
    sym = cfg.get("symbol", "BTCUSDT")
    tf = cfg.get("timeframe", "15m")
    lev = float(cfg.get("leverage", 5.0))
    max_d = cfg.get("max_trades_per_day", 2)
    today_cnt = state.get("trades_today_count", 0)
    paper_bal = float(state.get("paper_balance_usdt", 1000.0))
    active = state.get("active_trade")

    msg = (
        f"🤖 *ESTADO DEL BOT CUANTITATIVO*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Modo:* `{mode}` | *Apalancamiento:* `{lev:.0f}x`\n"
        f"• *Activo:* `{sym}` ({tf})\n"
        f"• *Operaciones Hoy:* `{today_cnt} / {max_d}`\n"
        f"• *Saldo Base:* `${paper_bal:,.2f} USDT`\n"
        f"• *Cerradas Históricas:* `{state.get('total_trades', 0)} trades`\n\n"
    )

    msg += format_active_operation_block(active, cfg, paper_bal)
    msg += f"📖 _{v['verse']}_\n— *{v['reference']}*"
    return msg


def build_history_message() -> str:
    state = load_json(STATE_FILE)
    history = state.get("trade_history", [])
    usdt_ars = fetch_usdt_ars()

    if not history:
        return (
            "📋 *HISTORIAL DE OPERACIONES*\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Aún no se han cerrado operaciones en el registro en vivo.\n"
            "El bot notificará aquí cada vez que cierre un trade con su ganancia o diagnóstico de mejora."
        )

    wins = sum(1 for t in history if t.get("pnl_usdt", 0) > 0)
    losses = len(history) - wins
    total_pnl = sum(t.get("pnl_usdt", 0.0) for t in history)
    total_pnl_ars = total_pnl * usdt_ars

    msg = (
        f"📋 *HISTORIAL Y DIAGNÓSTICO DE TRADES*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Total:* {len(history)} ({wins} Positivas 🟢 / {losses} Negativas 🔴)\n"
        f"• *Resultado Acumulado:* `{total_pnl:+,.2f} USDT` (`ARS$ {total_pnl_ars:+,.0f}`)\n\n"
    )

    for t in history[-5:]:
        pnl_u = float(t.get("pnl_usdt", 0.0))
        pnl_a = pnl_u * usdt_ars
        lev_t = float(t.get("leverage", 1.0))
        roe_t = float(t.get("roe_pct", 0.0))
        icon = "🟢 POSITIVA" if pnl_u >= 0 else "🔴 NEGATIVA"
        msg += (
            f"{icon} — *Trade #{t.get('id', 1)} ({t.get('symbol', 'BTCUSDT')} {lev_t:.0f}x)*\n"
            f"• *Resultado:* `{pnl_u:+,.2f} USDT` (`ARS$ {pnl_a:+,.0f}` | ROE `{roe_t:+.2f}%`)\n"
            f"• *Entrada / Salida:* `${t.get('entry_price', 0):,.2f}` ➔ `${t.get('exit_price', 0):,.2f}` ({t.get('exit_reason', '')})\n"
            f"• *Análisis:* {t.get('explanation', '')}\n"
            f"• *Cómo mejorar:* _{t.get('improvement', '')}_\n\n"
        )

    return msg


def run_telegram_listener():
    last_update_id = 0
    initial_state = load_json(STATE_FILE)
    notified_trades_count = len(initial_state.get("trade_history", []))
    last_active_entry_time = (initial_state.get("active_trade") or {}).get("entry_time")
    connected_logged = False

    while True:
        try:
            cfg = load_json(CONFIG_FILE)
            token = os.environ.get("TELEGRAM_BOT_TOKEN", cfg.get("telegram_bot_token", "")).strip()

            if not token:
                time.sleep(15)
                continue

            if not connected_logged:
                print("[TELEGRAM APP] Conectado y escuchando comandos desde tu celular...")
                connected_logged = True

            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"offset": last_update_id + 1, "timeout": 10}
            resp = requests.get(url, params=params, timeout=15)

            if resp.status_code == 200:
                updates = resp.json().get("result", [])
                for upd in updates:
                    last_update_id = upd["update_id"]
                    msg_obj = upd.get("message", {})
                    chat_id = str(msg_obj.get("chat", {}).get("id", ""))
                    text = msg_obj.get("text", "").strip().lower()

                    if not chat_id:
                        continue

                    # Guardar chat_id automáticamente en config_bot.json si no estaba
                    if not cfg.get("telegram_chat_id"):
                        cfg["telegram_chat_id"] = chat_id
                        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                            json.dump(cfg, f, indent=4)

                    if "/operacion" in text or "operacion" in text or "operación" in text:
                        send_telegram_message(token, chat_id, build_operation_message())
                    elif "/estado" in text or "estado" in text:
                        send_telegram_message(token, chat_id, build_status_message())
                    elif "/historial" in text or "historial" in text:
                        send_telegram_message(token, chat_id, build_history_message())
                    elif "/versiculo" in text or "versiculo" in text:
                        v = get_random_verse()
                        send_telegram_message(
                            token, chat_id,
                            f"📖 *Palabra de Sabiduría:*\n\n_{v['verse']}_\n\n— *{v['reference']}* ({v['theme']})"
                        )
                    else:
                        welcome = (
                            "🙏 *Bendiciones. Bienvenido a tu Bot Cuantitativo Móvil.*\n\n"
                            "Tocá cualquiera de los botones de abajo en tu celular para consultar:\n"
                            "• 📈 */operacion* — Ver cómo va la operación actual (si vas *POSITIVO* o *NEGATIVO* y con cuánto en USDT, ARS y ROE%)\n"
                            "• 📊 */estado* — Ver resumen general del bot + operación abierta\n"
                            "• 📋 */historial* — Ver operaciones cerradas, ganancias y diagnóstico\n"
                            "• 📖 */versiculo* — Recibir un versículo bíblico cristiano"
                        )
                        send_telegram_message(token, chat_id, welcome)

            # Verificar cambios en el estado para notificaciones automáticas al celular
            state = load_json(STATE_FILE)
            active = state.get("active_trade")
            current_entry_time = (active or {}).get("entry_time")

            # 1) Si se acaba de ABRIR una nueva operación, notificar al celular
            if current_entry_time and current_entry_time != last_active_entry_time and cfg.get("telegram_chat_id"):
                open_msg = (
                    "🚀 *NUEVA OPERACIÓN ABIERTA POR EL BOT*\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    + format_active_operation_block(active, cfg, float(state.get("paper_balance_usdt", 1000.0)))
                    + "💡 _Tocá el botón_ 📈 */operacion* _en cualquier momento para ver cómo va en vivo._"
                )
                send_telegram_message(token, cfg["telegram_chat_id"], open_msg)
            last_active_entry_time = current_entry_time

            # 2) Si se acaba de CERRAR una operación, notificar al celular con el resultado final
            history = state.get("trade_history", [])
            if len(history) > notified_trades_count and cfg.get("telegram_chat_id"):
                new_trade = history[-1]
                pnl_u = float(new_trade.get("pnl_usdt", 0.0))
                pnl_ars = pnl_u * fetch_usdt_ars()
                roe_t = float(new_trade.get("roe_pct", 0.0))
                lev_t = float(new_trade.get("leverage", cfg.get("leverage", 5.0)))
                icon = "🟢 POSITIVA (GANANCIA)" if pnl_u >= 0 else "🔴 NEGATIVA (PÉRDIDA)"
                alert_msg = (
                    f"🔔 *OPERACIÓN CERRADA: {icon}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"• *Par:* `{new_trade.get('symbol')}` (`{lev_t:.0f}x`)\n"
                    f"• *Resultado Final:* `{pnl_u:+,.2f} USDT` (`ARS$ {pnl_ars:+,.0f}`)\n"
                    f"• *ROE / R-Múltiplo:* `{roe_t:+.2f}%` (`{new_trade.get('r_multiple', 0):+.2f}R`)\n"
                    f"• *Diagnóstico:* {new_trade.get('explanation')}\n"
                    f"• *Lección de mejora:* _{new_trade.get('improvement')}_\n\n"
                    f"📖 _{new_trade.get('verse')}_"
                )
                send_telegram_message(token, cfg["telegram_chat_id"], alert_msg)
                notified_trades_count = len(history)

        except Exception:
            pass

        time.sleep(3)


if __name__ == "__main__":
    run_telegram_listener()
