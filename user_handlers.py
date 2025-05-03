import logging
from datetime import datetime
import time
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes

# Importar funciones de base de datos y otros módulos necesarios
import database as db
# Importar selectivamente para evitar dependencia circular completa
from callback_handlers import get_main_menu_keyboard

# Cargar ADMIN_USER_ID para comprobaciones (aunque status_command lo usa)
load_dotenv()
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))

logger = logging.getLogger(__name__)

# --- Funciones de Comandos de Usuario ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía un mensaje de bienvenida con el menú principal e instrucciones de activación."""
    user_id = update.effective_user.id
    keyboard = get_main_menu_keyboard(user_id) # Llama a la función del módulo callback

    welcome_message = (
        "¡Hola! 👋 Bienvenido al Gestor de Cuentas.\n\n"
        "Para poder usar todas las funciones, necesitas ser activado.\n"
        "Por favor, contacta al Owner @lestermel para solicitar tu activación.\n\n"
        "Mientras tanto, puedes ver tu estado actual usando los botones:"
    )

    await update.message.reply_text(
        welcome_message,
        reply_markup=keyboard
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía un mensaje de ayuda simple o redirige a /start."""
    await update.message.reply_text(
        "Usa /start para ver el menú principal con las opciones disponibles."
    )

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Autorizados) Lista los servicios de streaming disponibles."""
    query = update.callback_query
    if query:
        user_id = query.from_user.id
        # await query.answer() # Se responde en el callback handler principal
    else:
        user_id = update.effective_user.id

    if not db.is_user_authorized(user_id):
        message = "No tienes permiso para ver la lista de cuentas."
        if query:
            await query.edit_message_text(text=message)
        else:
            await update.message.reply_text(text=message)
        return

    try:
        services = db.list_accounts_db()
        if not services:
            message = "No hay cuentas almacenadas todavía."
        else:
            # Escapar servicios antes de unirlos
            services_escaped = [db.escape_markdown(s) for s in services]
            services_text = "\n- ".join(services_escaped)
            message = f"📄 Cuentas disponibles:\n- {services_text}\n\nUsa `/get <servicio>` para obtener detalles\\." # Escapar punto final

        # La lógica de editar/responder con teclado se maneja mejor en el callback handler
        if query:
             # Solo editamos el texto aquí, el teclado lo pone el callback handler
             await query.edit_message_text(text=message, parse_mode='MarkdownV2')
        else:
            await update.message.reply_text(text=message, parse_mode='MarkdownV2')

    except Exception as e:
        logger.error(f"Error al procesar list_accounts: {e}")
        message = "Ocurrió un error al obtener la lista de cuentas."
        if query:
            await query.edit_message_text(text=message)
        else:
            await update.message.reply_text(text=message)


async def get_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Autorizados) Obtiene los detalles de una cuenta específica (comando)."""
    user_id = update.effective_user.id
    if not db.is_user_authorized(user_id):
        await update.message.reply_text("No tienes permiso para usar este comando.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Uso: /get <servicio>")
        return

    # No capitalizar aquí, buscar tal cual y capitalizar solo para mostrar
    service_arg = context.args[0]

    try:
        # Intentar buscar capitalizado y no capitalizado podría ser una mejora
        account = db.get_account_db(service_arg.capitalize())
        if not account:
             account = db.get_account_db(service_arg) # Intentar sin capitalizar

        if account:
            # Usar el nombre del servicio como está en la BD o el argumento capitalizado
            service_display = service_arg.capitalize()
            username = account['username']
            password = account['password']
            try:
                username_escaped = db.escape_markdown(username)
                password_escaped = db.escape_markdown(password)
                service_display_escaped = db.escape_markdown(service_display)

                await context.bot.send_message(
                    chat_id=update.effective_user.id,
                    text=f"🔑 Detalles de la cuenta *{service_display_escaped}*:\n"
                         f"Usuario: `{username_escaped}`\n"
                         f"Contraseña: `{password_escaped}`",
                    parse_mode='MarkdownV2'
                )
                if update.message.chat.type != 'private':
                     await update.message.reply_text(f"✅ Te he enviado los detalles de *{service_display_escaped}* por mensaje privado.", parse_mode='MarkdownV2')
                logger.info(f"Usuario {user_id} solicitó la cuenta: {service_display}")
            except Exception as e:
                logger.error(f"Error enviando mensaje privado a {user_id}: {e}")
                await update.message.reply_text(
                    "⚠️ No pude enviarte los detalles por privado. Asegúrate de haber iniciado una conversación conmigo."
                )
        else:
            service_arg_escaped = db.escape_markdown(service_arg)
            await update.message.reply_text(f"❌ No se encontró ninguna cuenta para el servicio: *{service_arg_escaped}*", parse_mode='MarkdownV2')

    except Exception as e:
        logger.error(f"Error al procesar /get para {service_arg}: {e}")
        await update.message.reply_text(" Ocurrió un error al buscar la cuenta.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el estado de acceso del usuario (puede ser llamado por botón o comando)."""
    query = update.callback_query
    if query:
        user_id = query.from_user.id
        # await query.answer() # Se responde en el callback handler principal
    else:
        user_id = update.effective_user.id

    message = ""
    user_name = "Usuario" # Nombre por defecto
    is_authorized = False

    if user_id == ADMIN_USER_ID:
        message = "👑 Eres el administrador. Tienes acceso permanente."
        is_authorized = True # Admin siempre está autorizado
    else:
        try:
            user_status = db.get_user_status_db(user_id)
            if user_status:
                user_name = user_status.get('name', user_name) # Obtener nombre si existe
                expiry_ts = user_status['expiry_ts']
                current_ts = int(time.time())
                expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%d/%m/%Y')
                name_escaped = db.escape_markdown(user_name)
                if current_ts <= expiry_ts:
                    message = f"✅ Hola {name_escaped}. Tu acceso está activo hasta: *{expiry_date}*"
                    is_authorized = True
                else:
                    message = f"⏳ Hola {name_escaped}. Tu acceso expiró el: *{expiry_date}*"
                    is_authorized = False # Acceso expirado
            else:
                message = "❌ No estás registrado como usuario autorizado."
                is_authorized = False # No registrado
        except Exception as e:
            logger.error(f"Error al procesar status_command para {user_id}: {e}")
            message = "⚠️ Ocurrió un error al verificar tu estado."
            is_authorized = False # Error, asumir no autorizado

    # La lógica de editar/responder con teclado se maneja mejor en el callback handler
    if query:
        # Solo editamos el texto aquí
        await query.edit_message_text(text=message, parse_mode='MarkdownV2')
    else:
        await update.message.reply_text(text=message, parse_mode='MarkdownV2')

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja comandos desconocidos."""
    await update.message.reply_text("Lo siento, no entendí ese comando. Usa /start para ver el menú principal.")

