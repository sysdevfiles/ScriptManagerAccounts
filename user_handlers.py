import logging
from datetime import datetime, timedelta
import time
import os
import tempfile
import re # Importar re para parseo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, InputFile # Importar InputFile
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    JobQueue
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Importar funciones de base de datos y otros módulos necesarios
import database as db
# Importar desde utils.py (asumiendo que las funciones de borrado están ahí o se moverán)
from utils import ADMIN_USER_ID, get_back_to_menu_keyboard, delete_message_later, DELETE_DELAY_SECONDS

logger = logging.getLogger(__name__)

# --- Constantes y Estados para Conversaciones ---
# addmyaccount
CALLBACK_ADD_MY_ACCOUNT = "add_my_account"
SELECT_SERVICE, GET_MY_EMAIL, GET_MY_PROFILE, GET_MY_PIN = range(10, 14)
# deletemyaccount
CALLBACK_DELETE_MY_ACCOUNT = "delete_my_account"
SELECT_ACCOUNT_TO_DELETE, CONFIRM_DELETE = range(14, 16)
# editmyaccount
CALLBACK_EDIT_MY_ACCOUNT = "edit_my_account"
SELECT_ACCOUNT_TO_EDIT, CHOOSE_EDIT_FIELD, GET_NEW_EMAIL, GET_NEW_PIN = range(16, 20)
# Backup
CALLBACK_BACKUP_MY_ACCOUNTS = "backup_my_accounts"
# Import
CALLBACK_IMPORT_MY_ACCOUNTS = "import_my_accounts"
GET_BACKUP_FILE, CONFIRM_IMPORT = range(20, 22) # Nuevos estados

# Lista de servicios predefinidos
STREAMING_SERVICES = ["Netflix", "HBO Max", "Spotify", "Disney Plus", "Paramount Plus", "Prime Video", "YouTube Premium", "Crunchyroll", "Otro"]

# --- Funciones de Teclados ---

def get_main_menu_keyboard(is_admin: bool, is_authorized: bool) -> InlineKeyboardMarkup:
    """Genera el teclado del menú principal según el rol y autorización."""
    keyboard = []
    # Opciones comunes si está autorizado o es admin
    if is_authorized or is_admin: # Corregido: 'or' en lugar de '()' innecesarios
        keyboard.extend([
            [InlineKeyboardButton("📊 Estado", callback_data='show_status')],
            [InlineKeyboardButton("📋 Mis Cuentas", callback_data='list_accounts')],
        ])
        # Opciones solo para usuarios normales autorizados
        if is_authorized and not is_admin:
             keyboard.append([InlineKeyboardButton("➕ Añadir Mi Cuenta", callback_data=CALLBACK_ADD_MY_ACCOUNT)])
             keyboard.append([InlineKeyboardButton("✏️ Editar Mi Cuenta", callback_data=CALLBACK_EDIT_MY_ACCOUNT)])
             keyboard.append([InlineKeyboardButton("🗑️ Eliminar Mi Cuenta", callback_data=CALLBACK_DELETE_MY_ACCOUNT)])
             keyboard.append([InlineKeyboardButton("💾 Backup Mis Cuentas", callback_data=CALLBACK_BACKUP_MY_ACCOUNTS)]) # <-- Nuevo botón
             keyboard.append([InlineKeyboardButton("📥 Importar Backup", callback_data=CALLBACK_IMPORT_MY_ACCOUNTS)]) # <-- Nuevo botón

    # Opciones solo para Admin
    if is_admin:
        keyboard.extend([
            [InlineKeyboardButton("🔑 Admin: Listar Usuarios", callback_data='admin_list_users')],
            [InlineKeyboardButton("👤 Admin: Añadir/Act. Usuario", callback_data='admin_add_user_prompt')],
            [InlineKeyboardButton("🧾 Admin: Listar Todas Cuentas", callback_data='admin_list_all_accounts')],
        ])

    # Si no hay botones (no autorizado y no admin), no añadir nada
    if not keyboard:
         return None # O un teclado vacío si se prefiere InlineKeyboardMarkup([])

    return InlineKeyboardMarkup(keyboard)

# --- Funciones Auxiliares ---

async def _send_or_edit_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup, schedule_delete: bool = True):
    """Envía o edita un mensaje, opcionalmente programa su borrado."""
    query = update.callback_query
    is_callback = bool(query)
    chat_id = update.effective_chat.id
    job_queue = context.job_queue
    sent_message = None

    try:
        if is_callback:
            sent_message = await query.edit_message_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        elif update.message:
            # Borrar comando original si es posible
            try: await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
            except Exception: pass
            sent_message = await update.message.reply_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )

        if sent_message and schedule_delete:
            job_queue.run_once(
                delete_message_later,
                when=timedelta(seconds=DELETE_DELAY_SECONDS * 2), # Usar un delay más largo para listas
                data={'chat_id': chat_id, 'message_id': sent_message.message_id},
                name=f'delete_{chat_id}_{sent_message.message_id}'
            )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Error al enviar/editar mensaje en _send_or_edit_message: {e}")
            # Intentar enviar un mensaje simple si falla la edición/envío
            if not is_callback and update.message:
                try: await update.message.reply_text("⚠️ Ocurrió un error al mostrar la información.")
                except Exception: pass
    except Exception as e:
        logger.error(f"Error inesperado en _send_or_edit_message: {e}", exc_info=True)
        if not is_callback and update.message:
            try: await update.message.reply_text("⚠️ Ocurrió un error inesperado.")
            except Exception: pass


# --- Funciones de Comandos de Usuario ---

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

        # Comprobar si el user_id coincide con el ADMIN_USER_ID cargado
        is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
        is_authorized_user = db.is_user_authorized(user_id)
        logger.info(f"User {user_id}: is_admin={is_admin_user}, is_authorized={is_authorized_user}")

        welcome_message = f"¡Hola, {user_name}! 👋\n\nBienvenido al Gestor de Cuentas."
        if is_authorized_user or is_admin_user:
             welcome_message += "\nPuedes usar los botones de abajo 👇 o escribir /help para ver los comandos."
        else:
            welcome_message += "\n⛔ Parece que no tienes acceso autorizado. Contacta al administrador."

        keyboard = get_main_menu_keyboard(is_admin_user, is_authorized_user)

        logger.info(f"Preparado para enviar mensaje de bienvenida a user_id: {user_id}")
        await update.message.reply_text(welcome_message, reply_markup=keyboard)
        logger.info(f"Mensaje de bienvenida enviado a user_id: {user_id}")
    except Exception as e:
        logger.error(f"Error dentro de la función start (lógica restaurada): {e}", exc_info=True)
        try:
            await update.message.reply_text("Ocurrió un error procesando tu solicitud. Por favor, intenta más tarde.")
        except Exception as send_error:
            logger.error(f"No se pudo enviar mensaje de error al usuario {user_id}: {send_error}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra la ayuda."""
    logger.info(f"--- FUNCIÓN HELP INICIADA --- Update ID: {update.update_id}")
    try:
        user_id = update.effective_user.id
        is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
        is_authorized = db.is_user_authorized(user_id)

        help_text = "🤖 *Comandos Disponibles*\n\n"
        help_text += "*/start* - Muestra el menú principal.\n"
        help_text += "*/help* - Muestra esta ayuda.\n"
        help_text += "*/status* - Verifica tu estado de acceso.\n"

        if is_authorized or is_admin_user:
            help_text += "\n*Comandos Autorizados:*\n"
            help_text += "`/list` - 📋 Muestra tus perfiles activos.\n"
            help_text += "`/get` - 🔑 Obtiene los detalles (PIN) de tus perfiles (privado).\n"
            if is_authorized and not is_admin_user:
                 help_text += "`/addmyaccount` - ➕ Añade un perfil propio (válido 30 días).\n"
                 help_text += "`/editmyaccount` - ✏️ Edita el Email o PIN de un perfil propio.\n"
                 help_text += "`/deletemyaccount` - 🗑️ Elimina un perfil propio.\n"

        if is_admin_user:
            help_text += "\n*Comandos de Administrador:*\n"
            help_text += "`/adduser <user_id> <nombre> <días>` - Autoriza/actualiza un usuario.\n"
            help_text += "`/listusers` - Lista usuarios autorizados.\n"
            help_text += "`/listallaccounts` - Lista todos los perfiles registrados (propios y de usuarios).\n"

        keyboard = get_main_menu_keyboard(is_admin_user, is_authorized)
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        logger.info(f"Mensaje de ayuda enviado a user_id: {user_id}")

    except Exception as e:
        logger.error(f"Error dentro de la función help_command: {e}", exc_info=True)
        try:
            await update.message.reply_text("Ocurrió un error al mostrar la ayuda.")
        except Exception as send_error:
            logger.error(f"No se pudo enviar mensaje de error de ayuda al usuario {user_id}: {send_error}")

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Autorizados) Lista los perfiles propios activos."""
    query = update.callback_query
    user_id = update.effective_user.id
    is_callback = bool(query)
    if is_callback: await query.answer()

    logger.info(f"list_accounts: user_id={user_id}, is_callback={is_callback}")

    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
    is_authorized = db.is_user_authorized(user_id)

    if not is_authorized and not is_admin_user:
        await _send_or_edit_message(update, context, "⛔ No tienes permiso para ver cuentas.", get_back_to_menu_keyboard())
        return

    try:
        user_accounts = db.get_accounts_for_user(user_id)
        if not user_accounts:
            message = "ℹ️ No tienes cuentas propias activas."
        else:
            accounts_text_list = ["📋 *Tus Cuentas Activas:*"]
            for acc in user_accounts:
                expiry_date = datetime.fromtimestamp(acc['expiry_ts']).strftime('%d/%m/%Y') if acc.get('expiry_ts') else 'N/A'
                accounts_text_list.append(f"🆔 `{acc.get('id')}`: {db.escape_markdown(acc.get('service', 'N/A'))} (👤 {db.escape_markdown(acc.get('profile_name', 'N/A'))}) - 🗓️ Expira: {expiry_date}")
            message = "\n".join(accounts_text_list)
            message += "\n\n_Para obtener el PIN, usa /get_\n_Para editar/eliminar, usa los botones del menú._"

        await _send_or_edit_message(update, context, message, get_back_to_menu_keyboard(), schedule_delete=True)

    except Exception as e:
        logger.error(f"Error al procesar list_accounts para {user_id}: {e}", exc_info=True)
        await _send_or_edit_message(update, context, "⚠️ Ocurrió un error al obtener tus cuentas.", get_back_to_menu_keyboard())

async def get_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Autorizados) Obtiene los detalles (PIN) de los perfiles propios activos."""
    user_id = update.effective_user.id
    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
    is_authorized = db.is_user_authorized(user_id)
    job_queue = context.job_queue
    chat_id = update.effective_chat.id
    command_message_id = update.message.message_id if update.message else None

    if not is_authorized and not is_admin_user:
        await update.message.reply_text("⛔ No tienes permiso para usar este comando.")
        return

    try:
        user_accounts = db.get_accounts_for_user(user_id)
        if not user_accounts:
            await update.message.reply_text("ℹ️ No tienes cuentas propias activas para obtener detalles.")
            return

        details_text_list = ["🔑 *Detalles de tus Perfiles Activos:*"]
        for acc in user_accounts:
            expiry_date = datetime.fromtimestamp(acc['expiry_ts']).strftime('%d/%m/%Y') if acc.get('expiry_ts') else 'N/A'
            details_text_list.append(
                f"*{db.escape_markdown(acc.get('service', 'N/A'))}* (👤 {db.escape_markdown(acc.get('profile_name', 'N/A'))})\n"
                f"  📧 Email: `{db.escape_markdown(acc.get('email', 'N/A'))}`\n"
                f"  🔑 PIN: `{db.escape_markdown(acc.get('pin', 'N/A'))}`\n"
                f"  🗓️ Expira: {expiry_date}"
            )
        message = "\n\n".join(details_text_list)

        confirmation_msg = None
        try:
            # Siempre enviar por privado
            await context.bot.send_message(chat_id=user_id, text=message, parse_mode=ParseMode.MARKDOWN)
            # Corregido: 'and' en lugar de '&&'
            if update.message and update.message.chat.type != 'private':
                 confirmation_msg = await update.message.reply_text("✅ Te he enviado los detalles por mensaje privado.")
            logger.info(f"🔑 Usuario {user_id} solicitó detalles con /get")
        except Exception as e:
            logger.error(f"Error enviando mensaje privado de /get a {user_id}: {e}", exc_info=True)
            confirmation_msg = await update.message.reply_text("⚠️ No pude enviarte los detalles por privado...")

        # Borrar comando original
        if command_message_id:
            try: await context.bot.delete_message(chat_id=chat_id, message_id=command_message_id)
            except Exception: pass
        # Borrar mensaje de confirmación (si se envió)
        if confirmation_msg:
             job_queue.run_once(
                 delete_message_later,
                 when=timedelta(seconds=DELETE_DELAY_SECONDS),
                 data={'chat_id': chat_id, 'message_id': confirmation_msg.message_id},
                 name=f'delete_{chat_id}_{confirmation_msg.message_id}'
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
    user_name = "Usuario"

    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)

    if is_admin_user:
        message = "👑 Eres el *administrador*. Tienes acceso permanente."
    else:
        try:
            user_status = db.get_user_status_db(user_id)
            if user_status:
                user_name = user_status.get('name', user_name)
                expiry_ts = user_status.get('expiry_ts')
                name_escaped = db.escape_markdown(user_name)

                if expiry_ts:
                    current_ts = int(time.time())
                    expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%d/%m/%Y %H:%M')
                    if current_ts <= expiry_ts:
                        message = f"✅ Hola {name_escaped}. Tu acceso está *activo* hasta: {expiry_date}"
                    else:
                        message = f"⏳ Hola {name_escaped}. Tu acceso *expiró* el: {expiry_date}"
                else:
                    message = f"❓ Hola {name_escaped}. Tu estado de acceso es indeterminado. Contacta al admin."
            else:
                message = "❌ No estás registrado como usuario autorizado."
        except Exception as e:
            logger.error(f"Error al procesar status_command para {user_id}: {e}", exc_info=True)
            message = "⚠️ Ocurrió un error al verificar tu estado."

    is_authorized = db.is_user_authorized(user_id)
    final_keyboard = get_back_to_menu_keyboard() if is_callback else get_main_menu_keyboard(is_admin_user, is_authorized)

    if is_callback:
        await query.edit_message_text(text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard)
    elif update.message:
        await update.message.reply_text(text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard)

# --- Nueva Función: Backup Cuentas Propias ---
async def backup_my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Autorizados) Genera y envía un backup de las cuentas propias activas."""
    query = update.callback_query
    user_id = update.effective_user.id
    is_callback = bool(query)
    if is_callback: await query.answer()

    logger.info(f"backup_my_accounts: user_id={user_id}, is_callback={is_callback}")

    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
    is_authorized = db.is_user_authorized(user_id)

    if not is_authorized or is_admin_user: # Solo usuarios autorizados NO admin
        await _send_or_edit_message(update, context, "⛔ Esta función es solo para usuarios autorizados.", get_back_to_menu_keyboard())
        return

    try:
        user_accounts = db.get_accounts_for_user(user_id)
        if not user_accounts:
            await _send_or_edit_message(update, context, "ℹ️ No tienes cuentas propias activas para hacer backup.", get_back_to_menu_keyboard())
            return

        # Formatear datos para el archivo
        backup_content = f"Backup de Cuentas para Usuario ID: {user_id}\n"
        backup_content += f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        backup_content += "=" * 30 + "\n\n"

        for acc in user_accounts:
            expiry_date = datetime.fromtimestamp(acc['expiry_ts']).strftime('%d/%m/%Y') if acc.get('expiry_ts') else 'N/A'
            backup_content += f"ID Cuenta: {acc.get('id', 'N/A')}\n"
            backup_content += f"Servicio: {acc.get('service', 'N/A')}\n"
            backup_content += f"Email: {acc.get('email', 'N/A')}\n"
            backup_content += f"Perfil: {acc.get('profile_name', 'N/A')}\n"
            backup_content += f"PIN: {acc.get('pin', 'N/A')}\n"
            backup_content += f"Expira: {expiry_date}\n"
            backup_content += "-" * 30 + "\n"

        # Crear archivo temporal
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
            temp_file.write(backup_content)
            temp_file_path = temp_file.name
            file_name = f"backup_cuentas_{user_id}_{datetime.now().strftime('%Y%m%d')}.txt"

        logger.info(f"Archivo de backup temporal creado en: {temp_file_path}")

        # Enviar archivo
        try:
            with open(temp_file_path, 'rb') as file_to_send:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=InputFile(file_to_send, filename=file_name),
                    caption="📄 Aquí tienes el backup de tus cuentas activas.",
                    reply_markup=get_back_to_menu_keyboard() # Añadir botón volver después de enviar
                )
            logger.info(f"Backup enviado a user_id {user_id}.")
            # Si se envió desde un botón, editar el mensaje original para quitar el menú de backup
            if is_callback:
                 try:
                     await query.edit_message_text("Backup enviado. Revisa tus mensajes.", reply_markup=get_back_to_menu_keyboard())
                 except BadRequest: pass # Ignorar si no se puede editar
        except Exception as send_error:
            logger.error(f"Error al enviar archivo de backup a {user_id}: {send_error}", exc_info=True)
            await _send_or_edit_message(update, context, "⚠️ Ocurrió un error al enviar el archivo de backup.", get_back_to_menu_keyboard())
        finally:
            # Limpiar archivo temporal
            try:
                os.remove(temp_file_path)
                logger.info(f"Archivo de backup temporal eliminado: {temp_file_path}")
            except OSError as e:
                logger.error(f"Error al eliminar archivo temporal {temp_file_path}: {e}")

    except Exception as e:
        logger.error(f"Error al procesar backup_my_accounts para {user_id}: {e}", exc_info=True)
        await _send_or_edit_message(update, context, "⚠️ Ocurrió un error al generar el backup.", get_back_to_menu_keyboard())

# --- Conversación: Añadir Cuenta Propia (/addmyaccount) ---

async def add_my_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para que un usuario añada su cuenta."""
    user = update.effective_user
    user_id = user.id
    is_authorized = db.is_user_authorized(user_id)
    is_admin = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)

    if not is_authorized or is_admin:
        # Usar _send_or_edit_message para consistencia
        await _send_or_edit_message(update, context, "⛔ Esta función es solo para usuarios autorizados.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    logger.info(f"User {user_id} iniciando conversación add_my_account.")

    buttons = []
    for service in STREAMING_SERVICES:
        buttons.append([InlineKeyboardButton(service, callback_data=f"service_{service}")])
    service_keyboard = InlineKeyboardMarkup(buttons)

    # Definir el texto del mensaje
    message_text = (
        "➕ Ok, vamos a añadir un perfil de cuenta.\n"
        "1️⃣ Por favor, selecciona el *Servicio* de la lista 👇:\n\n"
        "Puedes cancelar en cualquier momento con /cancel."
    )
    # Usar _send_or_edit_message para enviar/editar el mensaje inicial
    await _send_or_edit_message(update, context, message_text, service_keyboard, schedule_delete=False) # No borrar el menú de selección

    return SELECT_SERVICE

async def received_service_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la selección del servicio, pide el email."""
    query = update.callback_query
    await query.answer()
    service = query.data.split("service_")[-1]
    user_id = query.from_user.id
    context.user_data['my_service'] = service
    logger.info(f"User {user_id} en add_my_account: Seleccionado servicio '{service}'.")

    await query.edit_message_text(
        text=f"✔️ Servicio: {service}.\n"
             "2️⃣ Ahora, envíame el *Email* 📧 de tu cuenta principal asociada.",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_MY_EMAIL

async def received_my_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el email, pide el nombre del perfil y borra mensaje."""
    email = update.message.text.strip()
    user_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id

    if '@' not in email or '.' not in email.split('@')[-1]:
        await update.message.reply_text("📧 Eso no parece un email válido. Intenta de nuevo.")
        return GET_MY_EMAIL

    context.user_data['my_email'] = email
    logger.info(f"User {user_id} en add_my_account: Recibido email '{email}'.")

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e: logger.warning(f"No se pudo borrar mensaje (my_email) {user_message_id}: {e}")

    service = context.user_data.get('my_service', 'Servicio desconocido')
    await update.message.reply_text(
        f"✔️ Servicio: {service}\n"
        f"📧 Email: {email}.\n"
        "3️⃣ Ahora, envíame el *Nombre del Perfil* 👤 específico que quieres añadir.",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_MY_PROFILE

async def received_my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre del perfil, pide el PIN y borra mensaje."""
    profile_name = update.message.text.strip()
    user_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    context.user_data['my_profile_name'] = profile_name
    logger.info(f"User {user_id} en add_my_account: Recibido perfil '{profile_name}'.")

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e: logger.warning(f"No se pudo borrar mensaje (my_profile) {user_message_id}: {e}")

    service = context.user_data.get('my_service', 'Servicio desconocido')
    email = context.user_data.get('my_email', 'Email desconocido')
    await update.message.reply_text(
        f"✔️ Servicio: {service}\n"
        f"📧 Email: {email}\n"
        f"👤 Perfil: {profile_name}.\n"
        "4️⃣ Finalmente, envíame el *PIN* 🔑 de acceso para este perfil (si no tiene, escribe '0000' o 'N/A').",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_MY_PIN

async def received_my_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el PIN, calcula fechas, guarda la cuenta y termina."""
    pin = update.message.text.strip()
    user_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    try:
        service = context.user_data.get('my_service')
        email = context.user_data.get('my_email')
        profile_name = context.user_data.get('my_profile_name')

        if not all([service, email, profile_name]):
             logger.error(f"User {user_id} en add_my_account: Faltan datos en context.user_data al recibir PIN.")
             await update.message.reply_text("¡Ups! Algo salió mal. Por favor, empieza de nuevo con /addmyaccount.")
             context.user_data.clear()
             return ConversationHandler.END

        registration_ts = int(time.time())
        expiry_ts = registration_ts + (30 * 24 * 60 * 60)
        expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%d/%m/%Y')

        try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        except Exception as e: logger.warning(f"No se pudo borrar mensaje (my_pin) {user_message_id}: {e}")

        success = db.add_account_db(user_id, service, email, profile_name, pin, registration_ts, expiry_ts)

        if success:
            service_escaped = db.escape_markdown(service)
            profile_escaped = db.escape_markdown(profile_name)
            email_escaped = db.escape_markdown(email)
            pin_escaped = db.escape_markdown(pin)

            confirmation_text = (
                f"✅ ¡Tu perfil ha sido añadido/actualizado!\n\n"
                f"🔧 Servicio: {service_escaped}\n"
                f"📧 Email Cuenta: {email_escaped}\n"
                f"👤 Perfil: {profile_escaped}\n"
                f"🔑 PIN: `{pin_escaped}`\n"
                f"🗓️ Válido hasta: *{expiry_date}*"
            )
        else:
            confirmation_text = "❌ Hubo un error al guardar tu perfil. Es posible que ya exista un perfil con el mismo nombre para este servicio. Intenta de nuevo o contacta al administrador."

        confirmation_message = await update.message.reply_text(
            confirmation_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_to_menu_keyboard()
        )
        job_queue.run_once(
            delete_message_later,
            when=timedelta(seconds=DELETE_DELAY_SECONDS),
            data={'chat_id': chat_id, 'message_id': confirmation_message.message_id},
            name=f'delete_{chat_id}_{confirmation_message.message_id}'
        )
        logger.info(f"User {user_id} completó add_my_account para {service} - {profile_name}. Resultado: {success}")
        context.user_data.clear()
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error al procesar received_my_pin para user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error inesperado al guardar el perfil. Intenta de nuevo con /addmyaccount.")
        context.user_data.clear()
        return ConversationHandler.END

async def cancel_add_my_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación de añadir cuenta propia."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} canceló la conversación add_my_account.")
    if update.callback_query:
        try: await update.callback_query.edit_message_text("Operación cancelada.", reply_markup=None)
        except BadRequest: await context.bot.send_message(chat_id=user_id, text="Operación cancelada.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

addmyaccount_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("addmyaccount", add_my_account_start),
        CallbackQueryHandler(add_my_account_start, pattern=f"^{CALLBACK_ADD_MY_ACCOUNT}$")
    ],
    states={
        SELECT_SERVICE: [CallbackQueryHandler(received_service_selection, pattern="^service_")],
        GET_MY_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_my_email)],
        GET_MY_PROFILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_my_profile)],
        GET_MY_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_my_pin)],
    },
    fallbacks=[CommandHandler("cancel", cancel_add_my_account)],
    allow_reentry=True
)

# --- Conversación: Eliminar Cuenta Propia (/deletemyaccount) ---

async def delete_my_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para que un usuario elimine su cuenta."""
    user = update.effective_user
    user_id = user.id
    is_authorized = db.is_user_authorized(user_id)
    is_admin = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)

    if not is_authorized or is_admin:
        await _send_or_edit_message(update, context, "⛔ Esta función es solo para usuarios autorizados.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    logger.info(f"User {user_id} iniciando conversación delete_my_account.")
    user_accounts = db.get_accounts_for_user(user_id)

    if not user_accounts:
        await _send_or_edit_message(update, context, "ℹ️ No tienes cuentas propias activas para eliminar.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    buttons = []
    for acc in user_accounts:
        label = f"🆔 {acc.get('id')}: {acc.get('service', 'N/A')} ({acc.get('profile_name', 'N/A')})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"delacc_{acc.get('id')}")])

    message_text = "🗑️ Selecciona la cuenta que deseas eliminar 👇:\n\nPuedes cancelar con /cancel."
    accounts_keyboard = InlineKeyboardMarkup(buttons)

    # Usar _send_or_edit_message para manejar envío/edición inicial
    await _send_or_edit_message(update, context, message_text, accounts_keyboard, schedule_delete=False) # No borrar el menú de selección
    return SELECT_ACCOUNT_TO_DELETE

async def received_delete_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la selección de la cuenta a eliminar, pide confirmación."""
    query = update.callback_query
    await query.answer()
    account_id_str = query.data.split("delacc_")[-1]
    user_id = query.from_user.id

    try:
        account_id = int(account_id_str)
        context.user_data['delete_account_id'] = account_id
        logger.info(f"User {user_id} en delete_my_account: Seleccionado ID {account_id} para eliminar.")

        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sí, eliminar", callback_data="delete_confirm_yes")],
            [InlineKeyboardButton("❌ No, cancelar", callback_data="delete_confirm_no")]
        ])

        # Editar el mensaje anterior para pedir confirmación
        await query.edit_message_text(
            text=f"❓ ¿Estás seguro de que quieres eliminar la cuenta con ID `{account_id}`?\n"
                 f"⚠️ ¡Esta acción no se puede deshacer!",
            reply_markup=confirm_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return CONFIRM_DELETE
    except ValueError:
        logger.error(f"Error al parsear account_id para eliminar: {account_id_str}")
        await query.edit_message_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

async def confirm_delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma o cancela la eliminación de la cuenta."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    confirmation = query.data
    account_id = context.user_data.get('delete_account_id')

    if not account_id:
         logger.error(f"User {user_id} en confirm_delete_account: Falta delete_account_id.")
         await query.edit_message_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
         context.user_data.clear()
         return ConversationHandler.END

    if confirmation == "delete_confirm_yes":
        logger.info(f"User {user_id} confirma eliminar cuenta ID {account_id}.")
        # LLAMAR A LA FUNCIÓN DE BD (NECESITA SER CREADA)
        success = db.delete_account_db(account_id=account_id, user_id=user_id) # Pasar user_id para seguridad

        if success:
            confirmation_text = f"🗑️ ¡Cuenta ID `{account_id}` eliminada correctamente!"
        else:
            confirmation_text = f"❌ No se pudo eliminar la cuenta ID `{account_id}`. Puede que ya no exista o no te pertenezca."

        await _send_or_edit_message(update, context, confirmation_text, get_back_to_menu_keyboard(), schedule_delete=True)
    else:
        logger.info(f"User {user_id} canceló la eliminación de cuenta ID {account_id}.")
        await _send_or_edit_message(update, context, "❌ Eliminación cancelada.", get_back_to_menu_keyboard(), schedule_delete=True)

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_delete_my_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación de eliminar cuenta propia."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} canceló la conversación delete_my_account.")
    await _send_or_edit_message(update, context, "Operación cancelada.", None, schedule_delete=True) # Sin teclado, borrar mensaje
    context.user_data.clear()
    return ConversationHandler.END

deletemyaccount_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("deletemyaccount", delete_my_account_start),
        CallbackQueryHandler(delete_my_account_start, pattern=f"^{CALLBACK_DELETE_MY_ACCOUNT}$")
    ],
    states={
        SELECT_ACCOUNT_TO_DELETE: [CallbackQueryHandler(received_delete_selection, pattern="^delacc_")],
        CONFIRM_DELETE: [CallbackQueryHandler(confirm_delete_account, pattern="^delete_confirm_")],
    },
    fallbacks=[CommandHandler("cancel", cancel_delete_my_account)],
    allow_reentry=True
)

# --- Conversación: Editar Cuenta Propia (/editmyaccount) ---

async def edit_my_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para que un usuario edite su cuenta."""
    user = update.effective_user
    user_id = user.id
    is_authorized = db.is_user_authorized(user_id)
    is_admin = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)

    if not is_authorized or is_admin:
        await _send_or_edit_message(update, context, "⛔ Esta función es solo para usuarios autorizados.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    logger.info(f"User {user_id} iniciando conversación edit_my_account.")
    user_accounts = db.get_accounts_for_user(user_id)

    if not user_accounts:
        await _send_or_edit_message(update, context, "ℹ️ No tienes cuentas propias activas para editar.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    buttons = []
    for acc in user_accounts:
        label = f"🆔 {acc.get('id')}: {acc.get('service', 'N/A')} ({acc.get('profile_name', 'N/A')})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"editacc_{acc.get('id')}")])

    message_text = "✏️ Selecciona la cuenta que deseas editar 👇:\n\nPuedes cancelar con /cancel."
    accounts_keyboard = InlineKeyboardMarkup(buttons)

    await _send_or_edit_message(update, context, message_text, accounts_keyboard, schedule_delete=False)
    return SELECT_ACCOUNT_TO_EDIT

async def received_edit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la selección de la cuenta a editar, pide qué campo editar."""
    query = update.callback_query
    await query.answer()
    account_id_str = query.data.split("editacc_")[-1]
    user_id = query.from_user.id

    try:
        account_id = int(account_id_str)
        context.user_data['edit_account_id'] = account_id
        logger.info(f"User {user_id} en edit_my_account: Seleccionado ID {account_id} para editar.")

        field_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📧 Email", callback_data="editfield_email")],
            [InlineKeyboardButton("🔑 PIN", callback_data="editfield_pin")]
        ])

        await query.edit_message_text(
            text=f"✏️ Editando cuenta ID `{account_id}`.\n"
                 f"¿Qué deseas editar?",
            reply_markup=field_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return CHOOSE_EDIT_FIELD
    except ValueError:
        logger.error(f"Error al parsear account_id para editar: {account_id_str}")
        await query.edit_message_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

async def received_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el campo a editar, pide el nuevo valor."""
    query = update.callback_query
    await query.answer()
    field_to_edit = query.data.split("editfield_")[-1]
    user_id = query.from_user.id
    context.user_data['edit_field'] = field_to_edit
    account_id = context.user_data.get('edit_account_id')

    logger.info(f"User {user_id} en edit_my_account (ID {account_id}): Seleccionado campo '{field_to_edit}'.")

    prompt_text = ""
    next_state = ConversationHandler.END

    if field_to_edit == "email":
        prompt_text = f"✏️ Editando cuenta ID `{account_id}`.\n" \
                      f"Por favor, introduce el nuevo *Email* 📧:"
        next_state = GET_NEW_EMAIL
    elif field_to_edit == "pin":
        prompt_text = f"✏️ Editando cuenta ID `{account_id}`.\n" \
                      f"Por favor, introduce el nuevo *PIN* 🔑:"
        next_state = GET_NEW_PIN
    else:
        logger.error(f"Campo a editar no reconocido: {field_to_edit}")
        await query.edit_message_text("❌ Error interno. Campo no válido.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    # Editar mensaje anterior para pedir el nuevo valor
    await query.edit_message_text(
        text=prompt_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=None # Quitar teclado
    )
    return next_state

async def received_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nuevo email, lo guarda y termina."""
    new_email = update.message.text.strip()
    user_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    account_id = context.user_data.get('edit_account_id')
    if not account_id:
         logger.error(f"User {user_id} en received_new_email: Falta edit_account_id.")
         await update.message.reply_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
         context.user_data.clear()
         return ConversationHandler.END

    if '@' not in new_email or '.' not in new_email.split('@')[-1]:
        await update.message.reply_text("📧 Eso no parece un email válido. Intenta de nuevo.")
        return GET_NEW_EMAIL

    logger.info(f"User {user_id} en edit_my_account (ID {account_id}): Recibido nuevo email '{new_email}'.")

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e: logger.warning(f"No se pudo borrar mensaje (new_email) {user_message_id}: {e}")

    success = db.update_account_details_db(account_id=account_id, user_id=user_id, new_email=new_email)

    if success:
        confirmation_text = f"✅ ¡Email de la cuenta ID `{account_id}` actualizado correctamente!"
    else:
        confirmation_text = f"❌ No se pudo actualizar el email de la cuenta ID `{account_id}`. Verifica que la cuenta exista y te pertenezca."

    sent_message = await update.message.reply_text(
        confirmation_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_to_menu_keyboard()
    )
    job_queue.run_once(
        delete_message_later,
        when=timedelta(seconds=DELETE_DELAY_SECONDS),
        data={'chat_id': chat_id, 'message_id': sent_message.message_id},
        name=f'delete_{chat_id}_{sent_message.message_id}'
    )

    context.user_data.clear()
    return ConversationHandler.END

async def received_new_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nuevo PIN, lo guarda y termina."""
    new_pin = update.message.text.strip()
    user_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    account_id = context.user_data.get('edit_account_id')
    if not account_id:
         logger.error(f"User {user_id} en received_new_pin: Falta edit_account_id.")
         await update.message.reply_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
         context.user_data.clear()
         return ConversationHandler.END

    logger.info(f"User {user_id} en edit_my_account (ID {account_id}): Recibido nuevo PIN '{new_pin}'.")

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e: logger.warning(f"No se pudo borrar mensaje (new_pin) {user_message_id}: {e}")

    success = db.update_account_details_db(account_id=account_id, user_id=user_id, new_pin=new_pin)

    if success:
        confirmation_text = f"✅ ¡PIN de la cuenta ID `{account_id}` actualizado correctamente!"
    else:
        confirmation_text = f"❌ No se pudo actualizar el PIN de la cuenta ID `{account_id}`. Verifica que la cuenta exista y te pertenezca."

    sent_message = await update.message.reply_text(
        confirmation_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_to_menu_keyboard()
    )
    job_queue.run_once(
        delete_message_later,
        when=timedelta(seconds=DELETE_DELAY_SECONDS),
        data={'chat_id': chat_id, 'message_id': sent_message.message_id},
        name=f'delete_{chat_id}_{sent_message.message_id}'
    )

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_edit_my_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación de editar cuenta propia."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} canceló la conversación edit_my_account.")
    await _send_or_edit_message(update, context, "Operación cancelada.", None, schedule_delete=True)
    context.user_data.clear()
    return ConversationHandler.END

editmyaccount_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("editmyaccount", edit_my_account_start),
        CallbackQueryHandler(edit_my_account_start, pattern=f"^{CALLBACK_EDIT_MY_ACCOUNT}$")
    ],
    states={
        SELECT_ACCOUNT_TO_EDIT: [CallbackQueryHandler(received_edit_selection, pattern="^editacc_")],
        CHOOSE_EDIT_FIELD: [CallbackQueryHandler(received_edit_field, pattern="^editfield_")],
        GET_NEW_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_new_email)],
        GET_NEW_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_new_pin)],
    },
    fallbacks=[CommandHandler("cancel", cancel_edit_my_account)],
    allow_reentry=True
)

# --- Conversación: Importar Cuentas Propias (/importmyaccounts) ---

async def import_my_accounts_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para importar cuentas desde un backup."""
    user = update.effective_user
    user_id = user.id
    is_authorized = db.is_user_authorized(user_id)
    # Corregido: 'and' en lugar de '&&'
    is_admin = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)

    if not is_authorized or is_admin:
        await _send_or_edit_message(update, context, "⛔ Esta función es solo para usuarios autorizados.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    logger.info(f"User {user_id} iniciando conversación import_my_accounts.")
    message_text = (
        "📥 Ok, vamos a importar cuentas desde un archivo de backup (.txt).\n"
        "Por favor, envíame el archivo de texto que descargaste previamente.\n\n"
        "Puedes cancelar en cualquier momento con /cancel."
    )
    await _send_or_edit_message(update, context, message_text, None, schedule_delete=False) # No borrar este mensaje
    return GET_BACKUP_FILE

async def received_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el archivo de backup, lo parsea y pide confirmación."""
    user_id = update.effective_user.id
    document = update.message.document

    if not document or not document.file_name.lower().endswith('.txt'):
        await update.message.reply_text("❌ Por favor, envía un archivo de texto (.txt) válido.")
        return GET_BACKUP_FILE

    try:
        backup_file = await document.get_file()
        # Descargar a un archivo temporal en memoria (bytes)
        file_content_bytes = await backup_file.download_as_bytearray()
        file_content = file_content_bytes.decode('utf-8')

        # Parsear el contenido
        parsed_accounts = []
        current_account = {}
        # Regex más robustos para extraer datos
        service_re = re.compile(r"^\s*Servicio:\s*(.+)$", re.IGNORECASE)
        email_re = re.compile(r"^\s*Email:\s*(.+)$", re.IGNORECASE)
        profile_re = re.compile(r"^\s*Perfil:\s*(.+)$", re.IGNORECASE)
        pin_re = re.compile(r"^\s*PIN:\s*(.+)$", re.IGNORECASE)

        for line in file_content.splitlines():
            line = line.strip()
            if not line or line.startswith("Backup de Cuentas") or line.startswith("Fecha:") or line.startswith("="):
                continue

            service_match = service_re.match(line)
            email_match = email_re.match(line)
            profile_match = profile_re.match(line)
            pin_match = pin_re.match(line)

            if service_match:
                current_account['service'] = service_match.group(1).strip()
            elif email_match:
                current_account['email'] = email_match.group(1).strip()
            elif profile_match:
                current_account['profile_name'] = profile_match.group(1).strip()
            elif pin_match:
                current_account['pin'] = pin_match.group(1).strip()

            # Si tenemos todos los datos necesarios y encontramos la línea separadora o el final
            if all(k in current_account for k in ('service', 'email', 'profile_name', 'pin')) and (line.startswith("-") or line == ""):
                # Validar datos básicos (ej. email)
                if '@' in current_account['email'] and '.' in current_account['email'].split('@')[-1]:
                    parsed_accounts.append(current_account)
                else:
                    logger.warning(f"Cuenta omitida en importación por email inválido: {current_account}")
                current_account = {} # Reset para la siguiente cuenta

        # Añadir la última cuenta si no hubo separador al final
        if all(k in current_account for k in ('service', 'email', 'profile_name', 'pin')) and '@' in current_account['email']:
             parsed_accounts.append(current_account)

        if not parsed_accounts:
            await update.message.reply_text("❌ No se encontraron cuentas válidas en el archivo o el formato es incorrecto.", reply_markup=get_back_to_menu_keyboard())
            return ConversationHandler.END

        context.user_data['parsed_accounts'] = parsed_accounts
        logger.info(f"User {user_id} - Backup parseado: {len(parsed_accounts)} cuentas encontradas.")

        # Mostrar resumen y pedir confirmación
        summary_text = f"📄 Se encontraron {len(parsed_accounts)} cuentas en el archivo:\n\n"
        for i, acc in enumerate(parsed_accounts[:5]): # Mostrar las primeras 5 como ejemplo
            summary_text += f"- {db.escape_markdown(acc['service'])} ({db.escape_markdown(acc['profile_name'])})\n"
        if len(parsed_accounts) > 5:
            summary_text += "- ... y más.\n\n"
        summary_text += "¿Deseas importar/actualizar estas cuentas? Se establecerá una nueva validez de 30 días."

        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sí, importar", callback_data="import_confirm_yes")],
            [InlineKeyboardButton("❌ No, cancelar", callback_data="import_confirm_no")]
        ])

        await update.message.reply_text(summary_text, reply_markup=confirm_keyboard, parse_mode=ParseMode.MARKDOWN)
        return CONFIRM_IMPORT

    except Exception as e:
        logger.error(f"Error procesando archivo de backup para user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("❌ Ocurrió un error al leer o procesar el archivo. Asegúrate de que es el archivo correcto y está en formato UTF-8.", reply_markup=get_back_to_menu_keyboard())
        return ConversationHandler.END

async def confirm_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma o cancela la importación de las cuentas parseadas."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    confirmation = query.data
    parsed_accounts = context.user_data.get('parsed_accounts')

    if not parsed_accounts:
         logger.error(f"User {user_id} en confirm_import: Faltan parsed_accounts.")
         await query.edit_message_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
         context.user_data.clear()
         return ConversationHandler.END

    if confirmation == "import_confirm_yes":
        logger.info(f"User {user_id} confirma importar {len(parsed_accounts)} cuentas.")
        imported_count = 0
        failed_count = 0
        registration_ts = int(time.time())
        expiry_ts = registration_ts + (30 * 24 * 60 * 60) # Nueva validez de 30 días

        for acc in parsed_accounts:
            success = db.add_account_db(
                user_id=user_id,
                service=acc['service'],
                email=acc['email'],
                profile_name=acc['profile_name'],
                pin=acc['pin'],
                registration_ts=registration_ts,
                expiry_ts=expiry_ts
            )
            if success:
                imported_count += 1
            else:
                failed_count += 1

        confirmation_text = f"✅ Importación completada.\n" \
                            f"- Cuentas importadas/actualizadas: {imported_count}\n"
        if failed_count > 0:
             confirmation_text += f"- Cuentas fallidas (error interno o duplicado no actualizable): {failed_count}"

        await _send_or_edit_message(update, context, confirmation_text, get_back_to_menu_keyboard(), schedule_delete=True)

    else: # import_confirm_no
        logger.info(f"User {user_id} canceló la importación.")
        await _send_or_edit_message(update, context, "❌ Importación cancelada.", get_back_to_menu_keyboard(), schedule_delete=True)

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación de importar cuentas."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} canceló la conversación import_my_accounts.")
    await _send_or_edit_message(update, context, "Operación cancelada.", None, schedule_delete=True)
    context.user_data.clear()
    return ConversationHandler.END

importmyaccounts_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("importmyaccounts", import_my_accounts_start),
        CallbackQueryHandler(import_my_accounts_start, pattern=f"^{CALLBACK_IMPORT_MY_ACCOUNTS}$")
    ],
    states={
        GET_BACKUP_FILE: [MessageHandler(filters.Document.TXT, received_backup_file)],
        CONFIRM_IMPORT: [CallbackQueryHandler(confirm_import, pattern="^import_confirm_")],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_import),
        # Añadir un manejador para mensajes que no son el archivo esperado
        MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Por favor, envía el archivo .txt o usa /cancel.")),
    ],
    allow_reentry=True
)

# --- Fin Conversaciones ---

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja comandos desconocidos."""
    await update.message.reply_text("Lo siento, no entendí ese comando. Usa /start para ver el menú principal.")


