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
        # Silenciar logs http para mantener limpios los registros de Telegram
        return

def run_http_server():
    # Render asigna dinamicamente la variable PORT (usualmente 10000 o 8080)
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHealthCheckHandler)
    server.serve_forever()

# ==============================================================================
# CONFIGURACIÓN DE LOGS Y CREDENCIALES
# ==============================================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Lectura segura desde las variables de entorno de Render
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    logger.critical("Error critico: Faltan las variables de entorno TELEGRAM_TOKEN o GEMINI_API_KEY en Render.")
    sys.exit(1)

# Inicializar cliente Gemini con SDK oficial
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# ==============================================================================
# ESTADOS DEL FLUJO CONVERSACIONAL
# ==============================================================================
(
    SOLICITAR_SR,
    SOLICITAR_CLIENTE,
    SOLICITAR_MODELO,
    SOLICITAR_SERIE,
    SOLICITAR_PERSONA_VALIDA,
    SELECCIONAR_TIPO,
    SOLICITAR_NUMERO_PARTE,
    SOLICITAR_DETALLE
) = range(8)

def safe_html(text: str) -> str:
    """Escapa caracteres especiales para evitar errores de parseo en Telegram HTML."""
    return html.escape(str(text or "N/A"))

# ==============================================================================
# CONTROLADORES DE MENSAJES Y PASOS
# ==============================================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    mensaje = (
        "🤖 <b>Generador de comentarios con IA BOT</b>\n"
        "👨‍💻 <b>Creado por Víctor Ocaña</b>\n\n"
        "Vamos a generar el comentario técnico para tu atención.\n\n"
        "Por favor, ingresa el número de <b>SR</b> (Service Request / Incidencia):"
    )
    await update.message.reply_text(mensaje, parse_mode="HTML")
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
    context.user_data['tipo'] = tipo
    
    if tipo == "cierre":
        await query.edit_message_text(
            "Has seleccionado: <b>Cierre</b>\n\nPor favor, ingresa el <b>Detalle del trabajo realizado</b>:", 
            parse_mode="HTML"
        )
        return SOLICITAR_DETALLE
    else:
        await query.edit_message_text(
            "Has seleccionado: <b>Suspensión</b>\n\nPor favor, ingresa el <b>Número de Parte</b>:", 
            parse_mode="HTML"
        )
        return SOLICITAR_NUMERO_PARTE

async def recibir_numero_parte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['numero_parte'] = update.message.text.strip()
    await update.message.reply_text("Ingresa el <b>Detalle del trabajo / motivo de la suspensión</b>:", parse_mode="HTML")
    return SOLICITAR_DETALLE

async def recibir_detalle_y_generar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['detalle'] = update.message.text.strip()
    
    msg_espera = await update.message.reply_text("🔄 <b>Procesando y redactando informe técnico con IA...</b>", parse_mode="HTML")
    
    sr = context.user_data.get('sr', 'N/A')
    cliente = context.user_data.get('cliente', 'N/A')
    modelo = context.user_data.get('modelo', 'N/A')
    serie = context.user_data.get('serie', 'N/A')
    persona_valida = context.user_data.get('persona_valida', 'N/A')
    tipo = context.user_data.get('tipo', 'cierre')
    detalle = context.user_data.get('detalle', '')
    numero_parte = context.user_data.get('numero_parte', '')

    if tipo == "cierre":
        instrucciones_tipo = (
            "Es un CIERRE de atención. Reescribe y mejora el detalle del trabajo en un tono "
            "técnico, formal y profesional para un informe de servicio técnico de campo."
        )
    else:
        instrucciones_tipo = (
            f"Es una SUSPENSIÓN de atención. El número de parte requerido es: {numero_parte}. "
            "Reescribe el detalle indicando la causa técnica y explicita claramente que la "
            "atención queda suspendida a la espera del repuesto."
        )

    prompt = f"""
Actúa como un Ingeniero de Soporte Técnico Senior especializado en redacción de informes operativos.

Debes generar un comentario técnico final con la siguiente estructura exacta:

SR: {sr}
Cliente: {cliente}
Modelo de Equipo: {modelo}
Serie: {serie}
Persona que valida: {persona_valida}
Tipo de Comentario: {'Cierre' if tipo == 'cierre' else 'Suspensión'}

Detalle de trabajo:
[AQUÍ COLOCAS LA REDACCIÓN MEJORADA]

Instrucciones para mejorar el detalle:
{instrucciones_tipo}

Notas ingresadas por el técnico:
"{detalle}"

Devuelve ÚNICAMENTE el texto estructurado listo para pegar en el sistema de tickets. No agregues saludos ni notas adicionales.
"""

    try:
        response = ai_client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        resultado_ia = response.text.strip()
    except Exception as e:
        resultado_ia = f"Error al procesar con IA: {e}\n\nDetalle original: {detalle}"

    mensaje_final = (
        "✅ <b>Comentario técnico generado exitosamente:</b>\n\n"
        f"<pre>{safe_html(resultado_ia)}</pre>\n\n"
        "Para realizar una nueva consulta, usa /start"
    )
    
    await msg_espera.edit_text(mensaje_final, parse_mode="HTML")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Proceso cancelado. Envía /start para comenzar de nuevo.")
    return ConversationHandler.END

# ==============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ==============================================================================
if __name__ == '__main__':
    # 1. Iniciar el servidor HTTP en un hilo independiente para responder a los pings de Render / UptimeRobot
    server_thread = threading.Thread(target=run_http_server, daemon=True)
    server_thread.start()

    # 2. Iniciar la aplicación de Telegram
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
            SOLICITAR_NUMERO_PARTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_numero_parte)],
            SOLICITAR_DETALLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_detalle_y_generar)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(conv_handler)
    print("🤖 Generador de comentarios con IA BOT iniciado...")
    app.run_polling(drop_pending_updates=True)
