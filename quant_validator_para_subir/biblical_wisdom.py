"""
Módulo de Sabiduría Bíblica Cristiana y Diagnóstico de Mejora de Operaciones (biblical_wisdom.py).
"Encomienda a Jehová tus obras, y tus pensamientos serán afirmados." — Proverbios 16:3 (RVR1960)

Incluye:
1. Colección de versículos bíblicos cristianos sobre sabiduría, prudencia, paciencia y fe.
2. Analizador forense de operaciones negativas: explica por qué se perdió un trade
   y qué ajuste matemático o estratégico ayuda a mejorarlo.
"""

import random
from typing import Any, Dict, Optional

# Colección ampliada de 45 Versículos Bíblicos Cristianos (Reina-Valera 1960)
BIBLE_VERSES = [
    {
        "verse": "Los pensamientos del diligente ciertamente tienden a la abundancia; mas todo el que se apresura alocadamente, de cierto va a la pobreza.",
        "reference": "Proverbios 21:5",
        "theme": "Paciencia y Prudencia"
    },
    {
        "verse": "Encomienda a Jehová tus obras, y tus pensamientos serán afirmados.",
        "reference": "Proverbios 16:3",
        "theme": "Dirección de Dios"
    },
    {
        "verse": "Fíate de Jehová de todo tu corazón, y no te apoyes en tu propia prudencia. Reconócelo en todos tus caminos, y él enderezará tus veredas.",
        "reference": "Proverbios 3:5-6",
        "theme": "Confianza y Fe"
    },
    {
        "verse": "Y si alguno de vosotros tiene falta de sabiduría, pídala a Dios, el cual da a todos abundantemente y sin reproche, y le será dada.",
        "reference": "Santiago 1:5",
        "theme": "Sabiduría Divina"
    },
    {
        "verse": "Por nada estéis afanosos, sino sean conocidas vuestras peticiones delante de Dios en toda oración y ruego, con acción de gracias. Y la paz de Dios, que sobrepasa todo entendimiento, guardará vuestros corazones y vuestros pensamientos en Cristo Jesús.",
        "reference": "Filipenses 4:6-7",
        "theme": "Paz en medio del mercado"
    },
    {
        "verse": "Porque ¿quién de vosotros, queriendo edificar una torre, no se sienta primero y calcula los gastos, a ver si tiene lo que necesita para acabarla?",
        "reference": "Lucas 14:28",
        "theme": "Planificación y Gestión de Riesgo"
    },
    {
        "verse": "Las riquezas de vanidad disminuirán; pero el que recoge con mano laboriosa las aumenta.",
        "reference": "Proverbios 13:11",
        "theme": "Constancia Paso a Paso"
    },
    {
        "verse": "Reparte a siete, y aun a ocho; porque no sabes el mal que vendrá sobre la tierra.",
        "reference": "Eclesiastés 11:2",
        "theme": "Diversificación y Cuidado"
    },
    {
        "verse": "Encomienda a Jehová tu camino, y confía en él; y él hará.",
        "reference": "Salmos 37:5",
        "theme": "Esperanza y Confianza"
    },
    {
        "verse": "Todo lo puedo en Cristo que me fortalece.",
        "reference": "Filipenses 4:13",
        "theme": "Fortaleza en Cristo"
    },
    {
        "verse": "Mira que te mando que te esfuerces y seas valiente; no temas ni desmayes, porque Jehová tu Dios estará contigo en dondequiera que vayas.",
        "reference": "Josué 1:9",
        "theme": "Valentía y Fe"
    },
    {
        "verse": "Porque Dios no nos ha dado espíritu de cobardía, sino de poder, de amor y de dominio propio.",
        "reference": "2 Timoteo 1:7",
        "theme": "Dominio Propio y Templanza"
    },
    {
        "verse": "El principio de la sabiduría es el temor de Jehová; los insensatos desprecian la sabiduría y la enseñanza.",
        "reference": "Proverbios 1:7",
        "theme": "Principio de Sabiduría"
    },
    {
        "verse": "Porque Jehová da la sabiduría, y de su boca viene el conocimiento y la inteligencia.",
        "reference": "Proverbios 2:6",
        "theme": "Conocimiento e Inteligencia"
    },
    {
        "verse": "Mejor es el que tarda en airarse que el fuerte; y el que se enseñorea de su espíritu, que el que toma una ciudad.",
        "reference": "Proverbios 16:32",
        "theme": "Control Emocional"
    },
    {
        "verse": "El corazón del hombre piensa su camino; mas Jehová endereza sus pasos.",
        "reference": "Proverbios 16:9",
        "theme": "Soberanía de Dios"
    },
    {
        "verse": "Donde no hay dirección sabia, caerá el pueblo; mas en la multitud de consejeros hay seguridad.",
        "reference": "Proverbios 11:14",
        "theme": "Confirmación y Prudencia"
    },
    {
        "verse": "El avisado ve el mal y se esconde; mas los simples pasan y reciben el daño.",
        "reference": "Proverbios 22:3",
        "theme": "Protección y Stop Loss"
    },
    {
        "verse": "Su señor le dijo: Bien, buen siervo y fiel; sobre poco has sido fiel, sobre mucho te pondré; entra en el gozo de tu señor.",
        "reference": "Mateo 25:21",
        "theme": "Mayordomía Fiel"
    },
    {
        "verse": "El que es fiel en lo muy poco, también en lo más es fiel; y el que en lo muy poco es injusto, también en lo más es injusto.",
        "reference": "Lucas 16:10",
        "theme": "Fidelidad en lo Poco"
    },
    {
        "verse": "Mas buscad primeramente el reino de Dios y su justicia, y todas estas cosas os serán añadidas.",
        "reference": "Mateo 6:33",
        "theme": "Prioridad Espiritual"
    },
    {
        "verse": "Así que, no os afanéis por el día de mañana, porque el día de mañana traerá su afán. Basta a cada día su propio mal.",
        "reference": "Mateo 6:34",
        "theme": "Vivir Un Día a la Vez"
    },
    {
        "verse": "La bendición de Jehová es la que enriquece, y no añade tristeza con ella.",
        "reference": "Proverbios 10:22",
        "theme": "Bendición Genuina"
    },
    {
        "verse": "Mejor es lo poco con el temor de Jehová, que el gran tesoro donde hay turbación.",
        "reference": "Proverbios 15:16",
        "theme": "Paz Interior"
    },
    {
        "verse": "Y sabemos que a los que aman a Dios, todas las cosas les ayudan a bien, esto es, a los que conforme a su propósito son llamados.",
        "reference": "Romanos 8:28",
        "theme": "Propósito y Aprendizaje"
    },
    {
        "verse": "Porque yo sé los pensamientos que tengo acerca de vosotros, dice Jehová, pensamientos de paz, y no de mal, para daros el fin que esperáis.",
        "reference": "Jeremías 29:11",
        "theme": "Futuro y Esperanza"
    },
    {
        "verse": "Jehová es mi pastor; nada me faltará. En lugares de delicados pastos me hará descansar; junto a aguas de reposo me pastoreará.",
        "reference": "Salmos 23:1-2",
        "theme": "Provisión y Descanso"
    },
    {
        "verse": "Dios es nuestro amparo y fortaleza, nuestro pronto auxilio en las tribulaciones.",
        "reference": "Salmos 46:1",
        "theme": "Refugio Seguro"
    },
    {
        "verse": "Estad quietos, y conoced que yo soy Dios.",
        "reference": "Salmos 46:10",
        "theme": "Quietud y Paciencia"
    },
    {
        "verse": "Lámpara es a mis pies tu palabra, y lumbrera a mi camino.",
        "reference": "Salmos 119:105",
        "theme": "Luz y Guía"
    },
    {
        "verse": "Pero los que esperan a Jehová tendrán nuevas fuerzas; levantarán alas como las águilas; correrán, y no se cansarán; caminarán, y no se fatigarán.",
        "reference": "Isaías 40:31",
        "theme": "Perseverancia y Paciencia"
    },
    {
        "verse": "No temas, porque yo estoy contigo; no desmayes, porque yo soy tu Dios que te esfuerzo; siempre te ayudaré, siempre te sustentaré con la diestra de mi justicia.",
        "reference": "Isaías 41:10",
        "theme": "Sostén de Dios"
    },
    {
        "verse": "Tú guardarás en completa paz a aquel cuyo pensamiento en ti persevera; porque en ti ha confiado.",
        "reference": "Isaías 26:3",
        "theme": "Paz Completa"
    },
    {
        "verse": "La paz os dejo, mi paz os doy; yo no os la doy como el mundo la da. No se turbe vuestro corazón, ni tenga miedo.",
        "reference": "Juan 14:27",
        "theme": "La Paz de Cristo"
    },
    {
        "verse": "Echando toda vuestra ansiedad sobre él, porque él tiene cuidado de vosotros.",
        "reference": "1 Pedro 5:7",
        "theme": "Cuidado de Dios"
    },
    {
        "verse": "No nos cansemos, pues, de hacer bien; porque a su tiempo segaremos, si no desmayamos.",
        "reference": "Gálatas 6:9",
        "theme": "Siembra y Cosecha"
    },
    {
        "verse": "Y todo lo que hagáis, hacedlo de corazón, como para el Señor y no para los hombres.",
        "reference": "Colosenses 3:23",
        "theme": "Excelencia y Dedicación"
    },
    {
        "verse": "Por la misericordia de Jehová no hemos sido consumidos, porque nunca decayeron sus misericordias. Nuevas son cada mañana; grande es tu fidelidad.",
        "reference": "Lamentaciones 3:22-23",
        "theme": "Fidelidad Cada Mañana"
    },
    {
        "verse": "Es, pues, la fe la certeza de lo que se espera, la convicción de lo que no se ve.",
        "reference": "Hebreos 11:1",
        "theme": "Fe Viva"
    },
    {
        "verse": "Mi Dios, pues, suplirá todo lo que os falta conforme a sus riquezas en gloria en Cristo Jesús.",
        "reference": "Filipenses 4:19",
        "theme": "Provisión Divina"
    },
    {
        "verse": "Todo tiene su tiempo, y todo lo que se quiere debajo del cielo tiene su hora.",
        "reference": "Eclesiastés 3:1",
        "theme": "Tiempo Oportuno"
    },
    {
        "verse": "El hombre de doble ánimo es inconstante en todos sus caminos.",
        "reference": "Santiago 1:8",
        "theme": "Firmeza y Disciplina"
    },
    {
        "verse": "Antes bien, creced en la gracia y el conocimiento de nuestro Señor y Salvador Jesucristo. A él sea gloria ahora y hasta el día de la eternidad. Amén.",
        "reference": "2 Pedro 3:18",
        "theme": "Crecimiento Espiritual"
    },
    {
        "verse": "Jehová te bendiga, y te guarde; Jehová haga resplandecer su rostro sobre ti, y tenga de ti misericordia; Jehová alce sobre ti su rostro, y ponga en ti paz.",
        "reference": "Números 6:24-26",
        "theme": "Bendición Sacerdotal"
    },
    {
        "verse": "Sobre toda cosa guardada, guarda tu corazón; porque de él mana la vida.",
        "reference": "Proverbios 4:23",
        "theme": "Guardar el Corazón"
    }
]


def get_random_verse() -> Dict[str, str]:
    """Devuelve un versículo bíblico cristiano aleatorio."""
    return random.choice(BIBLE_VERSES)


def format_verse_banner(verse_dict: Optional[Dict[str, str]] = None) -> str:
    """Formatea un versículo para mostrar en consola o interfaz."""
    v = verse_dict or get_random_verse()
    return f'📖 "{v["verse"]}" — {v["reference"]} ({v["theme"]})'


def diagnose_trade_outcome(
    pnl: float,
    r_multiple: float,
    exit_reason: str,
    bars_held: int,
    strategy_type: str = "TENDENCIA",
    adx_at_exit: Optional[float] = None
) -> Dict[str, str]:
    """
    Evalúa una operación cerrada:
    - Si es POSITIVA: resume el acierto y la ganancia.
    - Si es NEGATIVA: genera una explicación clara de cuál fue el error o causa de mercado
      y cómo mejorarlo en la configuración.
    """
    if pnl > 0:
        if exit_reason == "TAKE_PROFIT":
            explanation = (
                "Operación exitosa: El precio respetó la dirección proyectada y alcanzó el objetivo "
                f"de Take Profit (+{r_multiple:.2f}R) en {bars_held} velas."
            )
            improvement = "Mantener la disciplina y el ratio Riesgo/Beneficio actual."
        else:
            explanation = (
                f"Operación positiva cerrada por cambio de señal con ganancia parcial (+{r_multiple:.2f}R) "
                f"tras {bars_held} velas."
            )
            improvement = "Buena protección de ganancias antes de que el movimiento se agotara."
        return {
            "status": "POSITIVA (GANANCIA)",
            "explanation": explanation,
            "improvement": improvement
        }

    # Diagnóstico detallado cuando la operación es NEGATIVA (Pérdida)
    if exit_reason == "STOP_LOSS":
        if bars_held <= 2:
            explanation = (
                "Falsa ruptura o barrido rápido de liquidez (Stop Loss tocado en solo "
                f"{bars_held} vela(s)). La volatilidad inmediata sacó la posición antes de que desarrollara."
            )
            improvement = (
                "Mejora sugerida: Aumentar ligeramente el Stop de 2.0x ATR a 2.5x ATR o operar en una "
                "temporalidad superior (ej. pasar de 15m a 1h) para filtrar el ruido de corto plazo."
            )
        elif strategy_type == "TENDENCIA" and adx_at_exit is not None and adx_at_exit < 22:
            explanation = (
                f"Pérdida por mercado lateral (ADX bajo en {adx_at_exit:.1f}). Se intentó seguir una tendencia "
                "cuando el mercado entró en rango sin fuerza direccional."
            )
            improvement = (
                "Mejora sugerida: Utilizar estrategias con filtro ADX > 25 o de Reversión (Bollinger/RSI) "
                "cuando el mercado no tiene tendencia clara."
            )
        else:
            explanation = (
                f"El movimiento perdió fuerza tras {bars_held} velas y se dio vuelta hasta tocar el "
                f"Stop Loss ({r_multiple:.2f}R). Parte normal de la probabilidad estadística."
            )
            improvement = (
                "Mejora sugerida: El Stop Loss cumplió su función de limitar el daño a ~1R. "
                "Si se repite, reducir el Ratio Take Profit de 2.0 a 1.5 para asegurar ganancias antes."
            )
    elif exit_reason in ["SIGNAL", "CAMBIO_SENAL"]:
        explanation = (
            f"Agotamiento de impulso: La señal se invirtió tras {bars_held} velas antes de llegar al "
            f"Take Profit, cerrando con pérdida controlada ({r_multiple:.2f}R)."
        )
        improvement = (
            "Mejora sugerida: Salir por cambio de señal evitó que la pérdida llegara al Stop Loss completo (-1R). "
            "Verificar que no se esté entrando tarde al movimiento."
        )
    else:
        explanation = (
            f"Operación cerrada en negativo ({r_multiple:.2f}R) al finalizar el ciclo ({exit_reason})."
        )
        improvement = "Revisar las condiciones de volatilidad del horario operado."

    return {
        "status": "NEGATIVA (PÉRDIDA)",
        "explanation": explanation,
        "improvement": improvement
    }
