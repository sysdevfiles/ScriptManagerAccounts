import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Importar funciones y constantes necesarias
import user_handlers
import admin_handlers
from utils import ADMIN_USER_ID, get_back_to_menu_keyboard
import database as db

# Importar constantes de callback data
from user_handlers import (
    CALLBACK_ADD_MY_ACCOUNT, CALLBACK_DELETE_MY_ACCOUNT, CALLBACK_EDIT_MY_ACCOUNT,
    CALLBACK_BACKUP_MY_ACCOUNTS, CALLBACK_IMPORT_MY_ACCOUNTS
)
# Importar constantes de admin
from admin_handlers import (
    CALLBACK_ADMIN_ADD_USER_PROMPT,
    CALLBACK_ADMIN_LIST_USERS,
    CALLBACK_ADMIN_EDIT_USER_PROMPT,
    CALLBACK_ADMIN_DELETE_USER_START
)

logger = logging.getLogger(__name__)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja las pulsaciones de los botones inline."""
    query = update.callback_query
    await query.answer() # Siempre responder al callback
    user_id = query.from_user.id
    callback_data = query.data

    logger.info(f"Button pressed: user_id={user_id}, data='{callback_data}'")

    # Obtener estado de autorización una vez
    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
    is_authorized_user = db.is_user_authorized(user_id)
    logger.debug(f"Authorization check in button_callback: is_admin={is_admin_user}, is_authorized={is_authorized_user}")

    # --- Manejo de Callbacks ---
    try:
        # --- Callbacks Comunes / Usuario ---
        if callback_data == 'show_status':
            await user_handlers.status_command(update, context)
        elif callback_data == 'list_accounts':
            # Solo usuarios autorizados no admin o admin pueden listar sus cuentas
            if is_authorized_user or is_admin_user:
                 await user_handlers.list_accounts(update, context)
            else: # Redundancia por si acaso, aunque get_main_menu no debería mostrarlo
                 await query.edit_message_text("⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_ADD_MY_ACCOUNT:
            # Solo usuarios autorizados NO admin
            if is_authorized_user and not is_admin_user:
                await user_handlers.add_my_account_start(update, context)
            else:
                 await query.edit_message_text("⛔ Función no disponible para administradores.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_EDIT_MY_ACCOUNT:
             # Solo usuarios autorizados NO admin
            if is_authorized_user and not is_admin_user:
                await user_handlers.edit_my_account_start(update, context)
            else:
                 await query.edit_message_text("⛔ Función no disponible para administradores.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_DELETE_MY_ACCOUNT:
             # Solo usuarios autorizados NO admin
            if is_authorized_user and not is_admin_user:
                await user_handlers.delete_my_account_start(update, context)
            else:
                 await query.edit_message_text("⛔ Función no disponible para administradores.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_BACKUP_MY_ACCOUNTS:
            # Solo usuarios autorizados NO admin
            if is_authorized_user and not is_admin_user:
                await user_handlers.backup_my_accounts(update, context)
            else:
                 await query.edit_message_text("⛔ Función no disponible para administradores.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_IMPORT_MY_ACCOUNTS:
             # Solo usuarios autorizados NO admin
            if is_authorized_user and not is_admin_user:
                await user_handlers.import_my_accounts_start(update, context)
            else:
                 await query.edit_message_text("⛔ Función no disponible para administradores.", reply_markup=get_back_to_menu_keyboard())

        # --- Callbacks de Admin ---
        elif callback_data == CALLBACK_ADMIN_LIST_USERS:
            if is_admin_user:
                await admin_handlers.list_users(update, context)
            else: await query.edit_message_text("⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_ADMIN_ADD_USER_PROMPT:
            if is_admin_user:
                await admin_handlers.add_user_start(update, context) # Inicia conversación adduser
            else: await query.edit_message_text("⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_ADMIN_EDIT_USER_PROMPT: # Editar Usuario
            if is_admin_user:
                await admin_handlers.edit_user_start(update, context) # Inicia conversación edituser
            else: await query.edit_message_text("⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_ADMIN_DELETE_USER_START: # Iniciar Borrar
            if is_admin_user:
                await admin_handlers.delete_user_start(update, context) # Inicia conversación deleteuser
            else: await query.edit_message_text("⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
        # Se elimina el handler para CALLBACK_ADMIN_LIST_ALL_ACCOUNTS

        # --- Callback para volver al menú ---
        elif callback_data == 'back_to_main_menu':
            # Re-generar y mostrar el menú principal usando la función actualizada
            keyboard = user_handlers.get_main_menu_keyboard(is_admin_user, is_authorized_user)
            try:
                await query.edit_message_text(
                    text="Menú Principal:",
                    reply_markup=keyboard
                )
            except BadRequest as e:
                 # Si el mensaje original fue borrado, enviar uno nuevo
                 if "message to edit not found" in str(e).lower():
                     logger.warning(f"No se pudo editar mensaje para back_to_main_menu (probablemente borrado), enviando nuevo: {e}")
                     await context.bot.send_message(
                         chat_id=query.message.chat_id,
                         text="Menú Principal:",
                         reply_markup=keyboard
                     )
                 else:
                     raise e # Re-lanzar otros errores

        else:
            logger.warning(f"Callback data '{callback_data}' no manejado explícitamente.")
            # Informar al usuario si el botón no hace nada esperado
            try:
                # Usar el teclado de volver al menú aquí también
                await query.edit_message_text(text="Acción no reconocida o ya procesada.", reply_markup=get_back_to_menu_keyboard())
            except BadRequest: pass # Ignorar si el mensaje ya fue borrado

    except Exception as e:
        logger.error(f"Error procesando callback '{callback_data}' para user {user_id}: {e}", exc_info=True)
        try:
            await query.edit_message_text(
                text="⚠️ Ocurrió un error al procesar tu solicitud.",
                reply_markup=get_back_to_menu_keyboard()
            )
        except BadRequest:
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="⚠️ Ocurrió un error al procesar tu solicitud.",
                    reply_markup=get_back_to_menu_keyboard()
                )
            except Exception as send_error:
                logger.error(f"Error enviando mensaje de error de callback a {user_id}: {send_error}")

