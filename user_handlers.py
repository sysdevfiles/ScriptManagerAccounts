import logging
from datetime import datetime
import time
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Importar funciones de base de datos y otros módulos necesarios
import database as db

# Cargar y verificar ADMIN_USER_ID
load_dotenv()
ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID")
ADMIN_USER_ID = None
if ADMIN_USER_ID_STR and ADMIN_USER_ID_STR.isdigit():
    ADMIN_USER_ID = int(ADMIN_USER_ID_STR)
    logging.info(f"ADMIN_USER_ID cargado correctamente: {ADMIN_USER_ID}")
else:
    logging.critical("Error: ADMIN_USER_ID no encontrado o inválido en .env al cargar user_handlers.py")
    # Considera si el bot debe detenerse aquí o continuar con funcionalidad limitada

logger = logging.getLogger(__name__)

# --- Funciones de Comandos de Usuario ---

def get_main_menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    """Genera el teclado del menú principal según el rol del usuario."""
    keyboard = [
        [InlineKeyboardButton("📊 Estado", callback_data='status')],
        [InlineKeyboardButton("📋 Mis Cuentas", callback_data='list_accounts')],
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton("🔑 Admin: Listar Usuarios", callback_data='admin_list_users')])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía un mensaje de bienvenida con el menú principal."""
    logger.info(f"--- FUNCIÓN START (LÓGICA RESTAURADA) INICIADA --- Update ID: {update.update_id}")
    try:
        user = update.effective_user
        if not user:
            logger.warning("No se pudo obtener effective_user en start.")
            return
        user_id = user.id
        user_name = user.first_name
        logger.info(f"Comando /start recibido de user_id: {user_id} ({user_name})")

        # --- Lógica original restaurada ---
        # Comprobar si el user_id coincide con el ADMIN_USER_ID cargado
        is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
        is_authorized_user = db.is_user_authorized(user_id) # Asignar directamente el booleano devuelto
        logger.info(f"User {user_id}: is_admin={is_admin_user}, is_authorized={is_authorized_user}")

        welcome_message = f"¡Hola, {user_name}! 👋\n\nBienvenido al Gestor de Cuentas."
        if is_authorized_user or is_admin_user:
             welcome_message += "\nPuedes usar los botones de abajo o escribir /help para ver los comandos."
        else:
            welcome_message += "\nParece que no tienes acceso autorizado. Contacta al administrador."

        keyboard = get_main_menu_keyboard(is_admin_user) # Llama a la función definida localmente
        # --- Fin lógica original restaurada ---

        logger.info(f"Preparado para enviar mensaje de bienvenida a user_id: {user_id}")

        await update.message.reply_text(welcome_message, reply_markup=keyboard)
        logger.info(f"Mensaje de bienvenida enviado a user_id: {user_id}")

    except Exception as e:
        # Mantenemos el bloque de captura de errores
        logger.error(f"Error dentro de la función start (lógica restaurada): {e}", exc_info=True)
        try:
            await update.message.reply_text("Ocurrió un error procesando tu solicitud. Por favor, intenta más tarde.")
        except Exception as send_error:
            logger.error(f"No se pudo enviar mensaje de error al usuario {user_id}: {send_error}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la ayuda."""
    user_id = update.effective_user.id
    # Reemplazar también aquí
    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
    is_authorized = db.is_user_authorized(user_id) # Asignar directamente el booleano devuelto

    help_text = "🤖 *Comandos Disponibles*\n\n"
    help_text += "*/start* - Muestra el menú principal.\n"
    help_text += "*/help* - Muestra esta ayuda.\n"
    help_text += "*/status* - Verifica tu estado de acceso.\n"

    if is_authorized or is_admin_user:
        help_text += "\n*Comandos Autorizados:*\n"
        help_text += "*/list* - Muestra tus perfiles asignados.\n"
        help_text += "*/get* - Obtiene los detalles de tus perfiles (privado).\n"

    if is_admin_user:
        help_text += "\n*Comandos de Administrador:*\n"
        help_text += "`/add <servicio> <email> <perfil> <pin>` - Añade un perfil.\n"
        help_text += "`/adduser <user_id> <nombre> <días>` - Autoriza/actualiza un usuario.\n"
        help_text += "`/assign <user_id> <account_id>` - Asigna un perfil a un usuario.\n"
        help_text += "`/listallaccounts` - Lista todos los perfiles con ID.\n"
        help_text += "`/listusers` - Lista usuarios autorizados.\n"
        help_text += "`/listassignments` - Lista todas las asignaciones.\n"

    keyboard = get_main_menu_keyboard(is_admin_user)
    await update.message.reply_text(help_text, parse_mode='MarkdownV2', reply_markup=keyboard)

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Autorizados) Lista los servicios de streaming disponibles."""
    query = update.callback_query
    if query:
        user_id = query.from_user.id
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
            services_escaped = [db.escape_markdown(s) for s in services]
            services_text = "\n- ".join(services_escaped)
            message = f"📄 Cuentas disponibles:\n- {services_text}\n\nUsa `/get <servicio>` para obtener detalles\\."

        if query:
             await query.edit_message_text(text=message, parse_mode='MarkdownV2')
        else:
            await update.message.reply_text(text=message, parse_mode='MarkdownV2')

    except Exception as e:
        logger.error(f"Error al procesar list_accounts: {e}")
        message = "Ocurrió un error al obtener la lista de cuentas."
        if query:
            await query.edit_message_text(text=message)
        else:
            await update.message.reply_text(text=message, parse_mode='MarkdownV2')

async def get_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Autorizados) Obtiene los detalles de una cuenta específica (comando)."""
    user_id = update.effective_user.id
    if not db.is_user_authorized(user_id):
        await update.message.reply_text("No tienes permiso para usar este comando.")
        return

    if len(context.args) != 1:
        await update.message.reply_text("Uso: /get <servicio>")
        return

    service_arg = context.args[0]

    try:
        account = db.get_account_db(service_arg.capitalize())
        if not account:
             account = db.get_account_db(service_arg)

        if account:
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
    else:
        user_id = update.effective_user.id

    message = ""
    user_name = "Usuario"
    is_authorized = False

    if user_id == ADMIN_USER_ID:
        message = "👑 Eres el administrador. Tienes acceso permanente."
        is_authorized = True
    else:
        try:
            user_status = db.get_user_status_db(user_id)
            if user_status:
                user_name = user_status.get('name', user_name)
                expiry_ts = user_status['expiry_ts']
                current_ts = int(time.time())
                expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%d/%m/%Y')
                name_escaped = db.escape_markdown(user_name)
                if current_ts <= expiry_ts:
                    message = f"✅ Hola {name_escaped}. Tu acceso está activo hasta: *{expiry_date}*"
                    is_authorized = True
                else:
                    message = f"⏳ Hola {name_escaped}. Tu acceso expiró el: *{expiry_date}*"
                    is_authorized = False
            else:
                message = "❌ No estás registrado como usuario autorizado."
                is_authorized = False
        except Exception as e:
            logger.error(f"Error al procesar status_command para {user_id}: {e}")
            message = "⚠️ Ocurrió un error al verificar tu estado."
            is_authorized = False

    if query:
        await query.edit_message_text(text=message, parse_mode='MarkdownV2')
    else:
        await update.message.reply_text(text=message, parse_mode='MarkdownV2')

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja comandos desconocidos."""
    await update.message.reply_text("Lo siento, no entendí ese comando. Usa /start para ver el menú principal.")

