#!/bin/bash

# Script de instalación para el Bot Gestor de Cuentas en Ubuntu 20.04+
# Ejecutar con: sudo bash install.sh O directamente como root

# --- Verificación de Privilegios ---
if [ "$(id -u)" -ne 0 ]; then
  echo "ERROR: Este script necesita privilegios de root para instalar paquetes y configurar systemd." >&2
  echo "Ejecútalo usando 'sudo bash install.sh' o directamente como usuario root." >&2
  exit 1
fi

# --- Variables ---
# Como se ejecuta con privilegios root, se asume que el usuario y home son de root
CURRENT_USER="root"
USER_HOME="/root"
echo "INFO: Ejecutando instalación como usuario '$CURRENT_USER'."

BOT_DIR="$USER_HOME/telegram_bot" # Directorio de instalación (/root/telegram_bot)
SERVICE_NAME="telegrambot"
PYTHON_EXEC="python3"
# !!! URL del repositorio actualizada !!!
GITHUB_REPO_URL="https://github.com/sysdevfiles/ScriptManagerAccounts.git"
# --- Credenciales eliminadas de aquí ---


echo "--- Iniciando Instalación del Bot Gestor de Cuentas para el usuario '$CURRENT_USER' ---"
echo "Directorio de instalación: $BOT_DIR"

# --- 0. Limpieza Opcional ---
if [ -d "$BOT_DIR" ] || [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
    read -p "Parece que existe una instalación anterior. ¿Deseas limpiarla? (s/N): " clean_confirm
    if [[ "$clean_confirm" =~ ^[Ss]$ ]]; then
        echo "Limpiando instalación anterior..."
        systemctl stop ${SERVICE_NAME}.service > /dev/null 2>&1
        systemctl disable ${SERVICE_NAME}.service > /dev/null 2>&1
        rm -rf "$BOT_DIR"
        rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
        systemctl daemon-reload
        echo "Limpieza completada."
    else
        echo "Continuando sin limpiar. Esto podría causar conflictos."
    fi
fi


# --- 1. Prerrequisitos del Sistema ---
echo "[1/8] Actualizando sistema e instalando paquetes base..."
apt update
# apt upgrade -y # Comentado para rapidez, descomentar si se desea upgrade completo
apt install -y $PYTHON_EXEC ${PYTHON_EXEC}-pip ${PYTHON_EXEC}-venv sqlite3 libsqlite3-dev git curl # Añadido git y curl

# --- 2. Crear Directorio Padre (si es necesario, git clone crea el directorio final) ---
echo "[2/8] Asegurando directorio padre $USER_HOME..."
mkdir -p "$USER_HOME"
# No se necesita chown si es root

# --- 3. Clonar Repositorio ---
echo "[3/8] Clonando repositorio desde $GITHUB_REPO_URL..."
# Clonar directamente como root
git clone "$GITHUB_REPO_URL" "$BOT_DIR"
if [ $? -ne 0 ]; then
    echo "ERROR: Falló la clonación del repositorio. Verifica la URL y los permisos."
    exit 1
fi
# Verificar si los archivos clonados existen
if [ ! -f "$BOT_DIR/bot.py" ] || [ ! -f "$BOT_DIR/requirements.txt" ]; then
    echo "ERROR: No se encontraron bot.py o requirements.txt después de clonar. Verifica el contenido del repositorio."
    exit 1
fi

# --- 4. Crear/Verificar .env (Paso Manual Requerido) ---
echo "[4/8] Verificando archivo .env..."
ENV_FILE_PATH="$BOT_DIR/.env"
echo "---------------------------------------------------------------------"
echo "[PASO MANUAL REQUERIDO]"
echo "El código fuente ha sido clonado en $BOT_DIR."
echo "Ahora DEBES crear o verificar el archivo .env en $ENV_FILE_PATH con tu TOKEN y ADMIN_ID:"
echo "  Ejemplo de contenido para $ENV_FILE_PATH:"
echo '  # Inserte su token de Telegram (obtenido de @BotFather)'
echo '  TELEGRAM_BOT_TOKEN="TU_TOKEN_DE_BOTFATHER"'
echo '  # Inserte su ID de Telegram (obtenido de @userinfobot)'
echo '  ADMIN_USER_ID="TU_ID_DE_USERINFOBOT"'
echo ""
echo "Puedes usar el siguiente comando para crearlo/editarlo (si no lo has hecho ya):"
echo "  nano $ENV_FILE_PATH"
echo "---------------------------------------------------------------------"

while true; do
    read -p "Presiona Enter CUANDO hayas creado/verificado el archivo .env en $ENV_FILE_PATH..."
    # Verificar si .env existe
    if [ -f "$ENV_FILE_PATH" ]; then
        # Asegurar permisos correctos para .env ANTES de configurar systemd
        echo "Verificando permisos de $ENV_FILE_PATH..."
        chown root:root "$ENV_FILE_PATH" # Asumiendo ejecución como root
        if [ $? -ne 0 ]; then
             echo "ADVERTENCIA: No se pudo cambiar el propietario de $ENV_FILE_PATH."
        fi
        chmod 600 "$ENV_FILE_PATH"
         if [ $? -ne 0 ]; then
             echo "ADVERTENCIA: No se pudo cambiar los permisos de $ENV_FILE_PATH a 600."
        fi
        echo "Archivo .env detectado y permisos ajustados (propietario: root, modo: 600). Continuando..."
        break # Salir del bucle si el archivo existe
    else
        # Si el archivo NO existe, mostrar error y el comando nano
        echo "---------------------------------------------------------------------"
        echo "ERROR: El archivo .env NO se encontró en $ENV_FILE_PATH."
        echo "Por favor, créalo usando el comando:"
        echo "  nano $ENV_FILE_PATH"
        echo "Y pega dentro tu TELEGRAM_BOT_TOKEN y ADMIN_USER_ID."
        echo "Luego, guarda (Ctrl+O, Enter) y sal (Ctrl+X)."
        echo "---------------------------------------------------------------------"
        # El bucle continuará y volverá a pedir presionar Enter
    fi
done


# --- 5. Entorno Virtual ---
echo "[5/8] Creando entorno virtual..."
# Ejecutar directamente como root
$PYTHON_EXEC -m venv "$BOT_DIR/venv"
if [ $? -ne 0 ]; then
    echo "ERROR: Falló la creación del entorno virtual."
    exit 1
fi
# Asegurar permisos de ejecución para el intérprete de Python en venv
chmod +x "$BOT_DIR/venv/bin/python"
if [ $? -ne 0 ]; then
    echo "ADVERTENCIA: No se pudo asegurar permisos de ejecución para $BOT_DIR/venv/bin/python."
fi


# --- 6. Instalar Dependencias ---
echo "[6/8] Instalando dependencias de Python..."
# Activar venv y ejecutar pip directamente como root
bash -c "source \"$BOT_DIR/venv/bin/activate\" && pip install --upgrade pip && pip install -r \"$BOT_DIR/requirements.txt\""
if [ $? -ne 0 ]; then
    echo "ERROR: Falló la instalación de dependencias de Python."
    exit 1
fi

# --- 7. Configurar systemd ---
echo "[7/8] Configurando servicio systemd ($SERVICE_NAME.service)..."
SERVICE_FILE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
# Asegurar permisos de ejecución para el script principal del bot (como root)
chmod +x "$BOT_DIR/bot.py"
if [ $? -ne 0 ]; then
    echo "ADVERTENCIA: No se pudo asegurar permisos de ejecución para $BOT_DIR/bot.py."
fi

# Establecer User y Group explícitamente como root
SERVICE_USER="root"
SERVICE_GROUP="root"

# Crear el archivo de servicio
echo "Generando $SERVICE_FILE_PATH con User=$SERVICE_USER y Group=$SERVICE_GROUP..."

cat << EOF > "$SERVICE_FILE_PATH"
[Unit]
Description=Telegram Account Manager Bot (user $SERVICE_USER)
After=network.target

[Service]
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$BOT_DIR
# Usar la ruta completa al python del venv
ExecStart=$BOT_DIR/venv/bin/python $BOT_DIR/bot.py
Restart=on-failure
RestartSec=5
# Usar la ruta absoluta verificada para EnvironmentFile
EnvironmentFile=$ENV_FILE_PATH

[Install]
WantedBy=multi-user.target
EOF

if [ $? -ne 0 ]; then
    echo "ERROR: Falló la creación del archivo de servicio systemd en $SERVICE_FILE_PATH."
    exit 1
fi
echo "Archivo $SERVICE_FILE_PATH creado."
# Opcional: Mostrar contenido para depuración
# echo "Contenido de $SERVICE_FILE_PATH:"
# cat "$SERVICE_FILE_PATH"
# echo "------------------------------------"

# --- 8. Iniciar Servicio ---
echo "[8/8] Recargando systemd y habilitando el servicio..."
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}.service

echo "Iniciando el servicio del bot (usando restart)..."
systemctl restart ${SERVICE_NAME}.service # Usar restart para asegurar que toma la nueva config

echo "Esperando 5 segundos para que el servicio se estabilice..."
sleep 5

# Verificar estado final
echo "Verificando estado final del servicio..."
systemctl status ${SERVICE_NAME}.service --no-pager # Mostrar estado sin paginación
SERVICE_STATUS=$(systemctl is-active ${SERVICE_NAME}.service)
echo "Estado actual del servicio: $SERVICE_STATUS"

if [ "$SERVICE_STATUS" != "active" ]; then
     echo "---------------------------------------------------------------------"
     echo "ERROR: El servicio '$SERVICE_NAME' no está activo (Estado: $SERVICE_STATUS)."
     echo "Mostrando las últimas 15 líneas del log del servicio:"
     journalctl -u ${SERVICE_NAME}.service -n 15 --no-pager # Mostrar logs directamente
     echo "---------------------------------------------------------------------"
     echo "Posibles causas:"
     echo "  - Error en el código del bot (revisa los logs)."
     echo "  - Problema con el archivo .env (ruta o permisos)."
     echo "  - Problema con el archivo .service (sintaxis, rutas)."
     echo "Comandos útiles para diagnosticar:"
     echo "  1. Ver estado detallado: sudo systemctl status ${SERVICE_NAME}.service"
     echo "  2. Ver últimos logs: sudo journalctl -u ${SERVICE_NAME}.service -n 50 --no-pager"
     echo "  3. Seguir logs en tiempo real: sudo journalctl -u ${SERVICE_NAME}.service -f"
     echo "  4. Verificar archivo .env: ls -l $ENV_FILE_PATH"
     echo "  5. Verificar archivo service: cat $SERVICE_FILE_PATH"
     echo "  6. Reiniciar servicio después de corregir: sudo systemctl restart ${SERVICE_NAME}.service"
     echo "---------------------------------------------------------------------"

     # --- INICIO: Limpieza automática en caso de fallo (TEMPORALMENTE DESHABILITADA PARA DEBUG) ---
     echo "ADVERTENCIA: La limpieza automática está deshabilitada temporalmente para permitir la inspección manual."
     echo "Si deseas limpiar, ejecuta manualmente:"
     echo "  sudo systemctl stop ${SERVICE_NAME}.service"
     echo "  sudo systemctl disable ${SERVICE_NAME}.service"
     echo "  sudo rm -rf $BOT_DIR"
     echo "  sudo rm -f $SERVICE_FILE_PATH"
     echo "  sudo systemctl daemon-reload"
     # echo "Intentando limpiar la instalación fallida..."
     # ... (comandos de limpieza comentados) ...
     # echo "Limpieza automática completada. Por favor, revisa los errores e intenta la instalación de nuevo."
     # --- FIN: Limpieza automática en caso de fallo ---

     exit 1
fi

echo "--- Instalación Completada ---"
echo "El bot se está ejecutando como un servicio systemd."
echo "  Ver estado: sudo systemctl status ${SERVICE_NAME}.service"
echo "  Ver logs: sudo journalctl -u ${SERVICE_NAME}.service -f"

exit 0
