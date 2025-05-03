import logging
import time
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    JobQueue
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Importar funciones de base de datos y otros módulos necesarios
import database as db
# Importar desde utils.py
from utils import ADMIN_USER_ID, get_back_to_menu_keyboard
# Importar get_main_menu_keyboard desde user_handlers si se necesita aquí
from user_handlers import get_main_menu_keyboard as get_user_main_menu

logger = logging.getLogger(__name__)

# --- Constantes de Tiempo de Borrado ---
DELETE_DELAY_SECONDS = 20 # Segundos para borrar mensajes de confirmación

# --- Estados para Conversaciones ---
# add_user
GET_USER_ID, GET_NAME, GET_DAYS = range(3)
# add_account
GET_SERVICE, GET_EMAIL, GET_PROFILE, GET_PIN = range(3, 7)
# assign_account
GET_ASSIGN_USER_ID, GET_ASSIGN_ACCOUNT_ID = range(7, 9)

# --- Función auxiliar para borrar mensajes ---
async def delete_message_later(context: ContextTypes.DEFAULT_TYPE):
    """Borra un mensaje específico después de un tiempo."""
    job = context.job
    chat_id = job.data['chat_id']
    message_id = job.data['message_id']
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Mensaje {message_id} borrado automáticamente en chat {chat_id}.")
    except BadRequest as e:
        # Ignorar si el mensaje ya no existe o no se puede borrar
        if "Message to delete not found" in str(e) or "message can't be deleted" in str(e):
            logger.warning(f"No se pudo borrar automáticamente el mensaje {message_id} en chat {chat_id}: {e}")
        else:
            logger.error(f"Error inesperado al borrar automáticamente el mensaje {message_id} en chat {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Error general al borrar automáticamente el mensaje {message_id} en chat {chat_id}: {e}")

# --- Decorador Admin Required ---
def admin_required(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if ADMIN_USER_ID is None:
             logger.critical("ADMIN_USER_ID no está configurado. Denegando acceso de admin.")
             await update.message.reply_text("Error de configuración: ADMIN_USER_ID no definido.")
             return None # O manejar de otra forma
        if user_id != ADMIN_USER_ID:
            logger.warning(f"Intento de acceso de admin fallido por user_id: {user_id}")
            # No enviar mensaje si es callback, ya que callback_handlers lo maneja
            if update.message:
                 await update.message.reply_text("⛔ No tienes permiso para usar este comando.")
            # Si es callback, callback_handlers ya debería haber respondido o lo hará
            return None
        return await func(update, context, *args, **kwargs)
    return wrapper

# --- Conversación: Añadir/Actualizar Usuario (/adduser) ---

@admin_required
async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para añadir un usuario o procesa directamente si hay args."""
    args = context.args
    user_id = update.effective_user.id # Admin ID

    # Caso 1: Argumentos proporcionados (comportamiento antiguo)
    if len(args) == 3:
        try:
            target_user_id = int(args[0])
            name = args[1]
            days_active = int(args[2])

            if days_active <= 0:
                 await update.message.reply_text("Los días de activación deben ser un número positivo.")
                 return ConversationHandler.END # Terminar si hay error en args

            registration_ts = int(time.time())
            expiry_ts = registration_ts + (days_active * 24 * 60 * 60)
            expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%d/%m/%Y')

            db.add_user_db(target_user_id, name, "N/A", registration_ts, expiry_ts)

            name_escaped = db.escape_markdown(name)
            await update.message.reply_text(
                f"Usuario {name_escaped} (ID: `{target_user_id}`) añadido/actualizado directamente.\n"
                f"Acceso activo hasta: *{expiry_date}*.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationHandler.END # Terminar después de procesar args

        except ValueError:
            await update.message.reply_text("Error en argumentos: El user_id y los días deben ser números.")
            return ConversationHandler.END # Terminar si hay error en args
        except Exception as e:
            logger.error(f"Error al procesar /adduser con args para {args[0]}: {e}")
            await update.message.reply_text("Ocurrió un error al añadir al usuario directamente.")
            return ConversationHandler.END # Terminar si hay error en args

    # Caso 2: Sin argumentos o argumentos incorrectos -> Iniciar conversación
    elif len(args) != 0:
        # Si se dieron argumentos pero no 3, mostrar uso y terminar
        await update.message.reply_text(
            "Uso: `/adduser` (interactivo) o `/adduser <user_id> <nombre> <días>` (directo)",
            parse_mode=ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    # Iniciar conversación interactiva
    logger.info(f"Admin {user_id} iniciando conversación add_user.")
    await update.message.reply_text(
        "👤 Ok, vamos a añadir/actualizar un usuario.\n"
        "1️⃣ Por favor, envíame el *ID de Telegram* del usuario.\n\n"
        "Puedes cancelar en cualquier momento con /cancel.",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_USER_ID

async def received_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el ID del usuario, lo valida, pide el nombre y borra el mensaje del ID."""
    user_input = update.message.text
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id # ID del mensaje del usuario
    chat_id = update.effective_chat.id

    try:
        target_user_id = int(user_input)
        context.user_data['target_user_id'] = target_user_id
        logger.info(f"Admin {admin_id} en add_user: Recibido ID {target_user_id}.")

        # Borrar mensaje del usuario con el ID
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        except Exception as e:
            logger.warning(f"No se pudo borrar el mensaje del usuario (ID) {user_message_id}: {e}")

        await update.message.reply_text(
            f"🆔 ¡Entendido! ID: `{target_user_id}`.\n"
            "2️⃣ Ahora, envíame el *nombre* que quieres asignarle.",
            parse_mode=ParseMode.MARKDOWN
        )
        return GET_NAME
    except ValueError:
        logger.warning(f"Admin {admin_id} en add_user: Entrada inválida para ID: {user_input}")
        await update.message.reply_text(
            "Eso no parece un ID de Telegram válido. Debe ser un número entero.\n"
            "Por favor, envíame el ID de Telegram del usuario (solo números)."
        )
        return GET_USER_ID # Permanecer en el mismo estado

async def received_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre, pide los días y borra el mensaje del nombre."""
    name = update.message.text
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id # ID del mensaje del usuario
    chat_id = update.effective_chat.id
    context.user_data['target_name'] = name
    logger.info(f"Admin {admin_id} en add_user: Recibido nombre '{name}'.")

    # Borrar mensaje del usuario con el nombre
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e:
        logger.warning(f"No se pudo borrar el mensaje del usuario (nombre) {user_message_id}: {e}")

    await update.message.reply_text(
        f"👤 ¡Genial! Nombre: {name}.\n"
        "3️⃣ Finalmente, ¿cuántos *días* de acceso quieres darle? (Introduce solo el número).",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_DAYS

async def received_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe los días, guarda el usuario, borra mensajes y termina con botón."""
    user_input = update.message.text
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id # ID del mensaje del usuario
    chat_id = update.effective_chat.id
    job_queue = context.job_queue # Obtener JobQueue

    try:
        days_active = int(user_input)
        if days_active <= 0:
            await update.message.reply_text("El número de días debe ser positivo. Intenta de nuevo.")
            # No borrar mensaje de error del bot
            return GET_DAYS

        # Recuperar datos guardados
        target_user_id = context.user_data.get('target_user_id')
        name = context.user_data.get('target_name')

        if not target_user_id or not name:
             logger.error(f"Admin {admin_id} en add_user: Faltan datos en context.user_data al recibir días.")
             await update.message.reply_text("¡Ups! Algo salió mal y perdí los datos anteriores. Por favor, empieza de nuevo con /adduser.")
             context.user_data.clear()
             return ConversationHandler.END

        logger.info(f"Admin {admin_id} en add_user: Recibidos días {days_active}. Procesando...")

        # Borrar mensaje del usuario con los días
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        except Exception as e:
            logger.warning(f"No se pudo borrar el mensaje del usuario (días) {user_message_id}: {e}")

        # Calcular timestamps y guardar en BD
        registration_ts = int(time.time())
        expiry_ts = registration_ts + (days_active * 24 * 60 * 60)
        expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%d/%m/%Y')

        db.add_user_db(target_user_id, name, "N/A", registration_ts, expiry_ts)

        name_escaped = db.escape_markdown(name)

        # Enviar mensaje de confirmación y guardar su ID
        confirmation_message = await update.message.reply_text(
            f"✅ ¡Usuario añadido/actualizado con éxito!\n\n"
            f"🆔: `{target_user_id}`\n"
            f"👤 Nombre: {name_escaped}\n"
            f"⏳ Acceso por: {days_active} días\n"
            f"🗓️ Expira el: *{expiry_date}*",
            parse_mode=ParseMode.MARKDOWN,
            # Cambiar ReplyKeyboardRemove por el botón inline
            reply_markup=get_back_to_menu_keyboard()
        )
        confirmation_message_id = confirmation_message.message_id
        logger.info(f"Admin {admin_id} completó add_user para {target_user_id}.")

        # Programar borrado del mensaje de confirmación después de X segundos
        delay = 15 # Segundos
        job_queue.run_once(
            delete_message_later,
            when=timedelta(seconds=delay),
            data={'chat_id': chat_id, 'message_id': confirmation_message_id},
            name=f'delete_{chat_id}_{confirmation_message_id}'
        )
        logger.info(f"Programado borrado del mensaje {confirmation_message_id} en {delay} segundos.")

        context.user_data.clear() # Limpiar datos temporales
        return ConversationHandler.END

    except ValueError:
        logger.warning(f"Admin {admin_id} en add_user: Entrada inválida para días: {user_input}")
        await update.message.reply_text(
            "Eso no parece un número de días válido. Debe ser un número entero positivo.\n"
            "Por favor, introduce el número de días."
        )
        return GET_DAYS # Permanecer en el mismo estado
    except Exception as e:
        logger.error(f"Error al procesar received_days para admin {admin_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error inesperado al guardar el usuario. Intenta de nuevo con /adduser.")
        context.user_data.clear()
        return ConversationHandler.END

async def cancel_adduser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación de añadir usuario."""
    admin_id = update.effective_user.id
    logger.info(f"Admin {admin_id} canceló la conversación add_user.")
    await update.message.reply_text(
        "Operación cancelada.", reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END

# Crear el ConversationHandler para adduser
adduser_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("adduser", add_user_start)],
    states={
        GET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_user_id)],
        GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_name)],
        GET_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_days)],
    },
    fallbacks=[CommandHandler("cancel", cancel_adduser)],
)

# --- Conversación: Añadir Cuenta/Perfil (/add) ---

@admin_required
async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para añadir un perfil de cuenta."""
    admin_id = update.effective_user.id
    logger.info(f"Admin {admin_id} iniciando conversación add_account.")
    await update.message.reply_text(
        "➕ Ok, vamos a añadir un nuevo perfil de cuenta.\n"
        "1️⃣ Por favor, envíame el nombre del *Servicio* (ej: Netflix, Spotify).\n\n"
        "Puedes cancelar en cualquier momento con /cancel.",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_SERVICE

async def received_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el servicio, pide el email y borra mensaje."""
    service = update.message.text.strip().capitalize()
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    context.user_data['add_service'] = service
    logger.info(f"Admin {admin_id} en add_account: Recibido servicio '{service}'.")

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e: logger.warning(f"No se pudo borrar mensaje (servicio) {user_message_id}: {e}")

    await update.message.reply_text(
        f"✔️ Servicio: {service}.\n"
        "2️⃣ Ahora, envíame el *Email* de la cuenta principal asociada.",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_EMAIL

async def received_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el email, pide el nombre del perfil y borra mensaje."""
    email = update.message.text.strip()
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    # Validación simple de email (opcional)
    if '@' not in email or '.' not in email.split('@')[-1]:
        await update.message.reply_text("📧 Eso no parece un email válido. Intenta de nuevo.")
        return GET_EMAIL # Permanecer en el estado

    context.user_data['add_email'] = email
    logger.info(f"Admin {admin_id} en add_account: Recibido email '{email}'.")

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e: logger.warning(f"No se pudo borrar mensaje (email) {user_message_id}: {e}")

    await update.message.reply_text(
        f"📧 Email: {email}.\n"
        "3️⃣ Ahora, envíame el *Nombre del Perfil* específico que quieres añadir.",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_PROFILE

async def received_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nombre del perfil, pide el PIN y borra mensaje."""
    profile_name = update.message.text.strip()
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    context.user_data['add_profile_name'] = profile_name
    logger.info(f"Admin {admin_id} en add_account: Recibido perfil '{profile_name}'.")

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception as e: logger.warning(f"No se pudo borrar mensaje (perfil) {user_message_id}: {e}")

    await update.message.reply_text(
        f"👤 Perfil: {profile_name}.\n"
        "4️⃣ Finalmente, envíame el *PIN* de acceso para este perfil (si no tiene, escribe '0000' o 'N/A').",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_PIN

async def received_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el PIN, guarda la cuenta y termina."""
    pin = update.message.text.strip()
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    try:
        # Recuperar datos
        service = context.user_data.get('add_service')
        email = context.user_data.get('add_email')
        profile_name = context.user_data.get('add_profile_name')

        if not all([service, email, profile_name]):
             logger.error(f"Admin {admin_id} en add_account: Faltan datos en context.user_data al recibir PIN.")
             await update.message.reply_text("¡Ups! Algo salió mal. Por favor, empieza de nuevo con /add.")
             context.user_data.clear()
             return ConversationHandler.END

        logger.info(f"Admin {admin_id} en add_account: Recibido PIN '{pin}'. Procesando...")

        # Borrar mensaje del usuario con el PIN
        try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        except Exception as e: logger.warning(f"No se pudo borrar mensaje (PIN) {user_message_id}: {e}")

        # Guardar en BD
        db.add_account_db(service, email, profile_name, pin)

        service_escaped = db.escape_markdown(service)
        profile_escaped = db.escape_markdown(profile_name)
        email_escaped = db.escape_markdown(email) # Escapar por si acaso

        # Enviar confirmación y programar borrado
        confirmation_message = await update.message.reply_text(
            f"✅ ¡Perfil añadido/actualizado con éxito!\n\n"
            f"🔧 Servicio: {service_escaped}\n"
            f"📧 Email Cuenta: {email_escaped}\n"
            f"👤 Perfil: {profile_escaped}\n"
            f"🔑 PIN: `{db.escape_markdown(pin)}`", # Escapar PIN también
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_to_menu_keyboard()
        )
        job_queue.run_once(
            delete_message_later,
            when=timedelta(seconds=DELETE_DELAY_SECONDS),
            data={'chat_id': chat_id, 'message_id': confirmation_message.message_id},
            name=f'delete_{chat_id}_{confirmation_message.message_id}'
        )
        logger.info(f"Admin {admin_id} completó add_account para {service} - {profile_name}.")
        context.user_data.clear()
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error al procesar received_pin para admin {admin_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error inesperado al guardar el perfil. Intenta de nuevo con /add.")
        context.user_data.clear()
        return ConversationHandler.END

async def cancel_add_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación de añadir cuenta."""
    admin_id = update.effective_user.id
    logger.info(f"Admin {admin_id} canceló la conversación add_account.")
    await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

add_account_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("add", add_account_start)],
    states={
        GET_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_service)],
        GET_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_email)],
        GET_PROFILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_profile)],
        GET_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_pin)],
    },
    fallbacks=[CommandHandler("cancel", cancel_add_account)],
)

# --- Conversación: Asignar Cuenta a Usuario (/assign) ---

@admin_required
async def assign_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para asignar una cuenta."""
    admin_id = update.effective_user.id
    logger.info(f"Admin {admin_id} iniciando conversación assign_account.")
    # Podríamos mostrar aquí la lista de usuarios y cuentas para facilitar, pero sería complejo.
    # Mantenemos la petición de IDs.
    await update.message.reply_text(
        "🔗 Ok, vamos a asignar un perfil a un usuario.\n"
        "1️⃣ Por favor, envíame el *ID de Telegram* del usuario al que quieres asignar.\n\n"
        "Puedes cancelar en cualquier momento con /cancel.",
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_ASSIGN_USER_ID

async def received_assign_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el ID del usuario, valida, pide ID de cuenta y borra mensaje."""
    user_input = update.message.text
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id

    try:
        target_user_id = int(user_input)
        # Validar si el usuario existe (opcional pero bueno)
        user_info = db.get_user_status_db(target_user_id)
        if not user_info and target_user_id != ADMIN_USER_ID: # Permitir asignar al admin si se quiere
             await update.message.reply_text(f"⚠️ Usuario con ID `{target_user_id}` no encontrado. Verifica el ID e intenta de nuevo.", parse_mode=ParseMode.MARKDOWN)
             return GET_ASSIGN_USER_ID

        context.user_data['assign_user_id'] = target_user_id
        user_name = user_info.get('name', f'ID {target_user_id}') if user_info else "Admin"
        logger.info(f"Admin {admin_id} en assign_account: Recibido User ID {target_user_id} ({user_name}).")

        try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        except Exception as e: logger.warning(f"No se pudo borrar mensaje (assign user id) {user_message_id}: {e}")

        await update.message.reply_text(
            f"👤 Usuario: {db.escape_markdown(user_name)} (`{target_user_id}`).\n"
            "2️⃣ Ahora, envíame el *ID del Perfil/Cuenta* que quieres asignarle.\n"
            "_(Puedes obtener los IDs con /listallaccounts)_",
            parse_mode=ParseMode.MARKDOWN
        )
        return GET_ASSIGN_ACCOUNT_ID
    except ValueError:
        await update.message.reply_text("❌ ID de usuario inválido. Debe ser un número. Intenta de nuevo.")
        return GET_ASSIGN_USER_ID

async def received_assign_account_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el ID de la cuenta, realiza la asignación y termina."""
    user_input = update.message.text
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    job_queue = context.job_queue

    try:
        account_id = int(user_input)
        target_user_id = context.user_data.get('assign_user_id')

        if not target_user_id:
             logger.error(f"Admin {admin_id} en assign_account: Faltan datos en context.user_data al recibir account ID.")
             await update.message.reply_text("¡Ups! Algo salió mal. Por favor, empieza de nuevo con /assign.")
             context.user_data.clear()
             return ConversationHandler.END

        logger.info(f"Admin {admin_id} en assign_account: Recibido Account ID {account_id} para User ID {target_user_id}. Procesando...")

        # Borrar mensaje del usuario con el account ID
        try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
        except Exception as e: logger.warning(f"No se pudo borrar mensaje (assign account id) {user_message_id}: {e}")

        # Realizar asignación en BD
        success = db.assign_account_to_user(target_user_id, account_id)

        if success:
            user_info = db.get_user_status_db(target_user_id)
            account_info = db.get_account_details_by_id(account_id)
            user_name = user_info.get('name', f'ID {target_user_id}') if user_info else f'ID {target_user_id}'
            account_desc = f"{account_info['service']} ({account_info['profile_name']})" if account_info else f'ID {account_id}'
            user_name_escaped = db.escape_markdown(user_name)
            account_desc_escaped = db.escape_markdown(account_desc)

            confirmation_text = f"✅ ¡Asignación realizada!\n\n👤 Usuario: {user_name_escaped} (`{target_user_id}`)\n🔗 Perfil: {account_desc_escaped} (`{account_id}`)"
        else:
            # La BD ya loggeó el error específico (no existe, ya asignado, etc.)
            confirmation_text = f"❌ No se pudo realizar la asignación.\nVerifica que los IDs sean correctos y que la asignación no exista ya."

        # Enviar confirmación/error y programar borrado
        confirmation_message = await update.message.reply_text(
            confirmation_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_to_menu_keyboard()
        )
        job_queue.run_once(
            delete_message_later,
            when=timedelta(seconds=DELETE_DELAY_SECONDS),
            data={'chat_id': chat_id, 'message_id': confirmation_message.message_id},
            name=f'delete_{chat_id}_{confirmation_message.message_id}'
        )
        logger.info(f"Admin {admin_id} completó assign_account para user {target_user_id}, account {account_id}. Resultado: {success}")
        context.user_data.clear()
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ ID de cuenta inválido. Debe ser un número. Intenta de nuevo.")
        return GET_ASSIGN_ACCOUNT_ID
    except Exception as e:
        logger.error(f"Error al procesar received_assign_account_id para admin {admin_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error inesperado al asignar la cuenta. Intenta de nuevo con /assign.")
        context.user_data.clear()
        return ConversationHandler.END

async def cancel_assign_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancela la conversación de asignar cuenta."""
    admin_id = update.effective_user.id
    logger.info(f"Admin {admin_id} canceló la conversación assign_account.")
    await update.message.reply_text("Operación cancelada.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

assign_account_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("assign", assign_account_start)],
    states={
        GET_ASSIGN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_assign_user_id)],
        GET_ASSIGN_ACCOUNT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_assign_account_id)],
    },
    fallbacks=[CommandHandler("cancel", cancel_assign_account)],
)


# --- Handlers Simples (Listados) - Modificados ---

async def _send_paginated_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup):
    """Envía o edita un mensaje, paginando si es necesario y programando borrado."""
    query = update.callback_query
    is_callback = bool(query)
    chat_id = update.effective_chat.id
    job_queue = context.job_queue
    max_length = 4096 # Límite de Telegram

    sent_messages_ids = []

    try:
        if is_callback:
            # Editar mensaje original (puede truncar si es muy largo)
            edited_message = await query.edit_message_text(
                text=text[:max_length],
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
            sent_messages_ids.append(edited_message.message_id)
            if len(text) > max_length:
                 logger.warning("Mensaje editado truncado por longitud.")
                 # Opcional: enviar el resto en mensajes nuevos
                 # for i in range(max_length, len(text), max_length):
                 #    msg = await context.bot.send_message(chat_id, text[i:i+max_length], parse_mode=ParseMode.MARKDOWN)
                 #    sent_messages_ids.append(msg.message_id)
        else:
            # Borrar comando original si es posible
            if update.message:
                try: await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
                except Exception: pass # Ignorar si no se puede borrar

            # Enviar mensaje(s) paginados
            for i in range(0, len(text), max_length):
                # Añadir teclado solo al último mensaje
                current_keyboard = keyboard if (i + max_length >= len(text)) else None
                msg = await context.bot.send_message(
                    chat_id=chat_id,
                    text=text[i:i+max_length],
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=current_keyboard
                )
                sent_messages_ids.append(msg.message_id)

        # Programar borrado de todos los mensajes enviados/editados
        for msg_id in sent_messages_ids:
            job_queue.run_once(
                delete_message_later,
                when=timedelta(seconds=DELETE_DELAY_SECONDS),
                data={'chat_id': chat_id, 'message_id': msg_id},
                name=f'delete_{chat_id}_{msg_id}'
            )
            logger.info(f"Programado borrado del mensaje {msg_id} en {DELETE_DELAY_SECONDS} segundos.")

    except BadRequest as e:
        logger.error(f"Error de Telegram al enviar/editar/borrar mensaje: {e}")
        # Intentar enviar un mensaje de error simple si falla la edición/envío principal
        if not sent_messages_ids:
             try: await context.bot.send_message(chat_id, "⚠️ Ocurrió un error al mostrar la información.")
             except Exception as send_e: logger.error(f"No se pudo enviar mensaje de error: {send_e}")
    except Exception as e:
        logger.error(f"Error inesperado en _send_paginated_or_edit: {e}", exc_info=True)
        if not sent_messages_ids:
             try: await context.bot.send_message(chat_id, "⚠️ Ocurrió un error inesperado.")
             except Exception as send_e: logger.error(f"No se pudo enviar mensaje de error: {send_e}")


@admin_required
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Admin) Lista todos los usuarios autorizados."""
    query = update.callback_query
    is_callback = bool(query)
    if is_callback: await query.answer()

    try:
        users = db.list_users_db()
        if not users:
            user_list_text = "ℹ️ No hay usuarios registrados."
        else:
            # ... (construcción de user_list_text - sin cambios) ...
            current_ts = int(time.time())
            user_list_text = "👥 *Usuarios Registrados:*\n"
            for user in users:
                expiry_date = datetime.fromtimestamp(user['expiry_ts']).strftime('%d/%m/%Y')
                status = "✅ Activo" if current_ts <= user['expiry_ts'] else "❌ Expirado"
                name_escaped = db.escape_markdown(user['name'])
                user_list_text += (
                    f"\n👤 ID: `{user['user_id']}`\n"
                    f"   Nombre: {name_escaped}\n"
                    f"   Expira: {expiry_date} ({status})"
                )

        final_keyboard = get_back_to_menu_keyboard() # Siempre botón volver para listados
        await _send_paginated_or_edit(update, context, user_list_text, final_keyboard)

    except Exception as e:
        logger.error(f"Error al procesar list_users: {e}", exc_info=True)
        await _send_paginated_or_edit(update, context, "⚠️ Ocurrió un error al listar usuarios.", get_back_to_menu_keyboard())


@admin_required
async def list_all_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Admin) Lista todas las cuentas/perfiles registrados con su ID."""
    query = update.callback_query
    is_callback = bool(query)
    if is_callback: await query.answer()

    try:
        all_accounts = db.get_all_accounts_with_ids()
        if not all_accounts:
            message = "ℹ️ No hay ninguna cuenta registrada en la base de datos."
        else:
            # ... (construcción de message - sin cambios) ...
            accounts_text_list = ["🧾 *Todas las Cuentas Registradas:*"]
            for acc in all_accounts:
                acc_id = acc.get('id', '??')
                service = acc.get('service', 'N/A')
                email = acc.get('email', 'N/A')
                profile = acc.get('profile_name', 'N/A')
                pin = acc.get('pin', 'N/A')
                service_escaped = db.escape_markdown(service)
                email_escaped = db.escape_markdown(email)
                profile_escaped = db.escape_markdown(profile)
                pin_escaped = db.escape_markdown(pin)
                accounts_text_list.append(
                    f"\n*🆔 ID:* `{acc_id}`\n"
                    f"  🔧 Servicio: {service_escaped}\n"
                    f"  📧 Email: {email_escaped}\n"
                    f"  👤 Perfil: {profile_escaped}\n"
                    f"  🔑 PIN: `{pin_escaped}`"
                )
            message = "\n".join(accounts_text_list)
            message += "\n\n_Usa el ID para asignar cuentas con /assign_"


        final_keyboard = get_back_to_menu_keyboard()
        await _send_paginated_or_edit(update, context, message, final_keyboard)

    except Exception as e:
        logger.error(f"Error al procesar list_all_accounts: {e}", exc_info=True)
        await _send_paginated_or_edit(update, context, "⚠️ Ocurrió un error al obtener la lista completa de cuentas.", get_back_to_menu_keyboard())


@admin_required
async def list_assignments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Admin) Lista todas las asignaciones de cuentas a usuarios."""
    query = update.callback_query
    is_callback = bool(query)
    if is_callback: await query.answer()

    try:
        all_assignments = db.get_all_assignments()
        if not all_assignments:
            message = "ℹ️ No hay ninguna asignación registrada."
        else:
            # ... (construcción de message - sin cambios) ...
            assignments_text_list = ["🔗 *Todas las Asignaciones:*"]
            all_assignments.sort(key=lambda x: (x.get('user_name', x.get('user_id')), x.get('service', ''), x.get('profile_name', '')))
            current_user_id = None
            for assign in all_assignments:
                assign_user_id = assign.get('user_id')
                user_name = assign.get('user_name', f'ID {assign_user_id}')
                account_id = assign.get('account_id')
                service = assign.get('service', 'N/A')
                profile = assign.get('profile_name', 'N/A')
                user_name_escaped = db.escape_markdown(user_name)
                service_escaped = db.escape_markdown(service)
                profile_escaped = db.escape_markdown(profile)
                if assign_user_id != current_user_id:
                    assignments_text_list.append(f"\n👤 *Usuario:* {user_name_escaped} (`{assign_user_id}`)")
                    current_user_id = assign_user_id
                assignments_text_list.append(
                    f"  - 🆔 `{account_id}`: {service_escaped} ({profile_escaped})"
                )
            message = "\n".join(assignments_text_list)

        final_keyboard = get_back_to_menu_keyboard()
        await _send_paginated_or_edit(update, context, message, final_keyboard)

    except Exception as e:
        logger.error(f"Error al procesar list_assignments: {e}", exc_info=True)
        await _send_paginated_or_edit(update, context, "⚠️ Ocurrió un error al obtener la lista de asignaciones.", get_back_to_menu_keyboard())
