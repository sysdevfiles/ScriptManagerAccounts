import logging
import os
from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Importar módulos locales de handlers
import database as db
import user_handlers
# Importar handlers específicos y conversaciones
import admin_handlers
from admin_handlers import adduser_conv_handler # Solo queda esta conversación de admin
# Importar nuevas conversaciones de usuario
from user_handlers import addmyaccount_conv_handler, deletemyaccount_conv_handler, editmyaccount_conv_handler, importmyaccounts_conv_handler
import callback_handlers

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

    # --- Registrar Handlers ---

    # Comandos/Conversaciones de Usuario (desde user_handlers.py)
    application.add_handler(CommandHandler("start", user_handlers.start))
    application.add_handler(CommandHandler("help", user_handlers.help_command))
    application.add_handler(CommandHandler("status", user_handlers.status_command))
    application.add_handler(CommandHandler("list", user_handlers.list_accounts))
    application.add_handler(CommandHandler("get", user_handlers.get_account))
    application.add_handler(CommandHandler("backupmyaccounts", user_handlers.backup_my_accounts)) # <-- Nuevo comando
    application.add_handler(CommandHandler("importmyaccounts", user_handlers.import_my_accounts_start)) # <-- Nuevo comando
    application.add_handler(addmyaccount_conv_handler) # Añadir nueva conversación de usuario
    application.add_handler(deletemyaccount_conv_handler) # Añadir handler de eliminar
    application.add_handler(editmyaccount_conv_handler) # Añadir handler de editar
    application.add_handler(importmyaccounts_conv_handler) # <-- Nueva conversación

    # Comandos/Conversaciones de Admin (desde admin_handlers.py)
    application.add_handler(adduser_conv_handler)
    application.add_handler(CommandHandler("listusers", admin_handlers.list_users))
    application.add_handler(CommandHandler("listallaccounts", admin_handlers.list_all_accounts))
    # ELIMINAR handlers obsoletos de admin
    # application.add_handler(add_account_conv_handler)
    # application.add_handler(assign_account_conv_handler)
    # application.add_handler(CommandHandler("listassignments", admin_handlers.list_assignments))

    # Callback Handler (desde callback_handlers.py)
    application.add_handler(CallbackQueryHandler(callback_handlers.button_callback_handler))

    # Manejador para comandos desconocidos (desde user_handlers.py)
    application.add_handler(MessageHandler(filters.COMMAND, user_handlers.unknown))

    # Iniciar el Bot
    logger.info("Iniciando el bot...")
    application.run_polling()
    logger.info("Bot detenido.")

if __name__ == "__main__":
    main()
