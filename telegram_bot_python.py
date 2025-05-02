import logging
import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
# Import escape_markdown
from telegram.helpers import escape_markdown
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputFile
# Completed the import block for telegram.ext
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
    JobQueue,
)

# --- Configuration ---
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, 'config.env')
DATA_FILE = os.path.join(SCRIPT_DIR, 'streaming_accounts.json')
REG_DATA_FILE = os.path.join(SCRIPT_DIR, 'registrations.json')
# Load environment variables from .env file
load_dotenv(CONFIG_FILE)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID')) # Ensure it's an integer
ACTIVATION_DATE = os.getenv('ACTIVATION_DATE')
EXPIRATION_DATE = os.getenv('EXPIRATION_DATE')

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Data Loading/Saving Functions (Basic) ---
def load_data(filepath):
    """Loads JSON data from a file."""
    try:
        if not os.path.exists(filepath):
            # Create default structure if file doesn't exist
            if 'accounts' in filepath:
                return {"accounts": []}
            elif 'registrations' in filepath:
                return {"registrations": []}
            else:
                return {}
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"Error loading data from {filepath}: {e}")
        # Return default structure on error
        if 'accounts' in filepath:
            return {"accounts": []}
        elif 'registrations' in filepath:
            return {"registrations": []}
        else:
            return {}


def save_data(filepath, data):
    """Saves data to a JSON file."""
    try:
        # Create temporary file path
        tmp_filepath = filepath + '.tmp'
        with open(tmp_filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Atomic rename
        os.replace(tmp_filepath, filepath)
        logger.info(f"Data saved successfully to {filepath}")
        return True
    except Exception as e:
        logger.error(f"Error saving data to {filepath}: {e}")
        # Attempt to remove temporary file if it exists
        if os.path.exists(tmp_filepath):
            try:
                os.remove(tmp_filepath)
            except OSError as rm_e:
                logger.error(f"Error removing temporary file {tmp_filepath}: {rm_e}")
        return False

# --- Security Decorator ---
from functools import wraps

def restricted(func):
    """Restrict usage of func to the admin chat ID."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id # Use chat_id for group compatibility if needed
        if chat_id != ADMIN_CHAT_ID:
            logger.warning(f"Unauthorized access denied for {user_id} in chat {chat_id}.")
            await update.message.reply_text("No estás autorizado para usar este comando.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def callback_restricted(func):
    """Restrict usage of callback func to the admin chat ID."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        query = update.callback_query
        user_id = query.from_user.id
        chat_id = query.message.chat.id
        if chat_id != ADMIN_CHAT_ID:
            logger.warning(f"Unauthorized callback access denied for {user_id} in chat {chat_id}.")
            await query.answer("No estás autorizado.", show_alert=True)
            return
        # Answer the query first before processing
        await query.answer()
        return await func(update, context, *args, **kwargs)
    return wrapped


# --- Helper Functions ---
def format_accounts_list(accounts_data):
    """Formats the list of accounts for display."""
    if not accounts_data or not accounts_data.get("accounts"):
        return "No se encontraron cuentas\\."
    output = "--- Cuentas ---\n```\n"
    for i, account in enumerate(accounts_data["accounts"]):
        service = account.get('service', 'N/A')
        username = account.get('username', 'N/A')
        # Escape potential markdown characters in service/username if needed, though unlikely here
        output += f"{i + 1}. {service} - {username}\n"
    output += "```"
    return output

def format_registrations_list(reg_data):
    """Formats the list of registrations for display."""
    if not reg_data or not reg_data.get("registrations"):
        return "No se encontraron registros de usuarios\\."
    output = "--- Registros de Usuarios ---\n```\n"
    for i, reg in enumerate(reg_data["registrations"]):
        # Escape user-provided data before including it
        name = escape_markdown(reg.get('name', 'N/A'), version=2)
        platform = escape_markdown(reg.get('platform', 'N/A'), version=2)
        end_date = escape_markdown(reg.get('end_date', 'N/A'), version=2)
        # Escape the literal '(' and ')' just in case, although ``` should handle it
        output += f"{i + 1}. {name} \\({platform}\\) - Vence: {end_date}\n"
    output += "```"
    return output

# --- Main Menu ---
async def send_main_menu(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Sends the main menu with inline buttons."""
    keyboard = [
        [InlineKeyboardButton("📊 Listar Cuentas", callback_data='list_accounts'),
         InlineKeyboardButton("📄 Ver Cuenta", callback_data='view_account_prompt')],
        [InlineKeyboardButton("➕ Añadir Cuenta", callback_data='add_account_prompt'),
         InlineKeyboardButton("✏️ Editar Cuenta", callback_data='edit_account_prompt'),
         InlineKeyboardButton("🗑️ Eliminar Cuenta", callback_data='delete_account_prompt')],
        [InlineKeyboardButton("👤 Registrar Usuario", callback_data='register_user_start'), # Changed callback_data
         InlineKeyboardButton("👥 Listar Registros", callback_data='list_regs'),
         InlineKeyboardButton("❌ Borrar Registro", callback_data='delete_reg_prompt')],
        [InlineKeyboardButton("💾 Backup", callback_data='backup_data'),
         InlineKeyboardButton("❓ Ayuda", callback_data='show_help'),
         InlineKeyboardButton("🔒 Licencia", callback_data='license_status')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=chat_id, text="*Menú Principal*\nElige una opción:", reply_markup=reply_markup, parse_mode='MarkdownV2')

@restricted
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /menu command."""
    await send_main_menu(update.effective_chat.id, context)

@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await help_command(update, context) # Redirect /start to /help

# --- Help Command ---
@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a help message."""
    # Determine if called from button (update.message is None) or command
    effective_update = update.callback_query if update.callback_query else update

    help_text = (
        "Usa `/menu` para ver los botones\\. \n\n"
        "*Gestión de Cuentas Streaming*\n"
        "*   📊 Listar:* Muestra la lista de cuentas\\.\n"
        "*   📄 Ver:* Inicia proceso para ver detalles de una cuenta\\.\n" # Updated
        "*   ➕ Añadir:* Inicia proceso para añadir una cuenta nueva\\.\n" # Updated
        "*   ✏️ Editar:* Inicia proceso para editar una cuenta\\.\n" # Updated
        "*   🗑️ Eliminar:* Inicia proceso para eliminar una cuenta\\.\n\n" # Updated
        "*Gestión de Registros de Usuarios*\n"
        "*   👤 Registrar:* Inicia el proceso de registro paso a paso\\.\n"
        "*   👥 Listar:* Muestra la lista de registros\\.\n"
        "*   ❌ Borrar:* Inicia proceso para borrar un registro\\.\n\n" # Updated
        "*Utilidades y Admin*\n"
        "*   💾 Backup:* Envía los archivos de datos `streaming_accounts\\.json` y `registrations\\.json`\\.\n"
        "*   ❓ Ayuda:* Muestra esta ayuda\\.\n"
        "*   🔒 Licencia:* Muestra el estado de la licencia\\.\n\n"
        "*Comandos Adicionales (Texto)*\n"
        "`/cancel` \\- Cancela la operación actual (Añadir/Editar/etc\\.)\\.\n" # Added cancel command
        "`/licencia_expira YYYY-MM-DD` \\- Cambia la fecha de expiración\\.\n"
        "`/listreg` \\- Alias para listar registros\\.\n"
        "`/delreg Numero` \\- Alias para borrar registro (no interactivo)\\.\n" # Clarified non-interactive alias
        "`/list` \\- Alias para listar cuentas\\.\n"
        "`/view Numero` \\- Alias para ver cuenta (no interactivo)\\.\n"
        "`/delete Numero` \\- Alias para borrar cuenta (no interactivo)\\.\n"
        # Add /add and /edit aliases if needed, but they are complex without conversation
    )
    # Use reply_text for commands, edit_message_text for callbacks
    if update.callback_query:
        await effective_update.edit_message_text(help_text, parse_mode='MarkdownV2')
        # Send main menu again after showing help from button
        await send_main_menu(effective_update.message.chat.id, context)
    else:
        await effective_update.message.reply_text(help_text, parse_mode='MarkdownV2')


# --- Registration Conversation ---
# Define states
PLATFORM, NAME, PHONE, PAYMENT_TYPE, EMAIL, PIN, START_DATE, END_DATE = range(8)

# Store conversation data
user_data = {}

@callback_restricted
async def register_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the registration conversation."""
    query = update.callback_query
    chat_id = query.message.chat.id
    user_data[chat_id] = {} # Initialize data for this chat
    await query.edit_message_text("📝 Iniciando proceso de registro de nuevo usuario...") # Edit the menu message
    await context.bot.send_message(chat_id=chat_id, text="1/8: 📺 Por favor, indica la plataforma de streaming:")
    return PLATFORM

async def ask_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the platform and asks for the name."""
    chat_id = update.message.chat.id
    user_data[chat_id]['platform'] = update.message.text
    await update.message.reply_text("2/8: 👤 Ingresa el nombre completo del usuario:")
    return NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the name and asks for the phone number."""
    chat_id = update.message.chat.id
    user_data[chat_id]['name'] = update.message.text
    await update.message.reply_text("3/8: 📱 ¿Cuál es el número de celular del usuario?")
    return PHONE

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the phone number and asks for payment type."""
    chat_id = update.message.chat.id
    user_data[chat_id]['phone'] = update.message.text
    await update.message.reply_text("4/8: 💳 Indica el tipo de pago realizado:")
    return PAYMENT_TYPE

async def ask_payment_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the payment type and asks for email."""
    chat_id = update.message.chat.id
    user_data[chat_id]['payment_type'] = update.message.text
    await update.message.reply_text("5/8: 📧 Ingresa la dirección de correo electrónico del usuario:")
    return EMAIL

async def ask_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the email and asks for PIN."""
    chat_id = update.message.chat.id
    user_data[chat_id]['email'] = update.message.text
    await update.message.reply_text("6/8: 🔢 ¿Cuál es el PIN de la cuenta? (Escribe 'N/A' si no aplica)")
    return PIN

async def ask_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the PIN and asks for the start date."""
    chat_id = update.message.chat.id
    user_data[chat_id]['pin'] = update.message.text
    await update.message.reply_text("7/8: 📅 Ingresa la fecha de alta del servicio (Formato: YYYY-MM-DD):")
    return START_DATE

async def ask_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the start date and asks for the end date."""
    chat_id = update.message.chat.id
    # Basic date validation could be added here
    user_data[chat_id]['start_date'] = update.message.text
    await update.message.reply_text("8/8: ⏳ Ingresa la fecha de vencimiento del servicio (Formato: YYYY-MM-DD):")
    return END_DATE

async def ask_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the end date, saves the registration, and ends the conversation."""
    chat_id = update.message.chat.id
    user_data[chat_id]['end_date'] = update.message.text

    # --- Save the data ---
    registrations = load_data(REG_DATA_FILE)
    new_registration = {
        "platform": user_data[chat_id].get('platform', 'N/A'),
        "name": user_data[chat_id].get('name', 'N/A'),
        "phone": user_data[chat_id].get('phone', 'N/A'),
        "payment_type": user_data[chat_id].get('payment_type', 'N/A'),
        "email": user_data[chat_id].get('email', 'N/A'),
        "pin": user_data[chat_id].get('pin', 'N/A'),
        "start_date": user_data[chat_id].get('start_date', 'N/A'),
        "end_date": user_data[chat_id].get('end_date', 'N/A'),
    }
    registrations['registrations'].append(new_registration)

    if save_data(REG_DATA_FILE, registrations):
        # More professional confirmation
        name_escaped = escape_markdown(new_registration['name'], version=2)
        platform_escaped = escape_markdown(new_registration['platform'], version=2)
        await update.message.reply_text(
            f"✅ *Registro Guardado*\n\n"
            f"Se ha registrado exitosamente al usuario *{name_escaped}* para la plataforma *{platform_escaped}*\\.",
            parse_mode='MarkdownV2'
        )
        # Send welcome message
        await update.message.reply_text(
             f"🎉 ¡Bienvenido/a, *{name_escaped}*\\! Tu registro para *{platform_escaped}* ha sido completado\\.",
             parse_mode='MarkdownV2'
        )

    else:
        await update.message.reply_text("❌ Error Crítico: No se pudo guardar el registro en el archivo.")

    # Clean up user data
    del user_data[chat_id]
    # Show main menu again
    await send_main_menu(chat_id, context)
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    chat_id = update.message.chat.id
    if chat_id in user_data:
        del user_data[chat_id]
    # Use context.user_data for other conversations
    keys_to_remove = [k for k in context.user_data if k.endswith('_index') or k.endswith('_data') or k.endswith('_field')]
    for key in keys_to_remove:
        del context.user_data[key]

    await update.message.reply_text(
        "🚫 Operación cancelada.", reply_markup=ReplyKeyboardRemove()
    )
    # Show main menu again
    await send_main_menu(chat_id, context)
    return ConversationHandler.END

# --- Add Account Conversation ---
# Renamed state for clarity
ADD_SERVICE, ADD_USERNAME, ADD_PASSWORD, ADD_PLAN, ADD_REGISTRATION_DATE, ADD_PIN = range(8, 14) # Continue numbering

@callback_restricted
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the add account conversation."""
    query = update.callback_query
    chat_id = query.message.chat.id
    # Initialize lists to store message IDs for cleanup
    context.user_data['bot_message_ids'] = [query.message.message_id] # Store the menu message ID
    context.user_data['user_message_ids'] = []
    context.user_data['add_account_data'] = {} # Use context.user_data

    await query.edit_message_text("➕ Iniciando proceso para añadir nueva cuenta de streaming...")
    # Store the ID of the message sent by the bot
    sent_message = await context.bot.send_message(chat_id=chat_id, text="1/6: 🌐 Por favor, ingresa el nombre del servicio:")
    context.user_data['bot_message_ids'].append(sent_message.message_id)
    return ADD_SERVICE

async def ask_add_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Store user reply ID
    context.user_data['user_message_ids'].append(update.message.message_id)
    context.user_data['add_account_data']['service'] = update.message.text
    # Store bot question ID
    sent_message = await update.message.reply_text("2/6: 📧 Ingresa el nombre de usuario (generalmente el email):")
    context.user_data['bot_message_ids'].append(sent_message.message_id)
    return ADD_USERNAME

async def ask_add_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Store user reply ID
    context.user_data['user_message_ids'].append(update.message.message_id)
    context.user_data['add_account_data']['username'] = update.message.text
    # Store bot question ID
    sent_message = await update.message.reply_text("3/6: 🔑 Ingresa la contraseña de la cuenta:")
    context.user_data['bot_message_ids'].append(sent_message.message_id)
    return ADD_PASSWORD

async def ask_add_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Store user reply ID
    context.user_data['user_message_ids'].append(update.message.message_id)
    context.user_data['add_account_data']['password'] = update.message.text
    # Store bot question ID
    sent_message = await update.message.reply_text("4/6: 🏷️ ¿Cuál es el plan contratado?")
    context.user_data['bot_message_ids'].append(sent_message.message_id)
    return ADD_PLAN

async def ask_add_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Store user reply ID
    context.user_data['user_message_ids'].append(update.message.message_id)
    context.user_data['add_account_data']['plan'] = update.message.text
    # Store bot question ID
    sent_message = await update.message.reply_text("5/6: 📅 Ingresa la fecha de registro inicial (Formato: YYYY-MM-DD):")
    context.user_data['bot_message_ids'].append(sent_message.message_id)
    return ADD_REGISTRATION_DATE # Go to the new state

# Renamed function and added date calculation logic
async def ask_add_registration_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores registration date, calculates renewal date, asks for PIN."""
    # Store user reply ID
    context.user_data['user_message_ids'].append(update.message.message_id)
    registration_date_str = update.message.text
    try:
        # Validate and parse registration date
        registration_dt = datetime.strptime(registration_date_str, '%Y-%m-%d')
        context.user_data['add_account_data']['registration_date'] = registration_date_str

        # Calculate renewal date (+30 days)
        renewal_dt = registration_dt + timedelta(days=30)
        renewal_date_str = renewal_dt.strftime('%Y-%m-%d')
        context.user_data['add_account_data']['renewal_date'] = renewal_date_str

        logger.info(f"Registration: {registration_date_str}, Calculated Renewal: {renewal_date_str}")

        # Ask for PIN
        reg_date_escaped = escape_markdown(registration_date_str, version=2)
        ren_date_escaped = escape_markdown(renewal_date_str, version=2)
        # Store bot question ID
        sent_message = await update.message.reply_text(
            f"🗓️ Fecha de registro: `{reg_date_escaped}`\n"
            f"🔄 Fecha de renovación calculada: `{ren_date_escaped}`\n\n"
            f"6/6: 🔢 Ingresa el PIN de la cuenta (Escribe 'N/A' si no aplica):",
            parse_mode='MarkdownV2'
        )
        context.user_data['bot_message_ids'].append(sent_message.message_id)
        return ADD_PIN # Proceed to PIN state

    except ValueError:
        # Invalid date format
        # Store bot error message ID
        sent_message = await update.message.reply_text("⚠️ Formato de fecha inválido\\. Por favor, usa YYYY-MM-DD\\. Intenta de nuevo:")
        context.user_data['bot_message_ids'].append(sent_message.message_id)
        return ADD_REGISTRATION_DATE # Ask for registration date again

async def save_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the PIN, saves the account with both dates, shows summary or error, and ends the conversation."""
    chat_id = update.message.chat.id
    final_message = "❌ Ocurrió un error inesperado al procesar la cuenta." # Default error message

    try:
        # Ensure data exists before proceeding
        if 'add_account_data' not in context.user_data:
             logger.error("save_add_account called without add_account_data in context.")
             final_message = "❌ Error Interno: No se encontraron datos temporales. Por favor, cancela (/cancel) e intenta de nuevo."
             # Let finally handle cleanup/menu

        else:
            # Store the last piece of data (PIN)
            context.user_data['add_account_data']['pin'] = update.message.text
            # Add creation timestamp
            context.user_data['add_account_data']['creation_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            logger.info(f"Attempting to save new account data: {context.user_data['add_account_data']}")

            # Load existing data
            accounts_data = load_data(DATA_FILE)
            # Ensure the loaded data has the 'accounts' list structure
            if 'accounts' not in accounts_data or not isinstance(accounts_data['accounts'], list):
                logger.warning(f"Data file {DATA_FILE} has invalid structure. Resetting to default.")
                accounts_data = {"accounts": []}

            new_account = context.user_data['add_account_data']

            # Double-check essential dates (already checked in previous step, but good practice)
            if 'registration_date' not in new_account or 'renewal_date' not in new_account:
                 logger.error(f"Critical Error: Missing dates in new_account data just before saving: {new_account}")
                 final_message = "❌ Error Interno: Faltan datos de fecha críticos. Por favor, cancela (/cancel) e intenta de nuevo."
                 # Let finally handle cleanup/menu
            else:
                # Append the new account data
                accounts_data['accounts'].append(new_account)
                logger.info(f"Appended new account. Total accounts now: {len(accounts_data['accounts'])}")

                # Attempt to save the updated data
                if save_data(DATA_FILE, accounts_data):
                    logger.info(f"Account added and saved successfully: {new_account.get('service')} - {new_account.get('username')}")

                    # --- Construct Success Summary Message ---
                    service_escaped = escape_markdown(new_account.get('service', 'N/A'), version=2)
                    username_escaped = escape_markdown(new_account.get('username', 'N/A'), version=2)
                    password_masked = escape_markdown("*" * len(new_account.get('password', '')), version=2) if new_account.get('password') else 'N/A'
                    pin_masked = escape_markdown("*" * len(new_account.get('pin', '')), version=2) if new_account.get('pin') and new_account.get('pin').upper() != 'N/A' else 'N/A'
                    plan_escaped = escape_markdown(new_account.get('plan', 'N/A'), version=2)
                    reg_date_escaped = escape_markdown(new_account.get('registration_date', 'N/A'), version=2)
                    ren_date_escaped = escape_markdown(new_account.get('renewal_date', 'N/A'), version=2)
                    creation_date_escaped = escape_markdown(new_account.get('creation_date', 'N/A'), version=2)

                    final_message = (
                        f"✅ *¡Cuenta Añadida Exitosamente!*\n\n"
                        f"*Resumen:*\n"
                        f" Servicio: *{service_escaped}*\n"
                        f" Usuario: `{username_escaped}`\n"
                        f" Contraseña: `{password_masked}`\n"
                        f" PIN: `{pin_masked}`\n"
                        f" Plan: `{plan_escaped}`\n"
                        f" Fecha Registro: `{reg_date_escaped}`\n"
                        f" Fecha Renovación: `{ren_date_escaped}`\n"
                        f" Fecha Creación Bot: `{creation_date_escaped}`"
                    )
                    # --- End Summary Message ---
                else:
                    # save_data returned False
                    final_message = "❌ Error Crítico: No se pudo guardar la cuenta en el archivo. Verifica los permisos o el espacio en disco."
                    logger.error(f"Failed to save account data to file {DATA_FILE}. save_data returned False.")
                    # Attempt to remove the potentially added (but unsaved) account from memory
                    # This might fail if accounts_data structure was bad, hence the check
                    if 'accounts' in accounts_data and isinstance(accounts_data['accounts'], list) and accounts_data['accounts']:
                         accounts_data['accounts'].pop() # Remove the last added item

    except Exception as e:
        logger.error(f"Exception caught in save_add_account: {e}", exc_info=True)
        final_message = f"❌ Ocurrió una excepción inesperada al guardar la cuenta: {e}"
    finally:
        # Send the final summary or error message regardless of what happened
        try:
            await update.message.reply_text(final_message, parse_mode='MarkdownV2')
        except Exception as send_e:
            logger.error(f"Failed to send final message in save_add_account: {send_e}")
            # Try sending a plain text message as fallback
            try:
                 await update.message.reply_text("Ocurrió un error al procesar y mostrar el resultado final.")
            except Exception as fallback_send_e:
                 logger.error(f"Failed to send fallback message: {fallback_send_e}")


        # Always clean up user data from context
        if 'add_account_data' in context.user_data:
            try:
                del context.user_data['add_account_data']
                logger.info("Cleaned up context.user_data['add_account_data']")
            except KeyError:
                 logger.warning("Tried to clean up context.user_data['add_account_data'], but it was already gone.")


        # Show main menu again
        await send_main_menu(chat_id, context)
        return ConversationHandler.END # Ensure conversation ends

# --- Helper function to delete messages ---
async def delete_conversation_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Deletes messages stored in context.user_data for the conversation."""
    # Delete bot messages
    if 'bot_message_ids' in context.user_data:
        logger.debug(f"Attempting to delete bot messages: {context.user_data['bot_message_ids']}")
        for msg_id in context.user_data['bot_message_ids']:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                # Ignore errors if message is already deleted or too old
                logger.warning(f"Could not delete bot message {msg_id} in chat {chat_id}: {e}")
        del context.user_data['bot_message_ids'] # Clean up

    # Delete user messages
    if 'user_message_ids' in context.user_data:
        logger.debug(f"Attempting to delete user messages: {context.user_data['user_message_ids']}")
        for msg_id in context.user_data['user_message_ids']:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                # Ignore errors if message is already deleted or too old
                logger.warning(f"Could not delete user message {msg_id} in chat {chat_id}: {e}")
        del context.user_data['user_message_ids'] # Clean up

# --- Generic Cancel Command ---
@restricted # Make sure only admin can cancel
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generic cancel handler for any conversation."""
    chat_id = update.effective_chat.id # Use effective_chat for broader compatibility
    user_id = update.effective_user.id
    logger.info(f"Cancel command initiated by user {user_id} in chat {chat_id}.")

    # Delete messages from the conversation
    await delete_conversation_messages(context, chat_id)

    # Clean up any potential user_data remnants (specific to conversations)
    keys_to_remove = [k for k in context.user_data if k.endswith('_index') or k.endswith('_data') or k.endswith('_field')]
    for key in keys_to_remove:
        logger.debug(f"Removing key from user_data during cancel: {key}")
        del context.user_data[key]

    # Send cancellation confirmation and remove reply keyboard if any
    cancel_msg = await update.message.reply_text(
        "🚫 Operación cancelada.", reply_markup=ReplyKeyboardRemove()
    )
    # Optionally delete the cancel command itself and the confirmation after a delay
    # This part is more complex and might require JobQueue, skipping for now.

    await send_main_menu(chat_id, context)
    return ConversationHandler.END

# --- View Account Conversation ---
VIEW_ACCOUNT_NUMBER = range(14, 15)[0]

@callback_restricted
async def view_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the view account conversation."""
    query = update.callback_query
    chat_id = query.message.chat.id
    accounts_data = load_data(DATA_FILE)
    list_output = format_accounts_list(accounts_data)

    if not accounts_data or not accounts_data.get("accounts"):
         await query.edit_message_text(list_output, parse_mode='MarkdownV2')
         await send_main_menu(chat_id, context) # Show menu again
         return ConversationHandler.END

    await query.edit_message_text(f"{list_output}\n\n🔢 Por favor, ingresa el número de la cuenta que deseas visualizar:", parse_mode='MarkdownV2')
    return VIEW_ACCOUNT_NUMBER

async def process_view_account_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the account number and displays the details."""
    chat_id = update.message.chat.id
    try:
        index = int(update.message.text) - 1
        accounts_data = load_data(DATA_FILE)
        accounts = accounts_data.get("accounts", [])

        if 0 <= index < len(accounts):
            account = accounts[index]
            details = f"📄 *Detalles Cuenta #{index + 1}*\n```\n" # Added emoji
            # Define the desired order of keys
            key_order = ["service", "username", "password", "pin", "plan", "registration_date", "renewal_date", "creation_date"]
            for key in key_order:
                if key in account: # Check if key exists
                    value = account[key]
                    # Escape value for MarkdownV2
                    escaped_value = escape_markdown(str(value), version=2)
                    # Capitalize key for display
                    display_key = key.replace('_', ' ').capitalize()
                    details += f"{display_key}: {escaped_value}\n"
            # Add any remaining keys not in the defined order
            for key, value in account.items():
                if key not in key_order:
                    escaped_value = escape_markdown(str(value), version=2)
                    display_key = key.replace('_', ' ').capitalize()
                    details += f"{display_key}: {escaped_value}\n"

            details += "```"
            await update.message.reply_text(details, parse_mode='MarkdownV2')
        else:
            await update.message.reply_text(f"⚠️ Número fuera de rango\\. Hay {len(accounts)} cuentas\\.", parse_mode='MarkdownV2')

    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ Número inválido\\. Por favor, ingresa solo el número de la lista\\.", parse_mode='MarkdownV2')

    # Show main menu again
    await send_main_menu(chat_id, context)
    return ConversationHandler.END

# --- Delete Account Conversation ---
DELETE_ACCOUNT_NUMBER, DELETE_ACCOUNT_CONFIRM = range(15, 17)

@callback_restricted
async def delete_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the delete account conversation."""
    query = update.callback_query
    chat_id = query.message.chat.id
    accounts_data = load_data(DATA_FILE)
    list_output = format_accounts_list(accounts_data)

    if not accounts_data or not accounts_data.get("accounts"):
         await query.edit_message_text(list_output, parse_mode='MarkdownV2')
         await send_main_menu(chat_id, context)
         return ConversationHandler.END

    await query.edit_message_text(f"{list_output}\n\n🗑️ Por favor, ingresa el número de la cuenta que deseas *eliminar*:", parse_mode='MarkdownV2')
    return DELETE_ACCOUNT_NUMBER

async def ask_delete_account_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the number and asks for confirmation."""
    chat_id = update.message.chat.id
    try:
        index = int(update.message.text) - 1
        accounts_data = load_data(DATA_FILE)
        accounts = accounts_data.get("accounts", [])

        if 0 <= index < len(accounts):
            context.user_data['delete_index'] = index
            account = accounts[index]
            # Escape user data before displaying
            service_escaped = escape_markdown(account.get('service', 'N/A'), version=2)
            username_escaped = escape_markdown(account.get('username', 'N/A'), version=2)
            keyboard = [[InlineKeyboardButton("✔️ Sí, eliminar", callback_data='confirm_delete_yes'),
                         InlineKeyboardButton("✖️ No, cancelar", callback_data='confirm_delete_no')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"❓ *Confirmación de Eliminación*\n\n"
                f"¿Estás seguro de que quieres eliminar la cuenta #{index + 1}?\n\n"
                f"🌐 Servicio: *{service_escaped}*\n" # Use escaped variable
                f"📧 Usuario: `{username_escaped}`\n\n" # Use escaped variable
                f"⚠️ *Esta acción no se puede deshacer\\.*",
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
            return DELETE_ACCOUNT_CONFIRM
        else:
            await update.message.reply_text(f"⚠️ Número fuera de rango\\. Hay {len(accounts)} cuentas\\.", parse_mode='MarkdownV2')
            await send_main_menu(chat_id, context)
            return ConversationHandler.END

    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ Número inválido\\. Por favor, ingresa solo el número de la lista\\.", parse_mode='MarkdownV2')
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

@callback_restricted # Use callback restricted for button press
async def process_delete_account_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processes the confirmation button press."""
    query = update.callback_query
    chat_id = query.message.chat.id
    decision = query.data # 'confirm_delete_yes' or 'confirm_delete_no'

    if decision == 'confirm_delete_yes' and 'delete_index' in context.user_data:
        index_to_delete = context.user_data['delete_index']
        accounts_data = load_data(DATA_FILE)
        accounts = accounts_data.get("accounts", [])

        if 0 <= index_to_delete < len(accounts):
            deleted_account = accounts.pop(index_to_delete)
            if save_data(DATA_FILE, accounts_data):
                # Escape user data before displaying
                service_escaped = escape_markdown(deleted_account.get('service', 'N/A'), version=2)
                await query.edit_message_text(f"✅ Cuenta #{index_to_delete + 1} (*{service_escaped}*) eliminada exitosamente\\.", parse_mode='MarkdownV2') # Use escaped variable
            else:
                await query.edit_message_text("❌ Error Crítico: No se pudo guardar los cambios después de eliminar la cuenta\\.", parse_mode='MarkdownV2')
        else:
             await query.edit_message_text("❌ Error Interno: Índice inválido encontrado durante la confirmación\\.", parse_mode='MarkdownV2') # Should not happen normally
    elif decision == 'confirm_delete_no':
        await query.edit_message_text("🚫 Eliminación cancelada\\.", parse_mode='MarkdownV2')
    else:
         await query.edit_message_text("❓ Acción desconocida o índice no encontrado\\. Cancelando\\.", parse_mode='MarkdownV2')

    # Clean up and show menu
    if 'delete_index' in context.user_data:
        del context.user_data['delete_index']
    await send_main_menu(chat_id, context)
    return ConversationHandler.END

# --- Edit Account Conversation ---
EDIT_ACCOUNT_NUMBER, EDIT_ACCOUNT_FIELD, EDIT_ACCOUNT_VALUE = range(17, 20)
# Keep renewal_date editable, registration_date is usually fixed. Add creation_date if needed.
VALID_EDIT_FIELDS = ["service", "username", "password", "pin", "plan", "renewal_date"]

@callback_restricted
async def edit_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the edit account conversation."""
    query = update.callback_query
    chat_id = query.message.chat.id
    accounts_data = load_data(DATA_FILE)
    list_output = format_accounts_list(accounts_data)

    if not accounts_data or not accounts_data.get("accounts"):
         await query.edit_message_text(list_output, parse_mode='MarkdownV2')
         await send_main_menu(chat_id, context)
         return ConversationHandler.END

    await query.edit_message_text(f"{list_output}\n\n✏️ Por favor, ingresa el número de la cuenta que deseas *editar*:", parse_mode='MarkdownV2')
    return EDIT_ACCOUNT_NUMBER

async def ask_edit_account_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the number and asks which field to edit."""
    chat_id = update.message.chat.id
    try:
        index = int(update.message.text) - 1
        accounts_data = load_data(DATA_FILE)
        accounts = accounts_data.get("accounts", [])

        if 0 <= index < len(accounts):
            context.user_data['edit_index'] = index
            account = accounts[index]
            # Escape user data before displaying
            service_escaped = escape_markdown(account.get('service', 'N/A'), version=2)

            # Create buttons for valid fields with emojis
            field_emojis = {
                "service": "🌐", "username": "📧", "password": "🔑",
                "pin": "🔢", "plan": "🏷️", "renewal_date": "🔄"
            }
            buttons = []
            for field in VALID_EDIT_FIELDS:
                 emoji = field_emojis.get(field, "⚙️") # Default emoji
                 buttons.append([InlineKeyboardButton(f"{emoji} {field.capitalize()}", callback_data=f'edit_field_{field}')])
            buttons.append([InlineKeyboardButton("✖️ Cancelar Edición", callback_data='edit_field_cancel')])
            reply_markup = InlineKeyboardMarkup(buttons)

            await update.message.reply_text(
                f"✏️ Editando cuenta #{index + 1} (*{service_escaped}*)\\.\n\n" # Use escaped variable
                f"Selecciona el campo que deseas modificar:",
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
            return EDIT_ACCOUNT_FIELD
        else:
            await update.message.reply_text(f"⚠️ Número fuera de rango\\. Hay {len(accounts)} cuentas\\.", parse_mode='MarkdownV2')
            await send_main_menu(chat_id, context)
            return ConversationHandler.END

    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ Número inválido\\. Por favor, ingresa solo el número de la lista\\.", parse_mode='MarkdownV2')
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

@callback_restricted # Use callback restricted for button press
async def ask_edit_account_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the field choice and asks for the new value."""
    query = update.callback_query
    chat_id = query.message.chat.id
    field_choice = query.data # e.g., 'edit_field_username' or 'edit_field_cancel'

    if field_choice == 'edit_field_cancel':
        await query.edit_message_text("🚫 Edición cancelada\\.", parse_mode='MarkdownV2')
        if 'edit_index' in context.user_data: del context.user_data['edit_index']
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

    if not field_choice.startswith('edit_field_'):
        await query.edit_message_text("❓ Opción inválida\\. Cancelando edición\\.", parse_mode='MarkdownV2')
        if 'edit_index' in context.user_data: del context.user_data['edit_index']
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

    field_to_edit = field_choice.split('edit_field_')[1]
    if field_to_edit not in VALID_EDIT_FIELDS:
        # Escape field name before showing error
        field_to_edit_escaped = escape_markdown(field_to_edit, version=2)
        await query.edit_message_text(f"❌ Campo '{field_to_edit_escaped}' no es válido para edición\\. Cancelando\\.", parse_mode='MarkdownV2')
        if 'edit_index' in context.user_data: del context.user_data['edit_index']
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

    context.user_data['edit_field'] = field_to_edit
    field_display = field_to_edit.replace('_', ' ').capitalize()
    # Escape display name before asking for value
    field_display_escaped = escape_markdown(field_display, version=2)
    await query.edit_message_text(f"✍️ Ingresa el nuevo valor para *{field_display_escaped}*:", parse_mode='MarkdownV2')
    return EDIT_ACCOUNT_VALUE

async def save_edit_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the new value, saves the changes, and ends the conversation."""
    chat_id = update.message.chat.id
    new_value = update.message.text

    if 'edit_index' not in context.user_data or 'edit_field' not in context.user_data:
        await update.message.reply_text("❌ Error Interno: No se encontró información de edición\\. Cancelando\\.", parse_mode='MarkdownV2')
        if 'edit_index' in context.user_data: del context.user_data['edit_index']
        if 'edit_field' in context.user_data: del context.user_data['edit_field']
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

    index_to_edit = context.user_data['edit_index']
    field_to_edit = context.user_data['edit_field']

    # Add validation for renewal_date format if needed
    if field_to_edit == "renewal_date":
        try:
            datetime.strptime(new_value, '%Y-%m-%d')
        except ValueError:
            await update.message.reply_text("⚠️ Formato de fecha inválido para Fecha de Renovación\\. Usa YYYY-MM-DD\\. Por favor, inicia la edición de nuevo\\.", parse_mode='MarkdownV2')
            # Clean up and end, forcing user to restart edit
            del context.user_data['edit_index']
            del context.user_data['edit_field']
            await send_main_menu(chat_id, context)
            return ConversationHandler.END

    accounts_data = load_data(DATA_FILE)
    accounts = accounts_data.get("accounts", [])

    if 0 <= index_to_edit < len(accounts):
        accounts[index_to_edit][field_to_edit] = new_value
        if save_data(DATA_FILE, accounts_data):
            field_md = escape_markdown(field_to_edit.replace('_', ' ').capitalize(), version=2)
            await update.message.reply_text(f"✅ *Cuenta Actualizada*\n\nLa cuenta #{index_to_edit + 1} ha sido actualizada\\. El campo `{field_md}` fue modificado\\.", parse_mode='MarkdownV2')
        else:
            await update.message.reply_text("❌ Error Crítico: No se pudieron guardar los cambios de la cuenta\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("❌ Error Interno: Índice inválido encontrado durante el guardado\\.", parse_mode='MarkdownV2')

    # Clean up and show menu
    del context.user_data['edit_index']
    del context.user_data['edit_field']
    await send_main_menu(chat_id, context)
    return ConversationHandler.END


# --- Delete Registration Conversation ---
DELETE_REG_NUMBER, DELETE_REG_CONFIRM = range(20, 22)

@callback_restricted
async def delete_reg_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the delete registration conversation."""
    query = update.callback_query
    chat_id = query.message.chat.id
    reg_data = load_data(REG_DATA_FILE)
    list_output = format_registrations_list(reg_data)

    if not reg_data or not reg_data.get("registrations"):
         await query.edit_message_text(list_output, parse_mode='MarkdownV2')
         await send_main_menu(chat_id, context)
         return ConversationHandler.END

    await query.edit_message_text(f"{list_output}\n\n❌ Por favor, ingresa el número del registro de usuario que deseas *eliminar*:", parse_mode='MarkdownV2')
    return DELETE_REG_NUMBER

async def ask_delete_reg_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the number and asks for confirmation."""
    chat_id = update.message.chat.id
    try:
        index = int(update.message.text) - 1
        reg_data = load_data(REG_DATA_FILE)
        registrations = reg_data.get("registrations", [])

        if 0 <= index < len(registrations):
            context.user_data['delete_reg_index'] = index
            reg = registrations[index]
            # Escape user data before displaying
            name_escaped = escape_markdown(reg.get('name', 'N/A'), version=2)
            platform_escaped = escape_markdown(reg.get('platform', 'N/A'), version=2)
            keyboard = [[InlineKeyboardButton("✔️ Sí, eliminar", callback_data='confirm_delreg_yes'),
                         InlineKeyboardButton("✖️ No, cancelar", callback_data='confirm_delreg_no')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"❓ *Confirmación de Eliminación de Registro*\n\n"
                f"¿Estás seguro de que quieres eliminar el registro #{index + 1}?\n\n"
                f"👤 Usuario: *{name_escaped}*\n" # Use escaped variable
                f"📺 Plataforma: *{platform_escaped}*\n\n" # Use escaped variable
                f"⚠️ *Esta acción no se puede deshacer\\.*",
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
            # The deletion logic is handled in process_delete_reg_confirm
            return DELETE_REG_CONFIRM
        else:
            await update.message.reply_text(f"⚠️ Número fuera de rango\\. Hay {len(registrations)} registros\\.", parse_mode='MarkdownV2')
            await send_main_menu(chat_id, context)
            return ConversationHandler.END

    except (ValueError, IndexError):
        await update.message.reply_text("⚠️ Número inválido\\. Por favor, ingresa solo el número de la lista\\.", parse_mode='MarkdownV2')
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

@callback_restricted # Use callback restricted for button press
async def process_delete_reg_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processes the confirmation button press for deleting a registration."""
    query = update.callback_query
    chat_id = query.message.chat.id
    decision = query.data # 'confirm_delreg_yes' or 'confirm_delreg_no'

    if decision == 'confirm_delreg_yes' and 'delete_reg_index' in context.user_data:
        index_to_delete = context.user_data['delete_reg_index']
        reg_data = load_data(REG_DATA_FILE)
        registrations = reg_data.get("registrations", []) # Use .get for safety

        if 0 <= index_to_delete < len(registrations):
            deleted_reg = registrations.pop(index_to_delete)
            if save_data(REG_DATA_FILE, reg_data):
                # Escape user data before displaying
                name_escaped = escape_markdown(deleted_reg.get('name', 'N/A'), version=2)
                platform_escaped = escape_markdown(deleted_reg.get('platform', 'N/A'), version=2)
                await query.edit_message_text(f"✅ Registro #{index_to_delete + 1} (*{name_escaped}* \\- *{platform_escaped}*) eliminado exitosamente\\.", parse_mode='MarkdownV2') # Use escaped variables
            else:
                await query.edit_message_text("❌ Error Crítico: No se pudieron guardar los cambios después de eliminar el registro\\.", parse_mode='MarkdownV2')
        else:
             await query.edit_message_text("❌ Error Interno: Índice inválido encontrado durante la confirmación\\.", parse_mode='MarkdownV2')
    elif decision == 'confirm_delreg_no':
        await query.edit_message_text("🚫 Eliminación cancelada\\.", parse_mode='MarkdownV2')
    else:
         await query.edit_message_text("❓ Acción desconocida o índice no encontrado\\. Cancelando\\.", parse_mode='MarkdownV2')

    # Clean up and show menu
    if 'delete_reg_index' in context.user_data:
        del context.user_data['delete_reg_index']
    await send_main_menu(chat_id, context)
    return ConversationHandler.END


# --- Direct Action Handlers (No Conversation) ---

@callback_restricted
async def list_accounts_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'List Accounts' button."""
    query = update.callback_query
    accounts_data = load_data(DATA_FILE)
    list_output = format_accounts_list(accounts_data)
    # Edit the original menu message to show the list
    await query.edit_message_text(list_output, parse_mode='MarkdownV2')
    # Send the menu again below the list
    await send_main_menu(query.message.chat.id, context)

@callback_restricted
async def list_regs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'List Registrations' button."""
    query = update.callback_query
    reg_data = load_data(REG_DATA_FILE)
    list_output = format_registrations_list(reg_data)
    await query.edit_message_text(list_output, parse_mode='MarkdownV2')
    await send_main_menu(query.message.chat.id, context)

@callback_restricted
async def backup_data_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Backup' button."""
    query = update.callback_query
    chat_id = query.message.chat.id
    backup_successful = False
    await query.edit_message_text("Generando backups...") # Acknowledge

    # Backup accounts
    if os.path.exists(DATA_FILE):
        try:
            # Escape filename for caption
            filename_escaped = escape_markdown(os.path.basename(DATA_FILE), version=2)
            await context.bot.send_document(
                chat_id=chat_id,
                document=InputFile(DATA_FILE),
                caption=f"Backup de cuentas \\({filename_escaped}\\) al {escape_markdown(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), version=2)}" # Escape filename and date
            )
            logger.info(f"Backup de cuentas enviado a {chat_id}")
            backup_successful = True
        except Exception as e:
            logger.error(f"Error enviando backup de cuentas: {e}")
            # Escape filename in error message
            filename_escaped = escape_markdown(os.path.basename(DATA_FILE), version=2)
            await context.bot.send_message(chat_id, f"Error al enviar backup de `{filename_escaped}`\\.", parse_mode='MarkdownV2')
    else:
        # Escape filename in info message
        filename_escaped = escape_markdown(os.path.basename(DATA_FILE), version=2)
        await context.bot.send_message(chat_id, f"Info: No se encontró archivo `{filename_escaped}` para backup\\.", parse_mode='MarkdownV2')

    # Backup registrations
    if os.path.exists(REG_DATA_FILE):
         try:
            # Escape filename for caption
            filename_escaped = escape_markdown(os.path.basename(REG_DATA_FILE), version=2)
            await context.bot.send_document(
                chat_id=chat_id,
                document=InputFile(REG_DATA_FILE),
                caption=f"Backup de registros \\({filename_escaped}\\) al {escape_markdown(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), version=2)}" # Escape filename and date
            )
            logger.info(f"Backup de registros enviado a {chat_id}")
            backup_successful = True
         except Exception as e:
            logger.error(f"Error enviando backup de registros: {e}")
            # Escape filename in error message
            filename_escaped = escape_markdown(os.path.basename(REG_DATA_FILE), version=2)
            await context.bot.send_message(chat_id, f"Error al enviar backup de `{filename_escaped}`\\.", parse_mode='MarkdownV2')
    else:
        # Escape filename in info message
        filename_escaped = escape_markdown(os.path.basename(REG_DATA_FILE), version=2)
        await context.bot.send_message(chat_id, f"Info: No se encontró archivo `{filename_escaped}` para backup\\.", parse_mode='MarkdownV2')

    if not backup_successful:
         await context.bot.send_message(chat_id, "No se pudo generar ningún backup\\. Comprueba los logs\\.", parse_mode='MarkdownV2')

    # Show menu again
    await send_main_menu(chat_id, context)


@callback_restricted
async def license_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'License Status' button."""
    query = update.callback_query
    chat_id = query.message.chat.id
    # Escape dates from config
    activation_escaped = escape_markdown(str(ACTIVATION_DATE), version=2)
    expiration_escaped = escape_markdown(str(EXPIRATION_DATE), version=2)
    status_msg = "*Estado de Licencia*\n"
    status_msg += f"Activación: `{activation_escaped}`\n"
    status_msg += f"Expiración: `{expiration_escaped}`\n"

    try:
        expiration_dt = datetime.strptime(EXPIRATION_DATE, '%Y-%m-%d')
        activation_dt = datetime.strptime(ACTIVATION_DATE, '%Y-%m-%d') # Also check activation format
        if datetime.now() > expiration_dt:
            status_msg += "Estado: 🔴 *Expirada*\n"
        else:
            days_left = (expiration_dt - datetime.now()).days
            # Escape days_left just in case, and ensure '(' ')' are escaped
            days_left_escaped = escape_markdown(str(days_left), version=2)
            status_msg += f"Estado: 🟢 *Activa* \\({days_left_escaped} días restantes\\)\n"
    except (ValueError, TypeError):
        # Ensure '(' ')' are escaped in error message
        status_msg += "Estado: ⚠️ *Error en formato de fechas* \\(YYYY\\-MM\\-DD esperado\\)\n"

    await query.edit_message_text(status_msg, parse_mode='MarkdownV2')
    await send_main_menu(chat_id, context)


# --- Command Aliases (Non-conversational) ---
@restricted
async def list_accounts_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts_data = load_data(DATA_FILE)
    list_output = format_accounts_list(accounts_data)
    await update.message.reply_text(list_output, parse_mode='MarkdownV2')

@restricted
async def list_regs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reg_data = load_data(REG_DATA_FILE)
    list_output = format_registrations_list(reg_data)
    await update.message.reply_text(list_output, parse_mode='MarkdownV2')

# Add non-conversational /view, /delete, /delreg if needed, similar to bash logic but simpler


# --- Generic Cancel Command ---
@restricted # Make sure only admin can cancel
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Generic cancel handler for any conversation."""
    chat_id = update.message.chat.id
    # Clean up any potential user_data remnants
    keys_to_remove = [k for k in context.user_data if k.endswith('_index') or k.endswith('_data') or k.endswith('_field')]
    for key in keys_to_remove:
        del context.user_data[key]

    await update.message.reply_text(
        "Operación cancelada.", reply_markup=ReplyKeyboardRemove()
    )
    await send_main_menu(chat_id, context)
    return ConversationHandler.END


# --- License Check (Basic Placeholder) ---
async def check_license(context: ContextTypes.DEFAULT_TYPE):
    """Periodically checks the license validity."""
    try:
        expiration_dt = datetime.strptime(EXPIRATION_DATE, '%Y-%m-%d')
        expiration_escaped = escape_markdown(EXPIRATION_DATE, version=2) # Escape date for messages
        if datetime.now() > expiration_dt:
            logger.critical(f"License expired on {EXPIRATION_DATE}. Stopping bot.")
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"Error Crítico: La licencia del bot expiró el {expiration_escaped}\\. El bot se ha detenido\\.", # Use escaped date
                parse_mode='MarkdownV2'
            )
            # Gracefully stop the application
            context.application.stop()
        else:
            logger.info(f"License check passed. Valid until {EXPIRATION_DATE}.")
            # Optional: Warn if nearing expiration
            days_left = (expiration_dt - datetime.now()).days
            if days_left <= 7:
                 logger.warning(f"License expires in {days_left} days ({EXPIRATION_DATE}).")
                 # Consider sending a Telegram warning less frequently
                 # if context.job.name == "license_check_daily_warn": # Example check
                 #    days_left_escaped = escape_markdown(str(days_left), version=2)
                 #    await context.bot.send_message(ADMIN_CHAT_ID, f"Advertencia: La licencia expira en {days_left_escaped} días \\({expiration_escaped}\\)\\.", parse_mode='MarkdownV2')

    except (ValueError, TypeError) as e:
        logger.error(f"Invalid date format in config.env for EXPIRATION_DATE: {EXPIRATION_DATE}. Error: {e}")
        # Escape date in error message
        expiration_escaped = escape_markdown(str(EXPIRATION_DATE), version=2)
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"Error Crítico: Formato de fecha de expiración inválido en config\\.env \\('{expiration_escaped}'\\)\\. El bot se detendrá\\.", # Use escaped date
            parse_mode='MarkdownV2'
        )
        context.application.stop()


# --- Conversation Handler Definitions ---

# Registration Conversation Handler
reg_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(register_user_start, pattern='^register_user_start$')],
    states={
        PLATFORM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_platform)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
        PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
        PAYMENT_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_payment_type)],
        EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_email)],
        PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_pin)],
        START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_start_date)],
        END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_end_date)],
    },
    fallbacks=[CommandHandler('cancel', cancel_command)],
    per_message=False # Explicitly set
    # Optional: Add conversation timeout
    # conversation_timeout=timedelta(minutes=5).total_seconds()
)

# Add Account Conversation Handler
add_account_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_account_start, pattern='^add_account_prompt$')],
    states={
        ADD_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_add_service)],
        ADD_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_add_username)],
        ADD_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_add_password)],
        ADD_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_add_plan)],
        ADD_REGISTRATION_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_add_registration_date)],
        ADD_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_add_account)],
    },
    fallbacks=[CommandHandler('cancel', cancel_command)],
    per_message=False # Explicitly set
)

# View Account Conversation Handler
view_account_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(view_account_start, pattern='^view_account_prompt$')],
    states={
        VIEW_ACCOUNT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_view_account_number)],
    },
    fallbacks=[CommandHandler('cancel', cancel_command)],
    per_message=False # Explicitly set
)

# Delete Account Conversation Handler
delete_account_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(delete_account_start, pattern='^delete_account_prompt$')],
    states={
        DELETE_ACCOUNT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_delete_account_confirm)],
        DELETE_ACCOUNT_CONFIRM: [CallbackQueryHandler(process_delete_account_confirm, pattern='^confirm_delete_(yes|no)$')],
    },
    fallbacks=[CommandHandler('cancel', cancel_command)],
    per_message=False # Explicitly set
)

# Edit Account Conversation Handler
edit_account_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(edit_account_start, pattern='^edit_account_prompt$')],
    states={
        EDIT_ACCOUNT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_edit_account_field)],
        EDIT_ACCOUNT_FIELD: [CallbackQueryHandler(ask_edit_account_value, pattern='^edit_field_')], # Handles button press
        EDIT_ACCOUNT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit_account)],
    },
    fallbacks=[CommandHandler('cancel', cancel_command), CallbackQueryHandler(ask_edit_account_value, pattern='^edit_field_cancel$')], # Allow cancel via button too
    per_message=False # Explicitly set
)

# Delete Registration Conversation Handler
delete_reg_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(delete_reg_start, pattern='^delete_reg_prompt$')],
    states={
        DELETE_REG_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_delete_reg_confirm)],
        DELETE_REG_CONFIRM: [CallbackQueryHandler(process_delete_reg_confirm, pattern='^confirm_delreg_(yes|no)$')],
    },
    fallbacks=[CommandHandler('cancel', cancel_command)],
    per_message=False # Explicitly set
)


# --- Main Function ---
def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Add Handlers ---
    # Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_accounts_command))
    application.add_handler(CommandHandler("listreg", list_regs_command))
    # Add other direct command aliases if implemented (e.g., /view, /delete, /delreg)
    # application.add_handler(CommandHandler("view", view_account_command)) # Example
    # application.add_handler(CommandHandler("delete", delete_account_command)) # Example
    # application.add_handler(CommandHandler("delreg", delete_reg_command)) # Example

    # Conversation Handlers
    application.add_handler(reg_conv_handler)
    application.add_handler(add_account_conv_handler)
    application.add_handler(view_account_conv_handler)
    application.add_handler(delete_account_conv_handler)
    application.add_handler(edit_account_conv_handler)
    application.add_handler(delete_reg_conv_handler)

    # Callback Query Handlers (for buttons not part of conversations)
    application.add_handler(CallbackQueryHandler(list_accounts_callback, pattern='^list_accounts$'))
    application.add_handler(CallbackQueryHandler(list_regs_callback, pattern='^list_regs$'))
    application.add_handler(CallbackQueryHandler(backup_data_callback, pattern='^backup_data$'))
    application.add_handler(CallbackQueryHandler(help_command, pattern='^show_help$')) # Reuse help_command for button
    application.add_handler(CallbackQueryHandler(license_status_callback, pattern='^license_status$'))

    # Generic Cancel Command Handler (should be low priority if used outside conversations)
    # Note: CommandHandler('cancel', cancel_command) is already added as fallback in conversations.
    # Adding it here might conflict or be redundant depending on desired behavior.
    # If you want /cancel to work *outside* conversations, add it here.
    # application.add_handler(CommandHandler('cancel', cancel_command))


    # --- Job Queue for License Check ---
    job_queue = application.job_queue
    # Run the check once shortly after startup, then daily
    job_queue.run_once(check_license, when=timedelta(seconds=5)) # Check 5 seconds after start
    job_queue.run_daily(check_license, time=datetime.strptime("03:00", "%H:%M").time()) # Check daily at 3 AM bot time

    # --- Start the Bot ---
    logger.info("Starting bot polling...")
    application.run_polling()

if __name__ == '__main__':
    # Validate essential config before starting
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN not found in config.env. Exiting.")
        exit(1)
    if not ADMIN_CHAT_ID:
        logger.critical("ADMIN_CHAT_ID not found or invalid in config.env. Exiting.")
        exit(1)
    if not ACTIVATION_DATE or not EXPIRATION_DATE:
        logger.critical("ACTIVATION_DATE or EXPIRATION_DATE not found in config.env. Exiting.")
        exit(1)
    # Basic date format check at startup
    try:
        datetime.strptime(ACTIVATION_DATE, '%Y-%m-%d')
        datetime.strptime(EXPIRATION_DATE, '%Y-%m-%d')
    except ValueError:
        logger.critical("Invalid date format found in ACTIVATION_DATE or EXPIRATION_DATE (use YYYY-MM-DD). Exiting.")
        exit(1)

    main()
