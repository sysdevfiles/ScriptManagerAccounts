import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import os
from dotenv import load_dotenv
from telegram.constants import ParseMode # <--- AÑADIR ESTA LÍNEA

# Importar funciones de base de datos y handlers específicos
import database as db
import user_handlers
# Importar funciones específicas de admin_handlers que serán llamadas por botones
from admin_handlers import (
    list_users as admin_list_users_func,
    list_all_accounts as admin_list_all_accounts_func, # <-- DESCOMENTADO
    list_assignments as admin_list_assignments_func
    # Importa otras funciones si creas botones para ellas (add_user, add_account, etc.)
    # Nota: Para añadir/asignar, es mejor guiar al usuario con mensajes que usar botones directos aquí
)

# Cargar ADMIN_USER_ID para comprobaciones
load_dotenv()
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))

logger = logging.getLogger(__name__)

# --- Constantes para Callback Data ---
CALLBACK_LIST_ACCOUNTS = "list_accounts"
CALLBACK_GET_ACCOUNT_PROMPT = "get_account_prompt"
CALLBACK_SHOW_STATUS = "show_status"
CALLBACK_ADMIN_ADD_ACCOUNT = "admin_add_account"
CALLBACK_ADMIN_ADD_USER = "admin_add_user"
CALLBACK_ADMIN_LIST_USERS = "admin_list_users"
CALLBACK_SHOW_HELP = "show_help"
CALLBACK_BACK_TO_MENU = "back_to_menu" # Nuevo: Botón para volver al menú

# --- Funciones de Menú con Botones ---

def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
     """Genera un teclado con solo el botón de volver al menú."""
     keyboard = [[InlineKeyboardButton("⬅️ Volver al Menú", callback_data=CALLBACK_BACK_TO_MENU)]]
     return InlineKeyboardMarkup(keyboard)

# --- Manejador de Callback Query ---

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja las pulsaciones de los botones inline."""
    query = update.callback_query
    await query.answer() # Responder al callback

    callback_data = query.data
    user_id = query.from_user.id

    # Determinar si el usuario está autorizado (para mostrar el menú correcto después)
    is_authorized = db.is_user_authorized(user_id)

    # Comprobar si es admin directamente aquí para proteger las acciones
    is_admin_user = (user_handlers.ADMIN_USER_ID is not None and user_id == user_handlers.ADMIN_USER_ID)

    # Redirigir a las funciones correspondientes
    if callback_data == CALLBACK_LIST_ACCOUNTS:
        await user_handlers.list_accounts(update, context)
        # Añadir botón de volver al menú después de listar
        await query.message.reply_text("Acciones:", reply_markup=get_back_to_menu_keyboard(), quote=False)

    elif callback_data == CALLBACK_SHOW_STATUS:
        await user_handlers.status_command(update, context)
        # El status_command ya edita el mensaje, añadir botón de volver
        await query.message.reply_text("Acciones:", reply_markup=get_back_to_menu_keyboard(), quote=False)

    # Mensajes informativos para comandos admin
    elif callback_data == CALLBACK_ADMIN_ADD_ACCOUNT:
        if user_id == ADMIN_USER_ID:
            await query.edit_message_text(
                text="Usa el comando:\n`/add <servicio> <usuario> <contraseña>`",
                parse_mode='MarkdownV2',
                reply_markup=get_back_to_menu_keyboard() # Añadir botón volver
            )
        else:
            await query.edit_message_text(text="❌ Acción no permitida.", reply_markup=get_back_to_menu_keyboard())

    elif callback_data == CALLBACK_ADMIN_ADD_USER:
        if user_id == ADMIN_USER_ID:
            await query.edit_message_text(
                text="Usa el comando:\n`/adduser <user_id> <nombre> <días_activo>`",
                parse_mode='MarkdownV2',
                reply_markup=get_back_to_menu_keyboard() # Añadir botón volver
            )
        else:
            await query.edit_message_text(text="❌ Acción no permitida.", reply_markup=get_back_to_menu_keyboard())

    elif callback_data == CALLBACK_ADMIN_LIST_USERS:
         if user_id == ADMIN_USER_ID:
             from admin_handlers import list_users as admin_list_users_func
             await admin_list_users_func(update, context)
             # Añadir botón de volver al menú después de listar
             await query.message.reply_text("Acciones:", reply_markup=get_back_to_menu_keyboard(), quote=False)
         else:
             await query.edit_message_text(text="❌ Acción no permitida.", reply_markup=get_back_to_menu_keyboard())

    elif callback_data == CALLBACK_BACK_TO_MENU:
         # Volver a mostrar el menú principal editando el mensaje original del menú
         keyboard = user_handlers.get_main_menu_keyboard(user_id)
         await query.edit_message_text(
             "Menú Principal:",
             reply_markup=keyboard
         )

    # --- Nuevos Handlers para Admin ---
    elif callback_data == 'admin_list_all_accounts': # <-- INICIO BLOQUE DESCOMENTADO
         if is_admin_user:
             await admin_list_all_accounts_func(update, context) # Asumiendo que maneja query
         else:
             await query.edit_message_text(text="⛔ Acceso denegado.") # <-- FIN BLOQUE DESCOMENTADO
    elif callback_data == 'admin_list_assignments':
         if is_admin_user:
             await admin_list_assignments_func(update, context) # Asumiendo que maneja query
         else:
             await query.edit_message_text(text="⛔ Acceso denegado.")
    elif callback_data == 'admin_add_user_prompt':
         if is_admin_user:
             # Modificar mensaje guía
             await query.edit_message_text(
                 text="Usa el comando `/adduser` para iniciar el proceso interactivo de añadir/actualizar un usuario.\n\n"
                      "Opcionalmente, puedes usar `/adduser <ID_TELEGRAM> <NOMBRE> <DÍAS_ACCESO>` para hacerlo directamente.",
                 parse_mode=ParseMode.MARKDOWN,
                 reply_markup=get_back_to_menu_keyboard() # Añadir botón volver
            )
         else:
             await query.edit_message_text(text="⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
    elif callback_data == 'admin_add_account_prompt':
         if is_admin_user:
             # Enviar mensaje guía
             await query.edit_message_text(
                 text="➕ Para añadir un nuevo perfil, usa el comando `/add` para iniciar el proceso interactivo.",
                 parse_mode=ParseMode.MARKDOWN,
                 reply_markup=get_back_to_menu_keyboard()
             )
         else:
             await query.edit_message_text(text="⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())

    else:
        logger.warning(f"Callback data no reconocido: {callback_data}")
        try:
            await query.edit_message_text(text="Opción no reconocida.", reply_markup=get_back_to_menu_keyboard())
        except Exception as e:
             logger.error(f"Error al editar mensaje para callback no reconocido: {e}")

