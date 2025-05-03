import os
import logging
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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

# --- Funciones de Teclado Compartidas ---
def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
     """Genera un teclado con solo el botón de volver al menú."""
     keyboard = [[InlineKeyboardButton("⬅️ Volver al Menú", callback_data=CALLBACK_BACK_TO_MENU)]]
     return InlineKeyboardMarkup(keyboard)

# Podrías mover get_main_menu_keyboard aquí también si causa problemas
# def get_main_menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup: ...
