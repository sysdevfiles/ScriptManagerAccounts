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
        # Modificar tabla accounts para tener ID autoincremental
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                email TEXT NOT NULL,
                profile_name TEXT NOT NULL,
                pin TEXT,
                UNIQUE(service, email, profile_name)
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
        # Crear tabla assignments
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assignments (
                assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE,
                UNIQUE (user_id, account_id)
            )
        ''')
        conn.commit()
        conn.close()
        logger.info(f"Base de datos '{DB_FILE}' inicializada correctamente (con tabla assignments).")
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

def add_account_db(service: str, email: str, profile_name: str, pin: str) -> None:
    """Añade o actualiza un perfil de cuenta en la BD."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Usar INSERT OR REPLACE con la combinación única
        cursor.execute("""
            INSERT INTO accounts (service, email, profile_name, pin)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(service, email, profile_name) DO UPDATE SET
            pin=excluded.pin
        """, (service, email, profile_name, pin))
        conn.commit()
        logger.info(f"Perfil {service} - {profile_name} añadido/actualizado en BD.")
    except sqlite3.Error as e:
        logger.error(f"Error de BD al añadir/actualizar perfil {service} - {profile_name}: {e}")
        raise
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

def list_accounts_db() -> list:
    """Obtiene la lista de servicios y perfiles de la BD."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, service, profile_name FROM accounts ORDER BY service, profile_name")
        rows = cursor.fetchall()
        # Devolver lista de diccionarios con id, servicio y perfil
        return [dict(row) for row in rows]
    except sqlite3.Error as e:
        logger.error(f"Error de BD al listar cuentas con ID: {e}")
        return []
    finally:
        conn.close()

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

def assign_account_to_user(user_id: int, account_id: int) -> bool:
    """Asigna una cuenta a un usuario en la tabla 'assignments'."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Verificar si usuario y cuenta existen (opcional, FK debería manejarlo pero da mejor feedback)
        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        user_exists = cursor.fetchone()
        cursor.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,))
        account_exists = cursor.fetchone()

        if not user_exists:
            logger.error(f"Intento de asignar cuenta a usuario inexistente: {user_id}")
            return False
        if not account_exists:
            logger.error(f"Intento de asignar cuenta inexistente: {account_id}")
            return False

        # Insertar la asignación, ignorando si ya existe (UNIQUE constraint)
        cursor.execute("INSERT OR IGNORE INTO assignments (user_id, account_id) VALUES (?, ?)", (user_id, account_id))
        conn.commit()
        # Verificar si la inserción tuvo efecto (si no existía antes)
        changes = conn.total_changes
        if changes > 0:
             logger.info(f"Cuenta ID {account_id} asignada a usuario ID {user_id}.")
             return True
        else:
             logger.warning(f"La asignación entre usuario {user_id} y cuenta {account_id} ya existía.")
             # Consideramos que no falló, pero no hubo cambios. Podríamos devolver True igual.
             # Devolvemos False para indicar que no se hizo una *nueva* asignación.
             return False # O True si se prefiere indicar "estado final es asignado"
    except sqlite3.Error as e:
        logger.error(f"Error de BD al asignar cuenta {account_id} a usuario {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_account_details_by_id(account_id: int) -> dict | None:
    """Obtiene los detalles de una cuenta por su ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, service, email, profile_name, pin FROM accounts WHERE id = ?", (account_id,))
        account = cursor.fetchone()
        return dict(account) if account else None
    except sqlite3.Error as e:
        logger.error(f"Error de BD al obtener detalles de cuenta ID {account_id}: {e}")
        return None
    finally:
        conn.close()

def get_all_assignments() -> list[dict]:
    """Obtiene todas las asignaciones con detalles del usuario y la cuenta."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Unir las tres tablas para obtener toda la información relevante
        cursor.execute("""
            SELECT
                asn.assignment_id,
                u.user_id,
                u.name as user_name,
                a.id as account_id,
                a.service,
                a.profile_name
            FROM assignments asn
            JOIN users u ON asn.user_id = u.user_id
            JOIN accounts a ON asn.account_id = a.id
            ORDER BY u.name, a.service, a.profile_name
        """)
        assignments = [dict(row) for row in cursor.fetchall()]
        logger.info(f"Recuperadas {len(assignments)} asignaciones de la base de datos.")
        return assignments
    except sqlite3.Error as e:
        logger.error(f"Error de BD al obtener todas las asignaciones: {e}")
        return []
    finally:
        conn.close()
