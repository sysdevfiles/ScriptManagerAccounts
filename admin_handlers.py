import logging
import time
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    JobQueue,
    CallbackQueryHandler
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Importar funciones de base de datos y otros módulos necesarios
import database as db
# Importar desde utils.py
from utils import ADMIN_USER_ID, get_back_to_menu_keyboard, delete_message_later, DELETE_DELAY_SECONDS, generic_cancel_conversation # Actualizar importación

logger = logging.getLogger(__name__)

# --- Constantes de Tiempo de Borrado ---
DELETE_DELAY_SECONDS = 20 # Segundos para borrar mensajes de confirmación

# --- Constantes de Callback Data (Admin) ---
CALLBACK_ADMIN_ADD_USER_PROMPT = 'admin_add_user_prompt'
CALLBACK_ADMIN_LIST_USERS = 'admin_list_users'
CALLBACK_ADMIN_EDIT_USER_PROMPT = 'admin_edit_user_prompt' # Para botón Editar Usuario (placeholder)
CALLBACK_ADMIN_DELETE_USER_START = 'admin_delete_user_start' # Para iniciar conversación de borrado desde botón

# --- Estados para Conversaciones ---
# add_user
GET_USER_ID, GET_NAME, GET_DAYS = range(3)
# delete_user
SELECT_USER_TO_DELETE, CONFIRM_USER_DELETE = range(3, 5) # Nuevos estados
# edit_user (Nuevos estados)
SELECT_USER_TO_EDIT, CHOOSE_FIELD_TO_EDIT, GET_NEW_NAME, GET_NEW_DAYS = range(5, 9)

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
    """Inicia la conversación para añadir/actualizar un usuario o procesa directamente si hay args."""
    query = update.callback_query
    is_callback = bool(query)
    admin_id = update.effective_user.id
    logger.info(f"Admin {admin_id} iniciando add_user (is_callback: {is_callback}). Args: {context.args}")

    if context.args and len(context.args) == 3:
        # Procesar argumentos directamente
        user_id_str, name, days_str = context.args
        # ... (validación de user_id_str, name, days_str) ...
        if not user_id_str.isdigit():
            await update.message.reply_text("❌ El ID de usuario debe ser numérico.", reply_markup=get_back_to_menu_keyboard())
            return ConversationHandler.END
        if not days_str.isdigit() or int(days_str) <= 0:
            await update.message.reply_text("❌ Los días deben ser un número positivo.", reply_markup=get_back_to_menu_keyboard())
            return ConversationHandler.END

        user_id = int(user_id_str)
        days = int(days_str)
        expiry_ts = int(time.time()) + days * 86400  # 86400 segundos en un día
        registration_ts = int(time.time())
        payment_method = 'N/A' # Valor por defecto para el nuevo campo

        try:
            # Pasar todos los argumentos requeridos, incluyendo el nuevo payment_method
            db.add_user_db(user_id, name, payment_method, registration_ts, expiry_ts)
            expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%d/%m/%Y')
            success_message = f"✅ Usuario `{user_id}` ({name}) añadido/actualizado. Acceso válido hasta: {expiry_date}."
            await update.message.reply_text(success_message, parse_mode=ParseMode.MARKDOWN, reply_markup=get_back_to_menu_keyboard())
            logger.info(f"Admin {admin_id} añadió/actualizó usuario {user_id} ({name}) directamente. Expira: {expiry_date}")
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Error al añadir/actualizar usuario {user_id} directamente: {e}", exc_info=True)
            await update.message.reply_text("❌ Ocurrió un error al guardar en la base de datos.", reply_markup=get_back_to_menu_keyboard())
            return ConversationHandler.END

    else: # Start conversation (no args or callback)
        if is_callback:
            # await query.answer() # Ya se hizo en callback_handler
            pass # No es necesario responder de nuevo
        message_text = "Por favor, dime el ID de Telegram del usuario que quieres añadir o actualizar:"
        # Usar None como teclado al editar el mensaje inicial de la conversación
        await _send_paginated_or_edit(update, context, message_text, None, schedule_delete=False)
        logger.info(f"Admin {admin_id} iniciando conversación add_user. Pidiendo USER_ID.")
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
    """Recibe los días, guarda/actualiza el usuario, borra mensajes y termina con botón."""
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
        payment_method = 'N/A' # Valor por defecto para el nuevo campo

        # add_user_db actúa como REPLACE, por lo que actualiza si ya existe
        db.add_user_db(target_user_id, name, payment_method, registration_ts, expiry_ts)

        name_escaped = db.escape_markdown(name)

        # Enviar mensaje de confirmación y guardar su ID
        confirmation_message = await update.message.reply_text(
            f"✅ ¡Usuario añadido/actualizado con éxito!\n\n" # Texto ajustado
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

# Crear el ConversationHandler para adduser
adduser_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("adduser", add_user_start),
        # Añadir la entrada por botón para iniciar la conversación
        CallbackQueryHandler(add_user_start, pattern=f"^{CALLBACK_ADMIN_ADD_USER_PROMPT}$")
        ],
    states={
        GET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_user_id)],
        GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_name)],
        GET_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_days)],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: generic_cancel_conversation(u, c, "add_user"))], # Usar cancelador genérico
)

# --- Conversación: Eliminar Usuario (/deleteuser) ---

@admin_required
async def delete_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para eliminar un usuario autorizado (vía comando o botón)."""
    admin_id = update.effective_user.id
    is_callback = update.callback_query is not None
    # Log de entrada
    logger.info(f"Admin {admin_id} iniciando delete_user_start (is_callback: {is_callback}).")
    if is_callback:
        try:
            await update.callback_query.answer() # Responder al callback si viene de botón
            logger.debug("Callback query answered in delete_user_start.")
        except Exception as e:
            logger.error(f"Error answering callback query in delete_user_start: {e}")

    try:
        users = db.list_users_db()
        # Log después de obtener usuarios
        logger.debug(f"delete_user_start: Fetched {len(users)} users from DB.")

        active_users = [u for u in users if u['user_id'] != admin_id] # No permitir eliminar al propio admin
        # Log después de filtrar usuarios
        logger.debug(f"delete_user_start: Found {len(active_users)} active users (excluding admin).")

        if not active_users:
            message_text = "ℹ️ No hay otros usuarios registrados para eliminar."
            keyboard = get_back_to_menu_keyboard()
            logger.info("delete_user_start: No active users found to delete. Sending info message.")
            await _send_paginated_or_edit(update, context, message_text, keyboard)
            return ConversationHandler.END

        buttons = []
        for user in active_users:
            label = f"ID: {user['user_id']} - {user['name']}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"deluser_{user['user_id']}")])

        users_keyboard = InlineKeyboardMarkup(buttons)
        message_text = "🗑️ Selecciona el usuario que deseas eliminar 👇:\n\nPuedes cancelar con /cancel." # Añadido texto inicial

        # Log antes de enviar/editar mensaje
        logger.debug("delete_user_start: Preparing to send user list for deletion.")
        await _send_paginated_or_edit(update, context, message_text, users_keyboard)
        logger.info("delete_user_start: User list sent. Returning SELECT_USER_TO_DELETE.")
        return SELECT_USER_TO_DELETE

    except Exception as e:
        # Log de error general en la función
        logger.error(f"Error in delete_user_start: {e}", exc_info=True)
        error_message = "❌ Ocurrió un error al iniciar el proceso de eliminación."
        try:
            await _send_paginated_or_edit(update, context, error_message, get_back_to_menu_keyboard())
        except Exception as send_e:
            logger.error(f"Failed to send error message in delete_user_start: {send_e}")
        return ConversationHandler.END

async def received_user_delete_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la selección del usuario a eliminar, pide confirmación."""
    query = update.callback_query
    await query.answer()
    user_id_to_delete_str = query.data.split("deluser_")[-1]
    admin_id = query.from_user.id

    try:
        user_id_to_delete = int(user_id_to_delete_str)

        if user_id_to_delete == admin_id:
             await query.edit_message_text("⛔ No puedes eliminarte a ti mismo.", reply_markup=get_back_to_menu_keyboard())
             return ConversationHandler.END

        user_info = db.get_user_status_db(user_id_to_delete)
        if not user_info:
             await query.edit_message_text("❌ Usuario no encontrado.", reply_markup=get_back_to_menu_keyboard())
             return ConversationHandler.END

        context.user_data['delete_user_id'] = user_id_to_delete
        logger.info(f"Admin {admin_id} en delete_user: Seleccionado ID {user_id_to_delete} para eliminar.")

        confirm_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Sí, eliminar", callback_data="deleteuser_confirm_yes")],
            [InlineKeyboardButton("❌ No, cancelar", callback_data="deleteuser_confirm_no")]
        ])

        name_escaped = db.escape_markdown(user_info.get('name', 'N/A'))
        await query.edit_message_text(
            text=f"❓ ¿Estás seguro de que quieres eliminar al usuario *{name_escaped}* (ID: `{user_id_to_delete}`) de la lista de autorizados?\n"
                 f"⚠️ ¡Esta acción no se puede deshacer!",
            reply_markup=confirm_keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return CONFIRM_USER_DELETE
    except ValueError:
        logger.error(f"Error al parsear user_id para eliminar: {user_id_to_delete_str}")
        await query.edit_message_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error en received_user_delete_selection: {e}", exc_info=True)
        await query.edit_message_text("❌ Error inesperado. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END


async def confirm_user_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirma o cancela la eliminación del usuario."""
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id
    is_callback = bool(query) # Define is_callback here
    confirmation = query.data
    user_id_to_delete = context.user_data.get('delete_user_id')
    job_queue = context.job_queue
    chat_id = update.effective_chat.id

    if not user_id_to_delete:
         logger.error(f"Admin {admin_id} en confirm_user_delete: Falta delete_user_id.")
         await query.edit_message_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
         context.user_data.clear()
         return ConversationHandler.END

    if confirmation == "deleteuser_confirm_yes":
        logger.info(f"Admin {admin_id} confirma eliminar usuario ID {user_id_to_delete}.")
        success = db.delete_user_db(user_id=user_id_to_delete)

        if success:
            confirmation_text = f"🗑️ ¡Usuario ID `{user_id_to_delete}` eliminado correctamente de la lista de autorizados!"
            # Opcional: Notificar al usuario eliminado
            # try:
            #     await context.bot.send_message(chat_id=user_id_to_delete, text="Tu acceso al bot ha sido revocado por el administrador.")
            # except Exception as e:
            #     logger.warning(f"No se pudo notificar al usuario eliminado {user_id_to_delete}: {e}")
        else:
            confirmation_text = f"❌ No se pudo eliminar al usuario ID `{user_id_to_delete}`. Puede que ya no exista."

        # Usar _send_paginated_or_edit para manejar el mensaje final y su borrado
        await _send_paginated_or_edit(update, context, confirmation_text, get_back_to_menu_keyboard())

    else: # deleteuser_confirm_no
        logger.info(f"Admin {admin_id} canceló la eliminación del usuario ID {user_id_to_delete}.")
    if is_callback:
        await update.callback_query.answer()

    context.user_data.clear() # Limpiar datos de la conversación
    return ConversationHandler.END # Terminar la conversación aquí

# Definir el ConversationHandler para deleteuser
deleteuser_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("deleteuser", delete_user_start),
        CallbackQueryHandler(delete_user_start, pattern=f"^{CALLBACK_ADMIN_DELETE_USER_START}$")
        ],
    states={
        SELECT_USER_TO_DELETE: [CallbackQueryHandler(received_user_delete_selection, pattern="^deluser_")],
        CONFIRM_USER_DELETE: [CallbackQueryHandler(confirm_user_delete, pattern="^deleteuser_confirm_")],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: generic_cancel_conversation(u, c, "delete_user"))],
    allow_reentry=True
)


# --- Conversación: Editar Usuario (/edituser) ---

@admin_required
async def edit_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia la conversación para editar un usuario autorizado (vía comando o botón)."""
    admin_id = update.effective_user.id
    is_callback = update.callback_query is not None
    logger.info(f"Admin {admin_id} iniciando edit_user_start (is_callback: {is_callback}).")
    if is_callback:
        try:
            await update.callback_query.answer()
            logger.debug("Callback query answered in edit_user_start.")
        except Exception as e:
            logger.error(f"Error answering callback query in edit_user_start: {e}")

    try:
        users = db.list_users_db()
        editable_users = [u for u in users if u['user_id'] != admin_id] # No permitir editar al propio admin

        if not editable_users:
            message_text = "ℹ️ No hay otros usuarios registrados para editar."
            keyboard = get_back_to_menu_keyboard()
            await _send_paginated_or_edit(update, context, message_text, keyboard)
            return ConversationHandler.END

        buttons = []
        for user in editable_users:
            label = f"ID: {user['user_id']} - {user['name']}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"edituser_{user['user_id']}")])

        users_keyboard = InlineKeyboardMarkup(buttons)
        message_text = "✏️ Selecciona el usuario que deseas editar 👇:\n\nPuedes cancelar con /cancel."

        await _send_paginated_or_edit(update, context, message_text, users_keyboard, schedule_delete=False) # No borrar lista de selección
        return SELECT_USER_TO_EDIT

    except Exception as e:
        logger.error(f"Error in edit_user_start: {e}", exc_info=True)
        error_message = "❌ Ocurrió un error al iniciar el proceso de edición."
        try:
            await _send_paginated_or_edit(update, context, error_message, get_back_to_menu_keyboard())
        except Exception as send_e:
            logger.error(f"Failed to send error message in edit_user_start: {send_e}")
        return ConversationHandler.END


async def received_user_edit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe la selección del usuario a editar, pide qué campo editar."""
    query = update.callback_query
    await query.answer()
    user_id_to_edit_str = query.data.split("edituser_")[-1]
    admin_id = query.from_user.id

    # Añadir logging para depurar el valor recibido
    logger.debug(f"received_user_edit_selection: Received query.data='{query.data}', parsed user_id_str='{user_id_to_edit_str}'")

    try:
        user_id_to_edit = int(user_id_to_edit_str)
        user_info = db.get_user_status_db(user_id_to_edit)

        if not user_info:
             await query.edit_message_text("❌ Usuario no encontrado.", reply_markup=get_back_to_menu_keyboard())
             return ConversationHandler.END

        context.user_data['edit_user_id'] = user_id_to_edit
        context.user_data['edit_user_name'] = user_info.get('name', 'N/A') # Guardar nombre actual
        logger.info(f"Admin {admin_id} en edit_user: Seleccionado ID {user_id_to_edit} ({user_info.get('name', 'N/A')}) para editar.")

        buttons = [
            [InlineKeyboardButton("👤 Nombre", callback_data="editfield_name")],
            [InlineKeyboardButton("⏳ Días de Acceso", callback_data="editfield_days")]
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        name_escaped = db.escape_markdown(user_info.get('name', 'N/A'))
        await query.edit_message_text(
            text=f"Editando a *{name_escaped}* (ID: `{user_id_to_edit}`).\n¿Qué deseas modificar?",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        return CHOOSE_FIELD_TO_EDIT
    except ValueError:
        # Log con nivel error si la conversión falla
        logger.error(f"Error al parsear user_id para editar: query.data='{query.data}', user_id_to_edit_str='{user_id_to_edit_str}'")
        await query.edit_message_text("❌ Error interno. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error en received_user_edit_selection: {e}", exc_info=True)
        await query.edit_message_text("❌ Error inesperado. Intenta de nuevo.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

async def received_field_edit_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el campo a editar, pide el nuevo valor."""
    query = update.callback_query
    await query.answer()
    field_to_edit = query.data.split("editfield_")[-1]
    context.user_data['edit_field'] = field_to_edit
    user_id_to_edit = context.user_data.get('edit_user_id')
    user_name = context.user_data.get('edit_user_name', 'Usuario')

    if not user_id_to_edit:
        logger.error("Falta edit_user_id en received_field_edit_selection.")
        await query.edit_message_text("❌ Error interno. Reinicia la edición.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    name_escaped = db.escape_markdown(user_name)
    if field_to_edit == "name":
        prompt_text = f"✏️ Editando nombre de *{name_escaped}* (ID: `{user_id_to_edit}`).\nIntroduce el *nuevo nombre*:"
        next_state = GET_NEW_NAME
    elif field_to_edit == "days":
        prompt_text = f"✏️ Editando acceso de *{name_escaped}* (ID: `{user_id_to_edit}`).\nIntroduce el *nuevo número total de días* de acceso (desde hoy):"
        next_state = GET_NEW_DAYS
    else:
        logger.error(f"Campo de edición no válido: {field_to_edit}")
        await query.edit_message_text("❌ Error interno. Campo no válido.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    await query.edit_message_text(text=prompt_text, parse_mode=ParseMode.MARKDOWN)
    return next_state

async def received_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe el nuevo nombre, actualiza la BD y finaliza."""
    new_name = update.message.text
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    user_id_to_edit = context.user_data.get('edit_user_id')

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception: pass

    if not user_id_to_edit:
        logger.error(f"Admin {admin_id} en received_new_name: Falta edit_user_id.")
        await update.message.reply_text("❌ Error interno. Reinicia la edición.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    success = db.update_user_name_db(user_id_to_edit, new_name)
    name_escaped = db.escape_markdown(new_name)
    if success:
        confirmation_text = f"✅ Nombre del usuario ID `{user_id_to_edit}` actualizado a *{name_escaped}*."
        logger.info(f"Admin {admin_id} actualizó nombre de {user_id_to_edit} a '{new_name}'.")
    else:
        confirmation_text = f"❌ No se pudo actualizar el nombre para el usuario ID `{user_id_to_edit}`."

    await _send_paginated_or_edit(update, context, confirmation_text, get_back_to_menu_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

async def received_new_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Recibe los nuevos días, calcula expiración, actualiza BD y finaliza."""
    user_input = update.message.text
    admin_id = update.effective_user.id
    user_message_id = update.message.message_id
    chat_id = update.effective_chat.id
    user_id_to_edit = context.user_data.get('edit_user_id')
    job_queue = context.job_queue

    try: await context.bot.delete_message(chat_id=chat_id, message_id=user_message_id)
    except Exception: pass

    if not user_id_to_edit:
        logger.error(f"Admin {admin_id} en received_new_days: Falta edit_user_id.")
        await update.message.reply_text("❌ Error interno. Reinicia la edición.", reply_markup=get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    try:
        days_active = int(user_input)
        if days_active <= 0:
            await update.message.reply_text("El número de días debe ser positivo. Intenta de nuevo.")
            return GET_NEW_DAYS

        current_ts = int(time.time())
        new_expiry_ts = current_ts + (days_active * 24 * 60 * 60)
        new_expiry_date = datetime.fromtimestamp(new_expiry_ts).strftime('%d/%m/%Y %H:%M')

        success = db.update_user_expiry_db(user_id_to_edit, new_expiry_ts)

        if success:
            confirmation_text = f"✅ Acceso del usuario ID `{user_id_to_edit}` actualizado.\nNueva expiración: *{new_expiry_date}* ({days_active} días desde ahora)."
            logger.info(f"Admin {admin_id} actualizó expiración de {user_id_to_edit} a {new_expiry_date}.")
        else:
            confirmation_text = f"❌ No se pudo actualizar la expiración para el usuario ID `{user_id_to_edit}`."

        await _send_paginated_or_edit(update, context, confirmation_text, get_back_to_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    except ValueError:
        logger.warning(f"Admin {admin_id} en edit_user: Entrada inválida para días: {user_input}")
        await update.message.reply_text(
            "Eso no parece un número de días válido. Debe ser un número entero positivo.\n"
            "Por favor, introduce el número de días."
        )
        return GET_NEW_DAYS
    except Exception as e:
        logger.error(f"Error al procesar received_new_days para admin {admin_id}: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error inesperado al actualizar el usuario.")
        context.user_data.clear()
        return ConversationHandler.END

edituser_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("edituser", edit_user_start),
        CallbackQueryHandler(edit_user_start, pattern=f"^{CALLBACK_ADMIN_EDIT_USER_PROMPT}$")
        ],
    states={
        SELECT_USER_TO_EDIT: [CallbackQueryHandler(received_user_edit_selection, pattern="^edituser_")],
        CHOOSE_FIELD_TO_EDIT: [CallbackQueryHandler(received_field_edit_selection, pattern="^editfield_")],
        GET_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_new_name)],
        GET_NEW_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_new_days)],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: generic_cancel_conversation(u, c, "edit_user"))],
    allow_reentry=True
)

# --- Handlers Simples (Listados) ---

async def _send_paginated_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup, schedule_delete: bool = True):
    """
    Envía o edita un mensaje, paginando si es necesario.
    Programa el borrado de los mensajes enviados/editados si schedule_delete es True,
    excepto si el teclado es el de 'Volver al Menú'.
    """
    query = update.callback_query
    is_callback = bool(query)
    chat_id = update.effective_chat.id
    job_queue = context.job_queue
    max_length = 4096 # Límite de Telegram

    sent_messages_ids = []
    is_back_to_menu_keyboard = (keyboard == get_back_to_menu_keyboard())

    try:
        if is_callback:
            # Intentar editar mensaje original
            try:
                edited_message = await query.edit_message_text(
                    text=text[:max_length],
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=keyboard
                )
                sent_messages_ids.append(edited_message.message_id)
                if len(text) > max_length:
                     logger.warning("Mensaje editado truncado por longitud.")
                     # Opcional: enviar el resto en mensajes nuevos si es necesario
            except BadRequest as e:
                 # Si el mensaje original fue borrado (ej. por timeout previo), enviar uno nuevo
                 if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
                     logger.warning(f"No se pudo editar mensaje (probablemente borrado), enviando nuevo: {e}")
                     is_callback = False # Tratar como si no fuera callback para el envío
                 else:
                     raise e # Re-lanzar otros errores de BadRequest

        if not is_callback: # Si no fue callback o la edición falló y necesitamos enviar nuevo
            # Borrar comando original si es posible y no es callback
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

        # Programar borrado solo si schedule_delete es True Y no es el teclado de volver al menú
        if schedule_delete and not is_back_to_menu_keyboard:
            for msg_id in sent_messages_ids:
                job_queue.run_once(
                    delete_message_later,
                    when=timedelta(seconds=DELETE_DELAY_SECONDS),
                    data={'chat_id': chat_id, 'message_id': msg_id},
                    name=f'delete_{chat_id}_{msg_id}'
                )
                logger.info(f"Programado borrado del mensaje {msg_id} en {DELETE_DELAY_SECONDS} segundos.")
        elif is_back_to_menu_keyboard:
             logger.info(f"No se programó borrado para mensaje {sent_messages_ids[-1]} (contiene botón 'Volver al Menú').")


    except BadRequest as e:
        logger.error(f"Error de Telegram al enviar/editar/borrar mensaje: {e}")
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
    admin_id = update.effective_user.id
    if is_callback: await query.answer()
    logger.info(f"Admin {admin_id} solicitó listar usuarios (is_callback: {is_callback}).")

    try:
        users = db.list_users_db()
        if not users:
            user_list_text = "ℹ️ No hay usuarios registrados."
            logger.info("list_users: No users found in DB.")
        else:
            logger.info(f"list_users: Formatting {len(users)} users.")
            current_ts = int(time.time())
            user_list_text = "👥 *Usuarios Registrados:*\n"
            for user in users:
                expiry_date = datetime.fromtimestamp(user['expiry_ts']).strftime('%d/%m/%Y %H:%M')
                status = "✅ Activo" if current_ts <= user['expiry_ts'] else "❌ Expirado"
                name_escaped = db.escape_markdown(user.get('name', 'N/A'))
                user_list_text += (
                    f"\n👤 ID: `{user['user_id']}`\n"
                    f"   Nombre: {name_escaped}\n"
                    f"   Expira: {expiry_date} ({status})"
                )

        final_keyboard = get_back_to_menu_keyboard()
        await _send_paginated_or_edit(update, context, user_list_text, final_keyboard)
        logger.info(f"list_users: Lista enviada/editada para admin {admin_id}.")

    except Exception as e:
        logger.error(f"Error al procesar list_users para admin {admin_id}: {e}", exc_info=True)
        await _send_paginated_or_edit(update, context, "⚠️ Ocurrió un error al listar usuarios.", get_back_to_menu_keyboard())

# --- Funciones Auxiliares ---

def get_admin_specific_buttons() -> list:
    """Devuelve la lista de botones específicos para el menú de administrador."""
    return [
        [InlineKeyboardButton("🔑 Admin: Listar Usuarios", callback_data=CALLBACK_ADMIN_LIST_USERS)],
        [InlineKeyboardButton("👤 Admin: Añadir/Act. Usuario", callback_data=CALLBACK_ADMIN_ADD_USER_PROMPT)],
        [InlineKeyboardButton("✏️ Admin: Editar Usuario", callback_data=CALLBACK_ADMIN_EDIT_USER_PROMPT)],
        [InlineKeyboardButton("🗑️ Admin: Eliminar Usuario", callback_data=CALLBACK_ADMIN_DELETE_USER_START)],
    ]

# --- ELIMINAR list_all_accounts ---
# @admin_required
# async def list_all_accounts(...): ... (Función eliminada)
