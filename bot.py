import logging
import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Importar módulos locales de handlers
import database as db
import user_handlers
import admin_handlers
import callback_handlers

# Importar conversaciones específicas para claridad
from user_handlers import (
    addmyaccount_conv_handler,
    deletemyaccount_conv_handler,
    editmyaccount_conv_handler,
    importmyaccounts_conv_handler
)
from admin_handlers import adduser_conv_handler, deleteuser_conv_handler

# Cargar variables de entorno
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID") # Leer como string primero

# Configurar logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG # Cambiado a DEBUG
)
# Opcional: Reducir verbosidad de httpx si es demasiado ruidoso en DEBUG
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

def main() -> None:
    """Configura e inicia el bot."""

    # Validar variables de entorno
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("Error: No se encontró el TELEGRAM_BOT_TOKEN en las variables de entorno.")
        return
    if not ADMIN_USER_ID_STR or not ADMIN_USER_ID_STR.isdigit():
         logger.critical("Error: No se encontró o es inválido el ADMIN_USER_ID en las variables de entorno.")
         return
    # ADMIN_USER_ID ya se carga en database.py y handlers.py

    # Inicializar la base de datos
    try:
        db.init_db()
    except Exception as e:
        logger.critical(f"No se pudo inicializar la base de datos: {e}. Abortando.")
        return

    # Crear la Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Agrupar Handlers ---

    user_command_handlers = [
        CommandHandler("start", user_handlers.start),
        CommandHandler("help", user_handlers.help_command),
        CommandHandler("status", user_handlers.status_command),
        CommandHandler("list", user_handlers.list_accounts),
        CommandHandler("get", user_handlers.get_account),
        CommandHandler("backupmyaccounts", user_handlers.backup_my_accounts),
        CommandHandler("importmyaccounts", user_handlers.import_my_accounts_start), # Entry point for conversation
    ]

    user_conversation_handlers = [
        addmyaccount_conv_handler,
        deletemyaccount_conv_handler,
        editmyaccount_conv_handler,
        importmyaccounts_conv_handler,
    ]

    admin_command_handlers = [
        CommandHandler("listusers", admin_handlers.list_users),
        CommandHandler("listallaccounts", admin_handlers.list_all_accounts), # <-- Descomentado
        # Nota: Los entry points de las conversaciones de admin también son CommandHandlers
        # pero se incluyen en el ConversationHandler mismo.
    ]

    admin_conversation_handlers = [
        adduser_conv_handler,
        deleteuser_conv_handler,
    ]

    # --- Registrar Handlers ---
    application.add_handlers(user_command_handlers)
    application.add_handlers(user_conversation_handlers)
    application.add_handlers(admin_command_handlers)
    application.add_handlers(admin_conversation_handlers)

    # Registrar otros handlers individuales
    application.add_handler(CallbackQueryHandler(callback_handlers.button_callback_handler))
    application.add_handler(MessageHandler(filters.COMMAND, user_handlers.unknown)) # Maneja comandos no reconocidos

    # Iniciar el Bot
    logger.info("Iniciando el bot...")
    application.run_polling()
    logger.info("Bot detenido.")

if __name__ == "__main__":
    main()
