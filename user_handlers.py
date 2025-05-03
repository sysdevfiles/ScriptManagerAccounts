import logging
from datetime import datetime
import time
import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode # Asegúrate que ParseMode está importado

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
        # Añadimos más botones de admin en filas separadas
        keyboard.append([InlineKeyboardButton("🔑 Admin: Listar Usuarios", callback_data='admin_list_users')])
        keyboard.append([InlineKeyboardButton("👤 Admin: Añadir Usuario", callback_data='admin_add_user_prompt')]) # Prompt para pedir datos
        keyboard.append([InlineKeyboardButton("🧾 Admin: Listar Cuentas", callback_data='admin_list_all_accounts')])
        keyboard.append([InlineKeyboardButton("➕ Admin: Añadir Cuenta", callback_data='admin_add_account_prompt')]) # Prompt para pedir datos
        keyboard.append([InlineKeyboardButton("🔗 Admin: Listar Asignaciones", callback_data='admin_list_assignments')])
        # Podrías añadir un botón para asignar, aunque /assign requiere IDs
        # keyboard.append([InlineKeyboardButton("🤝 Admin: Asignar Cuenta", callback_data='admin_assign_account_prompt')])
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
    logger.info(f"--- FUNCIÓN HELP INICIADA --- Update ID: {update.update_id}") # Log añadido
    try:
        user_id = update.effective_user.id
        is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
        is_authorized = db.is_user_authorized(user_id) # Asignar directamente el booleano devuelto

        help_text = "🤖 *Comandos Disponibles*\n\n"
        help_text += "*/start* - Muestra el menú principal.\n"
        help_text += "*/help* - Muestra esta ayuda.\n"
        help_text += "*/status* - Verifica tu estado de acceso.\n"

        if is_authorized or is_admin_user:
            help_text += "\n*Comandos Autorizados:*\n"
            help_text += "*/list* - Muestra tus perfiles asignados.\n"
            # Quitamos /get de la ayuda pública por ahora, ya que se envía por privado
            # help_text += "*/get* - Obtiene los detalles de tus perfiles (privado).\n"
            help_text += "_Usa los botones o /list para ver tus cuentas._\n"


        if is_admin_user:
            help_text += "\n*Comandos de Administrador:*\n"
            # Usamos `backticks` para los comandos y parámetros
            help_text += "`/add <servicio> <email> <perfil> <pin>` - Añade un perfil.\n"
            help_text += "`/adduser <user_id> <nombre> <días>` - Autoriza/actualiza un usuario.\n"
            help_text += "`/assign <user_id> <account_id>` - Asigna un perfil a un usuario.\n"
            help_text += "`/listallaccounts` - Lista todos los perfiles con ID.\n"
            help_text += "`/listusers` - Lista usuarios autorizados.\n"
            help_text += "`/listassignments` - Lista todas las asignaciones.\n"
            # Añadir comandos para eliminar/modificar si existen

        keyboard = get_main_menu_keyboard(is_admin_user)
        logger.info(f"Preparado para enviar mensaje de ayuda a user_id: {user_id}") # Log añadido
        # Cambiado a ParseMode.MARKDOWN
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        logger.info(f"Mensaje de ayuda enviado a user_id: {user_id}") # Log añadido

    except Exception as e:
        logger.error(f"Error dentro de la función help_command: {e}", exc_info=True)
        try:
            await update.message.reply_text("Ocurrió un error al mostrar la ayuda.")
        except Exception as send_error:
            logger.error(f"No se pudo enviar mensaje de error de ayuda al usuario {user_id}: {send_error}")


async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Autorizados) Lista los servicios de streaming disponibles."""
    query = update.callback_query
    user_id = None # Inicializar user_id
    is_callback = False # Flag para saber si es callback

    if query:
        user_id = query.from_user.id
        is_callback = True
        await query.answer() # Responder al callback si existe
    elif update.message:
        user_id = update.message.from_user.id
    else:
        logger.warning("No se pudo determinar user_id en list_accounts")
        return

    logger.info(f"list_accounts: user_id={user_id}, is_callback={is_callback}")

    # Verificar autorización (usando el user_id obtenido)
    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
    if not db.is_user_authorized(user_id) and not is_admin_user: # Permitir al admin también
        message = "⛔ No tienes permiso para ver la lista de cuentas."
        if is_callback:
            await query.edit_message_text(text=message, reply_markup=get_back_to_menu_keyboard()) # Añadir botón volver
        else:
            await update.message.reply_text(text=message)
        return

    try:
        # Obtener las cuentas asignadas AL USUARIO ESPECÍFICO
        assigned_accounts = db.get_assigned_accounts_for_user(user_id) # Necesitas esta función en database.py

        if not assigned_accounts:
            message = "ℹ️ No tienes ninguna cuenta asignada todavía."
        else:
            accounts_text_list = []
            for acc in assigned_accounts:
                # Asumiendo que get_assigned_accounts_for_user devuelve una lista de diccionarios
                # con claves como 'service', 'profile_name', etc.
                service = acc.get('service', 'N/A')
                profile = acc.get('profile_name', 'N/A')
                # Escapar caracteres de Markdown
                service_escaped = db.escape_markdown(service)
                profile_escaped = db.escape_markdown(profile)
                accounts_text_list.append(f"- {service_escaped} (Perfil: {profile_escaped})")

            accounts_text = "\n".join(accounts_text_list)
            message = f"📋 *Tus Cuentas Asignadas:*\n{accounts_text}\n\n_Para obtener el PIN, usa el comando /get_"

        # Determinar el teclado a mostrar (menú principal o solo volver)
        final_keyboard = get_back_to_menu_keyboard() if is_callback else get_main_menu_keyboard(is_admin_user)

        if is_callback:
             await query.edit_message_text(text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard)
        else:
            await update.message.reply_text(text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard)

    except Exception as e:
        logger.error(f"Error al procesar list_accounts para {user_id}: {e}", exc_info=True)
        message = "⚠️ Ocurrió un error al obtener la lista de cuentas."
        if is_callback:
            await query.edit_message_text(text=message, reply_markup=get_back_to_menu_keyboard())
        elif update.message:
            await update.message.reply_text(text=message)

# --- Necesitas añadir get_back_to_menu_keyboard() y get_assigned_accounts_for_user() ---
def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
     """Genera un teclado con solo el botón de volver al menú."""
     # Esta función debería estar preferiblemente en callback_handlers.py o un módulo de utilidades
     # pero la ponemos aquí temporalmente para que funcione list_accounts
     keyboard = [[InlineKeyboardButton("⬅️ Volver al Menú", callback_data='back_to_menu')]]
     return InlineKeyboardMarkup(keyboard)

# --- Modificar get_account para enviar PIN ---
async def get_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Autorizados) Obtiene los detalles (PIN) de los perfiles asignados."""
    user_id = update.effective_user.id
    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)

    if not db.is_user_authorized(user_id) and not is_admin_user:
        await update.message.reply_text("⛔ No tienes permiso para usar este comando.")
        return

    try:
        assigned_accounts = db.get_assigned_accounts_for_user(user_id) # Reutilizar la función

        if not assigned_accounts:
            await update.message.reply_text("ℹ️ No tienes ninguna cuenta asignada para obtener detalles.")
            return

        details_text_list = []
        for acc in assigned_accounts:
            service = acc.get('service', 'N/A')
            profile = acc.get('profile_name', 'N/A')
            pin = acc.get('pin', 'N/A') # Asumiendo que la función devuelve el PIN

            # Escapar caracteres
            service_escaped = db.escape_markdown(service)
            profile_escaped = db.escape_markdown(profile)
            pin_escaped = db.escape_markdown(pin) # Escapar el PIN también

            details_text_list.append(
                f"*{service_escaped}* (Perfil: {profile_escaped})\n PIN: `{pin_escaped}`"
            )

        details_text = "\n\n".join(details_text_list)
        message = f"🔑 *Detalles de tus Perfiles Asignados:*\n\n{details_text}"

        try:
            # Enviar por mensaje privado
            await context.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN
            )
            # Confirmar en el chat original si no es privado
            if update.message.chat.type != 'private':
                 await update.message.reply_text("✅ Te he enviado los detalles por mensaje privado.")
            logger.info(f"Usuario {user_id} solicitó detalles con /get")

        except Exception as e:
            logger.error(f"Error enviando mensaje privado de /get a {user_id}: {e}", exc_info=True)
            await update.message.reply_text(
                "⚠️ No pude enviarte los detalles por privado. Asegúrate de haber iniciado una conversación conmigo y vuelve a intentarlo."
            )

    except Exception as e:
        logger.error(f"Error al procesar /get para {user_id}: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Ocurrió un error al obtener los detalles de tus cuentas.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el estado de acceso del usuario (puede ser llamado por botón o comando)."""
    query = update.callback_query
    user_id = None
    is_callback = False

    if query:
        user_id = query.from_user.id
        is_callback = True
        await query.answer()
    elif update.message:
        user_id = update.message.from_user.id
    else:
        logger.warning("No se pudo determinar user_id en status_command")
        return

    logger.info(f"status_command: user_id={user_id}, is_callback={is_callback}")

    message = ""
    user_name = "Usuario" # Default name

    # Comprobar si es admin
    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)

    if is_admin_user:
        message = "👑 Eres el *administrador*. Tienes acceso permanente."
    else:
        try:
            # Obtener estado del usuario normal
            user_status = db.get_user_status_db(user_id) # Necesitas esta función en database.py
            if user_status:
                user_name = user_status.get('name', user_name)
                expiry_ts = user_status.get('expiry_ts')
                name_escaped = db.escape_markdown(user_name)

                if expiry_ts:
                    current_ts = int(time.time())
                    expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%d/%m/%Y %H:%M') # Añadir hora
                    if current_ts <= expiry_ts:
                        message = f"✅ Hola {name_escaped}. Tu acceso está *activo* hasta: {expiry_date}"
                    else:
                        message = f"⏳ Hola {name_escaped}. Tu acceso *expiró* el: {expiry_date}"
                else:
                    # Usuario existe pero sin fecha de expiración? Podría ser un estado inválido
                    message = f"❓ Hola {name_escaped}. Tu estado de acceso es indeterminado. Contacta al admin."
            else:
                message = "❌ No estás registrado como usuario autorizado."
        except Exception as e:
            logger.error(f"Error al procesar status_command para {user_id}: {e}", exc_info=True)
            message = "⚠️ Ocurrió un error al verificar tu estado."

    # Determinar teclado
    final_keyboard = get_back_to_menu_keyboard() if is_callback else get_main_menu_keyboard(is_admin_user)

    # Enviar respuesta
    if is_callback:
        await query.edit_message_text(text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard)
    elif update.message:
        await update.message.reply_text(text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja comandos desconocidos."""
    await update.message.reply_text("Lo siento, no entendí ese comando. Usa /start para ver el menú principal.")

