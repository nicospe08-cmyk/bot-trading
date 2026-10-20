"""
Aplicación Web Cuantitativa de Validación y Selección de Estrategias de Trading.
Desarrollada en Streamlit con visualizaciones interactivas de Velas Japonesas y Equity en Plotly.

"Los pensamientos del diligente ciertamente tienden a la abundancia;
 Mas todo el que se apresura alocadamente, de cierto va a la pobreza." — Proverbios 21:5 (RVR1960)
"Encomienda a Jehová tus obras, y tus pensamientos serán afirmados." — Proverbios 16:3 (RVR1960)

Incluye:
- Conexión directa con la API pública de Binance Spot para cualquier par de criptomonedas.
- Soporte para Yahoo Finance, subida de CSV y datos sintéticos.
- Gráfico de Velas Japonesas con personalización de colores (alcista/bajista).
- Herramientas de dibujo interactivas (líneas de tendencia, rectángulos, círculos, etc.).
- Superposición de indicadores de la estrategia ganadora y marcadores de trades (entradas y salidas).
- Historial con diagnóstico forense de ganancias/errores y sabiduría bíblica cristiana.
- División estricta Train / Test sin look-ahead bias.
"""

import io
import json
import os
import time
from typing import Optional
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import streamlit as st

from analysis import run_full_pipeline
from biblical_wisdom import (
    BIBLE_VERSES,
    diagnose_trade_outcome,
    get_random_verse,
)
from data import (
    clean_and_validate_dataframe,
    fetch_binance_data,
    fetch_yahoo_data,
    generate_synthetic_data,
    load_csv_data,
)
from indicators import (
    calc_bollinger,
    calc_ema,
)
from news_filter import evaluate_news_filter
from run_bot import start_embedded_bot_if_needed
from strategies import get_all_strategies

# Configuración de página
st.set_page_config(
    page_title="Validador Cuantitativo de Estrategias & Velas",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_resource
def init_cloud_autonomous_worker():
    """
    Garantiza que cuando la app se aloje en la Nube (Streamlit Cloud / Render / Railway)
    con la computadora apagada, el servidor web levante automáticamente el motor de trading 24/7
    y el bot de Telegram en segundo plano.
    """
    return start_embedded_bot_if_needed()


init_cloud_autonomous_worker()

# Estilos CSS con Colores de Cristo (Oro Sagrado, Azul Celestial y Carmesí Real),
# Cruz Cristiana Luminosa de Fondo y Botones de Pestañas Estilo Joya 3D
st.markdown("""
<style>
    @keyframes ticker-scroll {
        0% { transform: translateX(0%); }
        100% { transform: translateX(-50%); }
    }
    @keyframes pulse-green {
        0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
        70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
        100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }
    @keyframes cross-glow {
        0% { opacity: 0.20; transform: translate(-50%, -50%) scale(1.0); }
        50% { opacity: 0.32; transform: translate(-50%, -50%) scale(1.04); }
        100% { opacity: 0.20; transform: translate(-50%, -50%) scale(1.0); }
    }

    /* FONDO DEL SITIO: Colores de Cristo (Azul Celestial Profundo, Destello Carmesí Real y Luz Dorada) + Cruz de Fondo */
    .stApp {
        background:
            radial-gradient(circle at 50% 22%, rgba(212, 175, 55, 0.20) 0%, rgba(153, 27, 27, 0.14) 28%, rgba(10, 20, 45, 0.96) 70%),
            linear-gradient(160deg, #070d1f 0%, #0f1e3d 42%, #1e1633 75%, #091124 100%) !important;
        background-attachment: fixed !important;
    }

    /* CRUZ DE CRISTO RADIANTE EN EL FONDO FIJO DE TODA LA PANTALLA */
    .stApp::before {
        content: "";
        position: fixed;
        top: 52%;
        left: 55%;
        width: 560px;
        height: 560px;
        transform: translate(-50%, -50%);
        background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 240'><defs><radialGradient id='halo' cx='50%' cy='38%' r='50%'><stop offset='0%' stop-color='%23fde047' stop-opacity='0.65'/><stop offset='45%' stop-color='%23f59e0b' stop-opacity='0.22'/><stop offset='100%' stop-color='%23f59e0b' stop-opacity='0'/></radialGradient><linearGradient id='goldCross' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' stop-color='%23fef08a'/><stop offset='50%' stop-color='%23d4af37'/><stop offset='100%' stop-color='%23991b1b'/></linearGradient></defs><circle cx='100' cy='90' r='88' fill='url(%23halo)'/><path d='M90 15 H110 V72 H162 V92 H110 V220 H90 V92 H38 V72 H90 Z' fill='url(%23goldCross)' stroke='%23fef08a' stroke-width='2.5'/></svg>");
        background-repeat: no-repeat;
        background-position: center;
        background-size: contain;
        pointer-events: none;
        z-index: 0;
        animation: cross-glow 7s ease-in-out infinite;
    }

    /* BARRA LATERAL CON ESTILO CELESTIAL Y DORADO */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #081229 0%, #111c38 60%, #1c1429 100%) !important;
        border-right: 1px solid rgba(212, 175, 55, 0.35) !important;
    }

    /* BOTONES DE LA LÍNEA DE PESTAÑAS (VERSÍCULOS, BOT, GRÁFICO, HISTORIAL, ETC.) */
    div[data-baseweb="tab-list"] {
        gap: 10px !important;
        background: rgba(8, 18, 41, 0.78) !important;
        padding: 10px 12px !important;
        border-radius: 16px !important;
        border: 1px solid rgba(212, 175, 55, 0.38) !important;
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.45) !important;
        flex-wrap: wrap !important;
    }

    button[data-baseweb="tab"] {
        background: linear-gradient(135deg, rgba(17, 34, 68, 0.92) 0%, rgba(30, 27, 60, 0.92) 100%) !important;
        border: 1.5px solid rgba(212, 175, 55, 0.42) !important;
        border-radius: 12px !important;
        padding: 10px 18px !important;
        color: #fef3c7 !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
        transition: all 0.28s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35) !important;
        margin: 2px 0 !important;
    }

    button[data-baseweb="tab"]:hover {
        transform: translateY(-3px) scale(1.02) !important;
        border-color: #fde047 !important;
        background: linear-gradient(135deg, rgba(30, 58, 138, 0.95) 0%, rgba(127, 29, 29, 0.88) 100%) !important;
        box-shadow: 0 6px 20px rgba(245, 158, 11, 0.42) !important;
        color: #ffffff !important;
    }

    button[data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, #d97706 0%, #b45309 48%, #881337 100%) !important;
        border: 2px solid #fef08a !important;
        color: #ffffff !important;
        box-shadow: 0 0 22px rgba(251, 191, 36, 0.65), inset 0 1px 4px rgba(255, 255, 255, 0.4) !important;
        transform: translateY(-2px) !important;
    }

    /* Quitar la línea fina por defecto debajo de las tabs */
    div[data-baseweb="tab-highlight"] {
        display: none !important;
    }

    /* BOTONES GENERALES DE LA APLICACIÓN */
    div.stButton > button {
        background: linear-gradient(135deg, #b45309 0%, #881337 100%) !important;
        color: #fef3c7 !important;
        border: 1.5px solid #fbbf24 !important;
        border-radius: 10px !important;
        font-weight: 700 !important;
        transition: all 0.25s ease !important;
        box-shadow: 0 4px 14px rgba(212, 175, 55, 0.25) !important;
    }
    div.stButton > button:hover {
        transform: translateY(-2px) !important;
        border-color: #fef08a !important;
        box-shadow: 0 6px 20px rgba(251, 191, 36, 0.5) !important;
        color: #ffffff !important;
    }

    .ticker-wrap {
        width: 100%;
        overflow: hidden;
        background: linear-gradient(90deg, rgba(10, 20, 45, 0.92) 0%, rgba(30, 41, 75, 0.92) 50%, rgba(10, 20, 45, 0.92) 100%);
        border: 1px solid rgba(212, 175, 55, 0.45);
        border-radius: 12px;
        padding: 9px 0;
        margin-bottom: 14px;
        white-space: nowrap;
        box-shadow: 0 4px 18px rgba(0, 0, 0, 0.45);
    }
    .ticker-move {
        display: inline-block;
        white-space: nowrap;
        animation: ticker-scroll 28s linear infinite;
    }
    .ticker-wrap:hover .ticker-move {
        animation-play-state: paused;
    }
    .ticker-item {
        display: inline-block;
        padding: 0 22px;
        font-size: 0.9rem;
        font-weight: 600;
        color: #f8fafc;
        border-right: 1px solid rgba(212, 175, 55, 0.3);
    }
    .live-dot {
        display: inline-block;
        width: 10px;
        height: 10px;
        background-color: #10b981;
        border-radius: 50%;
        margin-right: 8px;
        animation: pulse-green 1.8s infinite;
    }
    .metric-container {
        background: linear-gradient(145deg, rgba(13, 25, 54, 0.88) 0%, rgba(28, 22, 50, 0.88) 100%);
        backdrop-filter: blur(6px);
        border: 1px solid rgba(212, 175, 55, 0.38);
        border-radius: 12px;
        padding: 14px 18px;
        margin-bottom: 10px;
        transition: all 0.25s ease;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
    }
    .metric-container:hover {
        transform: translateY(-3px);
        border-color: #fde047;
        box-shadow: 0 8px 22px rgba(245, 158, 11, 0.28);
    }
    .verse-banner {
        background: linear-gradient(90deg, rgba(20, 34, 70, 0.92) 0%, rgba(69, 18, 32, 0.88) 55%, rgba(15, 25, 52, 0.92) 100%);
        border-left: 5px solid #fde047;
        border-top: 1px solid rgba(251, 191, 36, 0.45);
        border-right: 1px solid rgba(251, 191, 36, 0.45);
        border-bottom: 1px solid rgba(251, 191, 36, 0.45);
        padding: 15px 20px;
        border-radius: 12px;
        margin-bottom: 14px;
        transition: all 0.3s ease;
        box-shadow: 0 6px 18px rgba(245, 158, 11, 0.18);
    }
    .verse-banner:hover {
        box-shadow: 0 8px 26px rgba(251, 191, 36, 0.32);
    }
    .status-badge-ok {
        background-color: rgba(16, 185, 129, 0.2);
        color: #10b981;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .status-badge-fail {
        background-color: rgba(239, 68, 68, 0.2);
        color: #ef4444;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .status-badge-warn {
        background-color: rgba(245, 158, 11, 0.25);
        color: #fde047;
        padding: 4px 10px;
        border-radius: 6px;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .card-title {
        color: #fde68a;
        font-size: 0.80rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 4px;
    }
    .card-value {
        color: #ffffff;
        font-size: 1.38rem;
        font-weight: 700;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False, ttl=12)
def fetch_live_ticker_strip():
    """Obtiene precios y variación 24h en tiempo real de Binance para la cinta animada superior."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT"]
    items = []
    try:
        resp = requests.get("https://data-api.binance.vision/api/v3/ticker/24hr", timeout=4)
        if resp.status_code == 200:
            data_map = {d["symbol"]: d for d in resp.json() if d.get("symbol") in symbols}
            for s in symbols:
                if s in data_map:
                    price = float(data_map[s]["lastPrice"])
                    chg = float(data_map[s]["priceChangePercent"])
                    color = "#10b981" if chg >= 0 else "#ef4444"
                    arrow = "▲" if chg >= 0 else "▼"
                    p_str = f"${price:,.2f}" if price >= 1 else f"${price:,.4f}"
                    items.append(
                        f"<span class='ticker-item'><b>{s.replace('USDT', '/USDT')}</b>: {p_str} "
                        f"<span style='color:{color};'>{arrow} {chg:+.2f}%</span></span>"
                    )
    except Exception:
        pass
    return "".join(items * 2) if items else ""


@st.cache_data(show_spinner=False, ttl=8)
def fetch_binance_terminal_info(symbol: str = "BTCUSDT"):
    """Obtiene datos estilo Terminal Binance: Estadísticas 24h, tasa ARS y Libro de Órdenes (Order Book)."""
    clean_sym = symbol.replace("-", "").upper()
    if not clean_sym.endswith("USDT"):
        clean_sym = "BTCUSDT"

    info = {
        "symbol": clean_sym,
        "last_price": 0.0,
        "price_change": 0.0,
        "price_change_pct": 0.0,
        "high_24h": 0.0,
        "low_24h": 0.0,
        "vol_base": 0.0,
        "vol_quote": 0.0,
        "usdt_ars": 1450.0,
        "asks": [],
        "bids": []
    }
    try:
        r24 = requests.get(f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={clean_sym}", timeout=3)
        if r24.status_code == 200:
            d = r24.json()
            info["last_price"] = float(d.get("lastPrice", 0.0))
            info["price_change"] = float(d.get("priceChange", 0.0))
            info["price_change_pct"] = float(d.get("priceChangePercent", 0.0))
            info["high_24h"] = float(d.get("highPrice", 0.0))
            info["low_24h"] = float(d.get("lowPrice", 0.0))
            info["vol_base"] = float(d.get("volume", 0.0))
            info["vol_quote"] = float(d.get("quoteVolume", 0.0))
    except Exception:
        pass

    try:
        r_ars = requests.get("https://data-api.binance.vision/api/v3/ticker/price?symbol=USDTARS", timeout=2)
        if r_ars.status_code == 200:
            info["usdt_ars"] = float(r_ars.json().get("price", 1450.0))
    except Exception:
        pass

    try:
        r_depth = requests.get(f"https://data-api.binance.vision/api/v3/depth?symbol={clean_sym}&limit=8", timeout=3)
        if r_depth.status_code == 200:
            depth = r_depth.json()
            info["asks"] = [(float(p), float(q)) for p, q in depth.get("asks", [])[:8]][::-1]
            info["bids"] = [(float(p), float(q)) for p, q in depth.get("bids", [])[:8]]
    except Exception:
        pass

    return info


# ==============================================================================
# BARRA LATERAL (CONFIGURACIÓN)
# ==============================================================================
st.sidebar.title("⚖️ Parámetros de Análisis")

# 1. Origen de Datos
st.sidebar.subheader("1. Origen de Datos")
data_source = st.sidebar.radio(
    "Seleccionar fuente:",
    [
        "🟡 Binance Spot (Crypto en Tiempo Real)",
        "🌐 Yahoo Finance (Acciones, Índices, Forex)",
        "📁 Subir archivo CSV",
        "🎲 Datos Sintéticos (Demo)"
    ],
    index=0
)

source_label = ""
binance_sym = "BTCUSDT"
binance_interval = "1h"
binance_candles = 600

if data_source == "🟡 Binance Spot (Crypto en Tiempo Real)":
    popular_crypto = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT",
        "XRPUSDT", "PEPEUSDT", "SUIUSDT", "NEARUSDT", "AVAXUSDT",
        "LINKUSDT", "ADAUSDT", "Otro (Personalizado)"
    ]
    sel_crypto = st.sidebar.selectbox("Par de Binance:", popular_crypto, index=0)

    if sel_crypto == "Otro (Personalizado)":
        binance_sym = st.sidebar.text_input("Ingresar Par (ej: LTCUSDT, FTMUSDT):", value="BTCUSDT").strip().upper()
    else:
        binance_sym = sel_crypto

    c_b1, c_b2 = st.sidebar.columns(2)
    with c_b1:
        binance_interval = st.selectbox(
            "Temporalidad:",
            ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"],
            index=4
        )
    with c_b2:
        binance_candles = st.slider("Cant. Velas:", min_value=300, max_value=1000, value=600, step=50)

    source_label = f"Binance Spot ({binance_sym} - {binance_interval})"

elif data_source == "🌐 Yahoo Finance (Acciones, Índices, Forex)":
    c1, c2 = st.sidebar.columns(2)
    with c1:
        symbol = st.text_input("Símbolo (ej: NVDA, AAPL, SPY, EURUSD=X):", value="BTC-USD").strip().upper()
    with c2:
        interval = st.selectbox("Intervalo:", ["1d", "1h", "15m"], index=0)

    period_opts = ["1y", "2y", "5y", "max"] if interval == "1d" else ["60d", "1mo", "3mo"]
    period = st.sidebar.selectbox("Período histórico:", period_opts, index=0)
    source_label = f"Yahoo Finance ({symbol} - {interval})"

elif data_source == "📁 Subir archivo CSV":
    uploaded_file = st.sidebar.file_uploader(
        "Subir CSV (columnas date, open, high, low, close):",
        type=["csv"]
    )
    source_label = "Archivo CSV Local"

else:  # Datos Sintéticos
    col_syn1, col_syn2 = st.sidebar.columns(2)
    with col_syn1:
        n_synth = st.number_input("Velas:", min_value=300, max_value=2500, value=750, step=50)
    with col_syn2:
        synth_trend = st.selectbox("Comportamiento:", ["mixed", "bullish", "bearish", "ranging"])
    source_label = f"Sintético ({synth_trend}, {n_synth} velas)"

# 2. Personalización Visual del Gráfico de Velas
st.sidebar.markdown("---")
st.sidebar.subheader("🎨 Personalización del Gráfico")

chart_type = st.sidebar.radio("Tipo de Gráfico:", ["Velas Japonesas (Candlesticks)", "Línea de Cierre"], index=0)

col_col1, col_col2 = st.sidebar.columns(2)
with col_col1:
    bull_color = st.color_picker("Vela Alcista:", value="#00C076")
with col_col2:
    bear_color = st.color_picker("Vela Bajista:", value="#FF6838")

show_volume = st.sidebar.checkbox("Mostrar Volumen Negociado", value=True)
show_overlay_indicators = st.sidebar.checkbox("Superponer Indicadores de la Ganadora", value=True)
show_trade_markers = st.sidebar.checkbox("Mostrar Flechas del Backtest Pasado", value=False)

# 3. Gestión de Riesgo y Cuenta
st.sidebar.markdown("---")
st.sidebar.subheader("3. Cuenta y Gestión de Riesgo")

col_k1, col_k2 = st.sidebar.columns(2)
with col_k1:
    initial_capital = st.number_input("Capital Inicial ($):", min_value=100.0, value=10000.0, step=500.0)
with col_k2:
    risk_pct = st.slider("Riesgo por Trade (%):", min_value=0.25, max_value=5.0, value=1.0, step=0.25) / 100.0

col_s1, col_s2 = st.sidebar.columns(2)
with col_s1:
    stop_atr_mult = st.slider("Stop (x ATR):", min_value=1.0, max_value=4.0, value=2.0, step=0.5)
with col_s2:
    rr_ratio = st.slider("Take Profit (RR):", min_value=1.0, max_value=5.0, value=2.0, step=0.5)

col_c1, col_c2 = st.sidebar.columns(2)
with col_c1:
    commission_pct = st.number_input("Comisión (% por lado):", min_value=0.0, max_value=1.0, value=0.05, step=0.01) / 100.0
with col_c2:
    slippage_pct = st.number_input("Slippage (% por lado):", min_value=0.0, max_value=1.0, value=0.02, step=0.01) / 100.0

col_l1, col_l2 = st.sidebar.columns(2)
with col_l1:
    max_leverage = st.slider("Apalancamiento Máx:", min_value=1.0, max_value=5.0, value=1.0, step=0.5)
with col_l2:
    allow_short = st.checkbox("Permitir Cortos", value=True)

# 4. Validación Fuera de Muestra
st.sidebar.markdown("---")
st.sidebar.subheader("4. Validación Fuera de Muestra")

train_pct = st.sidebar.slider("Porcentaje de Entrenamiento (Train):", min_value=50, max_value=85, value=70, step=5) / 100.0
min_trades = st.sidebar.slider("Mínimo de Operaciones Requeridas:", min_value=5, max_value=30, value=10, step=1)

btn_analyze = st.sidebar.button("🚀 Analizar y Validar Estrategias", type="primary", use_container_width=True)

st.sidebar.markdown("---")
_side_v = get_random_verse()
st.sidebar.markdown(
    f"📖 **{_side_v['reference']}**\n\n*\"{_side_v['verse']}\"*\n\n"
    f"<small style='color:#fbbf24;'>✨ {_side_v['theme']}</small>",
    unsafe_allow_html=True
)


# ==============================================================================
# CARGA Y VALIDACIÓN DE DATOS CON CACHÉ
# ==============================================================================
@st.cache_data(show_spinner=False, ttl=60)
def get_dataset(
    source: str,
    b_sym: str = "BTCUSDT",
    b_intv: str = "1h",
    b_limit: int = 600,
    y_sym: str = "",
    y_intv: str = "",
    y_per: str = "",
    n_s: int = 750,
    tr_s: str = "mixed",
    file_bytes: Optional[bytes] = None
):
    if "Binance" in source:
        return fetch_binance_data(symbol=b_sym, interval=b_intv, limit=b_limit)
    elif "Yahoo" in source:
        return fetch_yahoo_data(y_sym, y_intv, y_per)
    elif "CSV" in source:
        if file_bytes is None:
            return None
        return load_csv_data(io.BytesIO(file_bytes))
    else:
        return generate_synthetic_data(n_candles=n_s, trend_type=tr_s, seed=42)


# Manejo de trigger / persistencia
if btn_analyze or "last_results" not in st.session_state:
    try:
        f_bytes = uploaded_file.getvalue() if "CSV" in data_source and uploaded_file is not None else None

        if "CSV" in data_source and f_bytes is None:
            st.info("👆 Por favor, sube un archivo CSV en la barra lateral para comenzar.")
            st.stop()

        with st.spinner(f"Descargando datos en tiempo real de {source_label}..."):
            df_loaded = get_dataset(
                source=data_source,
                b_sym=binance_sym,
                b_intv=binance_interval,
                b_limit=binance_candles,
                y_sym=symbol if "Yahoo" in data_source else "",
                y_intv=interval if "Yahoo" in data_source else "",
                y_per=period if "Yahoo" in data_source else "",
                n_s=n_synth if "Sintético" in data_source else 750,
                tr_s=synth_trend if "Sintético" in data_source else "mixed",
                file_bytes=f_bytes
            )

        # Barra de progreso para optimización
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def on_progress(p: float, msg: str):
            progress_bar.progress(p)
            status_text.text(msg)

        pipeline_results = run_full_pipeline(
            df=df_loaded,
            train_pct=train_pct,
            initial_capital=initial_capital,
            risk_pct=risk_pct,
            stop_atr_mult=stop_atr_mult,
            rr_ratio=rr_ratio,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
            max_leverage=max_leverage,
            allow_short=allow_short,
            min_trades=min_trades,
            progress_callback=on_progress
        )

        progress_bar.empty()
        status_text.empty()

        active_sym = binance_sym if "Binance" in data_source else (symbol if "Yahoo" in data_source else "BTCUSDT")
        news_eval = evaluate_news_filter(active_sym)

        st.session_state["last_results"] = pipeline_results
        st.session_state["dataset"] = df_loaded
        st.session_state["source_label"] = source_label
        st.session_state["news_eval"] = news_eval

    except Exception as e:
        st.error(f"❌ Error al procesar los datos o el análisis: {e}")
        st.stop()


# ==============================================================================
# RENDERIZADO DEL DASHBOARD
# ==============================================================================
if "last_results" in st.session_state:
    res = st.session_state["last_results"]
    df = st.session_state["dataset"]
    s_label = st.session_state["source_label"]

    evaluations = res['evaluations']
    valid_strats = res['valid_strategies']
    best_strategy = res['best_strategy']
    current_regime = res['current_regime']
    current_adx = res['current_adx']
    bnh_return = res['buy_and_hold_return_pct']
    current_signal = res['current_signal_info']
    train_idx = len(res['df_train'])

    # Encabezado Dinámico con Cinta de Precios en Vivo y Versículo Bíblico Auto-Rotativo
    st.markdown("""
    <div style="display:flex; align-items:center; gap:14px; margin-bottom:6px;">
        <span style="font-size:2.4rem; filter: drop-shadow(0 0 12px rgba(253, 224, 71, 0.75));">✝️</span>
        <div>
            <h1 style="margin:0; padding:0; color:#fef08a; text-shadow: 0 2px 12px rgba(212, 175, 55, 0.45); font-size:2.0rem;">
                Validador Cuantitativo & Terminal Dinámica en Vivo
            </h1>
            <small style="color:#fde68a; letter-spacing:0.04em;">"Encomienda a Jehová tus obras, y tus pensamientos serán afirmados." — Proverbios 16:3</small>
        </div>
    </div>
    """, unsafe_allow_html=True)

    @st.fragment(run_every="15s")
    def render_dynamic_live_header():
        ticker_html = fetch_live_ticker_strip()
        now_str = time.strftime("%H:%M:%S")
        if ticker_html:
            st.markdown(f"""
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px;">
                <div><span class="live-dot"></span><b style="color:#10b981; font-size:0.88rem;">CONECTADO EN VIVO A BINANCE SPOT & BOT 24/7</b></div>
                <div style="color:#94a3b8; font-size:0.82rem;">⏱️ Actualización automática en vivo: <b>{now_str}</b> (Pasa el mouse sobre la cinta para pausar)</div>
            </div>
            <div class="ticker-wrap">
                <div class="ticker-move">{ticker_html}</div>
            </div>
            """, unsafe_allow_html=True)

        if "current_verse" not in st.session_state:
            st.session_state["current_verse"] = get_random_verse()

        col_v1, col_v2, col_v3 = st.columns([4.5, 1, 1])
        with col_v2:
            auto_rot = st.toggle("🔄 Auto-Rotar", value=True, help="Cambia el versículo automáticamente cada 15 segundos")
        with col_v3:
            if st.button("📖 Otro Versículo", use_container_width=True):
                st.session_state["current_verse"] = get_random_verse()

        if auto_rot:
            st.session_state["current_verse"] = get_random_verse()

        with col_v1:
            v = st.session_state["current_verse"]
            st.markdown(f"""
            <div class="verse-banner">
                <span style="color: #fbbf24; font-weight: 700;">📖 Palabra de Sabiduría ({v['reference']}):</span>
                <span style="color: #f8fafc; font-style: italic;"> "{v['verse']}"</span>
                <br><small style="color: #38bdf8;">✨ Enfoque espiritual y operativo: <b>{v['theme']}</b></small>
            </div>
            """, unsafe_allow_html=True)

    render_dynamic_live_header()

    last_price = float(df['close'].iloc[-1])
    first_price = float(df['close'].iloc[0])
    full_change_pct = ((last_price - first_price) / first_price) * 100.0

    st.caption(
        f"**Activo Analizado:** `{s_label}` | **Último Precio:** `${last_price:,.2f}` ({full_change_pct:+.2f}%) | "
        f"**Velas Analizadas:** {len(df)} | **Train:** {train_idx} velas ({int(train_pct*100)}%) | "
        f"**Validación (OOS):** {len(res['df_test'])} velas ({int((1-train_pct)*100)}%)"
    )

    # 1. BLOQUE DE RÉGIMEN Y BENCHMARK
    c_reg1, c_reg2, c_reg3, c_reg4 = st.columns(4)

    with c_reg1:
        reg_color = "#3b82f6" if current_regime == "TENDENCIA" else "#8b5cf6"
        st.markdown(f"""
        <div class="metric-container">
            <div class="card-title">Régimen Actual (ADX)</div>
            <div class="card-value" style="color: {reg_color};">{current_regime}</div>
            <small style="color:#9ca3af;">ADX(14): {current_adx:.1f} (Umbral: 25.0)</small>
        </div>
        """, unsafe_allow_html=True)

    with c_reg2:
        bnh_color = "#10b981" if bnh_return >= 0 else "#ef4444"
        st.markdown(f"""
        <div class="metric-container">
            <div class="card-title">Buy & Hold (Validación)</div>
            <div class="card-value" style="color: {bnh_color};">{bnh_return:+.2f}%</div>
            <small style="color:#9ca3af;">Rendimiento pasivo tramo test</small>
        </div>
        """, unsafe_allow_html=True)

    with c_reg3:
        n_ok = len(valid_strats)
        badge_style = "color:#10b981;" if n_ok > 0 else "color:#ef4444;"
        st.markdown(f"""
        <div class="metric-container">
            <div class="card-title">Estrategias Validadas (OK)</div>
            <div class="card-value" style="{badge_style}">{n_ok} de {len(evaluations)}</div>
            <small style="color:#9ca3af;">Superaron todos los filtros OOS</small>
        </div>
        """, unsafe_allow_html=True)

    with c_reg4:
        winner_name = best_strategy.display_name if best_strategy else "NINGUNA"
        st.markdown(f"""
        <div class="metric-container">
            <div class="card-title">Mejor Estrategia Validada</div>
            <div class="card-value" style="font-size:1.15rem;">{winner_name}</div>
            <small style="color:#9ca3af;">Rankeada por Puntaje OOS</small>
        </div>
        """, unsafe_allow_html=True)

    # Advertencia de régimen si corresponde
    if res.get('regime_warning'):
        st.warning(f"⚠️ **Alerta de Régimen:** {res['regime_warning']}")

    # ==========================================================================
    # 2. DECISIÓN DE VALIDACIÓN
    # ==========================================================================
    st.markdown("---")

    if best_strategy is None:
        st.error("""
        ### ⛔ ALERTA: NINGUNA ESTRATEGIA SUPERÓ LOS CRITERIOS DE VALIDACIÓN FUERA DE MUESTRA
        **Recomendación cuantitativa estricta: NO operar este activo con los modelos evaluados.**
        
        Ninguna de las 6 estrategias demostró solidez estadística en los datos que no vio durante la optimización.
        Forzar una operación en este escenario implica asumir un riesgo con expectativa matemática negativa o sobreajuste (*curve-fitting*).
        """)
    else:
        st.success(f"""
        ### 🏆 Estrategia Ganadora Validada: **{best_strategy.display_name}**
        * **Tipo:** {best_strategy.strategy_type} | **Parámetros Óptimos (Fijados en Train):** `{best_strategy.best_params}`
        * **Estado Fuera de Muestra:** `{best_strategy.status}` ({best_strategy.status_reason})
        """)

        # Métricas de la ganadora en validación (OOS)
        tm = best_strategy.test_metrics
        c_m1, c_m2, c_m3, c_m4, c_m5, c_m6 = st.columns(6)
        with c_m1:
            st.metric("Puntaje OOS", f"{tm.ranking_score:.2f}")
        with c_m2:
            st.metric("Retorno OOS", f"{tm.total_return_pct:+.2f}%", delta=f"{tm.total_return_pct - bnh_return:+.2f}% vs B&H")
        with c_m3:
            st.metric("Esperanza Matemática", f"{tm.expectancy_r:+.2f} R", f"t-stat: {tm.t_stat_r:.2f}")
        with c_m4:
            st.metric("% Acierto (Win Rate)", f"{tm.win_rate_pct:.1f}%", f"{tm.winning_trades}G / {tm.losing_trades}P")
        with c_m5:
            st.metric("Profit Factor", f"{tm.profit_factor:.2f}")
        with c_m6:
            st.metric("Máximo Drawdown", f"{tm.max_drawdown_pct:.1f}%")

        # Señal actual accionable
        if current_signal:
            st.markdown("#### 📍 Señal de Mercado Actual (Última Vela)")
            sig_col1, sig_col2, sig_col3, sig_col4 = st.columns(4)

            with sig_col1:
                dir_str = current_signal['direction_str']
                dir_color = "#10b981" if current_signal['direction'] == 1 else ("#ef4444" if current_signal['direction'] == -1 else "#9ca3af")
                st.markdown(f"""
                <div class="metric-container">
                    <div class="card-title">Dirección Sugerida</div>
                    <div class="card-value" style="color: {dir_color}; font-size:1.1rem;">{dir_str}</div>
                    <small style="color:#9ca3af;">Ref: ${current_signal['reference_price']:,.2f}</small>
                </div>
                """, unsafe_allow_html=True)

            with sig_col2:
                sl_text = f"${current_signal['stop_price']:,.2f}" if current_signal['direction'] != 0 else "N/A"
                st.markdown(f"""
                <div class="metric-container">
                    <div class="card-title">Stop Loss Dinámico</div>
                    <div class="card-value" style="color: #ef4444; font-size:1.1rem;">{sl_text}</div>
                    <small style="color:#9ca3af;">{stop_atr_mult}x ATR (${current_signal['stop_distance']:,.2f})</small>
                </div>
                """, unsafe_allow_html=True)

            with sig_col3:
                tp_text = f"${current_signal['tp_price']:,.2f}" if current_signal['direction'] != 0 else "N/A"
                st.markdown(f"""
                <div class="metric-container">
                    <div class="card-title">Take Profit Objetivo</div>
                    <div class="card-value" style="color: #10b981; font-size:1.1rem;">{tp_text}</div>
                    <small style="color:#9ca3af;">Ratio R:R {rr_ratio}:1</small>
                </div>
                """, unsafe_allow_html=True)

            with sig_col4:
                units_text = f"{current_signal['suggested_units']:.4f}" if current_signal['direction'] != 0 else "0.0"
                pos_val_text = f"${current_signal['suggested_position_value']:,.2f}" if current_signal['direction'] != 0 else "$0.00"
                st.markdown(f"""
                <div class="metric-container">
                    <div class="card-title">Tamaño Sugerido</div>
                    <div class="card-value" style="font-size:1.1rem;">{units_text} un.</div>
                    <small style="color:#9ca3af;">Valor: {pos_val_text}</small>
                </div>
                """, unsafe_allow_html=True)

            # Estado del Filtro Fundamental de Noticias
            news_ev = st.session_state.get("news_eval")
            if news_ev:
                if not news_ev["allow_long"] and current_signal["direction"] == 1:
                    st.error(f"🛑 **Filtro de Noticias BLOQUEA la compra:** {news_ev['reason']}")
                elif not news_ev["allow_short"] and current_signal["direction"] == -1:
                    st.error(f"🛑 **Filtro de Noticias BLOQUEA la venta en corto:** {news_ev['reason']}")
                else:
                    st.info(f"📰 **Filtro Fundamental de Noticias ({news_ev['overall_sentiment']} | Score {news_ev['avg_score']:+.2f}):** {news_ev['reason']}")

    # ==========================================================================
    # VELOCÍMETROS DINÁMICOS Y SIMULADOR INTERACTIVO EN PESOS (ARS) / USDT
    # ==========================================================================
    with st.expander("⚡ Panel Dinámico: Velocímetros de Mercado & Simulador de Ganancias en ARS / USDT", expanded=True):
        g_col1, g_col2, g_col3 = st.columns([1, 1, 1.35])

        with g_col1:
            fig_adx = go.Figure(go.Indicator(
                mode="gauge+number",
                value=float(current_adx),
                title={'text': "Fuerza de Tendencia (ADX)", 'font': {'size': 14, 'color': '#e2e8f0'}},
                number={'font': {'color': '#38bdf8', 'size': 26}},
                gauge={
                    'axis': {'range': [0, 60], 'tickcolor': '#94a3b8'},
                    'bar': {'color': '#38bdf8'},
                    'bgcolor': '#0f172a',
                    'steps': [
                        {'range': [0, 20], 'color': 'rgba(139, 92, 246, 0.25)'},
                        {'range': [20, 25], 'color': 'rgba(245, 158, 11, 0.25)'},
                        {'range': [25, 60], 'color': 'rgba(16, 185, 129, 0.28)'}
                    ],
                    'threshold': {'line': {'color': '#f59e0b', 'width': 3}, 'thickness': 0.8, 'value': 25}
                }
            ))
            fig_adx.update_layout(height=210, margin=dict(l=20, r=20, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)", font={'color': '#f8fafc'})
            st.plotly_chart(fig_adx, use_container_width=True)

        with g_col2:
            news_score_pct = float(st.session_state.get("news_eval", {}).get("avg_score", 0.0)) * 100.0
            fig_sent = go.Figure(go.Indicator(
                mode="gauge+number",
                value=news_score_pct,
                number={'suffix': "%", 'font': {'color': '#10b981' if news_score_pct >= 0 else '#ef4444', 'size': 26}},
                title={'text': "Termómetro de Noticias (-100 a +100)", 'font': {'size': 14, 'color': '#e2e8f0'}},
                gauge={
                    'axis': {'range': [-100, 100], 'tickcolor': '#94a3b8'},
                    'bar': {'color': '#10b981' if news_score_pct >= 0 else '#ef4444'},
                    'bgcolor': '#0f172a',
                    'steps': [
                        {'range': [-100, -30], 'color': 'rgba(239, 68, 68, 0.28)'},
                        {'range': [-30, 25], 'color': 'rgba(148, 163, 184, 0.2)'},
                        {'range': [25, 100], 'color': 'rgba(16, 185, 129, 0.28)'}
                    ],
                    'threshold': {'line': {'color': '#ef4444', 'width': 3}, 'thickness': 0.8, 'value': -30}
                }
            ))
            fig_sent.update_layout(height=210, margin=dict(l=20, r=20, t=40, b=10), paper_bgcolor="rgba(0,0,0,0)", font={'color': '#f8fafc'})
            st.plotly_chart(fig_sent, use_container_width=True)

        with g_col3:
            st.markdown("##### 🧮 Simulador Dinámico en Vivo (En Pesos ARS o USDT)")
            sim_curr = st.radio("Moneda a simular:", ["🇦🇷 Pesos Argentinos (ARS)", "💵 Dólares Crypto (USDT)"], horizontal=True)
            if "ARS" in sim_curr:
                sim_cap = st.slider("Tu Capital Disponible ($ ARS):", min_value=600, max_value=500000, value=15000, step=600)
                curr_sym = "ARS"
            else:
                sim_cap = st.slider("Tu Capital Disponible ($ USDT):", min_value=10, max_value=5000, value=100, step=10)
                curr_sym = "USDT"

            win_r = best_strategy.test_metrics.win_rate_pct / 100.0 if best_strategy else 0.52
            gain_per_win = sim_cap * risk_pct * rr_ratio
            loss_per_stop = sim_cap * risk_pct
            expected_per_trade = (win_r * gain_per_win) - ((1.0 - win_r) * loss_per_stop)
            monthly_proj = expected_per_trade * 2 * 30  # 2 trades al día x 30 días

            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                st.metric("Si toca Take Profit", f"+${gain_per_win:,.1f} {curr_sym}", f"+{risk_pct*rr_ratio*100:.1f}%")
            with sc2:
                st.metric("Si toca Stop Loss", f"-${loss_per_stop:,.1f} {curr_sym}", f"-{risk_pct*100:.1f}%", delta_color="inverse")
            with sc3:
                st.metric("Proyección 30 Días (2/día)", f"${monthly_proj:+,.0f} {curr_sym}", f"Acierto: {win_r*100:.0f}%")

    # ==========================================================================
    # PESTAÑAS PRINCIPALES DE VISUALIZACIÓN
    # ==========================================================================
    st.markdown("---")

    st.markdown("##### ✨ Seleccioná una sección:")
    tab_chart, tab_equity, tab_rank, tab_trades, tab_news, tab_bot, tab_bible = st.tabs([
        "🕯️ Gráfico de Velas",
        "📈 Curva de Equity",
        "🏆 Ranking Estrategias",
        "📋 Historial y Errores",
        "📰 Noticias y Filtro",
        "🤖 Bot Automático 24/7",
        "✝️ Versículos Bíblicos (45)"
    ])

    # --------------------------------------------------------------------------
    # TAB 1: TERMINAL DE VELAS ESTILO BINANCE SPOT (PRECIO GIGANTE, CUADRADITO EN VELA Y LIBRO DE ÓRDENES)
    # --------------------------------------------------------------------------
    with tab_chart:
        active_pair = binance_sym if "Binance" in data_source else "BTCUSDT"
        b_info = fetch_binance_terminal_info(active_pair)

        # Datos de la última vela y penúltima vela del gráfico
        last_o = float(df['open'].iloc[-1])
        last_h = float(df['high'].iloc[-1])
        last_l = float(df['low'].iloc[-1])
        last_c = float(df['close'].iloc[-1])
        last_v = float(df['volume'].iloc[-1])
        prev_c = float(df['close'].iloc[-2]) if len(df) > 1 else last_o
        candle_diff = last_c - prev_c
        candle_diff_pct = (candle_diff / prev_c * 100.0) if prev_c != 0 else 0.0
        is_last_bull = last_c >= last_o
        live_candle_color = "#0ecb81" if is_last_bull else "#f6465d"

        # Estadísticas 24h (de Binance en vivo o calculadas del dataframe)
        disp_price = b_info["last_price"] if b_info["last_price"] > 0 else last_c
        disp_chg = b_info["price_change"] if b_info["last_price"] > 0 else (last_c - first_price)
        disp_chg_pct = b_info["price_change_pct"] if b_info["last_price"] > 0 else full_change_pct
        disp_high = b_info["high_24h"] if b_info["high_24h"] > 0 else float(df['high'].tail(24).max())
        disp_low = b_info["low_24h"] if b_info["low_24h"] > 0 else float(df['low'].tail(24).min())
        disp_vol_base = b_info["vol_base"] if b_info["vol_base"] > 0 else float(df['volume'].tail(24).sum())
        disp_vol_quote = b_info["vol_quote"] if b_info["vol_quote"] > 0 else (disp_vol_base * disp_price)
        ars_price = disp_price * b_info["usdt_ars"]

        price_main_color = "#0ecb81" if disp_chg >= 0 else "#f6465d"
        base_coin = active_pair.replace("USDT", "")

        # 1. BARRA SUPERIOR ESTILO BINANCE (PRECIO GIGANTE EN LA ESQUINA + ARS + DATOS 24H)
        st.markdown(f"""
        <div style="background: rgba(11, 14, 17, 0.94); border: 1px solid rgba(212, 175, 55, 0.45); border-radius: 12px; padding: 14px 22px; margin-bottom: 12px; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 18px; box-shadow: 0 6px 20px rgba(0,0,0,0.5);">
            <div style="display: flex; align-items: center; gap: 22px;">
                <div>
                    <div style="font-size: 1.35rem; font-weight: 800; color: #f8fafc; letter-spacing: 0.02em;">
                        🪙 {base_coin}/USDT <span style="font-size: 0.78rem; background: rgba(245, 158, 11, 0.2); color: #fde047; padding: 2px 8px; border-radius: 4px; margin-left: 6px;">Spot</span>
                    </div>
                    <div style="font-size: 0.78rem; color: #94a3b8;">Precio de {base_coin} en Tiempo Real</div>
                </div>
                <div style="border-left: 1px solid #2b3139; padding-left: 20px;">
                    <div style="font-size: 2.15rem; font-weight: 900; color: {price_main_color}; line-height: 1.05; font-family: monospace;">
                        {disp_price:,.2f}
                    </div>
                    <div style="font-size: 0.85rem; color: #cbd5e1; font-weight: 600; margin-top: 2px;">
                        ARS$ {ars_price:,.2f}
                    </div>
                </div>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 24px; font-size: 0.82rem;">
                <div>
                    <div style="color: #848e9c;">Cambio en 24h</div>
                    <div style="color: {price_main_color}; font-weight: 700; font-size: 0.92rem;">{disp_chg:+,.2f} ({disp_chg_pct:+.2f}%)</div>
                </div>
                <div>
                    <div style="color: #848e9c;">Máx. en 24h</div>
                    <div style="color: #eaecef; font-weight: 700; font-size: 0.92rem;">{disp_high:,.2f}</div>
                </div>
                <div>
                    <div style="color: #848e9c;">Mín. en 24h</div>
                    <div style="color: #eaecef; font-weight: 700; font-size: 0.92rem;">{disp_low:,.2f}</div>
                </div>
                <div>
                    <div style="color: #848e9c;">Vol. 24h ({base_coin})</div>
                    <div style="color: #eaecef; font-weight: 700; font-size: 0.92rem;">{disp_vol_base:,.2f}</div>
                </div>
                <div>
                    <div style="color: #848e9c;">Vol. 24h (USDT)</div>
                    <div style="color: #eaecef; font-weight: 700; font-size: 0.92rem;">{disp_vol_quote:,.2f}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Cargar estado de la operación en vivo del Bot Automático 24/7 para mostrarla en el gráfico
        live_bot_trade = None
        state_file_chart = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_state.json")
        if os.path.exists(state_file_chart):
            try:
                with open(state_file_chart, "r", encoding="utf-8") as f_st:
                    st_data = json.load(f_st)
                    live_bot_trade = st_data.get("active_trade")
            except Exception:
                pass

        # PANEL VISUAL EN VIVO DE CÓMO VA LA OPERACIÓN ABIERTA DEL BOT
        if live_bot_trade is not None:
            bt_entry = float(live_bot_trade["entry_price"])
            bt_stop = float(live_bot_trade["stop_price"])
            bt_tp = float(live_bot_trade["tp_price"])
            bt_units = float(live_bot_trade["units"])
            bt_lev = float(live_bot_trade.get("leverage", 1.0))
            bt_margin = float(live_bot_trade.get("margin_usdt", (bt_units * bt_entry) / max(1.0, bt_lev)))
            bt_stop_dist = float(live_bot_trade.get("stop_distance", max(1.0, abs(bt_entry - bt_stop))))

            live_pnl_usdt = (disp_price - bt_entry) * bt_units
            live_pnl_ars = live_pnl_usdt * b_info["usdt_ars"]
            live_roe_pct = (live_pnl_usdt / bt_margin) * 100.0 if bt_margin > 0 else (((disp_price - bt_entry) / bt_entry) * 100.0 * bt_lev)
            live_r_mult = (disp_price - bt_entry) / bt_stop_dist if bt_stop_dist > 0 else 0.0

            # Porcentaje de recorrido desde el Stop Loss (0%) hasta el Take Profit (100%)
            total_span = max(0.0001, bt_tp - bt_stop)
            progress_pct = min(100.0, max(0.0, ((disp_price - bt_stop) / total_span) * 100.0))
            entry_marker_pct = min(100.0, max(0.0, ((bt_entry - bt_stop) / total_span) * 100.0))

            pnl_color = "#0ecb81" if live_pnl_usdt >= 0 else "#f6465d"
            pnl_sign = "+" if live_pnl_usdt >= 0 else ""
            status_label = "🟢 EN GANANCIA" if live_pnl_usdt >= 0 else "🔴 EN RETROCESO"

            live_trade_html = (
                f"<div style='background:linear-gradient(90deg, rgba(13,25,54,0.95) 0%, rgba(17,24,39,0.95) 100%); border:1.5px solid {pnl_color}; border-radius:12px; padding:14px 20px; margin-bottom:12px; box-shadow:0 4px 18px rgba(0,0,0,0.45);'>"
                f"<div style='display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:12px; margin-bottom:10px;'>"
                f"<div><span class='live-dot'></span><b style='color:#fde047; font-size:1.0rem;'>🤖 OPERACIÓN DEL BOT EN CURSO ({status_label})</b>"
                f"<span style='background:#f59e0b; color:#000000; font-weight:900; font-size:0.80rem; padding:2px 8px; border-radius:6px; margin-left:8px;'>⚡ {bt_lev:.0f}x Apalancado</span>"
                f"<span style='color:#94a3b8; font-size:0.82rem; margin-left:10px;'>Margen: ${bt_margin:,.0f} USDT ➔ Poder: ${(bt_margin * bt_lev):,.0f} USDT ({bt_units:.5f} {base_coin})</span></div>"
                f"<div style='font-family:monospace; font-size:1.15rem; font-weight:900; color:{pnl_color}; background:rgba(0,0,0,0.4); padding:4px 12px; border-radius:8px; border:1px solid {pnl_color};'>"
                f"PnL ({bt_lev:.0f}x): {pnl_sign}${live_pnl_usdt:,.2f} USDT (ROE: {pnl_sign}{live_roe_pct:.2f}%) | ARS$ {pnl_sign}{live_pnl_ars:,.0f}"
                f"</div></div>"
                f"<div style='display:flex; justify-content:space-between; font-size:0.82rem; font-family:monospace; margin-bottom:5px;'>"
                f"<span style='color:#f6465d; font-weight:700;'>🛑 Stop Loss: ${bt_stop:,.2f}</span>"
                f"<span style='color:#fde047; font-weight:700;'>📍 Entrada: ${bt_entry:,.2f}</span>"
                f"<span style='color:{pnl_color}; font-weight:800;'>⚡ Precio Actual: ${disp_price:,.2f}</span>"
                f"<span style='color:#0ecb81; font-weight:700;'>🎯 Take Profit: ${bt_tp:,.2f}</span>"
                f"</div>"
                f"<div style='position:relative; width:100%; height:14px; background:#1e293b; border-radius:8px; overflow:hidden; border:1px solid #334155;'>"
                f"<div style='position:absolute; left:0; top:0; bottom:0; width:{entry_marker_pct:.1f}%; background:rgba(246, 70, 93, 0.35); border-right:2px solid #fde047;'></div>"
                f"<div style='position:absolute; left:{entry_marker_pct:.1f}%; top:0; bottom:0; right:0; background:rgba(14, 203, 129, 0.25);'></div>"
                f"<div style='position:absolute; left:calc({progress_pct:.1f}% - 6px); top:1px; width:12px; height:12px; background:{pnl_color}; border:2px solid #ffffff; border-radius:50%; box-shadow:0 0 8px {pnl_color};'></div>"
                f"</div></div>"
            )
            st.markdown(live_trade_html, unsafe_allow_html=True)

        c_opt1, c_opt2, c_opt3 = st.columns([1.2, 1.2, 2.6])
        with c_opt1:
            show_binance_mas = st.checkbox("📈 Mostrar MA(7), MA(25), MA(99) de Binance", value=True)
        with c_opt2:
            show_orderbook = st.checkbox("📖 Mostrar Libro de Órdenes (Derecha)", value=True)
        with c_opt3:
            st.caption("✏️ **Herramientas de Dibujo:** Usa los íconos arriba a la derecha del gráfico para trazar líneas, rectángulos, círculos o borrar.")

        # Calcular Medias Móviles clásicas de Binance: MA(7), MA(25), MA(99)
        ma7 = df['close'].rolling(7).mean()
        ma25 = df['close'].rolling(25).mean()
        ma99 = df['close'].rolling(99).mean()
        ma7_val = float(ma7.iloc[-1]) if not np.isnan(ma7.iloc[-1]) else last_c
        ma25_val = float(ma25.iloc[-1]) if not np.isnan(ma25.iloc[-1]) else last_c
        ma99_val = float(ma99.iloc[-1]) if not np.isnan(ma99.iloc[-1]) else last_c

        chart_col, ob_col = st.columns([3.3, 1.05]) if show_orderbook else (st.container(), None)

        with chart_col:
            # Configurar figura con o sin subplot de volumen
            if show_volume:
                fig_candles = make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    vertical_spacing=0.02,
                    row_heights=[0.78, 0.22]
                )
            else:
                fig_candles = go.Figure()

            # 1. Velas Japonesas o Línea de Precio
            if "Velas" in chart_type:
                candle_trace = go.Candlestick(
                    x=df.index,
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close'],
                    name="Precio",
                    increasing=dict(line=dict(color=bull_color, width=1.2), fillcolor=bull_color),
                    decreasing=dict(line=dict(color=bear_color, width=1.2), fillcolor=bear_color)
                )
            else:
                candle_trace = go.Scatter(
                    x=df.index,
                    y=df['close'],
                    mode='lines',
                    name="Precio de Cierre",
                    line=dict(color=bull_color, width=2)
                )

            trace_kwargs = dict(row=1, col=1) if show_volume else {}
            fig_candles.add_trace(candle_trace, **trace_kwargs)

            # 2. Medias Móviles de Binance: MA(7) Amarilla, MA(25) Rosa/Magenta, MA(99) Violeta/Cian
            if show_binance_mas:
                fig_candles.add_trace(go.Scatter(
                    x=df.index, y=ma7, mode='lines', name=f"MA(7): {ma7_val:,.2f}",
                    line=dict(color='#f0b90b', width=1.4)
                ), **trace_kwargs)
                fig_candles.add_trace(go.Scatter(
                    x=df.index, y=ma25, mode='lines', name=f"MA(25): {ma25_val:,.2f}",
                    line=dict(color='#eb40b5', width=1.4)
                ), **trace_kwargs)
                fig_candles.add_trace(go.Scatter(
                    x=df.index, y=ma99, mode='lines', name=f"MA(99): {ma99_val:,.2f}",
                    line=dict(color='#8b5cf6', width=1.5)
                ), **trace_kwargs)

            # 3. Línea divisoria de Train / Test
            split_date = df.index[train_idx]
            fig_candles.add_vline(
                x=split_date,
                line_dash="dash",
                line_color="#f59e0b",
                annotation_text="Inicio Validación (Test)",
                annotation_position="bottom left",
                annotation_font_color="#f59e0b",
                **trace_kwargs
            )

            # 4. Superponer indicadores de la mejor estrategia
            if show_overlay_indicators and best_strategy:
                params = best_strategy.best_params
                s_name = best_strategy.strategy_name

                if "bollinger" in s_name:
                    u, m, l = calc_bollinger(df['close'], params['period'], params['num_std'])
                    fig_candles.add_trace(go.Scatter(x=df.index, y=u, mode='lines', name=f"BB Sup ({params['period']})", line=dict(color='#38bdf8', width=1.1, dash='dot')), **trace_kwargs)
                    fig_candles.add_trace(go.Scatter(x=df.index, y=l, mode='lines', name=f"BB Inf ({params['period']})", line=dict(color='#38bdf8', width=1.1, dash='dot')), **trace_kwargs)
                elif "ema" in s_name:
                    fast_ema = calc_ema(df['close'], params['fast_period'])
                    slow_ema = calc_ema(df['close'], params['slow_period'])
                    fig_candles.add_trace(go.Scatter(x=df.index, y=fast_ema, mode='lines', name=f"EMA({params['fast_period']})", line=dict(color='#38bdf8', width=1.5)), **trace_kwargs)
                    fig_candles.add_trace(go.Scatter(x=df.index, y=slow_ema, mode='lines', name=f"EMA({params['slow_period']})", line=dict(color='#f43f5e', width=1.5)), **trace_kwargs)
                elif "donchian" in s_name:
                    p = params['period']
                    donch_up = df['high'].shift(1).rolling(p).max()
                    donch_lo = df['low'].shift(1).rolling(p).min()
                    fig_candles.add_trace(go.Scatter(x=df.index, y=donch_up, mode='lines', name=f"Donchian Sup ({p})", line=dict(color='#22c55e', width=1.2, dash='dash')), **trace_kwargs)
                    fig_candles.add_trace(go.Scatter(x=df.index, y=donch_lo, mode='lines', name=f"Donchian Inf ({p})", line=dict(color='#ef4444', width=1.2, dash='dash')), **trace_kwargs)

            # 5. Marcar operaciones ejecutadas en el tramo Test
            if show_trade_markers and best_strategy:
                test_trades = best_strategy.test_result.trades
                if test_trades:
                    entry_dates_long = [t.entry_date for t in test_trades if t.direction == 1]
                    entry_prices_long = [t.entry_price for t in test_trades if t.direction == 1]
                    entry_dates_short = [t.entry_date for t in test_trades if t.direction == -1]
                    entry_prices_short = [t.entry_price for t in test_trades if t.direction == -1]
                    exit_dates = [t.exit_date for t in test_trades if t.exit_date is not None]
                    exit_prices = [t.exit_price for t in test_trades if t.exit_price is not None]
                    exit_labels = [f"{t.exit_reason} ({t.r_multiple:+.2f}R)" for t in test_trades if t.exit_date is not None]

                    if entry_dates_long:
                        fig_candles.add_trace(go.Scatter(
                            x=entry_dates_long, y=entry_prices_long, mode='markers', name='Entrada LARGO',
                            marker=dict(symbol='triangle-up', size=13, color='#10b981', line=dict(width=1, color='#ffffff'))
                        ), **trace_kwargs)
                    if entry_dates_short:
                        fig_candles.add_trace(go.Scatter(
                            x=entry_dates_short, y=entry_prices_short, mode='markers', name='Entrada CORTO',
                            marker=dict(symbol='triangle-down', size=13, color='#ef4444', line=dict(width=1, color='#ffffff'))
                        ), **trace_kwargs)
                    if exit_dates:
                        fig_candles.add_trace(go.Scatter(
                            x=exit_dates, y=exit_prices, mode='markers', name='Salida Trade', text=exit_labels,
                            marker=dict(symbol='x', size=9, color='#fbbf24')
                        ), **trace_kwargs)

            # 5.B DIBUJAR EN EL GRÁFICO LA OPERACIÓN EN VIVO DEL BOT 24/7 (CAJA DE GANANCIA/PÉRDIDA + NIVELES)
            if live_bot_trade is not None:
                bt_entry = float(live_bot_trade["entry_price"])
                bt_stop = float(live_bot_trade["stop_price"])
                bt_tp = float(live_bot_trade["tp_price"])
                bt_units = float(live_bot_trade["units"])
                bt_pnl = (last_c - bt_entry) * bt_units
                bt_pnl_str = f"{'+' if bt_pnl >= 0 else ''}${bt_pnl:,.2f} USDT"

                # Zona sombreada en las últimas 35 velas estilo herramienta Long Position de TradingView
                x_zone_start = df.index[-min(35, len(df))]
                x_zone_end = df.index[-1]

                # Rectángulo verde de zona de Take Profit
                fig_candles.add_shape(
                    type="rect",
                    x0=x_zone_start, x1=x_zone_end,
                    y0=bt_entry, y1=bt_tp,
                    fillcolor="rgba(14, 203, 129, 0.14)",
                    line=dict(color="rgba(14, 203, 129, 0.55)", width=1, dash="dot"),
                    **trace_kwargs
                )
                # Rectángulo rojo de zona de Stop Loss
                fig_candles.add_shape(
                    type="rect",
                    x0=x_zone_start, x1=x_zone_end,
                    y0=bt_stop, y1=bt_entry,
                    fillcolor="rgba(246, 70, 93, 0.14)",
                    line=dict(color="rgba(246, 70, 93, 0.55)", width=1, dash="dot"),
                    **trace_kwargs
                )

                # Línea de Take Profit del Bot
                fig_candles.add_hline(
                    y=bt_tp, line_dash="dash", line_width=1.6, line_color="#0ecb81",
                    annotation_text=f"🎯 TAKE PROFIT BOT: ${bt_tp:,.2f}",
                    annotation_position="top left",
                    annotation_font=dict(color="#0ecb81", size=11, family="monospace"),
                    annotation_bgcolor="rgba(11, 14, 17, 0.85)",
                    **trace_kwargs
                )
                # Línea de Entrada del Bot
                fig_candles.add_hline(
                    y=bt_entry, line_dash="solid", line_width=1.8, line_color="#fde047",
                    annotation_text=f"🤖 ENTRADA BOT: ${bt_entry:,.2f} (En Vivo: {bt_pnl_str})",
                    annotation_position="top left",
                    annotation_font=dict(color="#fde047", size=11.5, family="monospace"),
                    annotation_bgcolor="rgba(11, 14, 17, 0.88)",
                    **trace_kwargs
                )
                # Línea de Stop Loss del Bot
                fig_candles.add_hline(
                    y=bt_stop, line_dash="dash", line_width=1.6, line_color="#f6465d",
                    annotation_text=f"🛑 STOP LOSS BOT: ${bt_stop:,.2f}",
                    annotation_position="bottom left",
                    annotation_font=dict(color="#f6465d", size=11, family="monospace"),
                    annotation_bgcolor="rgba(11, 14, 17, 0.85)",
                    **trace_kwargs
                )

            # 6. LÍNEA PUNTEADA DEL PRECIO ACTUAL + CUADRADITO EN EL EJE DERECHO + PRECIO GIGANTE EN ESQUINA DEL GRÁFICO
            fig_candles.add_hline(
                y=last_c,
                line_dash="dot",
                line_width=1.5,
                line_color=live_candle_color,
                **trace_kwargs
            )

            # Cuadradito único pegado al eje derecho de precios (igual a la etiqueta de precio de Binance)
            fig_candles.add_annotation(
                x=1.0,
                y=last_c,
                xref="paper",
                yref="y",
                text=f"<b> {last_c:,.2f} </b>",
                showarrow=False,
                xanchor="left",
                yanchor="middle",
                font=dict(color="#ffffff", size=12, family="monospace"),
                bgcolor=live_candle_color,
                bordercolor="#ffffff",
                borderwidth=1,
                borderpad=4
            )

            # Precio Gigante en la Esquina Superior Derecha DENTRO del Gráfico
            fig_candles.add_annotation(
                x=0.985,
                y=0.985,
                xref="paper",
                yref="paper",
                text=(
                    f"<span style='font-size:20px; font-weight:900; color:{live_candle_color};'><b>${last_c:,.2f}</b></span><br>"
                    f"<span style='font-size:11px; color:#cbd5e1;'>ARS$ {ars_price:,.0f} ({candle_diff_pct:+.2f}%)</span>"
                ),
                showarrow=False,
                align="right",
                xanchor="right",
                yanchor="top",
                font=dict(family="monospace", color=live_candle_color),
                bgcolor="rgba(11, 14, 17, 0.85)",
                bordercolor=live_candle_color,
                borderwidth=1.5,
                borderpad=7
            )

            # HUD Superior Izquierdo dentro del Gráfico (O H L C + Variación + MA7 / MA25 / MA99 igual a Binance)
            hud_text = (
                f"<b>{active_pair} · {binance_interval} · Binance</b>   "
                f"<span style='color:{live_candle_color};'><b>O</b> {last_o:,.2f}   <b>H</b> {last_h:,.2f}   "
                f"<b>L</b> {last_l:,.2f}   <b>C</b> {last_c:,.2f}   {candle_diff:+,.2f} ({candle_diff_pct:+.2f}%)</span><br>"
                f"<span style='color:#f0b90b;'><b>MA(7) close:</b> {ma7_val:,.2f}</span>   "
                f"<span style='color:#eb40b5;'><b>MA(25) close:</b> {ma25_val:,.2f}</span>   "
                f"<span style='color:#8b5cf6;'><b>MA(99) close:</b> {ma99_val:,.2f}</span>"
            )
            fig_candles.add_annotation(
                x=0.01,
                y=0.99,
                xref="paper",
                yref="paper",
                text=hud_text,
                showarrow=False,
                align="left",
                xanchor="left",
                yanchor="top",
                font=dict(size=11.5, color="#eaecef", family="monospace"),
                bgcolor="rgba(11, 14, 17, 0.78)",
                bordercolor="rgba(212, 175, 55, 0.35)",
                borderwidth=1,
                borderpad=6
            )

            # 7. Subplot de Volumen + Cuadradito de Volumen en el Eje Derecho
            if show_volume:
                vol_colors = [bull_color if c >= o else bear_color for c, o in zip(df['close'], df['open'])]
                fig_candles.add_trace(
                    go.Bar(
                        x=df.index,
                        y=df['volume'],
                        name='Volumen',
                        marker_color=vol_colors,
                        opacity=0.7
                    ),
                    row=2, col=1
                )
                fig_candles.add_annotation(
                    x=1.0,
                    y=last_v,
                    xref="paper",
                    yref="y2",
                    text=f"<b> {last_v:,.3f} </b>",
                    showarrow=False,
                    xanchor="left",
                    yanchor="middle",
                    font=dict(color="#ffffff", size=11, family="monospace"),
                    bgcolor=live_candle_color,
                    borderpad=3
                )
                fig_candles.add_annotation(
                    x=0.01,
                    y=0.20,
                    xref="paper",
                    yref="paper",
                    text=f"<b>Volumen ({base_coin}):</b> <span style='color:{live_candle_color};'><b>{last_v:,.3f}</b></span>",
                    showarrow=False,
                    xanchor="left",
                    yanchor="top",
                    font=dict(size=11, color="#eaecef", family="monospace"),
                    bgcolor="rgba(11, 14, 17, 0.72)",
                    borderpad=4
                )

            # Eje de precios a la DERECHA con formato completo igual que Binance + Crosshairs
            fig_candles.update_layout(
                template='plotly_dark',
                height=680,
                paper_bgcolor='#0b0e11',
                plot_bgcolor='#0b0e11',
                margin=dict(l=12, r=92, t=28, b=20),
                xaxis_rangeslider_visible=False,
                dragmode='pan',
                hovermode='x unified',
                newshape=dict(line_color='#f0b90b', line_width=2),
                legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1, font=dict(size=10))
            )

            fig_candles.update_yaxes(
                side="right",
                tickformat=",.2f",
                gridcolor="rgba(43, 49, 57, 0.55)",
                showspikes=True,
                spikemode="across",
                spikesnap="cursor",
                spikedash="dot",
                spikecolor="#848e9c",
                spikethickness=1,
                row=1, col=1
            ) if show_volume else fig_candles.update_yaxes(
                side="right",
                tickformat=",.2f",
                gridcolor="rgba(43, 49, 57, 0.55)",
                showspikes=True,
                spikemode="across",
                spikesnap="cursor",
                spikedash="dot",
                spikecolor="#848e9c",
                spikethickness=1
            )

            if show_volume:
                fig_candles.update_yaxes(
                    side="right",
                    gridcolor="rgba(43, 49, 57, 0.55)",
                    row=2, col=1
                )

            fig_candles.update_xaxes(
                gridcolor="rgba(43, 49, 57, 0.55)",
                showspikes=True,
                spikemode="across",
                spikesnap="cursor",
                spikedash="dot",
                spikecolor="#848e9c",
                spikethickness=1
            )

            interactive_config = {
                'scrollZoom': True,
                'displayModeBar': True,
                'modeBarButtonsToAdd': [
                    'drawline',
                    'drawopenpath',
                    'drawclosedpath',
                    'drawcircle',
                    'drawrect',
                    'eraseshape'
                ],
                'displaylogo': False
            }

            st.plotly_chart(fig_candles, use_container_width=True, config=interactive_config)

        # 8. COLUMNA DERECHA: LIBRO DE ÓRDENES EN VIVO (ORDER BOOK DE BINANCE SIN ESPACIOS DE BLOQUE MARKDOWN)
        if show_orderbook and ob_col is not None:
            with ob_col:
                asks = b_info.get("asks", [])
                bids = b_info.get("bids", [])

                asks_html = "".join(
                    f"<div style='display:flex; justify-content:space-between; font-family:monospace; font-size:0.80rem; padding:2px 0;'>"
                    f"<span style='color:#f6465d; font-weight:700;'>{p:,.2f}</span>"
                    f"<span style='color:#eaecef;'>{q:.5f}</span>"
                    f"<span style='color:#848e9c;'>{(p * q):,.1f}</span></div>"
                    for p, q in asks
                )

                bids_html = "".join(
                    f"<div style='display:flex; justify-content:space-between; font-family:monospace; font-size:0.80rem; padding:2px 0;'>"
                    f"<span style='color:#0ecb81; font-weight:700;'>{p:,.2f}</span>"
                    f"<span style='color:#eaecef;'>{q:.5f}</span>"
                    f"<span style='color:#848e9c;'>{(p * q):,.1f}</span></div>"
                    for p, q in bids
                )

                tot_bid_q = sum(q for _, q in bids) if bids else 1.0
                tot_ask_q = sum(q for _, q in asks) if asks else 1.0
                buy_pct = (tot_bid_q / (tot_bid_q + tot_ask_q)) * 100.0
                sell_pct = 100.0 - buy_pct
                arrow_sym = "↑" if disp_chg >= 0 else "↓"

                asks_block = asks_html if asks_html else "<div style='color:#848e9c; font-size:0.8rem;'>Conectando con Binance...</div>"

                ob_full_html = (
                    f"<div style='background:#0b0e11; border:1px solid rgba(212, 175, 55, 0.4); border-radius:12px; padding:14px; height:680px; display:flex; flex-direction:column; justify-content:space-between;'>"
                    f"<div>"
                    f"<div style='font-weight:800; color:#f8fafc; font-size:0.95rem; margin-bottom:8px; border-bottom:1px solid #2b3139; padding-bottom:6px;'>📖 Libro de Órdenes</div>"
                    f"<div style='display:flex; justify-content:space-between; color:#848e9c; font-size:0.74rem; margin-bottom:6px;'>"
                    f"<span>Precio (USDT)</span><span>Monto ({base_coin})</span><span>Total</span></div>"
                    f"{asks_block}"
                    f"</div>"
                    f"<div style='background:#181a20; border-top:1px solid #2b3139; border-bottom:1px solid #2b3139; padding:10px 6px; margin:8px 0; text-align:center; border-radius:6px;'>"
                    f"<div style='font-size:1.38rem; font-weight:900; color:{price_main_color}; font-family:monospace;'>{disp_price:,.2f} {arrow_sym}</div>"
                    f"<div style='font-size:0.76rem; color:#848e9c; margin-top:2px;'>ARS$ {ars_price:,.2f}</div>"
                    f"</div>"
                    f"<div>"
                    f"{bids_html}"
                    f"<div style='margin-top:12px;'>"
                    f"<div style='display:flex; justify-content:space-between; font-size:0.75rem; font-weight:700; margin-bottom:4px;'>"
                    f"<span style='color:#0ecb81;'>C {buy_pct:.1f}%</span>"
                    f"<span style='color:#f6465d;'>{sell_pct:.1f}% V</span>"
                    f"</div>"
                    f"<div style='width:100%; height:7px; background:#f6465d; border-radius:4px; overflow:hidden;'>"
                    f"<div style='width:{buy_pct:.1f}%; height:100%; background:#0ecb81;'></div>"
                    f"</div></div></div></div>"
                )
                st.markdown(ob_full_html, unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # TAB 2: CURVA DE EQUITY VS BUY & HOLD
    # --------------------------------------------------------------------------
    with tab_equity:
        st.subheader("📈 Curva de Equity Fuera de Muestra vs Buy & Hold")

        plot_target = best_strategy if best_strategy else evaluations[0]
        eq_test = plot_target.test_result.equity_curve
        bnh_curve = res['buy_and_hold_curve']

        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(
            x=eq_test.index,
            y=eq_test.values,
            mode='lines',
            name=f"Estrategia: {plot_target.display_name}",
            line=dict(color='#10b981' if plot_target.status == "OK" else '#ef4444', width=2.5)
        ))

        fig_eq.add_trace(go.Scatter(
            x=bnh_curve.index,
            y=bnh_curve.values,
            mode='lines',
            name="Benchmark: Buy & Hold",
            line=dict(color='#6b7280', width=1.5, dash='dash')
        ))

        fig_eq.add_hline(
            y=initial_capital,
            line_dash="dot",
            line_color="#4b5563",
            annotation_text="Capital Inicial",
            annotation_position="bottom right"
        )

        fig_eq.update_layout(
            template="plotly_dark",
            height=450,
            margin=dict(l=20, r=20, t=30, b=20),
            xaxis_title="Fecha (Tramo de Validación / Out-of-Sample)",
            yaxis_title="Capital ($)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_eq, use_container_width=True)

    # --------------------------------------------------------------------------
    # TAB 3: TABLA DE RANKING COMPLETA
    # --------------------------------------------------------------------------
    with tab_rank:
        st.subheader("📊 Ranking Completo de Estrategias")
        st.caption("Comparación de desempeño dentro de muestra (Train) vs fuera de muestra (Test).")

        ranking_rows = []
        for ev in evaluations:
            status_badge = {
                "OK": "🟢 OK",
                "Pocas operaciones": "🟡 Pocas Operaciones",
                "Pierde fuera de muestra": "🔴 Pierde en Test",
                "Posible sobreoptimización": "🟠 Sobreoptimizado"
            }.get(ev.status, ev.status)

            ranking_rows.append({
                "Estrategia": ev.display_name,
                "Tipo": ev.strategy_type,
                "Estado": status_badge,
                "Puntaje OOS": f"{ev.ranking_score:.2f}",
                "Retorno Test (%)": f"{ev.test_metrics.total_return_pct:+.2f}%",
                "Esperanza R (Test)": f"{ev.test_metrics.expectancy_r:+.2f} R",
                "Win Rate Test": f"{ev.test_metrics.win_rate_pct:.1f}%",
                "Max DD Test": f"{ev.test_metrics.max_drawdown_pct:.1f}%",
                "Trades Test": ev.test_metrics.total_trades,
                "Retorno Train (%)": f"{ev.train_metrics.total_return_pct:+.2f}%",
                "Esperanza R (Train)": f"{ev.train_metrics.expectancy_r:+.2f} R",
                "Parámetros Óptimos": str(ev.best_params)
            })

        df_rank = pd.DataFrame(ranking_rows)
        st.dataframe(df_rank, use_container_width=True)

    # --------------------------------------------------------------------------
    # TAB 4: HISTORIAL DEL BOT EN VIVO + BACKTEST DE PRUEBA PASADO
    # --------------------------------------------------------------------------
    with tab_trades:
        st.subheader("📋 Historial de Operaciones: Tu Bot 24/7 vs. Pruebas Históricas")

        # Cargar el estado real/en vivo del Bot Automático 24/7
        t_state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_state.json")
        t_bot_state = {}
        if os.path.exists(t_state_path):
            try:
                with open(t_state_path, "r", encoding="utf-8") as f_ts:
                    t_bot_state = json.load(f_ts)
            except Exception:
                pass

        st.markdown("### 🤖 1. Operaciones Ejecutadas por TU Bot 24/7 (En Tiempo Real)")
        active_bt = t_bot_state.get("active_trade")
        real_bot_hist = t_bot_state.get("trade_history", [])

        if active_bt:
            bt_e = float(active_bt["entry_price"])
            bt_s = float(active_bt["stop_price"])
            bt_t = float(active_bt["tp_price"])
            bt_u = float(active_bt["units"])
            curr_p = float(df['close'].iloc[-1])
            floating_pnl = (curr_p - bt_e) * bt_u
            st.success(
                f"🟢 **OPERACIÓN #1 EN CURSO AHORA MISMO:** Abierta hoy a las `{active_bt.get('entry_time')}` | "
                f"Entrada: `${bt_e:,.2f}` | Precio Actual: `${curr_p:,.2f}` | "
                f"Resultado flotante actual: **`${floating_pnl:+,.2f} USDT`** | "
                f"Stop Loss: `${bt_s:,.2f}` | Take Profit: `${bt_t:,.2f}`"
            )

        if not real_bot_hist:
            st.info(
                "📌 **Todavía no se cerró ninguna operación de tu Bot 24/7.** "
                "La Operación #1 está abierta en este momento esperando tocar el Take Profit o Stop Loss. "
                "Apenas se cierre, aparecerá en esta tabla con su ganancia o la explicación del error."
            )
        else:
            live_rows = []
            for idx, h in enumerate(reversed(real_bot_hist), 1):
                is_w = h.get("pnl_usdt", 0) > 0
                live_rows.append({
                    "#": idx,
                    "Resultado": "🟢 POSITIVA" if is_w else "🔴 NEGATIVA",
                    "Cuánto se Ganó / Perdió": f"${h.get('pnl_usdt', 0):+,.2f} USDT ({h.get('r_multiple', 0):+.2f}R)",
                    "Estrategia": h.get("strategy", "-"),
                    "Entrada": f"${h.get('entry_price', 0):,.2f} ({h.get('entry_time', '-')})",
                    "Salida": f"${h.get('exit_price', 0):,.2f} ({h.get('exit_time', '-')})",
                    "Motivo": h.get("exit_reason", "-"),
                    "Explicación / Diagnóstico": h.get("explanation", "-"),
                    "Cómo Mejorarlo": h.get("improvement", "-"),
                    "Versículo": h.get("verse", "-")
                })
            st.dataframe(pd.DataFrame(live_rows), use_container_width=True)

        st.markdown("---")
        with st.expander("🔬 2. Ver Simulación de Laboratorio con Datos Pasados (Backtest de Días Anteriores)", expanded=False):
            st.caption(
                "ℹ️ **¿Qué son estas operaciones?** No son operaciones que haya hecho tu bot hoy, sino una **simulación matemática "
                "sobre las velas de días/semanas anteriores** que el sistema hace para poner a prueba cada estrategia y ver qué errores "
                "habría tenido en el pasado."
            )
            selected_strat_name = st.selectbox(
                "Ver simulación pasada de la estrategia:",
                options=[ev.strategy_name for ev in evaluations],
                format_func=lambda x: next(ev.display_name for ev in evaluations if ev.strategy_name == x),
                index=0
            )

            selected_eval = next(ev for ev in evaluations if ev.strategy_name == selected_strat_name)
            test_trades = selected_eval.test_result.trades

            if not test_trades:
                st.info("Esta estrategia no tuvo operaciones en el tramo de prueba pasado.")
            else:
                pos_trades = [t for t in test_trades if t.pnl > 0]
                neg_trades = [t for t in test_trades if t.pnl <= 0]
                total_won = sum(t.pnl for t in pos_trades)
                total_lost = sum(t.pnl for t in neg_trades)
                net_pnl = total_won + total_lost

                c_t1, c_t2, c_t3, c_t4 = st.columns(4)
                with c_t1:
                    st.metric("Positivas (En el Backtest)", f"{len(pos_trades)} ops", f"+${total_won:,.2f}")
                with c_t2:
                    st.metric("Negativas (En el Backtest)", f"{len(neg_trades)} ops", f"-${abs(total_lost):,.2f}", delta_color="inverse")
                with c_t3:
                    st.metric("Balance Simulado", f"${net_pnl:+,.2f}", f"Acierto: {(len(pos_trades)/len(test_trades))*100:.1f}%")
                with c_t4:
                    st.metric("Total Simuladas", f"{len(test_trades)} ops")

                trades_rows = []
                for idx, t in enumerate(test_trades, 1):
                    dir_label = "🟢 LARGO" if t.direction == 1 else "🔴 CORTO"
                    reason_badge = {
                        'TAKE_PROFIT': '🎯 Take Profit',
                        'STOP_LOSS': '🛑 Stop Loss',
                        'SIGNAL': '🔄 Cambio de Señal',
                        'END_OF_DATA': '⏳ Fin de Datos'
                    }.get(t.exit_reason, t.exit_reason)

                    diag = diagnose_trade_outcome(
                        pnl=t.pnl,
                        r_multiple=t.r_multiple,
                        exit_reason=t.exit_reason,
                        bars_held=t.bars_held,
                        strategy_type=selected_eval.strategy_type,
                        adx_at_exit=current_adx
                    )
                    res_badge = "🟢 POSITIVA" if t.pnl > 0 else "🔴 NEGATIVA"

                    trades_rows.append({
                        "#": idx,
                        "Resultado": res_badge,
                        "Cuánto se Ganó / Perdió": f"${t.pnl:+,.2f} ({t.r_multiple:+.2f}R)",
                        "Fecha Entrada": str(t.entry_date)[:16],
                        "Precio Entrada": f"${t.entry_price:,.2f}",
                        "Fecha Salida": str(t.exit_date)[:16] if t.exit_date else "-",
                        "Precio Salida": f"${t.exit_price:,.2f}" if t.exit_price else "-",
                        "Lado": dir_label,
                        "Motivo Salida": reason_badge,
                        "Velas": t.bars_held,
                        "Diagnóstico / Causa del Error": diag["explanation"],
                        "Cómo Mejorarlo": diag["improvement"]
                    })

                st.dataframe(pd.DataFrame(trades_rows), use_container_width=True)

    # --------------------------------------------------------------------------
    # TAB 5: NOTICIAS & FILTRO FUNDAMENTAL EN TIEMPO REAL
    # --------------------------------------------------------------------------
    with tab_news:
        st.subheader("📰 Noticias Financieras y Filtro de Protección del Bot")
        news_ev = st.session_state.get("news_eval")
        if not news_ev:
            st.info("No hay evaluación de noticias cargada.")
        else:
            col_n1, col_n2, col_n3 = st.columns(3)
            with col_n1:
                st.metric("Sentimiento Global", news_ev["overall_sentiment"])
            with col_n2:
                st.metric("Score Compuesto (-1 a +1)", f"{news_ev['avg_score']:+.2f}")
            with col_n3:
                status_f = "✅ COMPRAS PERMITIDAS" if news_ev["allow_long"] else "🛑 COMPRAS BLOQUEADAS"
                st.metric("Estado del Filtro en el Bot", status_f)

            st.markdown(f"**Diagnóstico Fundamental:** {news_ev['reason']}")
            st.markdown("---")

            if not news_ev["news"]:
                st.write("No se encontraron titulares recientes para este activo.")
            else:
                for item in news_ev["news"]:
                    badge = {
                        "ALCISTA": "🟢 ALCISTA",
                        "BAJISTA": "🔴 BAJISTA",
                        "NEUTRAL": "⚪ NEUTRAL"
                    }.get(item["sentiment"], "⚪ NEUTRAL")

                    st.markdown(f"""
                    <div class="metric-container">
                        <div style="display:flex; justify-content:space-between; align-items:center;">
                            <span style="font-size:0.8rem; color:#9ca3af;">{item['date']} | Fuente: {item['publisher']}</span>
                            <span><b>{badge} ({item['score']:+.2f})</b></span>
                        </div>
                        <div style="font-size:1.02rem; font-weight:600; margin-top:6px;">
                            <a href="{item['link']}" target="_blank" style="text-decoration:none; color:#38bdf8;">{item['title']}</a>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # TAB 6: BOT AUTOMÁTICO 24/7 (ESTADO, LOGS Y CONFIGURACIÓN)
    # --------------------------------------------------------------------------
    with tab_bot:
        st.subheader("🤖 Panel del Bot Automático 24/7 (Sin Activación Manual)")
        st.markdown("""
        El bot corre de forma autónoma en segundo plano, valida la mejor estrategia, revisa el filtro de noticias
        y **respeta el límite máximo de operaciones por día** (por defecto **2 operaciones diarias**).
        """)

        base_dir = os.path.dirname(os.path.abspath(__file__))
        cfg_path = os.path.join(base_dir, "config_bot.json")
        state_path = os.path.join(base_dir, "live_state.json")
        log_path = os.path.join(base_dir, "bot_activity.log")

        # Cargar estado actual
        bot_state = {}
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    bot_state = json.load(f)
            except Exception:
                pass

        # Cargar configuración actual
        bot_cfg = {
            "mode": "PAPER",
            "symbol": "BTCUSDT",
            "timeframe": "15m",
            "max_trades_per_day": 2,
            "risk_pct": 0.01,
            "stop_atr_mult": 2.0,
            "rr_ratio": 2.0,
            "max_position_usdt": 250.0,
            "leverage": 5.0,
            "binance_api_key": "",
            "binance_api_secret": ""
        }
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    bot_cfg.update(json.load(f))
            except Exception:
                pass

        # Mostrar métricas en vivo del bot
        b_col1, b_col2, b_col3, b_col4, b_col5 = st.columns(5)
        with b_col1:
            st.metric("Modo Activo", bot_cfg.get("mode", "PAPER"))
        with b_col2:
            curr_lev_cfg = float(bot_cfg.get("leverage", 5.0))
            st.metric("⚡ Apalancamiento", f"{curr_lev_cfg:.0f}x", f"Poder: ${float(bot_cfg.get('max_position_usdt', 250.0))*curr_lev_cfg:,.0f} USDT")
        with b_col3:
            trades_today = bot_state.get("trades_today_count", 0)
            max_daily = bot_cfg.get("max_trades_per_day", 2)
            st.metric("Operaciones Hoy", f"{trades_today} / {max_daily}", f"Fecha: {bot_state.get('trades_today_date', 'Hoy')}")
        with b_col4:
            st.metric("Saldo Virtual (Paper)", f"${bot_state.get('paper_balance_usdt', 1000.0):,.2f} USDT")
        with b_col5:
            act_tr = bot_state.get("active_trade")
            st.metric("Posición Abierta", "🟢 SÍ" if act_tr else "⚪ NINGUNA")

        if bot_state.get("active_trade"):
            at = bot_state["active_trade"]
            at_lev = float(at.get("leverage", curr_lev_cfg))
            st.success(
                f"📌 **Trade Activo en Curso ({at_lev:.0f}x Apalancado):** Entrada: `${at['entry_price']:,.2f}` ({at['entry_time']}) | "
                f"Unidades: `{at['units']:.5f}` | Stop Loss: `${at['stop_price']:,.2f}` | Take Profit: `${at['tp_price']:,.2f}`"
            )

        # Historial de Operaciones Ejecutadas por el Bot Automático 24/7
        st.markdown("---")
        st.markdown("#### 📊 Historial de Operaciones Realizadas por el Bot 24/7")
        bot_history = bot_state.get("trade_history", [])
        if not bot_history:
            st.info(
                "Aún no se ha cerrado ninguna operación en el Bot 24/7. Cuando el bot cierre su primera operación, "
                "aparecerá aquí automáticamente indicando si fue POSITIVA (y cuánto se ganó) o NEGATIVA (con la explicación del error y cómo mejorarlo)."
            )
        else:
            b_pos = [h for h in bot_history if h.get("pnl_usdt", 0) > 0]
            b_neg = [h for h in bot_history if h.get("pnl_usdt", 0) <= 0]
            b_won = sum(h.get("pnl_usdt", 0) for h in b_pos)
            b_lost = sum(h.get("pnl_usdt", 0) for h in b_neg)

            ch1, ch2, ch3 = st.columns(3)
            with ch1:
                st.metric("Positivas del Bot", f"{len(b_pos)} ops", f"+${b_won:,.4f} USDT")
            with ch2:
                st.metric("Negativas del Bot", f"{len(b_neg)} ops", f"-${abs(b_lost):,.4f} USDT", delta_color="inverse")
            with ch3:
                st.metric("Resultado Neto Bot", f"${(b_won + b_lost):+,.4f} USDT")

            hist_rows = []
            for idx, h in enumerate(reversed(bot_history), 1):
                is_win = h.get("pnl_usdt", 0) > 0
                hist_rows.append({
                    "#": idx,
                    "Resultado": "🟢 POSITIVA" if is_win else "🔴 NEGATIVA",
                    "Apalancamiento": h.get("leverage", "1x"),
                    "Ganancia / Pérdida": f"${h.get('pnl_usdt', 0):+,.2f} USDT ({h.get('r_multiple', 0):+.2f}R)",
                    "Estrategia": h.get("strategy", "-"),
                    "Entrada": f"${h.get('entry_price', 0):,.2f} ({h.get('entry_time', '-')})",
                    "Salida": f"${h.get('exit_price', 0):,.2f} ({h.get('exit_time', '-')})",
                    "Motivo": h.get("exit_reason", "-"),
                    "Explicación / Diagnóstico": h.get("explanation", "-"),
                    "Cómo Mejorarlo": h.get("improvement", "-"),
                    "Versículo": h.get("verse", "-")
                })
            st.dataframe(pd.DataFrame(hist_rows), use_container_width=True)

        st.markdown("---")
        col_cfg, col_log = st.columns([1, 1.3])

        with col_cfg:
            st.markdown("#### ⚙️ Configurar Parámetros y Apalancamiento del Bot")
            with st.form("bot_config_form"):
                new_mode = st.selectbox("Modo de Operación:", ["PAPER", "REAL"], index=0 if bot_cfg.get("mode") == "PAPER" else 1)
                new_sym = st.text_input("Par de Binance:", value=bot_cfg.get("symbol", "BTCUSDT")).strip().upper()
                new_tf = st.selectbox("Temporalidad:", ["5m", "15m", "30m", "1h", "4h"], index=1)
                new_lev = st.slider("⚡ Apalancamiento del Bot (x):", min_value=1, max_value=20, value=int(bot_cfg.get("leverage", 5)), step=1, help="Multiplica el poder de compra de cada operación (ej: 5x con $250 USDT abre una posición de $1,250 USDT)")
                new_max_daily = st.number_input("Máximo de Operaciones por Día:", min_value=1, max_value=10, value=int(bot_cfg.get("max_trades_per_day", 2)))
                new_max_usdt = st.number_input("Margen Máximo por Orden ($ USDT):", min_value=12.0, max_value=5000.0, value=float(bot_cfg.get("max_position_usdt", 250.0)))
                new_key = st.text_input("Binance API Key (Solo para modo REAL):", value=bot_cfg.get("binance_api_key", ""), type="password")
                new_sec = st.text_input("Binance Secret Key (Solo para modo REAL):", value=bot_cfg.get("binance_api_secret", ""), type="password")
                new_tg_token = st.text_input("📲 Token de Bot de Telegram (Para usar desde la App del Celular sin sitio web):", value=bot_cfg.get("telegram_bot_token", ""), type="password")

                save_cfg = st.form_submit_button("💾 Guardar Configuración y Apalancamiento", use_container_width=True)
                if save_cfg:
                    updated_cfg = {
                        "mode": new_mode,
                        "symbol": new_sym,
                        "timeframe": new_tf,
                        "leverage": float(new_lev),
                        "max_trades_per_day": int(new_max_daily),
                        "risk_pct": float(risk_pct),
                        "stop_atr_mult": float(stop_atr_mult),
                        "rr_ratio": float(rr_ratio),
                        "max_position_usdt": float(new_max_usdt),
                        "binance_api_key": new_key,
                        "binance_api_secret": new_sec,
                        "telegram_bot_token": new_tg_token.strip(),
                        "telegram_chat_id": bot_cfg.get("telegram_chat_id", "")
                    }
                    with open(cfg_path, "w", encoding="utf-8") as f:
                        json.dump(updated_cfg, f, indent=4)

                    # Si hay una operación activa, actualizar su apalancamiento inmediatamente
                    if bot_state.get("active_trade"):
                        at_obj = bot_state["active_trade"]
                        old_l = float(at_obj.get("leverage", 1.0))
                        m_usdt = float(at_obj.get("margin_usdt", (at_obj["units"] * at_obj["entry_price"]) / max(1.0, old_l)))
                        at_obj["margin_usdt"] = m_usdt
                        at_obj["leverage"] = float(new_lev)
                        at_obj["units"] = (m_usdt * float(new_lev)) / float(at_obj["entry_price"])
                        with open(state_path, "w", encoding="utf-8") as f_st2:
                            json.dump(bot_state, f_st2, indent=4)

                    st.success(f"✅ Configuración guardada con Apalancamiento {new_lev}x. Aplicado en vivo al Bot.")

            st.info("""
            📲 **¿Cómo entrar desde el Celular SIN usar un sitio web?**
            1. Abre la app **Telegram** en tu celular y busca a **`@BotFather`**.
            2. Envíale `/newbot`, ponle un nombre y te dará un **Token** (ej: `712345:AAH...`).
            3. Pega ese Token arriba en **Token de Bot de Telegram** y dale a **Guardar**.
            4. En tu celular, entra a tu nuevo bot en Telegram y toca **`📈 /operacion`** o **`📊 /estado`**. ¡Verás en vivo si vas **POSITIVO** o **NEGATIVO** y con cuánto dinero!
            """)

            st.success("""
            ☁️ **¿Cómo hacer que siga operando con la COMPU APAGADA?**
            - Ya integramos el **Motor Autónomo en Nube (`init_cloud_autonomous_worker`)** dentro de esta misma web y el archivo **`.github/workflows/bot_24_7_nube.yml`**.
            - **Opción A (100% Compu Apagada — Nube Gratuita):** Subí tu carpeta o el archivo `.zip` a un repositorio de **GitHub** (privado o público). GitHub Actions y/o **Streamlit Cloud (`share.streamlit.io`)** ejecutan automáticamente el bot y tu Telegram 24/7 en servidores de la nube aunque desenchufes tu PC.
            - **Opción B (Compu con Pantalla Apagada + Auto-Arranque Windows):** Ejecutá **`MODO_SIEMPRE_ACTIVO_WINDOWS.bat`** incluido en tu carpeta para que Windows **jamás suspenda el bot** al apagar el monitor y lo inicie solo si la compu se reinicia.
            """)

        with col_log:
            @st.fragment(run_every="8s")
            def render_live_bot_log():
                st.markdown(f"#### 📜 Registro de Actividad en Vivo (`bot_activity.log`) — ⏱️ *{time.strftime('%H:%M:%S')}*")
                if st.button("🔄 Actualizar Ahora"):
                    pass
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        last_lines = "".join(lines[-35:])
                    st.code(last_lines if last_lines else "Esperando primer ciclo...", language="text")
                else:
                    st.info("Aún no hay registros en `bot_activity.log`.")

            render_live_bot_log()

    # --------------------------------------------------------------------------
    # TAB 7: COLECCIÓN COMPLETA DE 45 VERSÍCULOS BÍBLICOS CRISTIANOS
    # --------------------------------------------------------------------------
    with tab_bible:
        st.subheader(f"📖 Biblioteca de Sabiduría Bíblica Cristiana ({len(BIBLE_VERSES)} Versículos RVR1960)")
        st.markdown(
            "Colección de promesas bíblicas cristianas sobre **sabiduría, dominio propio, paciencia, fe, provisión y paz de Dios** "
            "para acompañar cada jornada de análisis y operación."
        )

        search_q = st.text_input("🔍 Buscar por palabra clave, libro o tema (ej: Proverbios, Salmos, Paz, Sabiduría, Fe):", value="").strip().lower()

        filtered_verses = [
            bv for bv in BIBLE_VERSES
            if not search_q
            or search_q in bv["verse"].lower()
            or search_q in bv["reference"].lower()
            or search_q in bv["theme"].lower()
        ]

        st.caption(f"Mostrando **{len(filtered_verses)}** de **{len(BIBLE_VERSES)}** versículos disponibles.")

        col_bv1, col_bv2 = st.columns(2)
        for i, bv in enumerate(filtered_verses):
            target_col = col_bv1 if i % 2 == 0 else col_bv2
            with target_col:
                st.markdown(f"""
                <div class="metric-container" style="border-left: 4px solid #f59e0b; margin-bottom: 12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                        <span style="color:#fbbf24; font-weight:700; font-size:1.0rem;">📖 {bv['reference']}</span>
                        <span class="status-badge-warn">{bv['theme']}</span>
                    </div>
                    <div style="color:#f9fafb; font-style:italic; font-size:0.98rem; line-height:1.45;">
                        "{bv['verse']}"
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # ==========================================================================
    # EXPLICACIÓN METODOLÓGICA & DISCLAIMER
    # ==========================================================================
    st.markdown("---")
    with st.expander("📚 Metodología de Validación, Puntaje y Reglas Anti-Sesgo"):
        st.markdown(r"""
        ### 📐 Fórmula del Puntaje de Ranking
        $$\text{Puntaje} = t_{\bar{R}} \times (1 - \text{MaxDrawdown})$$
        
        * **$t_{\bar{R}}$ (t-statistic de la esperanza en R):**
          $$t = \frac{\bar{R}}{s_R / \sqrt{N}}$$
          Mide la significancia estadística de la ventaja del modelo. Un valor alto indica que las ganancias no se deben al azar.
        * **$(1 - \text{MaxDrawdown}):$** Penaliza severamente estrategias con caídas de capital profundas.
        * **Filtro de muestra mínima:** Si una estrategia tiene menos de $N$ operaciones configuradas, se le asigna un puntaje de `-999.0`.

        ### 🛡️ Estados de Validación Fuera de Muestra
        1. **🟢 OK:** La estrategia mantiene esperanza positiva y consistencia estadística en datos no vistos.
        2. **🟡 Pocas operaciones:** No completó la cantidad mínima requerida de trades en el tramo de validación.
        3. **🔴 Pierde fuera de muestra:** Esperanza matemática o retorno total negativo en test.
        4. **🟠 Posible sobreoptimización (Curve-Fitting):** El rendimiento fuera de muestra cayó a menos de la mitad del tramo de entrenamiento.
        """)

    st.info("""
    ℹ️ **Aviso Legal:** Los resultados pasados no garantizan resultados futuros. Esta herramienta fue desarrollada con fines de investigación cuantitativa y gestión personal del riesgo. No constituye recomendación ni asesoramiento financiero de inversión.
    """)
