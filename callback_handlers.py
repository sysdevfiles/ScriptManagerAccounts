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
    if not query or not query.data:
        logger.warning("Callback sin query o sin data recibido.")
        return

    await query.answer() # Responder al callback lo antes posible

    user_id = query.from_user.id
    callback_data = query.data
    logger.info(f"Callback recibido: '{callback_data}' de user_id: {user_id}")

    is_admin_user = (ADMIN_USER_ID is not None and user_id == ADMIN_USER_ID)
    # La autorización general se verifica dentro de cada handler si es necesario
    is_authorized_user = db.is_user_authorized(user_id)

    try:
        # --- Callback Común ---
        if callback_data == 'show_status':
            await user_handlers.status_command(update, context)
        elif callback_data == 'list_accounts':
             if is_authorized_user or is_admin_user: # Permitir al admin ver su propia lista si tuviera
                 await user_handlers.list_accounts(update, context)
             else:
                 await query.edit_message_text("⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())

        # --- Callbacks de Usuario (No Admin) ---
        elif callback_data == CALLBACK_ADD_MY_ACCOUNT:
            if is_authorized_user and not is_admin_user:
                await user_handlers.add_my_account_start(update, context)
            else:
                 await query.edit_message_text("⛔ Función no disponible.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_EDIT_MY_ACCOUNT:
             if is_authorized_user and not is_admin_user:
                 await user_handlers.edit_my_account_start(update, context)
             else:
                 await query.edit_message_text("⛔ Función no disponible.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_DELETE_MY_ACCOUNT:
             if is_authorized_user and not is_admin_user:
                 await user_handlers.delete_my_account_start(update, context)
             else:
                 await query.edit_message_text("⛔ Función no disponible.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_BACKUP_MY_ACCOUNTS:
             if is_authorized_user and not is_admin_user:
                 await user_handlers.backup_my_accounts(update, context)
             else:
                 await query.edit_message_text("⛔ Función no disponible.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_IMPORT_MY_ACCOUNTS:
            if is_authorized_user and not is_admin_user:
                await user_handlers.import_my_accounts_start(update, context)
            else:
                 await query.edit_message_text("⛔ Función no disponible.", reply_markup=get_back_to_menu_keyboard())

        # --- Callbacks de Admin ---
        elif callback_data == CALLBACK_ADMIN_LIST_USERS:
            if is_admin_user:
                try:
                    await admin_handlers.list_users(update, context)
                except Exception as e_admin:
                    logger.error(f"Error en admin_handlers.list_users (callback): {e_admin}", exc_info=True)
                    await query.edit_message_text("⚠️ Error al listar usuarios.", reply_markup=get_back_to_menu_keyboard())
            else: await query.edit_message_text("⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_ADMIN_ADD_USER_PROMPT:
            if is_admin_user:
                try:
                    await admin_handlers.add_user_start(update, context) # Inicia conversación adduser
                except Exception as e_admin:
                    logger.error(f"Error en admin_handlers.add_user_start (callback): {e_admin}", exc_info=True)
                    await query.edit_message_text("⚠️ Error al iniciar proceso de añadir usuario.", reply_markup=get_back_to_menu_keyboard())
            else: await query.edit_message_text("⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_ADMIN_EDIT_USER_PROMPT: # Editar Usuario
            if is_admin_user:
                try:
                    await admin_handlers.edit_user_start(update, context) # Inicia conversación edituser
                except Exception as e_admin:
                    logger.error(f"Error en admin_handlers.edit_user_start (callback): {e_admin}", exc_info=True)
                    await query.edit_message_text("⚠️ Error al iniciar proceso de editar usuario.", reply_markup=get_back_to_menu_keyboard())
            else: await query.edit_message_text("⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())
        elif callback_data == CALLBACK_ADMIN_DELETE_USER_START: # Eliminar Usuario
            if is_admin_user:
                try:
                    await admin_handlers.delete_user_start(update, context) # Inicia conversación deleteuser
                except Exception as e_admin:
                    logger.error(f"Error en admin_handlers.delete_user_start (callback): {e_admin}", exc_info=True)
                    await query.edit_message_text("⚠️ Error al iniciar proceso de eliminar usuario.", reply_markup=get_back_to_menu_keyboard())
            else: await query.edit_message_text("⛔ Acceso denegado.", reply_markup=get_back_to_menu_keyboard())

        # --- Volver al Menú ---
        elif callback_data == 'back_to_menu': # Usar la constante importada
            # await query.answer() # Ya se hizo al inicio
            # Reconstruir y mostrar el menú principal
            user_name = query.from_user.first_name
            welcome_message = f"¡Hola, {user_name}! 👋\n\nBienvenido al Gestor de Cuentas."
            if is_authorized_user or is_admin_user:
                 welcome_message += "\nPuedes usar los botones de abajo 👇 o escribir /help para ver los comandos."
            else:
                welcome_message += "\n⛔ Parece que no tienes acceso autorizado. Contacta al administrador."
            keyboard = user_handlers.get_main_menu_keyboard(is_admin_user, is_authorized_user)
            try:
                await query.edit_message_text(
                    text=welcome_message,
                    reply_markup=keyboard
                )
                logger.info(f"User {user_id} returned to main menu via button.")
            except BadRequest as e:
                if "message is not modified" in str(e).lower():
                    pass # Ignorar si el menú ya está mostrado
                else:
                    logger.error(f"Error editing message for back_to_menu callback: {e}")
                    # Podríamos intentar enviar un nuevo mensaje si la edición falla persistentemente
                    # await context.bot.send_message(chat_id=user_id, text=welcome_message, reply_markup=keyboard)

        else:
            # Si el callback no coincide con ninguno conocido Y NO es un callback de conversación
            # (los callbacks de conversación son manejados por ConversationHandler)
            # Podríamos asumir que es una acción ya procesada o desconocida.
            # Es difícil saber con certeza si un callback pertenece a una conversación activa
            # sin consultar context.user_data o context.chat_data, lo cual puede ser complejo aquí.
            # Por seguridad, mantenemos el mensaje genérico si no se maneja explícitamente.
            logger.warning(f"Callback '{callback_data}' no manejado explícitamente por button_callback_handler.")
            # Evitar editar si ya se respondió con error antes
            # await query.edit_message_text(text="Acción no reconocida o ya procesada.", reply_markup=get_back_to_menu_keyboard())
            # Simplemente no hacer nada si ya se respondió con answer()

    except BadRequest as e:
         # Capturar errores comunes de Telegram al intentar editar/responder
         if "message to edit not found" in str(e).lower():
             logger.warning(f"Error procesando callback '{callback_data}' para user {user_id}: Mensaje original no encontrado (probablemente borrado). {e}")
             # No intentar editar de nuevo, el query.answer() ya se envió.
         elif "message is not modified" in str(e).lower():
             logger.info(f"Callback '{callback_data}' para user {user_id}: Mensaje no modificado (ya estaba en ese estado).")
         else:
             logger.error(f"BadRequest procesando callback '{callback_data}' para user {user_id}: {e}", exc_info=True)
             # Intentar enviar un mensaje nuevo como último recurso si la edición falla catastróficamente
             try:
                 await context.bot.send_message(chat_id=user_id, text="⚠️ Ocurrió un error al procesar tu solicitud.", reply_markup=get_back_to_menu_keyboard())
             except Exception as send_error:
                 logger.error(f"Error enviando mensaje de error de callback a {user_id}: {send_error}")

    except Exception as e:
        logger.error(f"Error GENERAL procesando callback '{callback_data}' para user {user_id}: {e}", exc_info=True)
        try:
            # Intentar editar el mensaje original con un error genérico
            await query.edit_message_text(
                text="⚠️ Ocurrió un error al procesar tu solicitud.",
                reply_markup=get_back_to_menu_keyboard()
            )
        except BadRequest: # Si editar falla (ej. mensaje borrado)
            try:
                # Enviar un nuevo mensaje
                await context.bot.send_message(
                    chat_id=query.message.chat_id if query.message else user_id, # Usar chat_id del mensaje original si existe
                    text="⚠️ Ocurrió un error al procesar tu solicitud.",
                    reply_markup=get_back_to_menu_keyboard()
                )
            except Exception as send_error:
                logger.error(f"Error enviando mensaje de error de callback a {user_id}: {send_error}")

