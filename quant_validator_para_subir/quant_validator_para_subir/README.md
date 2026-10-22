# ⚖️ Validador Cuantitativo de Estrategias de Trading

Herramienta personal de trading cuantitativo desarrollada en Python 3.10+ y Streamlit. Analiza automáticamente cualquier activo financiero (acciones, índices, criptomonedas o forex) y determina qué estrategia tiene el mejor desempeño estadísticamente validado fuera de muestra (*Out-of-Sample*).

---

## 🏗️ Arquitectura y Estructura del Proyecto

```text
quant_validator/
├── app.py              # Interfaz gráfica web interactiva en Streamlit con gráficos Plotly
├── analysis.py         # Métricas cuantitativas, t-stat, función de score, régimen de mercado y pipeline
├── backtest.py         # Motor de backtesting realista vela a vela (cero look-ahead)
├── strategies.py       # Las 6 estrategias con sus grillas de parámetros y cálculo de señales
├── indicators.py       # Indicadores técnicos propietarios (EMA, SMA, RSI, ATR, ADX, Bollinger, MACD)
├── data.py             # Ingesta, validación y normalización (Yahoo Finance, CSV y Sintético)
├── test_engine.py      # Suite de pruebas unitarias con asserts rigurosos
├── requirements.txt    # Dependencias del proyecto
└── README.md           # Documentación técnica completa
```

---

## 🎯 Principios y Reglas de Calidad Anti-Sesgo

1. **Cero Look-Ahead Bias:**
   - La señal se calcula estrictamente con el precio de cierre de la vela $i-1$.
   - La orden se ejecuta en la **apertura de la vela $i$** sumando el slippage correspondiente.
2. **Ejecución Intrabar Realista:**
   - Stop Loss dinámico ($N \times \text{ATR}$) y Take Profit ($RR \times \text{Stop}$).
   - **Regla Tie-Breaker:** Si en la misma vela se tocan el Stop Loss y el Take Profit, el motor **asume que se tocó el Stop primero**.
   - **Protección contra Gaps:** Si la apertura supera el nivel de stop (gap desfavorable), la salida se ejecuta en la apertura real.
3. **Bloqueo de Reentrada Inmediata:**
   - Si una operación es cerrada por Stop Loss, el sistema bloquea nuevas entradas en esa misma dirección hasta que la señal cambie de estado.
4. **Validación Fuera de Muestra Rigurosa:**
   - División de la serie en **Entrenamiento (70%)** y **Validación (30%)**.
   - Los parámetros de cada estrategia se optimizan **únicamente en el tramo de entrenamiento**.
   - El ranking se define exclusivamente por el **puntaje fuera de muestra**.
   - Si ninguna estrategia supera los filtros estadísticos, el sistema **no fuerza ninguna recomendación** y advierte explícitamente no operar.

---

## 🧮 Métricas y Función de Puntaje

El ranking fuera de muestra se calcula mediante la fórmula:

$$\text{Puntaje} = t_{\bar{R}} \times (1 - \text{MaxDrawdown})$$

Donde:
* **$t_{\bar{R}}$ (t-statistic de los múltiplos R):**
  $$t = \frac{\bar{R}}{s_R / \sqrt{N}}$$
  Evalúa la significancia estadística de la esperanza matemática $\bar{R}$, penalizando varianzas erráticas y muestras pequeñas.
* **$\text{MaxDrawdown}$:** Caída máxima porcentual de la curva de equity en fracción.
* Si una estrategia ejecuta menos operaciones que el mínimo configurado (`min_trades`), se le asigna un puntaje de `-999.0`.

### Estados de Validación
* **`OK`**: Estrategia consistente con esperanza matemática positiva y muestra suficiente fuera de muestra.
* **`Pocas operaciones`**: No alcanzó el umbral mínimo de trades en validación.
* **`Pierde fuera de muestra`**: Retorno total $\le 0$ o esperanza en R negativa en test.
* **`Posible sobreoptimización`**: La esperanza matemática en test cayó a menos de la mitad del tramo de entrenamiento (*curve-fitting*).

---

## 📊 Estrategias Implementadas

1. **Cruce de EMAs (Tendencia):** Cruce de media exponencial rápida y lenta.
2. **Cruce de EMAs con Filtro ADX (Tendencia):** Exige confirmación de tendencia fuerte ($\text{ADX} > \text{umbral}$).
3. **Ruptura de Donchian (Tendencia):** Ruptura del canal de máximos/mínimos previos (desplazado en 1 vela para evitar look-ahead).
4. **MACD (Tendencia):** Cruces de momentum de la línea MACD y su señal.
5. **Reversión con RSI (Rango):** Compras en sobreventa extrema y salidas al volver a la media (50).
6. **Reversión con Bandas de Bollinger (Rango):** Rebote en bandas exteriores y toma de ganancias en la media móvil central.

---

## 🧪 Pruebas Unitarias del Motor

El archivo `test_engine.py` valida con `asserts` matemáticos:
1. Entrada en la vela siguiente a la señal (sin look-ahead).
2. Stop Loss produce exactamente $-1.0R$ sin costos.
3. Bloqueo de reentrada inmediata tras un Stop Loss.
4. Reducción estricta de ganancias por comisiones y slippage.
5. Pipeline completo de extremo a extremo con datos sintéticos.

Para ejecutar las pruebas:
```bash
python test_engine.py
```

---

## 🚀 Puesta en Marcha de la Interfaz Web

Para iniciar el dashboard interactivo en Streamlit:
```bash
streamlit run app.py
```
Acceder en el navegador a: `http://localhost:8501`.
