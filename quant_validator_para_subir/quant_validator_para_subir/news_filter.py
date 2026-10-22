"""
Módulo de Análisis de Noticias y Filtro Fundamental en Tiempo Real (news_filter.py).
Obtiene titulares recientes desde Yahoo Finance y Google News RSS,
clasifica el sentimiento financiero (Alcista / Bajista / Neutral)
y actúa como filtro de protección antes de ejecutar órdenes en el bot.
"""

import datetime
from typing import Any, Dict, List, Tuple
import xml.etree.ElementTree as ET
import requests
import yfinance as yf

# Diccionario de palabras clave financieras (Inglés y Español)
BULLISH_WORDS = [
    'surge', 'rally', 'jump', 'gain', 'soar', 'record', 'high', 'bull', 'bullish',
    'growth', 'upgrade', 'breakout', 'partnership', 'approval', 'etf', 'inflow',
    'adoption', 'accumulate', 'buy', 'profit', 'beat', 'optimism', 'recovery',
    'alcista', 'sube', 'ganancia', 'maximo', 'máximo', 'crecimiento', 'aprobacion',
    'aprobación', 'record', 'récord', 'adopcion', 'adopción', 'compra', 'impulso',
    'recuperacion', 'recuperación', 'supera'
]

BEARISH_WORDS = [
    'plunge', 'drop', 'fall', 'slump', 'tumble', 'crash', 'loss', 'bear', 'bearish',
    'cut', 'downgrade', 'lawsuit', 'investigation', 'inflation', 'recession',
    'hack', 'hacked', 'exploit', 'ban', 'sec', 'fine', 'bankrupt', 'bankruptcy',
    'outflow', 'selloff', 'sell-off', 'liquidation', 'panic', 'fraud', 'scam',
    'bajista', 'cae', 'caida', 'caída', 'desplome', 'perdida', 'pérdida', 'minimo',
    'mínimo', 'demanda', 'hackeo', 'prohibicion', 'prohibición', 'multa', 'quiebra',
    'liquidacion', 'liquidación', 'panico', 'pánico', 'estafa', 'fraude', 'riesgo'
]

# Palabras de alerta crítica (bloqueo inmediato si aparecen varias)
CRITICAL_BEARISH_WORDS = [
    'hack', 'hacked', 'exploit', 'bankrupt', 'bankruptcy', 'ban', 'fraud',
    'hackeo', 'quiebra', 'prohibición', 'colapso', 'insolvencia'
]


def _normalize_ticker_for_news(symbol: str) -> Tuple[str, str]:
    """
    Convierte un par de Binance (ej. BTCUSDT) a formato Yahoo Finance (BTC-USD)
    y a término de búsqueda para noticias.
    """
    s = symbol.strip().upper().replace("/", "").replace("-", "")
    crypto_map = {
        "BTC": ("BTC-USD", "Bitcoin BTC crypto"),
        "ETH": ("ETH-USD", "Ethereum ETH crypto"),
        "SOL": ("SOL-USD", "Solana SOL crypto"),
        "BNB": ("BNB-USD", "BNB Binance crypto"),
        "DOGE": ("DOGE-USD", "Dogecoin DOGE crypto"),
        "XRP": ("XRP-USD", "Ripple XRP crypto"),
        "PEPE": ("PEPE24478-USD", "Pepe coin crypto"),
        "SUI": ("SUI20947-USD", "Sui crypto"),
        "NEAR": ("NEAR-USD", "Near Protocol crypto"),
        "AVAX": ("AVAX-USD", "Avalanche AVAX crypto"),
        "LINK": ("LINK-USD", "Chainlink LINK crypto"),
        "ADA": ("ADA-USD", "Cardano ADA crypto"),
    }

    for prefix, (yf_sym, query) in crypto_map.items():
        if s == prefix or s == f"{prefix}USDT" or s == f"{prefix}USD" or s == f"{prefix}FDUSD":
            return yf_sym, query

    if s.endswith("USDT"):
        base = s[:-4]
        return f"{base}-USD", f"{base} cryptocurrency"

    return symbol.strip().upper(), f"{symbol.strip().upper()} finance market"


def score_headline_sentiment(title: str) -> Tuple[str, float]:
    """
    Evalúa el sentimiento de un titular financiero.
    Retorna ('ALCISTA' | 'BAJISTA' | 'NEUTRAL', score en [-1.0, +1.0])
    """
    text_lower = title.lower()

    bull_hits = sum(1 for w in BULLISH_WORDS if w in text_lower)
    bear_hits = sum(1 for w in BEARISH_WORDS if w in text_lower)
    crit_hits = sum(1 for w in CRITICAL_BEARISH_WORDS if w in text_lower)

    # Penalización extra si hay palabras críticas (hackeo, quiebra, etc.)
    bear_total = bear_hits + (crit_hits * 2)
    diff = bull_hits - bear_total

    if diff > 0:
        score = min(1.0, 0.35 + 0.20 * diff)
        return "ALCISTA", round(score, 2)
    elif diff < 0:
        score = max(-1.0, -0.35 + 0.20 * diff)
        return "BAJISTA", round(score, 2)
    else:
        return "NEUTRAL", 0.0


def fetch_google_news_rss(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Obtiene titulares recientes en tiempo real desde el feed RSS de Google News.
    """
    results = []
    try:
        url = "https://news.google.com/rss/search"
        params = {
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en"
        }
        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            for item in items[:limit]:
                title_el = item.find("title")
                link_el = item.find("link")
                pub_el = item.find("pubDate")
                source_el = item.find("source")

                title = title_el.text if title_el is not None else "Sin título"
                link = link_el.text if link_el is not None else ""
                pub_date = pub_el.text[:22] if (pub_el is not None and pub_el.text) else "Reciente"
                publisher = source_el.text if source_el is not None else "Google News"

                sentiment, score = score_headline_sentiment(title)
                results.append({
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "date": pub_date,
                    "sentiment": sentiment,
                    "score": score
                })
    except Exception:
        pass
    return results


def fetch_asset_news(symbol: str, limit: int = 8) -> List[Dict[str, Any]]:
    """
    Obtiene las últimas noticias combinando Yahoo Finance y Google News RSS.
    """
    yf_sym, search_query = _normalize_ticker_for_news(symbol)
    news_list = []

    # 1. Intentar con Yahoo Finance
    try:
        ticker = yf.Ticker(yf_sym)
        raw_news = ticker.news
        if raw_news:
            for item in raw_news[:limit]:
                content = item.get('content', {}) if 'content' in item else item
                title = content.get('title', item.get('title', ''))
                if not title:
                    continue
                publisher = content.get('provider', {}).get('displayName', item.get('publisher', 'Yahoo Finance'))
                link = content.get('canonicalUrl', {}).get('url', item.get('link', ''))
                pub_date = content.get('pubDate', item.get('providerPublishTime', None))

                if isinstance(pub_date, (int, float)):
                    date_str = datetime.datetime.fromtimestamp(pub_date).strftime('%Y-%m-%d %H:%M')
                elif isinstance(pub_date, str):
                    date_str = pub_date[:16].replace('T', ' ')
                else:
                    date_str = 'Reciente'

                sentiment, score = score_headline_sentiment(title)
                news_list.append({
                    'title': title,
                    'publisher': publisher,
                    'link': link,
                    'date': date_str,
                    'sentiment': sentiment,
                    'score': score
                })
    except Exception:
        pass

    # 2. Si Yahoo Finance trajo pocas noticias, complementar con Google News RSS
    if len(news_list) < 3:
        rss_news = fetch_google_news_rss(search_query, limit=limit)
        existing_titles = {n['title'].lower() for n in news_list}
        for rn in rss_news:
            if rn['title'].lower() not in existing_titles:
                news_list.append(rn)
                if len(news_list) >= limit:
                    break

    return news_list[:limit]


def evaluate_news_filter(symbol: str, block_threshold: float = -0.25) -> Dict[str, Any]:
    """
    Evalúa el impacto agregado de las noticias recientes para decidir si es seguro operar.
    - Si el puntaje promedio es menor o igual a block_threshold (ej. -0.25),
      bloquea compras para proteger el capital ante eventos fundamentales adversos.
    """
    news_items = fetch_asset_news(symbol, limit=8)

    if not news_items:
        return {
            "news": [],
            "avg_score": 0.0,
            "overall_sentiment": "NEUTRAL (Sin noticias recientes)",
            "allow_long": True,
            "allow_short": True,
            "reason": "No se detectaron noticias adversas; vía libre para la señal técnica."
        }

    scores = [n["score"] for n in news_items]
    avg_score = sum(scores) / len(scores)

    bull_count = sum(1 for n in news_items if n["sentiment"] == "ALCISTA")
    bear_count = sum(1 for n in news_items if n["sentiment"] == "BAJISTA")

    if avg_score <= block_threshold:
        overall = "FUERTEMENTE BAJISTA"
        allow_long = False
        allow_short = True
        reason = (
            f"PROTECCIÓN ACTIVADA: Se detectaron {bear_count} titulares negativos "
            f"(Score: {avg_score:+.2f}). Se bloquean compras para evitar caídas por noticias."
        )
    elif avg_score < -0.08:
        overall = "LIGERAMENTE BAJISTA"
        allow_long = True
        allow_short = True
        reason = f"Sentimiento moderadamente negativo ({avg_score:+.2f}), pero no crítico. Precaución en compras."
    elif avg_score >= 0.25:
        overall = "FUERTEMENTE ALCISTA"
        allow_long = True
        allow_short = False
        reason = (
            f"IMPULSO FUNDAMENTAL: {bull_count} titulares positivos (Score: {avg_score:+.2f}) "
            f"respaldan las entradas en largo y bloquean cortos."
        )
    elif avg_score > 0.08:
        overall = "LIGERAMENTE ALCISTA"
        allow_long = True
        allow_short = True
        reason = f"Sentimiento positivo ({avg_score:+.2f}) acompaña la operativa técnica."
    else:
        overall = "NEUTRAL"
        allow_long = True
        allow_short = True
        reason = f"Noticias en equilibrio (Score: {avg_score:+.2f}). Operativa guiada 100% por matemática."

    return {
        "news": news_items,
        "avg_score": round(avg_score, 2),
        "overall_sentiment": overall,
        "bull_count": bull_count,
        "bear_count": bear_count,
        "allow_long": allow_long,
        "allow_short": allow_short,
        "reason": reason
    }
