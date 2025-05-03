import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import os
from dotenv import load_dotenv
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Importar funciones de base de datos y handlers específicos
import database as db
import user_handlers
from user_handlers import ADMIN_USER_ID # Importar ADMIN_ID
# Importar funciones de admin que aún se usan
from admin_handlers import (
    list_users as admin_list_users_func,
    list_all_accounts as admin_list_all_accounts_func,
)
# Importar función de inicio de conversación de usuario
from user_handlers import add_my_account_start # Importar inicio de conversación

logger = logging.getLogger(__name__)

# --- Constantes para Callback Data ---
CALLBACK_LIST_ACCOUNTS = "list_accounts"
CALLBACK_SHOW_STATUS = "show_status"
CALLBACK_BACK_TO_MENU = "back_to_menu"
# Nueva constante para el botón de usuario
CALLBACK_ADD_MY_ACCOUNT = "add_my_account"
CALLBACK_EDIT_MY_ACCOUNT = "edit_my_account" # Nueva constante
CALLBACK_DELETE_MY_ACCOUNT = "delete_my_account" # Nueva constante
CALLBACK_BACKUP_MY_ACCOUNTS = "backup_my_accounts" # Nueva constante
CALLBACK_IMPORT_MY_ACCOUNTS = "import_my_accounts" # Nueva constante

# --- Funciones de Menú con Botones ---
def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
     """Genera un teclado con solo el botón de volver al menú."""
     keyboard = [[InlineKeyboardButton("⬅️ Volver al Menú", callback_data=CALLBACK_BACK_TO_MENU)]]
     return InlineKeyboardMarkup(keyboard)

# --- Manejador de Callback Query ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja las pulsaciones de los botones inline."""
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    user_id = query.from_user.id

    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
    is_authorized = db.is_user_authorized(user_id)

    # --- Handlers de Usuario ---
    if callback_data == CALLBACK_SHOW_STATUS:
        await user_handlers.status_command(update, context)
    elif callback_data == CALLBACK_LIST_ACCOUNTS:
        await user_handlers.list_accounts(update, context)
    # --- Simplificar Handlers para Botones de Conversación de Usuario ---
    elif callback_data == CALLBACK_ADD_MY_ACCOUNT:
        if is_authorized and not is_admin_user:
             # No hacer nada aquí, dejar que el ConversationHandler lo capture
             logger.debug(f"Callback {CALLBACK_ADD_MY_ACCOUNT} recibido, dejando que ConversationHandler lo tome.")
        else:
             # Mantener el manejo de acceso denegado
             try: await query.edit_message_text(text="⛔ Acción no permitida.", reply_markup=get_back_to_menu_keyboard())
             except BadRequest: pass
    elif callback_data == CALLBACK_EDIT_MY_ACCOUNT:
        if is_authorized and not is_admin_user:
             logger.debug(f"Callback {CALLBACK_EDIT_MY_ACCOUNT} recibido, dejando que ConversationHandler lo tome.")
        else:
             try: await query.edit_message_text(text="⛔ Acción no permitida.", reply_markup=get_back_to_menu_keyboard())
             except BadRequest: pass
    elif callback_data == CALLBACK_DELETE_MY_ACCOUNT:
        if is_authorized and not is_admin_user:
             logger.debug(f"Callback {CALLBACK_DELETE_MY_ACCOUNT} recibido, dejando que ConversationHandler lo tome.")
        else:
             try: await query.edit_message_text(text="⛔ Acción no permitida.", reply_markup=get_back_to_menu_keyboard())
             except BadRequest: pass
    # --- Nuevo Handler para Botón de Backup ---
    elif callback_data == CALLBACK_BACKUP_MY_ACCOUNTS:
        if is_authorized and not is_admin_user:
             await user_handlers.backup_my_accounts(update, context)
        else:
             try: await query.edit_message_text(text="⛔ Acción no permitida.", reply_markup=get_back_to_menu_keyboard())
             except BadRequest: pass
    # --- Nuevo Handler para Botón de Importar ---
    elif callback_data == CALLBACK_IMPORT_MY_ACCOUNTS:
        if is_authorized and not is_admin_user:
             logger.debug(f"Callback {CALLBACK_IMPORT_MY_ACCOUNTS} recibido, dejando que ConversationHandler lo tome.")
             # No hacer nada aquí, dejar que el ConversationHandler lo capture
        else:
             try: await query.edit_message_text(text="⛔ Acción no permitida.", reply_markup=get_back_to_menu_keyboard())
             except BadRequest: pass

    # --- Handlers de Botones Admin ---
    elif callback_data == 'admin_list_users':
         if is_admin_user:
             await admin_list_users_func(update, context) # Llama a la función de listado
         else:
             # Borrar mensaje de confirmación anterior si existe y mostrar error
             try: await query.edit_message_text(text="⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
             except BadRequest: pass # Ignorar si no se puede editar

    elif callback_data == 'admin_list_all_accounts':
         if is_admin_user:
             await admin_list_all_accounts_func(update, context)
         else:
             try: await query.edit_message_text(text="⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
             except BadRequest: pass

    elif callback_data == 'admin_add_user_prompt':
         if is_admin_user:
             # Borrar mensaje anterior y mostrar prompt
             try:
                 await query.edit_message_text(
                     text="👤 Para añadir/actualizar un usuario, usa el comando `/adduser` para iniciar el proceso interactivo.",
                     parse_mode=ParseMode.MARKDOWN,
                     reply_markup=get_back_to_menu_keyboard()
                 )
             except BadRequest: pass # Ignorar si no se puede editar
         else:
             try: await query.edit_message_text(text="⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
             except BadRequest: pass

    # --- Handler para Volver al Menú ---
    elif callback_data == CALLBACK_BACK_TO_MENU:
         # Volver a mostrar el menú principal editando el mensaje original del menú
         # *** CORRECCIÓN: Usar is_admin_user y is_authorized ***
         keyboard = user_handlers.get_main_menu_keyboard(is_admin_user, is_authorized) # Pasar ambos flags
         try:
             await query.edit_message_text(
                 "⬅️ Menú Principal:",
                 reply_markup=keyboard
             )
             logger.info(f"Usuario {user_id} volvió al menú principal (Admin: {is_admin_user}, Auth: {is_authorized}).")
         except BadRequest as e:
             if "Message is not modified" in str(e):
                 logger.info("Intento de volver al menú sin cambios necesarios.")
             else:
                 logger.error(f"Error al editar mensaje para volver al menú: {e}")
                 # Si falla la edición, intentar enviar uno nuevo (puede pasar si el mensaje original fue borrado)
                 try:
                     await context.bot.send_message(chat_id=user_id, text="⬅️ Menú Principal:", reply_markup=keyboard)
                 except Exception as send_error:
                     logger.error(f"Fallo al enviar nuevo menú principal a {user_id}: {send_error}")

    else:
        logger.warning(f"Callback data no reconocido: {callback_data}")
        try:
            await query.edit_message_text(text="Opción no reconocida.", reply_markup=get_back_to_menu_keyboard())
        except Exception as e:
             logger.error(f"Error al editar mensaje para callback no reconocido: {e}")

