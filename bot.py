import os
import sys
import logging
import html
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from google import genai

# ==============================================================================
# SERVIDOR HTTP EN SEGUNDO PLANO (Evita que Render entre en modo Sleep)
# ==============================================================================
class SimpleHealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot activo 24/7 - Generador de comentarios con IA")

    def log_message(self, format, *args):
        return  # Silenciar logs http en consola

def run_http_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHealthCheckHandler)
    server.serve_forever()

# ==============================================================================
# CONFIGURACIÓN DE LOGS Y CREDENCIALES
# ==============================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logger.critical("Faltan variables de entorno: Define TELEGRAM_TOKEN y GEMINI_API_KEY en Render.")
    sys.exit(1)

# Inicializar cliente de Gemini
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# ==============================================================================
# ESTADOS DE LA CONVERSACIÓN
# ==============================================================================
(
    SOLICITAR_SR,
    SOLICITAR_CLIENTE,
    SOLICITAR_MODELO,
    SOLICITAR_SERIE,
    SOLICITAR_PERSONA_VALIDA,
    SELECCIONAR_TIPO,
    SELECCIONAR_SUBTIPO_SUSPENSION,
    SOLICITAR_NUMERO_PARTE,
    SOLICITAR_DETALLE
) = range(9)

def safe_html(text: str) -> str:
    return html.escape(str(text or "N/A"))

# ==============================================================================
# CONTROLADORES DE MENSAJES Y PASOS
# ==============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicio del bot y bienvenida."""
    context.user_data.clear()
    
    mensaje_bienvenida = (
        "🤖 <b>Generador de comentarios con IA BOT</b>\n"
        "👨‍💻 <b>Creado por Víctor Ocaña</b>\n\n"
        "Vamos a generar el comentario técnico para tu atención.\n\n"
        "Por favor, ingresa el número de <b>SR</b> (Service Request / Incidencia):"
    )
    
    await update.message.reply_text(mensaje_bienvenida, parse_mode="HTML")
    return SOLICITAR_SR

async def recibir_sr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['sr'] = update.message.text.strip()
    await update.message.reply_text("Ingresa el nombre del <b>Cliente</b>:", parse_mode="HTML")
    return SOLICITAR_CLIENTE

async def recibir_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cliente'] = update.message.text.strip()
    await update.message.reply_text("Ingresa el <b>Modelo de Equipo</b>:", parse_mode="HTML")
    return SOLICITAR_MODELO

async def recibir_modelo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['modelo'] = update.message.text.strip()
    await update.message.reply_text("Ingresa la <b>Serie</b> del equipo:", parse_mode="HTML")
    return SOLICITAR_SERIE

async def recibir_serie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['serie'] = update.message.text.strip()
    await update.message.reply_text("Ingresa el nombre de la <b>Persona que valida</b> el servicio:", parse_mode="HTML")
    return SOLICITAR_PERSONA_VALIDA

async def recibir_persona_valida(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['persona_valida'] = update.message.text.strip()
    
    keyboard = [
        [
            InlineKeyboardButton("□ Cierre", callback_data="cierre"),
            InlineKeyboardButton("□ Suspensión", callback_data="suspension")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Selecciona el <b>Tipo de Comentario</b>:", reply_markup=reply_markup, parse_mode="HTML")
    return SELECCIONAR_TIPO

async def seleccionar_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tipo = query.data

    if tipo == "cierre":
        context.user_data['tipo'] = "Cierre"
        context.user_data['subtipo'] = "cierre"
        await query.edit_message_text("Has seleccionado: <b>Cierre</b>\n\nIngresa el <b>Detalle del trabajo realizado</b>:", parse_mode="HTML")
        return SOLICITAR_DETALLE
    else:
        keyboard = [
            [InlineKeyboardButton("PN/PPTO", callback_data="susp_ppto")],
            [InlineKeyboardButton("PN (Garantía)", callback_data="susp_garantia")],
            [InlineKeyboardButton("Reprogramación", callback_data="susp_reprog")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Selecciona el motivo de la <b>Suspensión</b>:", reply_markup=reply_markup, parse_mode="HTML")
        return SELECCIONAR_SUBTIPO_SUSPENSION

async def seleccionar_subtipo_suspension(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    subtipo = query.data
    context.user_data['subtipo'] = subtipo

    if subtipo == "susp_ppto":
        context.user_data['tipo'] = "Suspensión (PN/PPTO)"
        await query.edit_message_text("Has seleccionado: <b>PN/PPTO</b>\n\nPor favor, ingresa el <b>Número de Parte (PN)</b>:", parse_mode="HTML")
        return SOLICITAR_NUMERO_PARTE

    elif subtipo == "susp_garantia":
        context.user_data['tipo'] = "Suspensión (PN)"
        await query.edit_message_text("Has seleccionado: <b>PN (Garantía)</b>\n\nPor favor, ingresa el <b>Número de Parte (PN)</b>:", parse_mode="HTML")
        return SOLICITAR_NUMERO_PARTE

    else:  # susp_reprog
        context.user_data['tipo'] = "Suspensión (Reprogramación)"
        await query.edit_message_text("Has seleccionado: <b>Reprogramación</b>\n\nIngresa el <b>Motivo o detalle de la reprogramación solicitada por el cliente</b>:", parse_mode="HTML")
        return SOLICITAR_DETALLE

async def recibir_numero_parte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['numero_parte'] = update.message.text.strip()
    await update.message.reply_text("Ingresa el <b>Detalle del trabajo / diagnóstico realizado</b>:", parse_mode="HTML")
    return SOLICITAR_DETALLE

async def recibir_detalle_y_generar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['detalle'] = update.message.text.strip()
    
    msg_espera = await update.message.reply_text("🔄 <b>Procesando y generando reporte técnico con IA...</b>", parse_mode="HTML")
    
    sr = context.user_data.get('sr', 'N/A')
    cliente = context.user_data.get('cliente', 'N/A')
    modelo = context.user_data.get('modelo', 'N/A')
    serie = context.user_data.get('serie', 'N/A')
    persona_valida = context.user_data.get('persona_valida', 'N/A')
    tipo = context.user_data.get('tipo', 'Cierre')
    subtipo = context.user_data.get('subtipo', 'cierre')
    detalle = context.user_data.get('detalle', '')
    numero_parte = context.user_data.get('numero_parte', '')

    if subtipo == "cierre":
        instrucciones_tipo = (
            "Caso: CIERRE.\n"
            "Redacta de forma natural y técnica: qué falla se encontró, qué tareas se realizaron "
            "y confirma que el equipo quedó 100% operativo en pruebas con visto bueno."
        )
    elif subtipo == "susp_ppto":
        instrucciones_tipo = (
            f"Caso: SUSPENSIÓN (PN/PPTO). PN requerido: {numero_parte}.\n"
            "Redacta el diagnóstico y falla detectada, menciona el PN requerido y especifica que "
            "la atención queda suspendida a la espera de aprobación de presupuesto/cotización por parte del cliente."
        )
    elif subtipo == "susp_garantia":
        instrucciones_tipo = (
            f"Caso: SUSPENSIÓN (PN - Garantía). PN requerido: {numero_parte}.\n"
            "Redacta la falla encontrada, menciona el PN requerido y especifica que la "
            "atención queda suspendida a la espera de recepción del repuesto solicitado por garantía."
        )
    else:  # susp_reprog
        instrucciones_tipo = (
            "Caso: SUSPENSIÓN (Reprogramación por cliente).\n"
            "Redacta que se asistió o coordinó la atención, explica de forma breve y clara el motivo "
            "por el cual el cliente solicita reagendar la visita y deja constancia de que queda pendiente reprogramar fecha."
        )

    prompt = f"""
Actúa como un técnico de soporte de campo con experiencia redactando notas de servicio reales.
Tu objetivo es redactar de forma concisa, técnica y sobre todo NATURAL (humana, sin lenguaje rebuscado ni robótico).

Estructura final obligatoria:
SR: {sr}
Cliente: {cliente}
Modelo de Equipo: {modelo}
Serie: {serie}
Persona que valida: {persona_valida}
Tipo de Comentario: {tipo}

Detalle de trabajo:
[AQUÍ ESCRIBE LA REDACCIÓN NATURAL Y TÉCNICA]

Instrucciones del caso:
{instrucciones_tipo}

Datos ingresados por el técnico:
"{detalle}"

Reglas:
- No agregues introducciones, saludos ni conclusiones fuera del bloque.
- Mantén la redacción en primera o tercera persona profesional típica de campo (ej: "Se revisa equipo...", "Se detecta falla en...", "Se coordina con...").
"""

    try:
        response = ai_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        resultado_ia = response.text.strip()
    except Exception as e:
        resultado_ia = f"Error al consultar la IA: {e}\n\nDetalle original: {detalle}"

    mensaje_final = (
        "✅ <b>Comentario técnico generado:</b>\n\n"
        f"<pre>{safe_html(resultado_ia)}</pre>\n\n"
        "Para generar otro comentario, escribe /start"
    )
    
    await msg_espera.edit_text(mensaje_final, parse_mode="HTML")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Proceso cancelado. Envía /start para comenzar de nuevo.")
    return ConversationHandler.END

if __name__ == '__main__':
    # Iniciar servidor HTTP en segundo plano para Render y UptimeRobot
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SOLICITAR_SR: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_sr)],
            SOLICITAR_CLIENTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_cliente)],
            SOLICITAR_MODELO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_modelo)],
            SOLICITAR_SERIE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_serie)],
            SOLICITAR_PERSONA_VALIDA: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_persona_valida)],
            SELECCIONAR_TIPO: [CallbackQueryHandler(seleccionar_tipo)],
            SELECCIONAR_SUBTIPO_SUSPENSION: [CallbackQueryHandler(seleccionar_subtipo_suspension)],
            SOLICITAR_NUMERO_PARTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_numero_parte)],
            SOLICITAR_DETALLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_detalle_y_generar)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)

    print("🤖 Generador de comentarios con IA BOT (Por Víctor Ocaña) iniciado...")
    app.run_polling(drop_pending_updates=True)
