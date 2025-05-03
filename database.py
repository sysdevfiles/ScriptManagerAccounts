import sqlite3
import logging
import time
import os
from dotenv import load_dotenv

# Cargar ADMIN_USER_ID para la función de autorización
load_dotenv()
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))

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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                service TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                payment_method TEXT,
                registration_ts INTEGER,
                expiry_ts INTEGER
            )
        ''')
        conn.commit()
        conn.close()
        logger.info(f"Base de datos '{DB_FILE}' inicializada correctamente.")
    except sqlite3.Error as e:
        logger.error(f"Error al inicializar la base de datos: {e}")
        raise # Relanzar excepción para que el bot principal sepa del error

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

def add_account_db(service: str, username: str, password: str) -> None:
    """Añade o actualiza una cuenta de servicio en la BD."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("REPLACE INTO accounts (service, username, password) VALUES (?, ?, ?)",
                       (service, username, password))
        conn.commit()
        conn.close()
        logger.info(f"Cuenta {service} añadida/actualizada en BD.")
    except sqlite3.Error as e:
        logger.error(f"Error de BD al añadir cuenta {service}: {e}")
        raise

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

def list_accounts_db() -> list:
    """Obtiene la lista de servicios de la BD."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT service FROM accounts ORDER BY service")
        rows = cursor.fetchall()
        conn.close()
        return [row['service'] for row in rows] # Devolver lista de nombres
    except sqlite3.Error as e:
        logger.error(f"Error de BD al listar cuentas: {e}")
        raise

def get_account_db(service: str) -> dict | None:
    """Obtiene los detalles de una cuenta de servicio de la BD."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username, password FROM accounts WHERE service = ?", (service,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None # Devolver diccionario o None
    except sqlite3.Error as e:
        logger.error(f"Error de BD al obtener cuenta {service}: {e}")
        raise

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
    """Obtiene todas las cuentas de la tabla 'accounts' con su ID."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row # Devolver resultados como diccionarios
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, service, email, profile_name, pin FROM accounts ORDER BY service, profile_name")
        accounts = [dict(row) for row in cursor.fetchall()]
        logger.info(f"Recuperadas {len(accounts)} cuentas de la base de datos.")
        return accounts
    except sqlite3.Error as e:
        logger.error(f"Error al obtener todas las cuentas: {e}")
        return []
    finally:
        conn.close()

def get_assigned_accounts_for_user(user_id: int) -> list[dict]:
    """Obtiene los detalles de las cuentas asignadas a un usuario específico."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        # Unir 'assignments' con 'accounts' para obtener los detalles
        cursor.execute("""
            SELECT a.id, a.service, a.email, a.profile_name, a.pin
            FROM accounts a
            JOIN assignments asn ON a.id = asn.account_id
            WHERE asn.user_id = ?
            ORDER BY a.service, a.profile_name
        """, (user_id,))
        assigned = [dict(row) for row in cursor.fetchall()]
        logger.info(f"Recuperadas {len(assigned)} cuentas asignadas para user_id {user_id}.")
        return assigned
    except sqlite3.Error as e:
        logger.error(f"Error al obtener cuentas asignadas para user_id {user_id}: {e}")
        return []
    finally:
        conn.close()
