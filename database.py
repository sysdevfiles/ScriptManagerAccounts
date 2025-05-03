import sqlite3
import logging
import time
import os
from dotenv import load_dotenv
import re # Importar re para escape_markdown

# Cargar ADMIN_USER_ID para la función de autorización
load_dotenv()
ADMIN_USER_ID_STR = os.getenv("ADMIN_USER_ID")
ADMIN_USER_ID = int(ADMIN_USER_ID_STR) if ADMIN_USER_ID_STR and ADMIN_USER_ID_STR.isdigit() else None

logger = logging.getLogger(__name__)
DB_FILE = "accounts.db"

def get_db_connection():
    """Establece conexión con la BD y configura row_factory."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # Devolver filas como diccionarios
    return conn

def init_db():
    """Inicializa las tablas de la base de datos si no existen."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Modificar tabla accounts: añadir user_id, registration_ts, expiry_ts
        # Cambiar UNIQUE constraint
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                service TEXT NOT NULL,
                email TEXT NOT NULL,
                profile_name TEXT NOT NULL,
                pin TEXT,
                registration_ts INTEGER NOT NULL,
                expiry_ts INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                UNIQUE(user_id, service, profile_name)
            )
        ''')
        # Mantener tabla users para autorización general
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                payment_method TEXT, -- Se mantiene pero no se usa activamente
                registration_ts INTEGER,
                expiry_ts INTEGER -- Caducidad general del permiso para usar el bot
            )
        ''')
        # Eliminar tabla assignments si existe (opcional, para limpieza)
        cursor.execute('DROP TABLE IF EXISTS assignments')

        conn.commit()
        conn.close()
        logger.info(f"Base de datos '{DB_FILE}' inicializada correctamente (accounts con user_id/timestamps, users, sin assignments).")
    except sqlite3.Error as e:
        logger.error(f"Error al inicializar la base de datos: {e}")
        raise

def is_user_authorized(user_id: int) -> bool:
    """Verifica si un usuario está autorizado."""
    if user_id == ADMIN_USER_ID:
        return True

    try:
        conn = get_db_connection()
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

def add_account_db(user_id: int, service: str, email: str, profile_name: str, pin: str, registration_ts: int, expiry_ts: int) -> bool:
    """Añade o actualiza un perfil de cuenta para un usuario específico."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Usar INSERT OR REPLACE o INSERT ON CONFLICT para manejar la unicidad
        cursor.execute("""
            INSERT INTO accounts (user_id, service, email, profile_name, pin, registration_ts, expiry_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, service, profile_name) DO UPDATE SET
            email=excluded.email,
            pin=excluded.pin,
            registration_ts=excluded.registration_ts,
            expiry_ts=excluded.expiry_ts
        """, (user_id, service, email, profile_name, pin, registration_ts, expiry_ts))
        conn.commit()
        logger.info(f"Perfil {service} - {profile_name} añadido/actualizado para user_id {user_id}.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error de BD al añadir/actualizar perfil {service} - {profile_name} para user {user_id}: {e}")
        # No relanzar, devolver False para que el handler lo maneje
        return False
    finally:
        conn.close()

def add_user_db(user_id: int, name: str, payment_method: str, registration_ts: int, expiry_ts: int) -> None:
    """Añade o actualiza un usuario autorizado en la BD."""
    try:
        conn = get_db_connection()
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

def get_accounts_for_user(user_id: int) -> list[dict]:
    """Obtiene los detalles de las cuentas activas de un usuario específico."""
    conn = get_db_connection()
    cursor = conn.cursor()
    current_ts = int(time.time())
    try:
        cursor.execute("""
            SELECT id, service, email, profile_name, pin, expiry_ts
            FROM accounts
            WHERE user_id = ? AND expiry_ts >= ?
            ORDER BY service, profile_name
        """, (user_id, current_ts))
        accounts = [dict(row) for row in cursor.fetchall()]
        logger.info(f"Recuperadas {len(accounts)} cuentas activas para user_id {user_id}.")
        return accounts
    except sqlite3.Error as e:
        logger.error(f"Error al obtener cuentas para user_id {user_id}: {e}")
        return []
    finally:
        conn.close()

def get_user_status_db(user_id: int) -> dict | None:
    """Obtiene el estado (nombre, expiración) de un usuario de la BD."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, expiry_ts FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error(f"Error de BD al verificar estado para user_id {user_id}: {e}")
        raise

def list_users_db() -> list:
    """Obtiene la lista de todos los usuarios registrados de la BD."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name, payment_method, expiry_ts FROM users ORDER BY expiry_ts DESC")
        users = cursor.fetchall()
        conn.close()
        return [dict(user) for user in users] # Devolver lista de diccionarios
    except sqlite3.Error as e:
        logger.error(f"Error de BD al listar usuarios: {e}")
        raise

# --- Helper para escapar Markdown V2 ---
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

def get_all_accounts_with_ids() -> list[dict]:
    """Obtiene todas las cuentas con ID, datos de usuario y expiración."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Unir con users para obtener el nombre del usuario
        cursor.execute("""
            SELECT
                a.id, a.service, a.email, a.profile_name, a.pin,
                a.user_id, u.name as user_name, a.expiry_ts
            FROM accounts a
            LEFT JOIN users u ON a.user_id = u.user_id
            ORDER BY a.user_id, a.service, a.profile_name
        """)
        accounts = [dict(row) for row in cursor.fetchall()]
        logger.info(f"Recuperadas {len(accounts)} cuentas totales de la base de datos.")
        return accounts
    except sqlite3.Error as e:
        logger.error(f"Error al obtener todas las cuentas con detalles de usuario: {e}")
        return []
    finally:
        conn.close()

# --- Nueva función para eliminar cuenta ---
def delete_account_db(account_id: int, user_id: int) -> bool:
    """Elimina una cuenta específica si pertenece al usuario."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Asegurarse de que la cuenta pertenece al usuario antes de borrar
        cursor.execute("DELETE FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
        conn.commit()
        # Verificar si se eliminó alguna fila
        changes = conn.total_changes
        if changes > 0:
            logger.info(f"Cuenta ID {account_id} eliminada por user_id {user_id}.")
            return True
        else:
            logger.warning(f"No se eliminó la cuenta ID {account_id} para user_id {user_id} (no encontrada o no pertenece).")
            return False
    except sqlite3.Error as e:
        logger.error(f"Error de BD al eliminar cuenta ID {account_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()

# --- Nueva función para actualizar cuenta ---
def update_account_details_db(account_id: int, user_id: int, new_email: str = None, new_pin: str = None) -> bool:
    """Actualiza el email o el PIN de una cuenta específica si pertenece al usuario."""
    if new_email is None and new_pin is None:
        logger.warning("Intento de actualizar cuenta sin especificar email o pin.")
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        updates = []
        params = []
        if new_email is not None:
            updates.append("email = ?")
            params.append(new_email)
        if new_pin is not None:
            updates.append("pin = ?")
            params.append(new_pin)

        # Añadir account_id y user_id a los parámetros para el WHERE
        params.extend([account_id, user_id])

        sql = f"UPDATE accounts SET {', '.join(updates)} WHERE id = ? AND user_id = ?"
        cursor.execute(sql, tuple(params))
        conn.commit()

        changes = conn.total_changes
        if changes > 0:
            updated_fields = []
            if new_email: updated_fields.append("email")
            if new_pin: updated_fields.append("pin")
            logger.info(f"Cuenta ID {account_id} actualizada ({', '.join(updated_fields)}) por user_id {user_id}.")
            return True
        else:
            logger.warning(f"No se actualizó la cuenta ID {account_id} para user_id {user_id} (no encontrada o no pertenece).")
            return False
    except sqlite3.Error as e:
        logger.error(f"Error de BD al actualizar cuenta ID {account_id} para user {user_id}: {e}")
        return False
    finally:
        conn.close()
