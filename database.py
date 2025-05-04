import sqlite3
import time
import logging
import re
from datetime import datetime
from dotenv import load_dotenv
import os

# Cargar ADMIN_USER_ID para la función de autorización
load_dotenv()
ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID")
ADMIN_USER_ID = int(ADMIN_USER_ID_STR) if ADMIN_USER_ID_STR and ADMIN_USER_ID_STR.isdigit() else None

DATABASE_FILE = 'access_control.db'
logger = logging.getLogger(__name__)

# --- Funciones de Utilidad ---
def escape_markdown(text: str) -> str:
    """Escapa caracteres especiales para MarkdownV2."""
    if not isinstance(text, str):
        text = str(text) # Asegurarse que es string
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    # No escapar caracteres ya escapados
    # Simple check: if the char before is already a backslash, skip
    escaped_text = ""
    for i, char in enumerate(text):
        if char in escape_chars and (i == 0 or text[i-1] != '\\'):
            escaped_text += '\\' + char
        else:
            escaped_text += char
    return escaped_text

# --- Inicialización y Migración de Base de Datos ---
def init_db():
    """Inicializa la base de datos y aplica migraciones si es necesario."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Crear tabla de usuarios si no existe
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                payment_method TEXT, -- Se mantiene pero no se usa activamente
                registration_ts INTEGER,
                expiry_ts INTEGER -- Caducidad general del permiso para usar el bot
            )
        ''')
    except sqlite3.Error as e:
        logger.error(f"Error al crear la tabla de usuarios: {e}")
        raise

    # --- Migración y Creación de Tablas de Cuentas ---
    try:
        # 1. Verificar si la tabla 'accounts' existe (vieja estructura)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts';")
        old_table_exists = cursor.fetchone()

        # 2. Verificar si la tabla 'streaming_accounts' existe (nueva estructura)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='streaming_accounts';")
        new_main_table_exists = cursor.fetchone()

        if old_table_exists and not new_main_table_exists:
            logger.info("Detectada estructura de tabla 'accounts' antigua. Migrando a 'streaming_accounts' y 'account_profiles'...")
            try:
                # Renombrar tabla principal
                cursor.execute("ALTER TABLE accounts RENAME TO streaming_accounts;")
                logger.info("Tabla 'accounts' renombrada a 'streaming_accounts'.")

                # Crear tabla de perfiles
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS account_profiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account_id INTEGER NOT NULL,
                        profile_name TEXT NOT NULL,
                        pin TEXT,
                        FOREIGN KEY(account_id) REFERENCES streaming_accounts(id) ON DELETE CASCADE
                    );
                ''')
                logger.info("Tabla 'account_profiles' creada o ya existente.")

                # Migrar datos de perfiles (esto es una aproximación, puede necesitar ajustes)
                # Asume que cada fila antigua representa un perfil único
                cursor.execute("SELECT id, profile_name, pin FROM streaming_accounts;")
                profiles_to_migrate = cursor.fetchall()
                for acc_id, profile_name, pin in profiles_to_migrate:
                    if profile_name: # Solo migrar si había un nombre de perfil
                        cursor.execute(
                            "INSERT INTO account_profiles (account_id, profile_name, pin) VALUES (?, ?, ?)",
                            (acc_id, profile_name, pin if pin else 'N/A')
                        )
                logger.info(f"Migrados {len(profiles_to_migrate)} perfiles iniciales a 'account_profiles'.")

                # Eliminar columnas antiguas de la tabla principal (¡SQLite tiene limitaciones!)
                # Forma segura: Crear nueva tabla sin las columnas, copiar datos, borrar vieja, renombrar nueva.
                # Intentaremos un método alternativo si la versión de SQLite lo soporta (>= 3.35.0)
                # O simplemente las dejamos NULAS si la migración anterior funcionó.
                logger.warning("Columnas 'profile_name' y 'pin' aún existen en 'streaming_accounts' pero no se usarán. Se recomienda limpieza manual o migración avanzada.")
                # Alternativamente, si se sabe que no hay datos importantes que perder y se quiere forzar:
                # cursor.execute("ALTER TABLE streaming_accounts DROP COLUMN profile_name;") # Requiere SQLite >= 3.35.0
                # cursor.execute("ALTER TABLE streaming_accounts DROP COLUMN pin;")      # Requiere SQLite >= 3.35.0

                conn.commit()
                logger.info("Migración de estructura de cuentas completada.")

            except sqlite3.Error as e:
                logger.error(f"Error durante la migración de la base de datos: {e}. Revise manualmente.", exc_info=True)
                conn.rollback() # Revertir cambios parciales si falla la migración
                # Podrías decidir salir o continuar con la estructura antigua si falla

        elif not new_main_table_exists:
             # Si ni la vieja ni la nueva existen, crear la nueva estructura directamente
            logger.info("Creando nueva estructura de tablas 'streaming_accounts' y 'account_profiles'.")
            cursor.execute('''
                CREATE TABLE streaming_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    service TEXT NOT NULL,
                    email TEXT NOT NULL,
                    registration_ts INTEGER,
                    expiry_ts INTEGER,
                    UNIQUE(user_id, service, email)
                );
            ''')
            cursor.execute('''
                CREATE TABLE account_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    profile_name TEXT NOT NULL,
                    pin TEXT,
                    FOREIGN KEY(account_id) REFERENCES streaming_accounts(id) ON DELETE CASCADE,
                    UNIQUE(account_id, profile_name)
                );
            ''')
            conn.commit()
            logger.info("Nuevas tablas creadas.")

    except sqlite3.Error as e:
        logger.error(f"Error al inicializar/migrar tablas de cuentas: {e}", exc_info=True)

    # Crear índices
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_account_user_id ON streaming_accounts(user_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_profile_account_id ON account_profiles(account_id);")

    conn.commit()
    conn.close()
    logger.info("Inicialización/Verificación de la base de datos completada.")

# --- Funciones CRUD para Usuarios ---
def add_user_db(user_id: int, name: str, payment_method: str, registration_ts: int, expiry_ts: int) -> None:
    """Añade o actualiza un usuario autorizado en la BD."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "REPLACE INTO users (user_id, name, payment_method, registration_ts, expiry_ts) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, payment_method, registration_ts, expiry_ts)
        )
        conn.commit()
        conn.close()
        logger.info(f"Usuario {user_id} ({name}) añadido/actualizado en BD.")
    except sqlite3.Error as e:
        logger.error(f"Error de BD al añadir usuario {user_id}: {e}")
        raise

def get_user_status_db(user_id: int) -> dict | None:
    """Obtiene el estado (nombre, expiración) de un usuario de la BD."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name, expiry_ts FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error(f"Error de BD al verificar estado para user_id {user_id}: {e}")
        raise

def is_user_authorized(user_id: int) -> bool:
    """Verifica si un usuario está autorizado."""
    if user_id == ADMIN_USER_ID:
        logger.debug(f"is_user_authorized: User {user_id} is ADMIN. Returning True.")
        return True

    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row # Asegurar acceso por nombre de columna
        cursor = conn.cursor()
        cursor.execute("SELECT expiry_ts FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        conn.close()

        if user_row:
            current_ts = int(time.time())
            expiry_ts = user_row['expiry_ts']
            is_valid = current_ts <= expiry_ts
            logger.debug(f"is_user_authorized: User {user_id} found. current_ts={current_ts}, expiry_ts={expiry_ts}. Is valid: {is_valid}")
            return is_valid
        else:
            logger.debug(f"is_user_authorized: User {user_id} not found in users table. Returning False.")
            return False
    except sqlite3.Error as e:
        logger.error(f"Error de BD al verificar autorización para user_id {user_id}: {e}")
        return False
    except Exception as e: # Capturar otros posibles errores (ej. acceso a user_row['expiry_ts'])
        logger.error(f"Error inesperado en is_user_authorized para user_id {user_id}: {e}", exc_info=True)
        return False

def list_users_db() -> list:
    """Obtiene la lista de todos los usuarios registrados de la BD."""
    users_list = []
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name, expiry_ts FROM users ORDER BY name")
        rows = cursor.fetchall()
        conn.close()
        users_list = [dict(row) for row in rows]
        logger.info(f"list_users_db: Found {len(users_list)} users.")
        logger.debug(f"list_users_db: Data retrieved: {users_list}") # Log detallado de datos
    except sqlite3.Error as e:
        logger.error(f"Error de BD al listar usuarios: {e}")
        # Devolver lista vacía en caso de error para no romper el flujo
    return users_list

def delete_user_db(user_id: int) -> bool:
    """Elimina un usuario autorizado de la BD."""
    if user_id == ADMIN_USER_ID:
        logger.warning(f"Intento de eliminar al administrador (ID: {user_id}). Operación denegada.")
        return False # No permitir eliminar al admin
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        deleted_rows = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted_rows > 0:
            logger.info(f"Usuario {user_id} eliminado de la BD.")
        else:
            logger.warning(f"Intento de eliminar usuario {user_id} fallido (no encontrado).")
        return deleted_rows > 0
    except sqlite3.Error as e:
        logger.error(f"Error de BD al eliminar usuario {user_id}: {e}")
        # No relanzar la excepción, devolver False
        return False

def update_user_name_db(user_id: int, new_name: str) -> bool:
    """Actualiza el nombre de un usuario autorizado."""
    if user_id == ADMIN_USER_ID:
        logger.warning(f"Intento de editar nombre del administrador (ID: {user_id}). Operación denegada.")
        return False # No permitir editar al admin
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET name = ? WHERE user_id = ?", (new_name, user_id))
        updated_rows = cursor.rowcount
        conn.commit()
        conn.close()
        if updated_rows > 0:
            logger.info(f"Nombre del usuario {user_id} actualizado a '{new_name}'.")
        else:
            logger.warning(f"Intento de actualizar nombre para usuario {user_id} fallido (no encontrado).")
        return updated_rows > 0
    except sqlite3.Error as e:
        logger.error(f"Error de BD al actualizar nombre para usuario {user_id}: {e}")
        return False

def update_user_expiry_db(user_id: int, new_expiry_ts: int) -> bool:
    """Actualiza la fecha de expiración de un usuario autorizado."""
    if user_id == ADMIN_USER_ID:
        logger.warning(f"Intento de editar expiración del administrador (ID: {user_id}). Operación denegada.")
        return False # No permitir editar al admin
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET expiry_ts = ? WHERE user_id = ?", (new_expiry_ts, user_id))
        updated_rows = cursor.rowcount
        conn.commit()
        conn.close()
        if updated_rows > 0:
            expiry_date = datetime.fromtimestamp(new_expiry_ts).strftime('%d/%m/%Y %H:%M')
            logger.info(f"Expiración del usuario {user_id} actualizada a {expiry_date} ({new_expiry_ts}).")
        else:
            logger.warning(f"Intento de actualizar expiración para usuario {user_id} fallido (no encontrado).")
        return updated_rows > 0
    except sqlite3.Error as e:
        logger.error(f"Error de BD al actualizar expiración para usuario {user_id}: {e}")
        return False

# --- Funciones CRUD para Cuentas y Perfiles (Revisadas) ---
def add_account_db(user_id: int, service: str, email: str, profiles: list, registration_ts: int, expiry_ts: int) -> bool:
    """
    Añade o actualiza una cuenta principal y sus perfiles asociados.
    Espera 'profiles' como una lista de diccionarios, ej: [{'name': 'P1', 'pin': '1111'}, ...].
    Actualiza la fecha de expiración si la cuenta principal ya existe.
    Añade/Actualiza perfiles basados en (account_id, profile_name).
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        conn.execute("PRAGMA foreign_keys = ON;") # Asegurar integridad referencial
        # Insertar o reemplazar la cuenta principal (actualiza timestamps si existe)
        cursor.execute(
            """
            INSERT INTO streaming_accounts (user_id, service, email, registration_ts, expiry_ts)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, service, email) DO UPDATE SET
            registration_ts=excluded.registration_ts, expiry_ts=excluded.expiry_ts;
            """,
            (user_id, service, email, registration_ts, expiry_ts)
        )
        # Obtener el ID de la cuenta insertada/actualizada
        cursor.execute(
            "SELECT id FROM streaming_accounts WHERE user_id=? AND service=? AND email=?",
            (user_id, service, email)
        )
        account_row = cursor.fetchone()
        if not account_row:
             logger.error(f"No se pudo obtener el ID de la cuenta principal después de insertar/actualizar para user {user_id}, service {service}, email {email}.")
             raise sqlite3.Error("No se pudo obtener el ID de la cuenta principal después de insertar/actualizar.")
        account_id = account_row[0]

        # Insertar o actualizar perfiles asociados
        profiles_added_updated = 0
        for profile in profiles:
            profile_name = profile.get('name')
            pin = profile.get('pin', 'N/A') # Usar N/A si no se proporciona PIN
            if profile_name: # Asegurarse de que hay un nombre de perfil
                # Verificar límite de perfiles (ej. 5) antes de insertar
                cursor.execute("SELECT COUNT(*) FROM account_profiles WHERE account_id = ?", (account_id,))
                count = cursor.fetchone()[0]
                if count >= 5: # Asumiendo un límite de 5 perfiles por cuenta
                    logger.warning(f"Límite de perfiles alcanzado para cuenta {account_id}. Omitiendo perfil '{profile_name}'.")
                    continue # Saltar este perfil

                cursor.execute(
                    """
                    INSERT INTO account_profiles (account_id, profile_name, pin)
                    VALUES (?, ?, ?)
                    ON CONFLICT(account_id, profile_name) DO UPDATE SET
                    pin=excluded.pin;
                    """,
                    (account_id, profile_name, pin)
                )
                if cursor.rowcount > 0:
                    profiles_added_updated += 1

        conn.commit()
        logger.info(f"Cuenta {account_id} y {profiles_added_updated} perfiles añadidos/actualizados para user {user_id}, service {service}, email {email}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error en add_account_db: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()

def get_accounts_for_user(user_id: int) -> list:
    """
    Obtiene una lista FLATTENED de perfiles para un usuario, incluyendo
    detalles de la cuenta padre y el ID del perfil.
    Solo incluye perfiles de cuentas cuya fecha de expiración no ha pasado.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # Devolver filas como diccionarios
    cursor = conn.cursor()
    profiles_data = []
    current_ts = int(time.time())
    try:
        # Unir las tablas y filtrar por user_id y expiry_ts
        cursor.execute(
            """
            SELECT
                sa.id AS account_id, -- ID de la cuenta principal
                sa.user_id,
                sa.service,
                sa.email,
                sa.registration_ts,
                sa.expiry_ts,
                ap.id AS profile_id, -- ID único del perfil
                ap.profile_name,
                ap.pin
            FROM streaming_accounts sa
            JOIN account_profiles ap ON sa.id = ap.account_id
            WHERE sa.user_id = ? AND sa.expiry_ts >= ?
            ORDER BY sa.service, ap.profile_name;
            """,
            (user_id, current_ts)
        )
        rows = cursor.fetchall()
        for row in rows:
            profiles_data.append(dict(row)) # Convertir cada fila a dict

        return profiles_data
    except sqlite3.Error as e:
        logger.error(f"Error en get_accounts_for_user (flattened): {e}", exc_info=True)
        return []
    finally:
        conn.close()

def update_account_email_db(account_id: int, user_id: int, new_email: str) -> bool:
    """Actualiza el email de una cuenta principal (streaming_accounts), verificando propiedad y unicidad."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        # 1. Verificar que la cuenta pertenece al usuario
        cursor.execute("SELECT service FROM streaming_accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
        service_row = cursor.fetchone()
        if not service_row:
            logger.warning(f"Intento de actualizar email de cuenta {account_id} por usuario {user_id} no propietario o cuenta no existe.")
            return False
        service = service_row[0]

        # 2. Verificar si ya existe OTRA cuenta con el nuevo email para el mismo servicio y usuario
        cursor.execute(
            "SELECT id FROM streaming_accounts WHERE user_id = ? AND service = ? AND email = ? AND id != ?",
            (user_id, service, new_email, account_id)
        )
        if cursor.fetchone():
            logger.warning(f"Conflicto al actualizar email: Ya existe cuenta para user {user_id}, service '{service}' con email '{new_email}'.")
            return False # Conflicto de unicidad

        # 3. Actualizar email
        cursor.execute(
            "UPDATE streaming_accounts SET email = ? WHERE id = ? AND user_id = ?",
            (new_email, account_id, user_id)
        )
        updated_rows = cursor.rowcount
        conn.commit()
        if updated_rows > 0:
            logger.info(f"Email actualizado para cuenta {account_id} a '{new_email}'. Filas afectadas: {updated_rows}")
        else:
             logger.warning(f"No se actualizó el email para la cuenta {account_id} (quizás ya tenía ese email?).")
        return updated_rows > 0
    except sqlite3.Error as e:
        logger.error(f"Error en update_account_email_db: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()

def update_profile_pin_db(profile_id: int, user_id: int, new_pin: str) -> bool:
    """
    Actualiza el PIN de un perfil específico (account_profiles),
    verificando que el usuario sea el dueño de la cuenta principal asociada.
    (Renamed from update_profile_details_db)
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        # 1. Verificar que el perfil existe y que el usuario es dueño de la cuenta padre
        cursor.execute(
            """
            SELECT ap.id
            FROM account_profiles ap
            JOIN streaming_accounts sa ON ap.account_id = sa.id
            WHERE ap.id = ? AND sa.user_id = ?
            """,
            (profile_id, user_id)
        )
        if not cursor.fetchone():
            logger.warning(f"Intento de actualizar PIN del perfil {profile_id} fallido: Perfil no encontrado o no pertenece al usuario {user_id}.")
            return False

        # 2. Actualizar el PIN del perfil
        cursor.execute(
            "UPDATE account_profiles SET pin = ? WHERE id = ?",
            (new_pin, profile_id)
        )
        updated_rows = cursor.rowcount
        conn.commit()
        if updated_rows > 0:
            logger.info(f"PIN actualizado para perfil {profile_id}.")
        else:
            logger.warning(f"No se actualizó el PIN para el perfil {profile_id} (quizás ya tenía ese PIN?).")
        return updated_rows > 0
    except sqlite3.Error as e:
        logger.error(f"Error en update_profile_pin_db: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()

def update_profile_name_db(profile_id: int, user_id: int, new_name: str) -> bool:
    """
    Actualiza el nombre de un perfil específico (account_profiles),
    verificando propiedad y unicidad del nombre dentro de la misma cuenta principal.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        # 1. Verificar que el perfil existe y que el usuario es dueño de la cuenta padre
        #    y obtener el account_id para la verificación de unicidad.
        cursor.execute(
            """
            SELECT sa.id AS account_id
            FROM account_profiles ap
            JOIN streaming_accounts sa ON ap.account_id = sa.id
            WHERE ap.id = ? AND sa.user_id = ?
            """,
            (profile_id, user_id)
        )
        account_row = cursor.fetchone()
        if not account_row:
            logger.warning(f"Intento de actualizar nombre del perfil {profile_id} fallido: Perfil no encontrado o no pertenece al usuario {user_id}.")
            return False
        account_id = account_row[0]

        # 2. Verificar si ya existe OTRO perfil con el nuevo nombre en la MISMA cuenta principal
        cursor.execute(
            "SELECT id FROM account_profiles WHERE account_id = ? AND profile_name = ? AND id != ?",
            (account_id, new_name, profile_id)
        )
        if cursor.fetchone():
            logger.warning(f"Conflicto al actualizar nombre perfil {profile_id}: Ya existe otro perfil con nombre '{new_name}' en la cuenta {account_id}.")
            return False # Conflicto de unicidad

        # 3. Actualizar el nombre del perfil
        cursor.execute(
            "UPDATE account_profiles SET profile_name = ? WHERE id = ?",
            (new_name, profile_id)
        )
        updated_rows = cursor.rowcount
        conn.commit()
        if updated_rows > 0:
            logger.info(f"Nombre actualizado para perfil {profile_id} a '{new_name}'.")
        else:
            logger.warning(f"No se actualizó el nombre para el perfil {profile_id} (quizás ya tenía ese nombre?).")
        return updated_rows > 0
    except sqlite3.Error as e:
        logger.error(f"Error en update_profile_name_db: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_account_db(account_id: int, user_id: int) -> bool:
    """
    Elimina una cuenta principal (streaming_accounts) y sus perfiles asociados (CASCADE),
    verificando propiedad.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        # Habilitar claves foráneas para que CASCADE funcione
        cursor.execute("PRAGMA foreign_keys = ON;")
        # Verificar propiedad y eliminar la cuenta principal
        # La eliminación de perfiles asociados ocurrirá automáticamente debido a ON DELETE CASCADE
        cursor.execute("DELETE FROM streaming_accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
        deleted_rows = cursor.rowcount
        conn.commit()
        if deleted_rows > 0:
            logger.info(f"Cuenta principal {account_id} y sus perfiles asociados eliminados para usuario {user_id}.")
        else:
            logger.warning(f"Intento de eliminar cuenta principal {account_id} fallido (no encontrada o no pertenece a usuario {user_id}).")
        return deleted_rows > 0
    except sqlite3.Error as e:
        logger.error(f"Error en delete_account_db: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()

def get_all_accounts_db() -> list:
    """
    Obtiene una lista FLATTENED de TODOS los perfiles en el sistema,
    incluyendo detalles de la cuenta padre y el ID del perfil.
    Utilizado por el administrador.
    """
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # Devolver filas como diccionarios
    cursor = conn.cursor()
    profiles_data = []
    try:
        # Unir las tablas
        cursor.execute(
            """
            SELECT
                sa.id AS account_id,
                sa.user_id,
                sa.service,
                sa.email,
                sa.registration_ts,
                sa.expiry_ts,
                ap.id AS profile_id,
                ap.profile_name,
                ap.pin,
                u.name AS owner_name -- Añadir nombre del dueño desde la tabla users
            FROM streaming_accounts sa
            JOIN account_profiles ap ON sa.id = ap.account_id
            LEFT JOIN users u ON sa.user_id = u.user_id -- Unir con users para obtener el nombre
            ORDER BY sa.user_id, sa.service, ap.profile_name;
            """
        )
        rows = cursor.fetchall()
        for row in rows:
            profiles_data.append(dict(row))

        return profiles_data
    except sqlite3.Error as e:
        logger.error(f"Error en get_all_accounts_db (flattened): {e}", exc_info=True)
        return []
    finally:
        conn.close()

# --- Funciones de Limpieza (Opcional) ---
def delete_expired_accounts():
    """Elimina las cuentas principales cuya fecha de expiración ha pasado."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        current_ts = int(time.time())
        cursor.execute("PRAGMA foreign_keys = ON;") # Asegurar que CASCADE funcione
        cursor.execute("DELETE FROM streaming_accounts WHERE expiry_ts < ?", (current_ts,))
        deleted_count = cursor.rowcount
        conn.commit()
        if deleted_count > 0:
            logger.info(f"Se eliminaron {deleted_count} cuentas expiradas.")
        return deleted_count
    except sqlite3.Error as e:
        logger.error(f"Error al eliminar cuentas expiradas: {e}", exc_info=True)
        conn.rollback()
        return 0
    finally:
        conn.close()
