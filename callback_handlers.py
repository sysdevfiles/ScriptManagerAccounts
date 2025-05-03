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
    # Necesitamos saber si está autorizado para el menú de vuelta
    is_authorized = db.is_user_authorized(user_id)

    # --- Handlers de Usuario ---
    if callback_data == CALLBACK_SHOW_STATUS:
        await user_handlers.status_command(update, context)
    elif callback_data == CALLBACK_LIST_ACCOUNTS:
        await user_handlers.list_accounts(update, context)
    # --- Nuevo Handler para Botón de Usuario ---
    elif callback_data == CALLBACK_ADD_MY_ACCOUNT:
        if is_authorized and not is_admin_user:
             # Iniciar la conversación desde user_handlers
             # Necesitamos simular un mensaje para iniciar ConversationHandler desde CallbackQuery
             # O modificar ConversationHandler para aceptar CallbackQueryHandler en entry_points (ya hecho)
             # await add_my_account_start(update, context) # Llamar directamente debería funcionar si entry_points lo maneja
             # No es necesario llamar explícitamente si el entry_point del ConversationHandler ya lo captura
             logger.info(f"Callback {CALLBACK_ADD_MY_ACCOUNT} recibido, dejando que ConversationHandler lo tome.")
             # Podríamos editar el mensaje para confirmar inicio si el CH no lo hace
             try:
                 await query.edit_message_text("➕ Iniciando proceso para añadir cuenta...", reply_markup=None)
             except BadRequest: pass # Ignorar si no se puede editar
        else:
             try: await query.edit_message_text(text="⛔ Acción no permitida.", reply_markup=get_back_to_menu_keyboard())
             except BadRequest: pass
    # --- Nuevos Handlers para Botones de Usuario ---
    elif callback_data == CALLBACK_EDIT_MY_ACCOUNT:
        if is_authorized and not is_admin_user:
             logger.info(f"Callback {CALLBACK_EDIT_MY_ACCOUNT} recibido, dejando que ConversationHandler lo tome.")
             try: await query.edit_message_text("✏️ Iniciando proceso para editar cuenta...", reply_markup=None)
             except BadRequest: pass
        else:
             try: await query.edit_message_text(text="⛔ Acción no permitida.", reply_markup=get_back_to_menu_keyboard())
             except BadRequest: pass
    elif callback_data == CALLBACK_DELETE_MY_ACCOUNT:
        if is_authorized and not is_admin_user:
             logger.info(f"Callback {CALLBACK_DELETE_MY_ACCOUNT} recibido, dejando que ConversationHandler lo tome.")
             try: await query.edit_message_text("🗑️ Iniciando proceso para eliminar cuenta...", reply_markup=None)
             except BadRequest: pass
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

