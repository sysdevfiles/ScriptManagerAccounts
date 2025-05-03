import os
import logging
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import BadRequest
from datetime import timedelta

logger = logging.getLogger(__name__)

# --- Cargar Variables de Entorno ---
load_dotenv()

# Cargar y verificar ADMIN_USER_ID centralizadamente
ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID")
ADMIN_USER_ID = None
if ADMIN_USER_ID_STR and ADMIN_USER_ID_STR.isdigit():
    ADMIN_USER_ID = int(ADMIN_USER_ID_STR)
    logger.info(f"ADMIN_USER_ID cargado correctamente desde utils.py: {ADMIN_USER_ID}")
else:
    # Usar logging.critical o lanzar una excepción si es fatal
    logger.critical("CRITICAL ERROR: ADMIN_USER_ID no encontrado o inválido en .env al cargar utils.py")
    # raise ValueError("ADMIN_USER_ID no está configurado correctamente en el archivo .env") # Alternativa

# --- Constantes de Callback Data (Opcional, podrían estar aquí o en callback_handlers) ---
CALLBACK_BACK_TO_MENU = "back_to_menu"

# --- Constantes de Tiempo ---
DELETE_DELAY_SECONDS = 15 # Ajustar según preferencia

# --- Funciones de Teclado ---
def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Devuelve un teclado inline con solo el botón 'Volver al Menú'."""
    keyboard = [[InlineKeyboardButton("⬅️ Volver al Menú", callback_data=CALLBACK_BACK_TO_MENU)]]
    return InlineKeyboardMarkup(keyboard)

# --- Funciones de Borrado de Mensajes ---
async def delete_message_later(context: ContextTypes.DEFAULT_TYPE):
    """Callback para borrar un mensaje específico."""
    job = context.job
    chat_id = job.data['chat_id']
    message_id = job.data['message_id']
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"🗑️ Mensaje {message_id} borrado automáticamente en chat {chat_id}.")
    except BadRequest as e:
        # Ignorar si el mensaje ya no existe o no se puede borrar
        if "Message to delete not found" in str(e) or "message can't be deleted" in str(e):
            logger.warning(f"⚠️ No se pudo borrar automáticamente el mensaje {message_id} en chat {chat_id}: {e}")
        else:
            logger.error(f"❌ Error inesperado al borrar automáticamente el mensaje {message_id} en chat {chat_id}: {e}")
    except Exception as e:
        logger.error(f"❌ Error general al borrar automáticamente el mensaje {message_id} en chat {chat_id}: {e}")

# --- Nueva Función Genérica de Cancelación ---
async def generic_cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, conversation_name: str) -> int:
    """Función genérica para cancelar una conversación."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} canceló la conversación '{conversation_name}'.")
    message_text = "Operación cancelada."

    # Intentar editar si es callback, si no, enviar respuesta
    if update.callback_query:
        try:
            # Editar mensaje para quitar botones y mostrar cancelación
            await update.callback_query.edit_message_text(message_text, reply_markup=None)
        except BadRequest as e:
            # Si no se puede editar (ej. mensaje muy viejo), enviar uno nuevo
            if "Message to edit not found" in str(e) or "message is not modified" not in str(e):
                 logger.warning(f"No se pudo editar mensaje al cancelar {conversation_name} para {user_id}: {e}. Enviando nuevo.")
                 try:
                     # Enviar mensaje simple sin teclado de respuesta
                     await context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=ReplyKeyboardRemove())
                 except Exception as send_error:
                     logger.error(f"Error enviando mensaje de cancelación a {user_id}: {send_error}")
            else:
                 logger.info(f"Mensaje no modificado al cancelar {conversation_name} para {user_id}.")

    elif update.message:
        # Si se canceló con /cancel, responder al comando
        await update.message.reply_text(message_text, reply_markup=ReplyKeyboardRemove())

    context.user_data.clear()
    return ConversationHandler.END
