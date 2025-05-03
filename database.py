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
        return True

    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT expiry_ts FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        conn.close()

        if user_row:
            current_ts = int(time.time())
            return current_ts <= user_row['expiry_ts']
        return False
    except sqlite3.Error as e:
        logger.error(f"Error de BD al verificar autorización para user_id {user_id}: {e}")
        return False

def list_users_db() -> list:
    """Obtiene la lista de todos los usuarios registrados de la BD."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name, payment_method, expiry_ts FROM users ORDER BY expiry_ts DESC")
        users = cursor.fetchall()
        conn.close()
        return [dict(user) for user in users] # Devolver lista de diccionarios
    except sqlite3.Error as e:
        logger.error(f"Error de BD al listar usuarios: {e}")
        raise

# --- Funciones CRUD para Cuentas y Perfiles (Nueva Estructura) ---
def add_account_db(user_id: int, service: str, email: str, profiles: list, registration_ts: int, expiry_ts: int) -> bool:
    """Añade una cuenta principal y sus perfiles asociados."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        # Insertar o reemplazar la cuenta principal
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
             raise sqlite3.Error("No se pudo obtener el ID de la cuenta principal después de insertar/actualizar.")
        account_id = account_row[0]

        # Insertar o reemplazar perfiles asociados
        for profile in profiles:
            profile_name = profile.get('name')
            pin = profile.get('pin', 'N/A')
            if profile_name: # Asegurarse de que hay un nombre de perfil
                cursor.execute(
                    """
                    INSERT INTO account_profiles (account_id, profile_name, pin)
                    VALUES (?, ?, ?)
                    ON CONFLICT(account_id, profile_name) DO UPDATE SET
                    pin=excluded.pin;
                    """,
                    (account_id, profile_name, pin)
                )
        conn.commit()
        logger.info(f"Cuenta y {len(profiles)} perfiles añadidos/actualizados para user {user_id}, service {service}, email {email}")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error en add_account_db: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()

def get_accounts_for_user(user_id: int) -> list:
    """Obtiene todas las cuentas y sus perfiles para un usuario."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row # Devolver filas como diccionarios
    cursor = conn.cursor()
    accounts_data = []
    try:
        current_ts = int(time.time())
        cursor.execute(
            """
            SELECT id, service, email, expiry_ts
            FROM streaming_accounts
            WHERE user_id = ? AND expiry_ts > ?
            ORDER BY service, email;
            """,
            (user_id, current_ts)
        )
        main_accounts = cursor.fetchall()

        for account in main_accounts:
            account_dict = dict(account) # Convertir fila a diccionario mutable
            account_id = account_dict['id']
            # Obtener perfiles para esta cuenta
            cursor.execute(
                """
                SELECT id as profile_id, profile_name, pin
                FROM account_profiles
                WHERE account_id = ?
                ORDER BY profile_name;
                """,
                (account_id,)
            )
            profiles = cursor.fetchall()
            account_dict['profiles'] = [dict(p) for p in profiles] # Añadir lista de perfiles
            accounts_data.append(account_dict)

        return accounts_data
    except sqlite3.Error as e:
        logger.error(f"Error en get_accounts_for_user: {e}", exc_info=True)
        return []
    finally:
        conn.close()

def update_account_email_db(account_id: int, user_id: int, new_email: str) -> bool:
    """Actualiza el email de una cuenta principal, verificando propiedad."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        # Verificar que la cuenta pertenece al usuario
        cursor.execute("SELECT id FROM streaming_accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
        if not cursor.fetchone():
            logger.warning(f"Intento de actualizar email de cuenta {account_id} por usuario {user_id} no propietario.")
            return False

        # Verificar si ya existe otra cuenta con el nuevo email para el mismo servicio y usuario
        cursor.execute("SELECT service FROM streaming_accounts WHERE id = ?", (account_id,))
        service_row = cursor.fetchone()
        if not service_row: return False # No debería pasar si la verificación anterior funcionó
        service = service_row[0]

        cursor.execute(
            "SELECT id FROM streaming_accounts WHERE user_id = ? AND service = ? AND email = ? AND id != ?",
            (user_id, service, new_email, account_id)
        )
        if cursor.fetchone():
            logger.warning(f"Conflicto: Ya existe cuenta para user {user_id}, service {service} con email {new_email}.")
            return False # Conflicto de unicidad

        # Actualizar email
        cursor.execute(
            "UPDATE streaming_accounts SET email = ? WHERE id = ? AND user_id = ?",
            (new_email, account_id, user_id)
        )
        updated_rows = cursor.rowcount
        conn.commit()
        logger.info(f"Email actualizado para cuenta {account_id} a {new_email}. Filas afectadas: {updated_rows}")
        return updated_rows > 0
    except sqlite3.Error as e:
        logger.error(f"Error en update_account_email_db: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()

def update_profile_details_db(profile_id: int, user_id: int, new_name: str = None, new_pin: str = None) -> bool:
    """Actualiza el nombre o PIN de un perfil específico, verificando propiedad."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        # Verificar que el perfil pertenece a una cuenta del usuario
        cursor.execute("""
            SELECT ap.account_id
            FROM account_profiles ap
            JOIN streaming_accounts sa ON ap.account_id = sa.id
            WHERE ap.id = ? AND sa.user_id = ?
        """, (profile_id, user_id))
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Intento de actualizar perfil {profile_id} por usuario {user_id} no propietario.")
            return False
        account_id = result[0]

        updates = []
        params = []
        if new_name is not None:
             # Verificar si ya existe otro perfil con el mismo nombre en la misma cuenta
             cursor.execute(
                 "SELECT id FROM account_profiles WHERE account_id = ? AND profile_name = ? AND id != ?",
                 (account_id, new_name, profile_id)
             )
             if cursor.fetchone():
                 logger.warning(f"Conflicto: Ya existe perfil '{new_name}' en cuenta {account_id}.")
                 return False # Conflicto de unicidad
             updates.append("profile_name = ?")
             params.append(new_name)
        if new_pin is not None:
             updates.append("pin = ?")
             params.append(new_pin)

        if not updates:
             logger.info(f"No hay cambios para actualizar en perfil {profile_id}.")
             return True # No hay nada que hacer

        params.append(profile_id)
        sql = f"UPDATE account_profiles SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(sql, tuple(params))
        updated_rows = cursor.rowcount
        conn.commit()
        logger.info(f"Detalles actualizados para perfil {profile_id}. Filas afectadas: {updated_rows}")
        return updated_rows > 0
    except sqlite3.Error as e:
        logger.error(f"Error en update_profile_details_db: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()

def add_profile_to_account_db(account_id: int, user_id: int, profile_name: str, pin: str) -> bool:
    """Añade un nuevo perfil a una cuenta existente, verificando propiedad y límite."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        # Verificar propiedad de la cuenta principal
        cursor.execute("SELECT id FROM streaming_accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
        if not cursor.fetchone():
            logger.warning(f"Intento de añadir perfil a cuenta {account_id} por usuario {user_id} no propietario.")
            return False

        # Verificar límite de perfiles (5)
        cursor.execute("SELECT COUNT(*) FROM account_profiles WHERE account_id = ?", (account_id,))
        count = cursor.fetchone()[0]
        if count >= 5:
            logger.warning(f"Intento de añadir perfil a cuenta {account_id} fallido: Límite de 5 perfiles alcanzado.")
            return False

        # Insertar el nuevo perfil (manejar conflicto de nombre)
        cursor.execute(
            """
            INSERT INTO account_profiles (account_id, profile_name, pin) VALUES (?, ?, ?)
            ON CONFLICT(account_id, profile_name) DO NOTHING;
            """,
            (account_id, profile_name, pin)
        )
        inserted_rows = cursor.rowcount
        conn.commit()
        if inserted_rows > 0:
             logger.info(f"Perfil '{profile_name}' añadido a cuenta {account_id}.")
             return True
        else:
             logger.warning(f"Conflicto al añadir perfil '{profile_name}' a cuenta {account_id} (probablemente ya existe).")
             return False # Podría indicar que ya existía
    except sqlite3.Error as e:
        logger.error(f"Error en add_profile_to_account_db: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_profile_db(profile_id: int, user_id: int) -> bool:
    """Elimina un perfil específico, verificando propiedad."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        # Verificar que el perfil pertenece a una cuenta del usuario
        cursor.execute("""
            SELECT ap.id FROM account_profiles ap
            JOIN streaming_accounts sa ON ap.account_id = sa.id
            WHERE ap.id = ? AND sa.user_id = ?
        """, (profile_id, user_id))
        if not cursor.fetchone():
            logger.warning(f"Intento de eliminar perfil {profile_id} por usuario {user_id} no propietario.")
            return False

        # Eliminar el perfil
        cursor.execute("DELETE FROM account_profiles WHERE id = ?", (profile_id,))
        deleted_rows = cursor.rowcount
        conn.commit()
        logger.info(f"Perfil {profile_id} eliminado. Filas afectadas: {deleted_rows}")
        return deleted_rows > 0
    except sqlite3.Error as e:
        logger.error(f"Error en delete_profile_db: {e}", exc_info=True)
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_account_db(account_id: int, user_id: int) -> bool:
    """Elimina una cuenta principal y sus perfiles asociados (CASCADE), verificando propiedad."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    try:
        # Habilitar claves foráneas para que CASCADE funcione
        cursor.execute("PRAGMA foreign_keys = ON;")
        # Verificar propiedad y eliminar
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
    """Obtiene todas las cuentas de todos los usuarios (para admin)."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    accounts_data = []
    try:
        cursor.execute(
            """
            SELECT sa.id, sa.user_id, sa.service, sa.email, sa.expiry_ts, u.name as user_name
            FROM streaming_accounts sa
            LEFT JOIN users u ON sa.user_id = u.user_id
            ORDER BY sa.user_id, sa.service, sa.email;
            """
        )
        main_accounts = cursor.fetchall()

        for account in main_accounts:
            account_dict = dict(account)
            account_id = account_dict['id']
            cursor.execute(
                "SELECT profile_name, pin FROM account_profiles WHERE account_id = ? ORDER BY profile_name;",
                (account_id,)
            )
            profiles = cursor.fetchall()
            account_dict['profiles'] = [dict(p) for p in profiles]
            accounts_data.append(account_dict)
        return accounts_data
    except sqlite3.Error as e:
        logger.error(f"Error en get_all_accounts_db: {e}", exc_info=True)
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
