import os
import logging
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

# Configuración de Logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ==========================================
# CREDENCIALES (Lectura desde Variables de Entorno en Render)
# ==========================================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("Faltan variables de entorno: Asegúrate de definir TELEGRAM_TOKEN y GEMINI_API_KEY en Render.")

# Inicializar cliente de Gemini
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Estados de la conversación
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicio del bot y bienvenida."""
    context.user_data.clear()
    
    mensaje_bienvenida = (
        "🤖 *Generador de comentarios con IA BOT*\n"
        "👨‍💻 *Creado por Víctor Ocaña*\n\n"
        "Vamos a generar el comentario técnico para tu atención.\n\n"
        "Por favor, ingresa el número de *SR* (Service Request / Incidencia):"
    )
    
    await update.message.reply_text(mensaje_bienvenida, parse_mode="Markdown")
    return SOLICITAR_SR


async def recibir_sr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['sr'] = update.message.text.strip()
    await update.message.reply_text("Ingresa el nombre del *Cliente*:", parse_mode="Markdown")
    return SOLICITAR_CLIENTE


async def recibir_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cliente'] = update.message.text.strip()
    await update.message.reply_text("Ingresa el *Modelo de Equipo*:", parse_mode="Markdown")
    return SOLICITAR_MODELO


async def recibir_modelo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['modelo'] = update.message.text.strip()
    await update.message.reply_text("Ingresa la *Serie* del equipo:", parse_mode="Markdown")
    return SOLICITAR_SERIE


async def recibir_serie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['serie'] = update.message.text.strip()
    await update.message.reply_text("Ingresa el nombre de la *Persona que valida* el servicio:", parse_mode="Markdown")
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
    
    await update.message.reply_text("Selecciona el *Tipo de Comentario*:", reply_markup=reply_markup, parse_mode="Markdown")
    return SELECCIONAR_TIPO


async def seleccionar_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    tipo = query.data

    if tipo == "cierre":
        context.user_data['tipo'] = "Cierre"
        context.user_data['subtipo'] = "cierre"
        await query.edit_message_text("Has seleccionado: *Cierre*\n\nIngresa el *Detalle del trabajo realizado*:", parse_mode="Markdown")
        return SOLICITAR_DETALLE
    else:
        keyboard = [
            [InlineKeyboardButton("PN/PPTO", callback_data="susp_ppto")],
            [InlineKeyboardButton("PN (Garantía)", callback_data="susp_garantia")],
            [InlineKeyboardButton("Reprogramación", callback_data="susp_reprog")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Selecciona el motivo de la *Suspensión*:", reply_markup=reply_markup, parse_mode="Markdown")
        return SELECCIONAR_SUBTIPO_SUSPENSION


async def seleccionar_subtipo_suspension(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    subtipo = query.data
    context.user_data['subtipo'] = subtipo

    if subtipo == "susp_ppto":
        context.user_data['tipo'] = "Suspensión (PN/PPTO)"
        await query.edit_message_text("Has seleccionado: *PN/PPTO*\n\nPor favor, ingresa el *Número de Parte (PN)*:", parse_mode="Markdown")
        return SOLICITAR_NUMERO_PARTE

    elif subtipo == "susp_garantia":
        context.user_data['tipo'] = "Suspensión (PN)"
        await query.edit_message_text("Has seleccionado: *PN (Garantía)*\n\nPor favor, ingresa el *Número de Parte (PN)*:", parse_mode="Markdown")
        return SOLICITAR_NUMERO_PARTE

    else:  # susp_reprog
        context.user_data['tipo'] = "Suspensión (Reprogramación)"
        await query.edit_message_text("Has seleccionado: *Reprogramación*\n\nIngresa el *Motivo o detalle de la reprogramación solicitada por el cliente*:", parse_mode="Markdown")
        return SOLICITAR_DETALLE


async def recibir_numero_parte(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['numero_parte'] = update.message.text.strip()
    await update.message.reply_text("Ingresa el *Detalle del trabajo / diagnóstico realizado*:", parse_mode="Markdown")
    return SOLICITAR_DETALLE


async def recibir_detalle_y_generar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['detalle'] = update.message.text.strip()
    
    await update.message.reply_text("🔄 *Procesando y generando reporte técnico con IA...*", parse_mode="Markdown")
    
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
            model='gemini-3.1-flash',
            contents=prompt,
        )
        resultado_ia = response.text.strip()
    except Exception as e:
        resultado_ia = f"Error al consultar la IA: {e}\n\nDetalle original: {detalle}"

    mensaje_final = (
        "✅ *Comentario técnico generado:*\n\n"
        f"```text\n{resultado_ia}\n```\n\n"
        "Para generar otro comentario, escribe /start"
    )
    
    await update.message.reply_text(mensaje_final, parse_mode="Markdown")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Proceso cancelado. Envía /start para comenzar de nuevo.")
    return ConversationHandler.END


if __name__ == '__main__':
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
    app.run_polling()
