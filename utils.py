import os
import logging
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
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
DELETE_DELAY_SECONDS = 20 # Segundos para borrar mensajes de confirmación

# --- Funciones de Teclado Compartidas ---
def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
     """Genera un teclado con solo el botón de volver al menú."""
     keyboard = [[InlineKeyboardButton("⬅️ Volver al Menú", callback_data=CALLBACK_BACK_TO_MENU)]]
     return InlineKeyboardMarkup(keyboard)

# --- Función auxiliar para borrar mensajes ---
async def delete_message_later(context: ContextTypes.DEFAULT_TYPE):
    """Borra un mensaje específico después de un tiempo."""
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

# Podrías mover get_main_menu_keyboard aquí también si causa problemas
# def get_main_menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup: ...
