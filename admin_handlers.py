import logging
import time
from datetime import datetime
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Importar funciones de base de datos y otros módulos necesarios
import database as db
# Importar desde utils.py
from utils import ADMIN_USER_ID, get_back_to_menu_keyboard
# Importar get_main_menu_keyboard desde user_handlers si se necesita aquí
from user_handlers import get_main_menu_keyboard as get_user_main_menu

logger = logging.getLogger(__name__)

# --- Funciones de Comandos de Administrador ---

# Decorador para verificar si el usuario es admin
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

@admin_required
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Admin) Añade una nueva cuenta de streaming."""
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("No tienes permiso para usar este comando.")
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "Uso: /add <servicio> <usuario> <contraseña>"
        )
        return

    service = context.args[0].capitalize()
    username = context.args[1]
    password = " ".join(context.args[2:])

    try:
        db.add_account_db(service, username, password)
        await update.message.reply_text(f"Cuenta de {db.escape_markdown(service)} añadida/actualizada correctamente.")
        # Intenta borrar el mensaje original
        try:
            await context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
            # No enviar mensaje de confirmación de borrado para reducir spam
            # await update.message.reply_text("He borrado tu mensaje anterior por seguridad.")
        except Exception as e:
            logger.warning(f"No se pudo borrar el mensaje de /add: {e}")
            # No enviar mensaje de error de borrado para reducir spam
            # await update.message.reply_text("Recuerda borrar tu mensaje con la contraseña por seguridad.")
    except Exception as e:
        logger.error(f"Error al procesar /add para {service}: {e}")
        await update.message.reply_text("Ocurrió un error al guardar la cuenta.")


@admin_required
async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Admin) Añade o actualiza un usuario autorizado."""
    admin_id = update.effective_user.id
    if admin_id != ADMIN_USER_ID:
        await update.message.reply_text("No tienes permiso para usar este comando.")
        return

    # Quitar método de pago, asumir /adduser <user_id> <nombre> <días>
    if len(context.args) != 3:
        await update.message.reply_text(
            "Uso: /adduser <user_id> <nombre> <días_activo>"
        )
        return

    try:
        target_user_id = int(context.args[0])
        name = context.args[1] # El nombre puede tener espacios si se usan comillas, pero el split simple lo separa.
                               # Para nombres con espacios, el admin debe usar comillas y el parseo debería ser más robusto.
                               # Por simplicidad, asumimos nombre sin espacios o el admin sabe usar comillas.
        days_active = int(context.args[2])


        if days_active <= 0:
             await update.message.reply_text("Los días de activación deben ser un número positivo.")
             return

        registration_ts = int(time.time())
        expiry_ts = registration_ts + (days_active * 24 * 60 * 60)
        expiry_date = datetime.fromtimestamp(expiry_ts).strftime('%d/%m/%Y')

        # Adaptar llamada a BD si quitamos payment_method
        # Asumiendo que add_user_db ahora es add_user_db(user_id, name, expiry_ts)
        # Si no, hay que modificar database.py también
        # db.add_user_db(target_user_id, name, payment_method, registration_ts, expiry_ts) # Llamada original
        db.add_user_db(target_user_id, name, "N/A", registration_ts, expiry_ts) # Llamada adaptada (asumiendo que payment_method sigue en BD)


        name_escaped = db.escape_markdown(name)
        await update.message.reply_text(
            f"Usuario {name_escaped} (ID: `{target_user_id}`) añadido/actualizado.\n"
            # f"Método de pago: {payment_method}\n" # Quitado
            f"Acceso activo hasta: *{expiry_date}*.",
            parse_mode='MarkdownV2'
        )

    except ValueError:
        await update.message.reply_text("Error: El user_id y los días deben ser números.")
    except Exception as e:
        logger.error(f"Error al procesar /adduser para {context.args[0]}: {e}")
        await update.message.reply_text("Ocurrió un error al añadir al usuario.")


@admin_required
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Admin) Lista todos los usuarios autorizados."""
    query = update.callback_query
    if query:
        admin_id = query.from_user.id
        # await query.answer() # Se responde en el callback handler principal
    else:
        admin_id = update.effective_user.id

    if admin_id != ADMIN_USER_ID:
        message = "No tienes permiso para usar este comando."
        if query:
            await query.edit_message_text(text=message)
        else:
            await update.message.reply_text(text=message)
        return

    try:
        users = db.list_users_db()
        if not users:
            user_list_text = "No hay usuarios registrados."
        else:
            current_ts = int(time.time())
            user_list_text = "👥 Usuarios Registrados:\n"
            for user in users:
                expiry_date = datetime.fromtimestamp(user['expiry_ts']).strftime('%d/%m/%Y')
                status = "Activo" if current_ts <= user['expiry_ts'] else "Expirado"
                name_escaped = db.escape_markdown(user['name'])
                # Asumiendo que payment_method ya no se muestra o no existe
                # payment_escaped = db.escape_markdown(user['payment_method'])

                user_list_text += (
                    f"- ID: `{user['user_id']}`, Nombre: {name_escaped}, "
                    # f"Pago: {payment_escaped}, Expira: {expiry_date} ({status})\n" # Original
                    f"Expira: {expiry_date} ({status})\n" # Modificado
                )

        # La lógica de editar/responder con teclado se maneja mejor en el callback handler
        if query:
             # Solo editamos el texto aquí
             # Dividir mensaje si es muy largo (solo para edición)
             max_length = 4096
             await query.edit_message_text(user_list_text[:max_length], parse_mode='MarkdownV2')
             # Si es más largo, el resto se pierde en la edición, pero es raro para esta lista
        else:
             # Dividir mensaje si es muy largo (para envío normal)
            max_length = 4096
            for i in range(0, len(user_list_text), max_length):
                await update.message.reply_text(user_list_text[i:i+max_length], parse_mode='MarkdownV2')

    except Exception as e:
        logger.error(f"Error al procesar list_users: {e}")
        message = "Ocurrió un error al listar usuarios."
        if query:
            await query.edit_message_text(text=message)
        else:
            await update.message.reply_text(text=message)

@admin_required
async def list_all_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Admin) Lista todas las cuentas/perfiles registrados con su ID."""
    query = update.callback_query
    is_callback = bool(query)
    user_id = update.effective_user.id # Ya verificado por @admin_required

    logger.info(f"list_all_accounts: user_id={user_id}, is_callback={is_callback}")

    if is_callback:
        await query.answer()

    try:
        all_accounts = db.get_all_accounts_with_ids() # Necesitas esta función en database.py

        if not all_accounts:
            message = "ℹ️ No hay ninguna cuenta registrada en la base de datos."
        else:
            accounts_text_list = ["🧾 *Todas las Cuentas Registradas:*"]
            for acc in all_accounts:
                acc_id = acc.get('id', '??')
                service = acc.get('service', 'N/A')
                email = acc.get('email', 'N/A')
                profile = acc.get('profile_name', 'N/A')
                pin = acc.get('pin', 'N/A')

                # Escapar caracteres para Markdown
                service_escaped = db.escape_markdown(service)
                email_escaped = db.escape_markdown(email)
                profile_escaped = db.escape_markdown(profile)
                pin_escaped = db.escape_markdown(pin)

                accounts_text_list.append(
                    f"\n*ID:* `{acc_id}`\n"
                    f"  Servicio: {service_escaped}\n"
                    f"  Email: {email_escaped}\n"
                    f"  Perfil: {profile_escaped}\n"
                    f"  PIN: `{pin_escaped}`"
                )
            message = "\n".join(accounts_text_list)
            message += "\n\n_Usa el ID para asignar cuentas con /assign_"

        # Determinar teclado
        # Usamos get_main_menu_keyboard de user_handlers para comandos
        # y get_back_to_menu_keyboard de callback_handlers para callbacks
        final_keyboard = get_back_to_menu_keyboard() if is_callback else get_user_main_menu(True) # True porque es admin

        # Enviar respuesta
        if is_callback:
            await query.edit_message_text(text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard)
        elif update.message:
            # Dividir mensaje si es muy largo (Telegram tiene límite ~4096 chars)
            if len(message) > 4000:
                 logger.warning("Mensaje de list_all_accounts demasiado largo, enviando sin formato completo.")
                 # Simplificar o paginar si es necesario, por ahora enviamos truncado o simple
                 simplified_message = "ℹ️ La lista de cuentas es muy larga. Se muestra un resumen:\n"
                 simplified_message += "\n".join([f"- ID: {a.get('id','??')} {a.get('service','N/A')} ({a.get('profile_name','N/A')})" for a in all_accounts[:50]]) # Mostrar solo 50
                 await update.message.reply_text(simplified_message, reply_markup=final_keyboard)
            else:
                 await update.message.reply_text(text=message, parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard)

    except Exception as e:
        logger.error(f"Error al procesar list_all_accounts para {user_id}: {e}", exc_info=True)
        error_message = "⚠️ Ocurrió un error al obtener la lista completa de cuentas."
        final_keyboard = get_back_to_menu_keyboard() if is_callback else get_user_main_menu(True)
        if is_callback:
            await query.edit_message_text(text=error_message, reply_markup=final_keyboard)
        elif update.message:
            await update.message.reply_text(text=error_message, reply_markup=final_keyboard)

@admin_required
async def assign_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Admin) Asigna un perfil de cuenta a un usuario."""
    if len(context.args) != 2:
        await update.message.reply_text("Uso: /assign <user_id> <account_id>")
        return

    try:
        target_user_id = int(context.args[0])
        account_id = int(context.args[1])

        # Verificar si el usuario existe y está autorizado (opcional pero recomendado)
        if not db.is_user_authorized(target_user_id):
             # Podríamos permitir asignar a usuarios no autorizados, pero avisamos
             logger.warning(f"Intentando asignar cuenta a usuario no autorizado o inexistente: {target_user_id}")
             # await update.message.reply_text(f"⚠️ Advertencia: El usuario {target_user_id} no está autorizado o no existe.")
             # return # Descomentar si se quiere bloquear la asignación

        # Llamar a la función de la base de datos
        success = db.assign_account_to_user(target_user_id, account_id) # Necesitas esta función en database.py

        if success:
            # Obtener nombres para un mensaje más claro (opcional)
            user_info = db.get_user_status_db(target_user_id)
            account_info = db.get_account_details_by_id(account_id) # Necesitas esta función en database.py
            user_name = user_info.get('name', f'ID {target_user_id}') if user_info else f'ID {target_user_id}'
            account_desc = f"{account_info['service']} ({account_info['profile_name']})" if account_info else f'ID {account_id}'

            user_name_escaped = db.escape_markdown(user_name)
            account_desc_escaped = db.escape_markdown(account_desc)

            await update.message.reply_text(
                f"✅ Cuenta *{account_desc_escaped}* asignada correctamente al usuario *{user_name_escaped}*.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # El error específico (usuario/cuenta no existe, ya asignado) se maneja en db.assign_account_to_user
            # La función db debe loggear el error específico. Aquí damos mensaje genérico.
             await update.message.reply_text(f"❌ No se pudo asignar la cuenta. Verifica que el User ID y el Account ID sean válidos y que la asignación no exista ya.")

    except ValueError:
        await update.message.reply_text("Error: El user_id y el account_id deben ser números.")
    except Exception as e:
        logger.error(f"Error al procesar /assign: {e}", exc_info=True)
        await update.message.reply_text("Ocurrió un error inesperado al asignar la cuenta.")

@admin_required
async def list_assignments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """(Admin) Lista todas las asignaciones de cuentas a usuarios."""
    query = update.callback_query
    is_callback = bool(query)
    user_id = update.effective_user.id # Ya verificado por @admin_required

    logger.info(f"list_assignments: user_id={user_id}, is_callback={is_callback}")

    if is_callback:
        await query.answer()

    try:
        all_assignments = db.get_all_assignments() # Necesitas esta función en database.py

        if not all_assignments:
            message = "ℹ️ No hay ninguna asignación registrada."
        else:
            assignments_text_list = ["🔗 *Todas las Asignaciones:*"]
            # Ordenar o agrupar para mejor legibilidad, por ejemplo por usuario
            all_assignments.sort(key=lambda x: (x.get('user_name', x.get('user_id')), x.get('service', ''), x.get('profile_name', '')))

            current_user_id = None
            for assign in all_assignments:
                assign_user_id = assign.get('user_id')
                user_name = assign.get('user_name', f'ID {assign_user_id}')
                account_id = assign.get('account_id')
                service = assign.get('service', 'N/A')
                profile = assign.get('profile_name', 'N/A')

                # Escapar
                user_name_escaped = db.escape_markdown(user_name)
                service_escaped = db.escape_markdown(service)
                profile_escaped = db.escape_markdown(profile)

                # Agrupar por usuario
                if assign_user_id != current_user_id:
                    assignments_text_list.append(f"\n👤 *Usuario:* {user_name_escaped} (`{assign_user_id}`)")
                    current_user_id = assign_user_id

                assignments_text_list.append(
                    f"  - Cuenta ID `{account_id}`: {service_escaped} ({profile_escaped})"
                )

            message = "\n".join(assignments_text_list)

        # Determinar teclado
        final_keyboard = get_back_to_menu_keyboard() if is_callback else get_user_main_menu(True)

        # Enviar respuesta
        if is_callback:
            # Dividir mensaje si es muy largo para edición
            max_length = 4096
            await query.edit_message_text(text=message[:max_length], parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard)
        elif update.message:
            # Dividir mensaje si es muy largo para envío
            max_length = 4096
            for i in range(0, len(message), max_length):
                await update.message.reply_text(text=message[i:i+max_length], parse_mode=ParseMode.MARKDOWN, reply_markup=final_keyboard)


    except Exception as e:
        logger.error(f"Error al procesar list_assignments para {user_id}: {e}", exc_info=True)
        error_message = "⚠️ Ocurrió un error al obtener la lista de asignaciones."
        final_keyboard = get_back_to_menu_keyboard() if is_callback else get_user_main_menu(True)
        if is_callback:
            await query.edit_message_text(text=error_message, reply_markup=final_keyboard)
        elif update.message:
            await update.message.reply_text(text=error_message, reply_markup=final_keyboard)
