import logging
from datetime import datetime, timedelta
import time
import os
import tempfile
import re # Importar re para parseo
import sqlite3
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
from utils import ADMIN_USER_ID, get_back_to_menu_keyboard, delete_message_later, DELETE_DELAY_SECONDS, generic_cancel_conversation # Importar cancelador genérico

# Importar nuevas constantes de admin_handlers si es necesario (o definirlas aquí si se prefiere)
from admin_handlers import (
    CALLBACK_ADMIN_ADD_USER_PROMPT,
    CALLBACK_ADMIN_LIST_USERS,
    CALLBACK_ADMIN_EDIT_USER_PROMPT, # Nueva constante para editar
    CALLBACK_ADMIN_DELETE_USER_START # Nueva constante para iniciar eliminación
)

logger = logging.getLogger(__name__)

# --- Constantes y Estados para Conversaciones ---
# addmyaccount
CALLBACK_ADD_MY_ACCOUNT = "add_my_account"
# Renamed/Added states for multi-profile add
SELECT_SERVICE, GET_MY_EMAIL, ASK_PROFILE_COUNT, GET_PROFILE_DETAILS = range(10, 14)
# deletemyaccount
CALLBACK_DELETE_MY_ACCOUNT = "delete_my_account"
SELECT_ACCOUNT_TO_DELETE, CONFIRM_DELETE = range(14, 16)
# editmyaccount
CALLBACK_EDIT_MY_ACCOUNT = "edit_my_account"
# Renamed/Added states for editing profile name
SELECT_PROFILE_TO_EDIT, CHOOSE_EDIT_FIELD, GET_NEW_EMAIL, GET_NEW_PROFILE_NAME, GET_NEW_PIN = range(16, 21)
# Backup
CALLBACK_BACKUP_MY_ACCOUNTS = "backup_my_accounts"
# Import
CALLBACK_IMPORT_MY_ACCOUNTS = "import_my_accounts"
GET_BACKUP_FILE, CONFIRM_IMPORT = range(21, 23) # Adjusted range

# Lista de servicios predefinidos
STREAMING_SERVICES = ["Netflix", "HBO Max", "Spotify", "Disney Plus", "Paramount Plus", "Prime Video", "YouTube Premium", "Crunchyroll", "Otro"]

# --- Funciones de Teclados ---

def get_main_menu_keyboard(is_admin: bool, is_authorized: bool) -> InlineKeyboardMarkup:
    """Genera el teclado del menú principal según el rol y autorización."""
    keyboard = []
    # Opciones comunes si está autorizado o es admin
    if (is_authorized or is_admin):
        keyboard.extend([
            [InlineKeyboardButton("📊 Estado", callback_data='show_status')],
        ])
        # Opciones solo para usuarios normales autorizados
        if is_authorized and not is_admin:
             keyboard.append([InlineKeyboardButton("📋 Mis Cuentas", callback_data='list_accounts')]) # Mantener para usuarios normales
             keyboard.append([InlineKeyboardButton("➕ Añadir Mi Cuenta", callback_data=CALLBACK_ADD_MY_ACCOUNT)])
             keyboard.append([InlineKeyboardButton("✏️ Editar Mi Cuenta", callback_data=CALLBACK_EDIT_MY_ACCOUNT)])
             keyboard.append([InlineKeyboardButton("🗑️ Eliminar Mi Cuenta", callback_data=CALLBACK_DELETE_MY_ACCOUNT)])
             keyboard.append([InlineKeyboardButton("💾 Backup Mis Cuentas", callback_data=CALLBACK_BACKUP_MY_ACCOUNTS)])
             keyboard.append([InlineKeyboardButton("📥 Importar Backup", callback_data=CALLBACK_IMPORT_MY_ACCOUNTS)])

    # Opciones solo para Admin
    if is_admin:
        # Botones específicos para Admin
        keyboard.extend([
            [InlineKeyboardButton("🔑 Admin: Listar Usuarios", callback_data=CALLBACK_ADMIN_LIST_USERS)],
            [InlineKeyboardButton("👤 Admin: Añadir/Act. Usuario", callback_data=CALLBACK_ADMIN_ADD_USER_PROMPT)],
            [InlineKeyboardButton("✏️ Admin: Editar Usuario", callback_data=CALLBACK_ADMIN_EDIT_USER_PROMPT)], # Botón Editar (placeholder)
            [InlineKeyboardButton("🗑️ Admin: Eliminar Usuario", callback_data=CALLBACK_ADMIN_DELETE_USER_START)], # Botón Eliminar
            # El botón "Listar Todas Cuentas" se elimina
        ])

    # Si no hay botones (no autorizado y no admin), no añadir nada
    if not keyboard:
         return None

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
            # Comandos para usuarios autorizados (incluido admin)
            help_text += "\n*Comandos Autorizados:*\n"
            help_text += "`/list` - 📋 Muestra tus perfiles propios activos.\n"
            help_text += "`/get` - 🔑 Obtiene los detalles (PIN) de tus perfiles propios (privado).\n"

            # Comandos solo para usuarios autorizados NO admin
            if is_authorized and not is_admin_user:
                 help_text += "`/addmyaccount` - ➕ Añade un perfil propio (válido 30 días).\n"
                 help_text += "`/editmyaccount` - ✏️ Edita el Email o PIN de un perfil propio.\n"
                 help_text += "`/deletemyaccount` - 🗑️ Elimina un perfil propio.\n"
                 help_text += "`/backupmyaccounts` - 💾 Genera un backup de tus cuentas.\n"
                 help_text += "`/importmyaccounts` - 📥 Importa cuentas desde un backup.\n"

        if is_admin_user:
            help_text += "\n*Comandos de Administrador:*\n"
            help_text += "`/adduser` - 👤 Inicia el proceso para añadir/actualizar un usuario autorizado.\n"
            help_text += "`/listusers` - 🔑 Lista todos los usuarios autorizados.\n"
            help_text += "`/edituser` - ✏️ Inicia el proceso para editar el nombre o días de acceso de un usuario.\n" # Actualizado
            help_text += "`/deleteuser` - 🗑️ Inicia el proceso para eliminar un usuario autorizado.\n"
            # help_text += "`/listallaccounts` - 🧾 Lista todos los perfiles registrados (eliminado del menú).\n" # Comando eliminado del menú

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
        user_profiles = db.get_accounts_for_user(user_id)
        if not user_profiles:
            message = "ℹ️ No tienes perfiles propios activos."
        else:
            accounts_text_list = ["📋 *Tus Perfiles Activos:*"]
            for profile in user_profiles:
                expiry_date = datetime.fromtimestamp(profile['expiry_ts']).strftime('%d/%m/%Y') if profile.get('expiry_ts') else 'N/A'
                accounts_text_list.append(
                    f"🆔 `{profile.get('profile_id')}`: {db.escape_markdown(profile.get('service', 'N/A'))} "
                    f"(👤 {db.escape_markdown(profile.get('profile_name', 'N/A'))}) - 🗓️ Expira: {expiry_date}"
                )
            message = "\n".join(accounts_text_list)
            message += "\n\n_Usa los botones del menú para editar/eliminar por ID._\n_Usa /get para ver detalles completos (privado)._"

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
        user_profiles = db.get_accounts_for_user(user_id)
        if not user_profiles:
            await update.message.reply_text("ℹ️ No tienes perfiles propios activos para obtener detalles.")
            return

        details_text_list = ["🔑 *Detalles de tus Perfiles Activos:*"]
        for profile in user_profiles:
            expiry_date = datetime.fromtimestamp(profile['expiry_ts']).strftime('%d/%m/%Y') if profile.get('expiry_ts') else 'N/A'
            details_text_list.append(
                f"*{db.escape_markdown(profile.get('service', 'N/A'))}* (👤 {db.escape_markdown(profile.get('profile_name', 'N/A'))})\n"
                f"  🆔 Perfil ID: `{profile.get('profile_id')}`\n" # Añadir ID de perfil
                f"  📧 Email Cuenta: `{db.escape_markdown(profile.get('email', 'N/A'))}`\n"
                f"  🔑 PIN: `{db.escape_markdown(profile.get('pin', 'N/A'))}`\n"
                f"  🗓️ Expira: {expiry_date}"
            )
        message = "\n\n".join(details_text_list)

        confirmation_msg = None
        try:
            await context.bot.send_message(chat_id=user_id, text=message, parse_mode=ParseMode.MARKDOWN)
            if update.message and update.message.chat.type != 'private':
                 confirmation_msg = await update.message.reply_text("✅ Te he enviado los detalles por mensaje privado.")
            logger.info(f"🔑 Usuario {user_id} solicitó detalles con /get")
        except Exception as e:
            logger.error(f"Error enviando mensaje privado de /get a {user_id}: {e}", exc_info=True)
            confirmation_msg = await update.message.reply_text("⚠️ No pude enviarte los detalles por privado...")

        if command_message_id:
            try: await context.bot.delete_message(chat_id=chat_id, message_id=command_message_id)
            except Exception: pass
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

        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as temp_file:
            temp_file.write(backup_content)
            temp_file_path = temp_file.name
            file_name = f"backup_cuentas_{user_id}_{datetime.now().strftime('%Y%m%d')}.txt"

        logger.info(f"Archivo de backup temporal creado en: {temp_file_path}")

        try:
            with open(temp_file_path, 'rb') as file_to_send:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=InputFile(file_to_send, filename=file_name),
                    caption="📄 Aquí tienes el backup de tus cuentas activas.",
                    reply_markup=get_back_to_menu_keyboard()
                )
            logger.info(f"Backup enviado a user_id {user_id}.")
            if is_callback:
                 try:
                     await query.edit_message_text("Backup enviado. Revisa tus mensajes.", reply_markup=get_back_to_menu_keyboard())
                 except BadRequest: pass
        except Exception as send_error:
            logger.error(f"Error al enviar archivo de backup a {user_id}: {send_error}", exc_info=True)
            await _send_or_edit_message(update, context, "⚠️ Ocurrió un error al enviar el archivo de backup.", get_back_to_menu_keyboard())
        finally:
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
        await _send_or_edit_message(update, context, "⛔ Esta función es solo para usuarios autorizados.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    logger.info(f"User {user_id} iniciando conversación add_my_account.")

    buttons = []
    for service in STREAMING_SERVICES:
        buttons.append([InlineKeyboardButton(service, callback_data=f"service_{service}")])
    service_keyboard = InlineKeyboardMarkup(buttons)

    message_text = (
        "➕ Ok, vamos a añadir un perfil de cuenta.\n"
        "1️⃣ Por favor, selecciona el *Servicio* de la lista 👇:\n\n"
        "Puedes cancelar en cualquier momento con /cancel."
    )
    await _send_or_edit_message(update, context, message_text, service_keyboard, schedule_delete=False)

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
    """Recibe el email, pide la cantidad de perfiles y borra mensaje."""
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
    # Ask for profile count instead of profile name
    await update.message.reply_text(
        f"✔️ Servicio: {service}\n"
        f"📧 Email: {email}.\n"
        "🔢 ¿Cuántos perfiles quieres añadir para esta cuenta? (1-5)",
        parse_mode=ParseMode.MARKDOWN
    )
    return ASK_PROFILE_COUNT # New state

async def received_profile_count(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la cantidad de perfiles, valida y pide el primer nombre de perfil."""
    user_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    try:
        count_str = update.message.text.strip()
        count = int(count_str)
        if not 1 <= count <= 5:
            raise ValueError("Count out of range")

        context.user_data['profile_count'] = count
        context.user_data['current_profile_index'] = 1
        context.user_data['profiles_to_add'] = [] # Initialize list to store profile data
        logger.info(f"User {user_id} en add_my_account: Añadirá {count} perfiles.")

        try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        except Exception as e: logger.warning(f"No se pudo borrar mensaje (profile_count) {user_message_id}: {e}")

        await update.message.reply_text(f"👤 Introduce el *Nombre* para el Perfil 1:")
        return GET_PROFILE_DETAILS # State to get name and PIN iteratively

    except ValueError:
        await update.message.reply_text("🔢 Por favor, introduce un número entre 1 y 5.")
        return ASK_PROFILE_COUNT
    except Exception as e:
        logger.error(f"Error en received_profile_count para user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

async def received_profile_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre o PIN del perfil actual, pide el siguiente dato o finaliza."""
    user_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    current_index = context.user_data.get('current_profile_index', 1)
    total_count = context.user_data.get('profile_count', 0)
    profiles_list = context.user_data.get('profiles_to_add', [])

    # Determine if we are expecting a name or a PIN
    expecting_name = 'current_profile_name' not in context.user_data

    try:
        # Delete user's message (name or PIN)
        try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        except Exception as e: logger.warning(f"No se pudo borrar mensaje (profile_detail) {user_message_id}: {e}")

        if expecting_name:
            profile_name = update.message.text.strip()
            # Basic validation: check if name already exists in the list being added
            if any(p['name'] == profile_name for p in profiles_list):
                 await update.message.reply_text(f"⚠️ Ya has introducido un perfil con el nombre '{profile_name}'. Por favor, usa un nombre diferente para el Perfil {current_index}:")
                 return GET_PROFILE_DETAILS # Ask for name again
            context.user_data['current_profile_name'] = profile_name
            logger.info(f"User {user_id} en add_my_account: Recibido nombre '{profile_name}' para perfil {current_index}.")
            await update.message.reply_text(f"🔑 Introduce el *PIN* para el Perfil {current_index} ('{profile_name}'):")
            return GET_PROFILE_DETAILS # Stay in the same state to get PIN

        else: # Expecting PIN
            pin = update.message.text.strip()
            profile_name = context.user_data.pop('current_profile_name') # Get and remove current name
            logger.info(f"User {user_id} en add_my_account: Recibido PIN para perfil {current_index} ('{profile_name}').")

            # Store the completed profile
            profiles_list.append({'name': profile_name, 'pin': pin})
            context.user_data['profiles_to_add'] = profiles_list

            # Check if more profiles are needed
            if current_index < total_count:
                context.user_data['current_profile_index'] = current_index + 1
                await update.message.reply_text(f"👤 Introduce el *Nombre* para el Perfil {current_index + 1}:")
                return GET_PROFILE_DETAILS # Loop back to get next name
            else:
                # All profiles collected, finalize
                logger.info(f"User {user_id} en add_my_account: Todos los {total_count} perfiles recogidos.")
                service = context.user_data.get('my_service')
                email = context.user_data.get('my_email')

                if not all([service, email, profiles_list]):
                    logger.error(f"User {user_id} en add_my_account: Faltan datos al finalizar.")
                    await update.message.reply_text("¡Ups! Algo salió mal al recopilar datos. Por favor, empieza de nuevo con /addmyaccount.", reply_markup=get_back_to_menu_keyboard())
                    context.user_data.clear()
                    return ConversationHandler.END

                registration_ts = int(time.time())
                expiry_ts = registration_ts + (30 * 24 * 60 * 60)
                expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%d/%m/%Y')

                success = db.add_account_db(
                    user_id=user_id,
                    service=service,
                    email=email,
                    profiles=profiles_list, # Pass the collected list
                    registration_ts=registration_ts,
                    expiry_ts=expiry_ts
                )

                if success:
                    service_escaped = db.escape_markdown(service)
                    email_escaped = db.escape_markdown(email)
                    profiles_summary = "\n".join([f"  - {db.escape_markdown(p['name'])} (PIN: `{db.escape_markdown(p['pin'])})`" for p in profiles_list])
                    confirmation_text = (
                        f"✅ ¡Cuenta añadida/actualizada con {len(profiles_list)} perfiles!\n\n"
                        f"🔧 Servicio: {service_escaped}\n"
                        f"📧 Email Cuenta: {email_escaped}\n"
                        f"👤 Perfiles:\n{profiles_summary}\n"
                        f"🗓️ Válido hasta: *{expiry_date}*"
                    )
                else:
                    confirmation_text = "❌ Hubo un error al guardar la cuenta/perfiles. Verifica si la cuenta ya existe y alcanzaste el límite de 5 perfiles, o si hubo otro problema."

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
                logger.info(f"User {user_id} completó add_my_account para {service}. Resultado: {success}")
                context.user_data.clear()
                return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error en received_profile_details para user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error inesperado. Intenta de nuevo con /addmyaccount.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

# Replace the old addmyaccount_conv_handler definition
addmyaccount_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("addmyaccount", add_my_account_start),
        CallbackQueryHandler(add_my_account_start, pattern=f"^{CALLBACK_ADD_MY_ACCOUNT}$")
    ],
    states={
        SELECT_SERVICE: [CallbackQueryHandler(received_service_selection, pattern="^service_")],
        GET_MY_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_my_email)],
        ASK_PROFILE_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_profile_count)],
        GET_PROFILE_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_profile_details)],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: generic_cancel_conversation(u, c, "add_my_account"))],
    allow_reentry=True
)

# --- Conversación: Eliminar Cuenta Propia (/deletemyaccount) ---

async def delete_my_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para que un usuario elimine SU CUENTA PRINCIPAL (y perfiles asociados)."""
    user = update.effective_user
    user_id = user.id
    is_authorized = db.is_user_authorized(user_id)
    is_admin = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)

    if not is_authorized or is_admin:
        await _send_or_edit_message(update, context, "⛔ Esta función es solo para usuarios autorizados.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    logger.info(f"User {user_id} iniciando conversación delete_my_account.")
    user_profiles = db.get_accounts_for_user(user_id)

    if not user_profiles:
        await _send_or_edit_message(update, context, "ℹ️ No tienes perfiles propios activos para eliminar.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    accounts_to_delete = {}
    for profile in user_profiles:
        acc_id = profile['account_id']
        if acc_id not in accounts_to_delete:
            accounts_to_delete[acc_id] = {
                'service': profile['service'],
                'email': profile['email'],
                'profiles': []
            }
        accounts_to_delete[acc_id]['profiles'].append(profile['profile_name'])

    if not accounts_to_delete:
         await _send_or_edit_message(update, context, "ℹ️ No se encontraron cuentas principales para eliminar.", get_back_to_menu_keyboard())
         return ConversationHandler.END

    buttons = []
    for acc_id, acc_data in accounts_to_delete.items():
        profile_names = ", ".join(acc_data['profiles'])
        label = (f"🆔 Cuenta {acc_id}: {acc_data['service']} ({acc_data['email']})\n"
                 f"   └─ Perfiles: {profile_names[:50]}{'...' if len(profile_names) > 50 else ''}")
        buttons.append([InlineKeyboardButton(label, callback_data=f"delacc_{acc_id}")])

    message_text = ("🗑️ Selecciona la *cuenta principal* que deseas eliminar 👇:\n"
                    "(Esto eliminará la cuenta y *todos* sus perfiles asociados)\n\n"
                    "Puedes cancelar con /cancel.")
    accounts_keyboard = InlineKeyboardMarkup(buttons)

    await _send_or_edit_message(update, context, message_text, accounts_keyboard, schedule_delete=False)
    return SELECT_ACCOUNT_TO_DELETE

async def received_delete_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la selección de la CUENTA PRINCIPAL a eliminar, pide confirmación."""
    query = update.callback_query
    await query.answer()
    account_id_str = query.data.split("delacc_")[-1]
    user_id = query.from_user.id

    try:
        account_id = int(account_id_str)
        context.user_data['delete_account_id'] = account_id
        logger.info(f"User {user_id} en delete_my_account: Seleccionado ACCOUNT ID {account_id} para eliminar.")

        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sí, eliminar CUENTA y perfiles", callback_data="delete_confirm_yes")],
            [InlineKeyboardButton("❌ No, cancelar", callback_data="delete_confirm_no")]
        ])

        await query.edit_message_text(
            text=f"❓ ¿Estás seguro de que quieres eliminar la cuenta principal con ID `{account_id}` y *todos* sus perfiles asociados?\n"
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
    """Confirma o cancela la eliminación de la CUENTA PRINCIPAL."""
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
        logger.info(f"User {user_id} confirma eliminar CUENTA ID {account_id}.")
        success = db.delete_account_db(account_id=account_id, user_id=user_id)

        if success:
            confirmation_text = f"🗑️ ¡Cuenta principal ID `{account_id}` y sus perfiles asociados eliminados correctamente!"
        else:
            confirmation_text = f"❌ No se pudo eliminar la cuenta ID `{account_id}`. Puede que ya no exista o no te pertenezca."

        await _send_or_edit_message(update, context, confirmation_text, get_back_to_menu_keyboard(), schedule_delete=True)
    else:
        logger.info(f"User {user_id} canceló la eliminación de cuenta ID {account_id}.")
        await _send_or_edit_message(update, context, "❌ Eliminación cancelada.", get_back_to_menu_keyboard(), schedule_delete=True)

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
    fallbacks=[CommandHandler("cancel", lambda u, c: generic_cancel_conversation(u, c, "delete_my_account"))], # Usar cancelador genérico
    allow_reentry=True
)

# --- Conversación: Editar Cuenta Propia (/editmyaccount) ---

async def edit_my_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para que un usuario edite el Email de la cuenta o el PIN de un perfil."""
    user = update.effective_user
    user_id = user.id
    is_authorized = db.is_user_authorized(user_id)
    is_admin = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)

    if not is_authorized or is_admin:
        await _send_or_edit_message(update, context, "⛔ Esta función es solo para usuarios autorizados.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    logger.info(f"User {user_id} iniciando conversación edit_my_account.")
    user_profiles = db.get_accounts_for_user(user_id)

    if not user_profiles:
        await _send_or_edit_message(update, context, "ℹ️ No tienes perfiles propios activos para editar.", get_back_to_menu_keyboard())
        return ConversationHandler.END

    buttons = []
    for profile in user_profiles:
        label = f"🆔 Perfil {profile.get('profile_id')}: {profile.get('service', 'N/A')} ({profile.get('profile_name', 'N/A')})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"editprof_{profile.get('profile_id')}")])

    message_text = "✏️ Selecciona el *perfil* cuyo PIN deseas editar, o cuya cuenta principal deseas modificar (Email) 👇:\n\nPuedes cancelar con /cancel."
    profiles_keyboard = InlineKeyboardMarkup(buttons)

    await _send_or_edit_message(update, context, message_text, profiles_keyboard, schedule_delete=False)
    return SELECT_PROFILE_TO_EDIT

async def received_edit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la selección del PERFIL, pide qué campo editar (Email cuenta, Nombre perfil, PIN perfil)."""
    query = update.callback_query
    await query.answer()
    profile_id_str = query.data.split("editprof_")[-1]
    user_id = query.from_user.id

    try:
        profile_id = int(profile_id_str)
        context.user_data['edit_profile_id'] = profile_id
        logger.info(f"User {user_id} en edit_my_account: Seleccionado PROFILE ID {profile_id} para editar.")

        # Add "Nombre (Este Perfil)" option
        field_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📧 Email (Cuenta Principal)", callback_data="editfield_email")],
            [InlineKeyboardButton("👤 Nombre (Este Perfil)", callback_data="editfield_name")], # New option
            [InlineKeyboardButton("🔑 PIN (Este Perfil)", callback_data="editfield_pin")]
        ])

        await query.edit_message_text(
            text=f"✏️ Editando (Perfil ID `{profile_id}`).\n"
                 f"¿Qué deseas editar?",
            reply_markup=field_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return CHOOSE_EDIT_FIELD
    except ValueError:
        logger.error(f"Error al parsear profile_id para editar: {profile_id_str}")
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
    profile_id = context.user_data.get('edit_profile_id')

    if not profile_id:
        logger.error(f"User {user_id} en received_edit_field: Falta edit_profile_id.")
        await query.edit_message_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    logger.info(f"User {user_id} en edit_my_account (Profile ID {profile_id}): Seleccionado campo '{field_to_edit}'.")

    prompt_text = ""
    next_state = ConversationHandler.END

    if field_to_edit == "email":
        conn = sqlite3.connect(db.DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT account_id FROM account_profiles WHERE id = ?", (profile_id,))
        acc_id_row = cursor.fetchone()
        conn.close()
        if not acc_id_row:
             logger.error(f"No se encontró account_id para profile_id {profile_id} al intentar editar email.")
             await query.edit_message_text("❌ Error interno al buscar datos de la cuenta. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
             context.user_data.clear()
             return ConversationHandler.END
        account_id = acc_id_row[0]
        context.user_data['edit_account_id'] = account_id

        prompt_text = f"✏️ Editando Email de la cuenta principal (ID `{account_id}`) asociada al perfil `{profile_id}`.\n" \
                      f"Por favor, introduce el nuevo *Email* 📧:"
        next_state = GET_NEW_EMAIL
    elif field_to_edit == "name": # Handle new option
        prompt_text = f"✏️ Editando Nombre del perfil ID `{profile_id}`.\n" \
                      f"Por favor, introduce el nuevo *Nombre* 👤:"
        next_state = GET_NEW_PROFILE_NAME # New state
    elif field_to_edit == "pin":
        prompt_text = f"✏️ Editando PIN del perfil ID `{profile_id}`.\n" \
                      f"Por favor, introduce el nuevo *PIN* 🔑:"
        next_state = GET_NEW_PIN
    else:
        logger.error(f"Campo a editar no reconocido: {field_to_edit}")
        await query.edit_message_text("❌ Error interno. Campo no válido.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    await query.edit_message_text(
        text=prompt_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=None # Remove keyboard before asking for text input
    )
    return next_state

async def received_new_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nuevo email, lo guarda para la CUENTA PRINCIPAL y termina."""
    new_email = update.message.text.strip()
    user_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    account_id = context.user_data.get('edit_account_id')
    profile_id = context.user_data.get('edit_profile_id')

    if not account_id:
         logger.error(f"User {user_id} en received_new_email: Falta edit_account_id.")
         await update.message.reply_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
         context.user_data.clear()
         return ConversationHandler.END

    if '@' not in new_email or '.' not in new_email.split('@')[-1]:
        await update.message.reply_text("📧 Eso no parece un email válido. Intenta de nuevo.")
        return GET_NEW_EMAIL

    logger.info(f"User {user_id} en edit_my_account (Account ID {account_id}, Profile ID {profile_id}): Recibido nuevo email '{new_email}'.")

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e: logger.warning(f"No se pudo borrar mensaje (new_email) {user_message_id}: {e}")

    success = db.update_account_email_db(account_id=account_id, user_id=user_id, new_email=new_email)

    if success:
        confirmation_text = f"✅ ¡Email de la cuenta principal ID `{account_id}` actualizado correctamente!"
    else:
        confirmation_text = f"❌ No se pudo actualizar el email de la cuenta ID `{account_id}`. Verifica que la cuenta exista, te pertenezca y el nuevo email no esté en uso por otra cuenta tuya del mismo servicio."

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

async def received_new_profile_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nuevo nombre de perfil, lo guarda y termina."""
    new_name = update.message.text.strip()
    user_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    profile_id = context.user_data.get('edit_profile_id')
    if not profile_id:
         logger.error(f"User {user_id} en received_new_profile_name: Falta edit_profile_id.")
         await update.message.reply_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
         context.user_data.clear()
         return ConversationHandler.END

    if not new_name: # Basic validation
        await update.message.reply_text("👤 El nombre del perfil no puede estar vacío. Intenta de nuevo.")
        return GET_NEW_PROFILE_NAME

    logger.info(f"User {user_id} en edit_my_account (Profile ID {profile_id}): Recibido nuevo nombre '{new_name}'.")

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e: logger.warning(f"No se pudo borrar mensaje (new_name) {user_message_id}: {e}")

    # Call the new DB function
    success = db.update_profile_name_db(profile_id=profile_id, user_id=user_id, new_name=new_name)

    if success:
        confirmation_text = f"✅ ¡Nombre del perfil ID `{profile_id}` actualizado correctamente a '{db.escape_markdown(new_name)}'!"
    else:
        confirmation_text = f"❌ No se pudo actualizar el nombre del perfil ID `{profile_id}`. Verifica que el perfil exista, te pertenezca y el nuevo nombre no esté ya en uso en esta cuenta."

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
    """Recibe el nuevo PIN, lo guarda para el PERFIL ESPECÍFICO y termina."""
    new_pin = update.message.text.strip()
    user_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    profile_id = context.user_data.get('edit_profile_id')
    if not profile_id:
         logger.error(f"User {user_id} en received_new_pin: Falta edit_profile_id.")
         await update.message.reply_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
         context.user_data.clear()
         return ConversationHandler.END

    logger.info(f"User {user_id} en edit_my_account (Profile ID {profile_id}): Recibido nuevo PIN '{new_pin}'.")

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e: logger.warning(f"No se pudo borrar mensaje (new_pin) {user_message_id}: {e}")

    # Call the renamed DB function
    success = db.update_profile_pin_db(profile_id=profile_id, user_id=user_id, new_pin=new_pin)

    if success:
        confirmation_text = f"✅ ¡PIN del perfil ID `{profile_id}` actualizado correctamente!"
    else:
        confirmation_text = f"❌ No se pudo actualizar el PIN del perfil ID `{profile_id}`. Verifica que el perfil exista y te pertenezca."

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

# Replace the old editmyaccount_conv_handler definition
editmyaccount_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("editmyaccount", edit_my_account_start),
        CallbackQueryHandler(edit_my_account_start, pattern=f"^{CALLBACK_EDIT_MY_ACCOUNT}$")
    ],
    states={
        SELECT_PROFILE_TO_EDIT: [CallbackQueryHandler(received_edit_selection, pattern="^editprof_")],
        CHOOSE_EDIT_FIELD: [CallbackQueryHandler(received_edit_field, pattern="^editfield_")],
        GET_NEW_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_new_email)],
        GET_NEW_PROFILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_new_profile_name)], # New state handler
        GET_NEW_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_new_pin)],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: generic_cancel_conversation(u, c, "edit_my_account"))],
    allow_reentry=True
)

# --- Conversación: Importar Cuentas Propias (/importmyaccounts) ---

async def import_my_accounts_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para importar cuentas desde un backup."""
    user = update.effective_user
    user_id = user.id
    is_authorized = db.is_user_authorized(user_id)
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
    await _send_or_edit_message(update, context, message_text, None, schedule_delete=False)
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
        file_content_bytes = await backup_file.download_as_bytearray()
        file_content = file_content_bytes.decode('utf-8')

        parsed_accounts = []
        current_account = {}
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

            if all(k in current_account for k in ('service', 'email', 'profile_name', 'pin')) and (line.startswith("-") or line == ""):
                if '@' in current_account['email'] and '.' in current_account['email'].split('@')[-1]:
                    parsed_accounts.append(current_account)
                else:
                    logger.warning(f"Cuenta omitida en importación por email inválido: {current_account}")
                current_account = {}

        if all(k in current_account for k in ('service', 'email', 'profile_name', 'pin')) and '@' in current_account['email']:
             parsed_accounts.append(current_account)

        if not parsed_accounts:
            await update.message.reply_text("❌ No se encontraron cuentas válidas en el archivo o el formato es incorrecto.", reply_markup=get_back_to_menu_keyboard())
            return ConversationHandler.END

        context.user_data['parsed_accounts'] = parsed_accounts
        logger.info(f"User {user_id} - Backup parseado: {len(parsed_accounts)} cuentas encontradas.")

        summary_text = f"📄 Se encontraron {len(parsed_accounts)} cuentas en el archivo:\n\n"
        for i, acc in enumerate(parsed_accounts[:5]):
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
        expiry_ts = registration_ts + (30 * 24 * 60 * 60)

        accounts_to_import = {}
        for acc_data in parsed_accounts:
            key = (acc_data['service'], acc_data['email'])
            if key not in accounts_to_import:
                accounts_to_import[key] = {'service': acc_data['service'], 'email': acc_data['email'], 'profiles': []}
            accounts_to_import[key]['profiles'].append({'name': acc_data['profile_name'], 'pin': acc_data['pin']})

        for key, account_info in accounts_to_import.items():
            success = db.add_account_db(
                user_id=user_id,
                service=account_info['service'],
                email=account_info['email'],
                profiles=account_info['profiles'],
                registration_ts=registration_ts,
                expiry_ts=expiry_ts
            )
            if success:
                imported_count += 1
            else:
                failed_count += 1

        confirmation_text = f"✅ Importación completada.\n" \
                            f"- Cuentas principales importadas/actualizadas: {imported_count}\n"
        if failed_count > 0:
             confirmation_text += f"- Cuentas fallidas (error interno, límite de perfiles o duplicado no actualizable): {failed_count}"

        await _send_or_edit_message(update, context, confirmation_text, get_back_to_menu_keyboard(), schedule_delete=True)

    else:
        logger.info(f"User {user_id} canceló la importación.")
        await _send_or_edit_message(update, context, "❌ Importación cancelada.", get_back_to_menu_keyboard(), schedule_delete=True)

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
        CommandHandler("cancel", lambda u, c: generic_cancel_conversation(u, c, "import_my_accounts")), # Usar cancelador genérico
        MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Por favor, envía el archivo .txt o usa /cancel.")),
    ],
    allow_reentry=True
)

# --- Fin Conversaciones ---

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja comandos desconocidos."""
    await update.message.reply_text("Lo siento, no entendí ese comando. Usa /start para ver el menú principal.")


