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
        name = reg.get('name', 'N/A')
        platform = reg.get('platform', 'N/A')
        end_date = reg.get('end_date', 'N/A')
        # Escape potential markdown characters if needed
        output += f"{i + 1}. {name} ({platform}) - Vence: {end_date}\n"
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
    await query.edit_message_text("Ok, vamos a registrar un nuevo usuario.") # Edit the menu message
    await context.bot.send_message(chat_id=chat_id, text="1/8: ¿Plataforma de streaming?")
    return PLATFORM

async def ask_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the platform and asks for the name."""
    chat_id = update.message.chat.id
    user_data[chat_id]['platform'] = update.message.text
    await update.message.reply_text("2/8: ¿Nombre completo del usuario?")
    return NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the name and asks for the phone number."""
    chat_id = update.message.chat.id
    user_data[chat_id]['name'] = update.message.text
    await update.message.reply_text("3/8: ¿Número de celular?")
    return PHONE

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the phone number and asks for payment type."""
    chat_id = update.message.chat.id
    user_data[chat_id]['phone'] = update.message.text
    await update.message.reply_text("4/8: ¿Tipo de pago realizado?")
    return PAYMENT_TYPE

async def ask_payment_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the payment type and asks for email."""
    chat_id = update.message.chat.id
    user_data[chat_id]['payment_type'] = update.message.text
    await update.message.reply_text("5/8: ¿Email del usuario?")
    return EMAIL

async def ask_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the email and asks for PIN."""
    chat_id = update.message.chat.id
    user_data[chat_id]['email'] = update.message.text
    await update.message.reply_text("6/8: ¿PIN de la cuenta (si aplica, si no, escribe 'N/A')?")
    return PIN

async def ask_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the PIN and asks for the start date."""
    chat_id = update.message.chat.id
    user_data[chat_id]['pin'] = update.message.text
    await update.message.reply_text("7/8: ¿Fecha de alta (YYYY-MM-DD)?")
    return START_DATE

async def ask_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the start date and asks for the end date."""
    chat_id = update.message.chat.id
    # Basic date validation could be added here
    user_data[chat_id]['start_date'] = update.message.text
    await update.message.reply_text("8/8: ¿Fecha de vencimiento (YYYY-MM-DD)?")
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
        await update.message.reply_text(
            f"✅ ¡Registro completado!\n"
            f"Usuario: *{new_registration['name']}*\n"
            f"Plataforma: *{new_registration['platform']}*\n"
            f"Guardado exitosamente\\.",
            parse_mode='MarkdownV2'
        )
        # Send welcome message
        await update.message.reply_text(
             f"🎉 ¡Bienvenido/a, *{new_registration['name']}*\\! Tu registro para *{new_registration['platform']}* ha sido completado\\.",
             parse_mode='MarkdownV2'
        )

    else:
        await update.message.reply_text("❌ Error al guardar el registro.")

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
    await update.message.reply_text(
        "Registro cancelado.", reply_markup=ReplyKeyboardRemove()
    )
    # Show main menu again
    await send_main_menu(chat_id, context)
    return ConversationHandler.END

# --- Add Account Conversation ---
ADD_SERVICE, ADD_USERNAME, ADD_PASSWORD, ADD_PLAN, ADD_RENEWAL_DATE, ADD_PIN = range(8, 14) # Continue numbering

@callback_restricted
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the add account conversation."""
    query = update.callback_query
    chat_id = query.message.chat.id
    context.user_data['add_account_data'] = {} # Use context.user_data
    await query.edit_message_text("Ok, vamos a añadir una nueva cuenta de streaming.")
    await context.bot.send_message(chat_id=chat_id, text="1/6: ¿Nombre del Servicio?")
    return ADD_SERVICE

async def ask_add_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['add_account_data']['service'] = update.message.text
    await update.message.reply_text("2/6: ¿Nombre de Usuario (email)?")
    return ADD_USERNAME

async def ask_add_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['add_account_data']['username'] = update.message.text
    await update.message.reply_text("3/6: ¿Contraseña?")
    return ADD_PASSWORD

async def ask_add_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['add_account_data']['password'] = update.message.text
    await update.message.reply_text("4/6: ¿Plan contratado?")
    return ADD_PLAN

async def ask_add_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['add_account_data']['plan'] = update.message.text
    await update.message.reply_text("5/6: ¿Fecha de Renovación (YYYY-MM-DD)?")
    return ADD_RENEWAL_DATE

async def ask_add_renewal_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Add date validation here if needed
    context.user_data['add_account_data']['renewal_date'] = update.message.text
    await update.message.reply_text("6/6: ¿PIN (opcional, escribe 'N/A' si no tiene)?")
    return ADD_PIN

async def save_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the PIN, saves the account, and ends the conversation."""
    chat_id = update.message.chat.id
    context.user_data['add_account_data']['pin'] = update.message.text
    context.user_data['add_account_data']['creation_date'] = datetime.now().strftime('%Y-%m-%d')

    accounts_data = load_data(DATA_FILE)
    new_account = context.user_data['add_account_data']
    accounts_data['accounts'].append(new_account)

    if save_data(DATA_FILE, accounts_data):
        await update.message.reply_text(
            f"✅ ¡Cuenta añadida!\n"
            f"Servicio: *{escape_markdown(new_account['service'], version=2)}*\n"
            f"Usuario: `{escape_markdown(new_account['username'], version=2)}`\n"
            f"Guardada exitosamente\\.",
            parse_mode='MarkdownV2'
        )
    else:
        await update.message.reply_text("❌ Error al guardar la cuenta.")

    # Clean up user data
    del context.user_data['add_account_data']
    # Show main menu again
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

    await query.edit_message_text(f"{list_output}\n\nPor favor, ingresa el número de la cuenta a ver:", parse_mode='MarkdownV2')
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
            details = "*Detalles Cuenta #{}*\n```\n".format(index + 1)
            for key, value in account.items():
                # Escape value for MarkdownV2
                escaped_value = escape_markdown(str(value), version=2)
                details += f"{key}: {escaped_value}\n"
            details += "```"
            await update.message.reply_text(details, parse_mode='MarkdownV2')
        else:
            await update.message.reply_text(f"Número fuera de rango\\. Hay {len(accounts)} cuentas\\.", parse_mode='MarkdownV2')

    except (ValueError, IndexError):
        await update.message.reply_text("Número inválido\\. Por favor, ingresa solo el número de la lista\\.", parse_mode='MarkdownV2')

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

    await query.edit_message_text(f"{list_output}\n\nPor favor, ingresa el número de la cuenta a *eliminar*:", parse_mode='MarkdownV2')
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
            service = escape_markdown(account.get('service', 'N/A'), version=2)
            username = escape_markdown(account.get('username', 'N/A'), version=2)
            keyboard = [[InlineKeyboardButton("Sí, eliminar", callback_data='confirm_delete_yes'),
                         InlineKeyboardButton("No, cancelar", callback_data='confirm_delete_no')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"¿Estás seguro de que quieres eliminar la cuenta #{index + 1}?\n"
                f"Servicio: *{service}*\n"
                f"Usuario: `{username}`",
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
            return DELETE_ACCOUNT_CONFIRM
        else:
            await update.message.reply_text(f"Número fuera de rango\\. Hay {len(accounts)} cuentas\\.", parse_mode='MarkdownV2')
            await send_main_menu(chat_id, context)
            return ConversationHandler.END

    except (ValueError, IndexError):
        await update.message.reply_text("Número inválido\\. Por favor, ingresa solo el número de la lista\\.", parse_mode='MarkdownV2')
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
                service = escape_markdown(deleted_account.get('service', 'N/A'), version=2)
                await query.edit_message_text(f"✅ Cuenta #{index_to_delete + 1} (*{service}*) eliminada exitosamente\\.", parse_mode='MarkdownV2')
            else:
                await query.edit_message_text("❌ Error al guardar los cambios después de eliminar la cuenta\\.", parse_mode='MarkdownV2')
        else:
             await query.edit_message_text("❌ Error: Índice inválido encontrado durante la confirmación\\.", parse_mode='MarkdownV2') # Should not happen normally
    elif decision == 'confirm_delete_no':
        await query.edit_message_text("Eliminación cancelada\\.", parse_mode='MarkdownV2')
    else:
         await query.edit_message_text("Acción desconocida o índice no encontrado\\. Cancelando\\.", parse_mode='MarkdownV2')

    # Clean up and show menu
    if 'delete_index' in context.user_data:
        del context.user_data['delete_index']
    await send_main_menu(chat_id, context)
    return ConversationHandler.END


# --- Edit Account Conversation ---
EDIT_ACCOUNT_NUMBER, EDIT_ACCOUNT_FIELD, EDIT_ACCOUNT_VALUE = range(17, 20)
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

    await query.edit_message_text(f"{list_output}\n\nPor favor, ingresa el número de la cuenta a *editar*:", parse_mode='MarkdownV2')
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
            service = escape_markdown(account.get('service', 'N/A'), version=2)

            # Create buttons for valid fields
            buttons = []
            for field in VALID_EDIT_FIELDS:
                 buttons.append([InlineKeyboardButton(field.capitalize(), callback_data=f'edit_field_{field}')])
            buttons.append([InlineKeyboardButton("Cancelar Edición", callback_data='edit_field_cancel')])
            reply_markup = InlineKeyboardMarkup(buttons)

            await update.message.reply_text(
                f"Editando cuenta #{index + 1} (*{service}*)\\.\n"
                f"¿Qué campo deseas modificar?",
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
            return EDIT_ACCOUNT_FIELD
        else:
            await update.message.reply_text(f"Número fuera de rango\\. Hay {len(accounts)} cuentas\\.", parse_mode='MarkdownV2')
            await send_main_menu(chat_id, context)
            return ConversationHandler.END

    except (ValueError, IndexError):
        await update.message.reply_text("Número inválido\\. Por favor, ingresa solo el número de la lista\\.", parse_mode='MarkdownV2')
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

@callback_restricted # Use callback restricted for button press
async def ask_edit_account_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the field choice and asks for the new value."""
    query = update.callback_query
    chat_id = query.message.chat.id
    field_choice = query.data # e.g., 'edit_field_username' or 'edit_field_cancel'

    if field_choice == 'edit_field_cancel':
        await query.edit_message_text("Edición cancelada\\.", parse_mode='MarkdownV2')
        if 'edit_index' in context.user_data: del context.user_data['edit_index']
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

    if not field_choice.startswith('edit_field_'):
        await query.edit_message_text("Opción inválida\\. Cancelando edición\\.", parse_mode='MarkdownV2')
        if 'edit_index' in context.user_data: del context.user_data['edit_index']
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

    field_to_edit = field_choice.split('edit_field_')[1]
    if field_to_edit not in VALID_EDIT_FIELDS:
        await query.edit_message_text(f"Campo '{field_to_edit}' no es válido para edición\\. Cancelando\\.", parse_mode='MarkdownV2')
        if 'edit_index' in context.user_data: del context.user_data['edit_index']
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

    context.user_data['edit_field'] = field_to_edit
    await query.edit_message_text(f"Ingresa el nuevo valor para *{escape_markdown(field_to_edit, version=2)}*:", parse_mode='MarkdownV2')
    return EDIT_ACCOUNT_VALUE

async def save_edit_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the new value, saves the changes, and ends the conversation."""
    chat_id = update.message.chat.id
    new_value = update.message.text

    if 'edit_index' not in context.user_data or 'edit_field' not in context.user_data:
        await update.message.reply_text("Error: No se encontró información de edición\\. Cancelando\\.", parse_mode='MarkdownV2')
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
            await update.message.reply_text("Formato de fecha inválido para renewal_date\\. Usa YYYY-MM-DD\\. Intenta editar de nuevo\\.", parse_mode='MarkdownV2')
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
            field_md = escape_markdown(field_to_edit, version=2)
            await update.message.reply_text(f"✅ Cuenta #{index_to_edit + 1} actualizada\\. Campo `{field_md}` modificado\\.", parse_mode='MarkdownV2')
        else:
            await update.message.reply_text("❌ Error al guardar los cambios de la cuenta\\.", parse_mode='MarkdownV2')
    else:
        await update.message.reply_text("❌ Error: Índice inválido encontrado durante el guardado\\.", parse_mode='MarkdownV2')

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

    await query.edit_message_text(f"{list_output}\n\nPor favor, ingresa el número del registro a *eliminar*:", parse_mode='MarkdownV2')
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
            name = escape_markdown(reg.get('name', 'N/A'), version=2)
            platform = escape_markdown(reg.get('platform', 'N/A'), version=2)
            keyboard = [[InlineKeyboardButton("Sí, eliminar", callback_data='confirm_delreg_yes'),
                         InlineKeyboardButton("No, cancelar", callback_data='confirm_delreg_no')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"¿Estás seguro de que quieres eliminar el registro #{index + 1}?\n"
                f"Usuario: *{name}*\n"
                f"Plataforma: *{platform}*",
                reply_markup=reply_markup,
                parse_mode='MarkdownV2'
            )
            return DELETE_REG_CONFIRM
        else:
            await update.message.reply_text(f"Número fuera de rango\\. Hay {len(registrations)} registros\\.", parse_mode='MarkdownV2')
            await send_main_menu(chat_id, context)
            return ConversationHandler.END

    except (ValueError, IndexError):
        await update.message.reply_text("Número inválido\\. Por favor, ingresa solo el número de la lista\\.", parse_mode='MarkdownV2')
        await send_main_menu(chat_id, context)
        return ConversationHandler.END

@callback_restricted # Use callback restricted for button press
async def process_delete_reg_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Processes the confirmation button press."""
    query = update.callback_query
    chat_id = query.message.chat.id
    decision = query.data # 'confirm_delreg_yes' or 'confirm_delreg_no'

    if decision == 'confirm_delreg_yes' and 'delete_reg_index' in context.user_data:
        index_to_delete = context.user_data['delete_reg_index']
        reg_data = load_data(REG_DATA_FILE)
        registrations = reg_data.get("registrations", [])

        if 0 <= index_to_delete < len(registrations):
            deleted_reg = registrations.pop(index_to_delete)
            if save_data(REG_DATA_FILE, reg_data):
                name = escape_markdown(deleted_reg.get('name', 'N/A'), version=2)
                platform = escape_markdown(deleted_reg.get('platform', 'N/A'), version=2)
                await query.edit_message_text(f"✅ Registro #{index_to_delete + 1} (*{name}* \\- *{platform}*) eliminado exitosamente\\.", parse_mode='MarkdownV2')
            else:
                await query.edit_message_text("❌ Error al guardar los cambios después de eliminar el registro\\.", parse_mode='MarkdownV2')
        else:
             await query.edit_message_text("❌ Error: Índice inválido encontrado durante la confirmación\\.", parse_mode='MarkdownV2')
    elif decision == 'confirm_delreg_no':
        await query.edit_message_text("Eliminación cancelada\\.", parse_mode='MarkdownV2')
    else:
         await query.edit_message_text("Acción desconocida o índice no encontrado\\. Cancelando\\.", parse_mode='MarkdownV2')

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
            await context.bot.send_document(
                chat_id=chat_id,
                document=InputFile(DATA_FILE),
                caption=f"Backup de cuentas al {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            logger.info(f"Backup de cuentas enviado a {chat_id}")
            backup_successful = True
        except Exception as e:
            logger.error(f"Error enviando backup de cuentas: {e}")
            await context.bot.send_message(chat_id, f"Error al enviar backup de `{os.path.basename(DATA_FILE)}`\\.", parse_mode='MarkdownV2')
    else:
        await context.bot.send_message(chat_id, f"Info: No se encontró archivo `{os.path.basename(DATA_FILE)}` para backup\\.", parse_mode='MarkdownV2')

    # Backup registrations
    if os.path.exists(REG_DATA_FILE):
         try:
            await context.bot.send_document(
                chat_id=chat_id,
                document=InputFile(REG_DATA_FILE),
                caption=f"Backup de registros al {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            logger.info(f"Backup de registros enviado a {chat_id}")
            backup_successful = True
         except Exception as e:
            logger.error(f"Error enviando backup de registros: {e}")
            await context.bot.send_message(chat_id, f"Error al enviar backup de `{os.path.basename(REG_DATA_FILE)}`\\.", parse_mode='MarkdownV2')
    else:
        await context.bot.send_message(chat_id, f"Info: No se encontró archivo `{os.path.basename(REG_DATA_FILE)}` para backup\\.", parse_mode='MarkdownV2')

    if not backup_successful:
         await context.bot.send_message(chat_id, "No se pudo generar ningún backup\\. Comprueba los logs\\.", parse_mode='MarkdownV2')

    # Show menu again
    await send_main_menu(chat_id, context)


@callback_restricted
async def license_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'License Status' button."""
    query = update.callback_query
    chat_id = query.message.chat.id
    status_msg = "*Estado de Licencia*\n"
    status_msg += f"Activación: `{escape_markdown(ACTIVATION_DATE, version=2)}`\n"
    status_msg += f"Expiración: `{escape_markdown(EXPIRATION_DATE, version=2)}`\n"

    try:
        expiration_dt = datetime.strptime(EXPIRATION_DATE, '%Y-%m-%d')
        activation_dt = datetime.strptime(ACTIVATION_DATE, '%Y-%m-%d') # Also check activation format
        if datetime.now() > expiration_dt:
            status_msg += "Estado: 🔴 *Expirada*\n"
        else:
            days_left = (expiration_dt - datetime.now()).days
            status_msg += f"Estado: 🟢 *Activa* \\({days_left} días restantes\\)\n"
    except (ValueError, TypeError):
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
        if datetime.now() > expiration_dt:
            logger.critical(f"License expired on {EXPIRATION_DATE}. Stopping bot.")
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"Error Crítico: La licencia del bot expiró el {EXPIRATION_DATE}\\. El bot se ha detenido\\.",
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
                 #    await context.bot.send_message(ADMIN_CHAT_ID, f"Advertencia: La licencia expira en {days_left} días ({EXPIRATION_DATE}).")

    except (ValueError, TypeError) as e:
        logger.error(f"Invalid date format in config.env for EXPIRATION_DATE: {EXPIRATION_DATE}. Error: {e}")
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"Error Crítico: Formato de fecha de expiración inválido en config\\.env \\('{EXPIRATION_DATE}'\\)\\. El bot se detendrá\\.",
            parse_mode='MarkdownV2'
        )
        context.application.stop()


# --- Main Function ---
def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID or not EXPIRATION_DATE:
        logger.critical("Missing essential configuration (Token, Admin ID, Expiration Date). Exiting.")
        exit(1)

    # Initial license check before starting
    try:
        expiration_dt = datetime.strptime(EXPIRATION_DATE, '%Y-%m-%d')
        if datetime.now() > expiration_dt:
             logger.critical(f"License expired on {EXPIRATION_DATE}. Cannot start bot.")
             # Optionally send a message if possible, but likely fails if token is bad
             exit(1)
    except (ValueError, TypeError):
         logger.critical(f"Invalid expiration date format '{EXPIRATION_DATE}'. Cannot start bot.")
         exit(1)

    logger.info(f"License valid until {EXPIRATION_DATE}. Starting bot...")


    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Setup Job Queue for Periodic Tasks ---
    job_queue = application.job_queue
    # Check license every hour (3600 seconds)
    job_queue.run_repeating(check_license, interval=3600, first=10, name="license_check_hourly")
    # Add renewal check job here later
    # job_queue.run_repeating(check_renewals, interval=21600, first=60, name="renewal_check_6hourly")


    # --- Conversation Handlers ---
    # Registration
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
        fallbacks=[CommandHandler('cancel', cancel_command)], # Use generic cancel
    )

    # Add Account
    add_account_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_account_start, pattern='^add_account_prompt$')],
        states={
            ADD_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_add_service)],
            ADD_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_add_username)],
            ADD_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_add_password)],
            ADD_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_add_plan)],
            ADD_RENEWAL_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_add_renewal_date)],
            ADD_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_add_account)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
    )

    # View Account
    view_account_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(view_account_start, pattern='^view_account_prompt$')],
        states={
            VIEW_ACCOUNT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_view_account_number)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
    )

    # Delete Account
    delete_account_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(delete_account_start, pattern='^delete_account_prompt$')],
        states={
            DELETE_ACCOUNT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_delete_account_confirm)],
            DELETE_ACCOUNT_CONFIRM: [CallbackQueryHandler(process_delete_account_confirm, pattern='^confirm_delete_(yes|no)$')],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
    )

    # Edit Account
    edit_account_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_account_start, pattern='^edit_account_prompt$')],
        states={
            EDIT_ACCOUNT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_edit_account_field)],
            EDIT_ACCOUNT_FIELD: [CallbackQueryHandler(ask_edit_account_value, pattern='^edit_field_')], # Handles field buttons
            EDIT_ACCOUNT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit_account)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
    )

    # Delete Registration
    delete_reg_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(delete_reg_start, pattern='^delete_reg_prompt$')],
        states={
            DELETE_REG_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_delete_reg_confirm)],
            DELETE_REG_CONFIRM: [CallbackQueryHandler(process_delete_reg_confirm, pattern='^confirm_delreg_(yes|no)$')],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)],
    )


    # --- Command Handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel_command)) # Ensure cancel works outside conversations too
    application.add_handler(CommandHandler("list", list_accounts_command)) # Alias
    application.add_handler(CommandHandler("listreg", list_regs_command)) # Alias
    # Add other command handlers here (/licencia_expira, non-interactive /view, /delete, /delreg)


    # --- Add Conversation Handlers ---
    # Order matters if entry points could overlap, but here they are distinct callbacks
    application.add_handler(reg_conv_handler)
    application.add_handler(add_account_conv_handler)
    application.add_handler(view_account_conv_handler)
    application.add_handler(delete_account_conv_handler)
    application.add_handler(edit_account_conv_handler)
    application.add_handler(delete_reg_conv_handler)

    # --- Callback Query Handlers (Direct Actions / Fallbacks) ---
    # These handle buttons NOT used as entry points for conversations
    application.add_handler(CallbackQueryHandler(list_accounts_callback, pattern='^list_accounts$'))
    application.add_handler(CallbackQueryHandler(list_regs_callback, pattern='^list_regs$'))
    application.add_handler(CallbackQueryHandler(backup_data_callback, pattern='^backup_data$'))
    application.add_handler(CallbackQueryHandler(help_command, pattern='^show_help$')) # Use help_command for the button
    application.add_handler(CallbackQueryHandler(license_status_callback, pattern='^license_status$'))
    # Handlers for confirmation buttons inside conversations are part of the ConversationHandler states


    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is running. Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == '__main__':
    main()
