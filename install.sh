#!/bin/bash

# Script de instalación para el Bot Gestor de Cuentas en Ubuntu 20.04+
# Ejecutar con: sudo bash install.sh

# --- Variables (Ajustar si es necesario) ---
# Obtener el nombre de usuario que inició la sesión (incluso con sudo)
# Si logname no funciona, intentar con $SUDO_USER o pedir al usuario
if [ -z "$SUDO_USER" ]; then
    CURRENT_USER=$(logname 2>/dev/null || echo $USER)
else
    CURRENT_USER=$SUDO_USER
fi

# Determinar el directorio home del usuario
USER_HOME=$(getent passwd "$CURRENT_USER" | cut -d: -f6)
if [ -z "$USER_HOME" ]; then
    echo "ERROR: No se pudo determinar el directorio home para el usuario '$CURRENT_USER'."
    exit 1
fi

BOT_DIR="$USER_HOME/telegram_bot" # Directorio de instalación
SERVICE_NAME="telegrambot"
PYTHON_EXEC="python3"
# !!! URL del repositorio actualizada !!!
GITHUB_REPO_URL="https://github.com/sysdevfiles/ScriptManagerAccounts.git"


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
chown "$CURRENT_USER:$CURRENT_USER" "$USER_HOME"

# --- 3. Clonar Repositorio ---
echo "[3/8] Clonando repositorio desde $GITHUB_REPO_URL..."
# Clonar como el usuario actual en su directorio home
sudo -u "$CURRENT_USER" git clone "$GITHUB_REPO_URL" "$BOT_DIR"
if [ $? -ne 0 ]; then
    echo "ERROR: Falló la clonación del repositorio. Verifica la URL y los permisos."
    exit 1
fi
# Verificar si los archivos clonados existen
if [ ! -f "$BOT_DIR/bot.py" ] || [ ! -f "$BOT_DIR/requirements.txt" ]; then
    echo "ERROR: No se encontraron bot.py o requirements.txt después de clonar. Verifica el contenido del repositorio."
    exit 1
fi

# --- 4. Crear/Verificar .env (Paso Manual Aún Necesario) ---
echo "---------------------------------------------------------------------"
echo "[PASO MANUAL REQUERIDO]"
echo "El código fuente ha sido clonado en $BOT_DIR."
echo "Ahora DEBES crear o verificar el archivo .env en $BOT_DIR con tu TOKEN y ADMIN_ID:"
echo "  Ejemplo de contenido para $BOT_DIR/.env:"
echo '  # Inserte su token de Telegram (obtenido de @BotFather)'
echo '  TELEGRAM_BOT_TOKEN="TU_TOKEN_DE_BOTFATHER"'
echo '  # Inserte su ID de Telegram (obtenido de @userinfobot)'
echo '  ADMIN_USER_ID="TU_ID_DE_USERINFOBOT"'
echo ""
echo "Puedes usar 'scp', 'rsync' o un cliente SFTP."
echo "Ejemplo con nano para crear .env: sudo -u $CURRENT_USER nano $BOT_DIR/.env"
echo "Asegúrate de que el archivo .env tenga permisos de lectura para '$CURRENT_USER'."
echo "Ejemplo: sudo chown $CURRENT_USER:$CURRENT_USER $BOT_DIR/.env && sudo chmod 600 $BOT_DIR/.env"
echo "---------------------------------------------------------------------"
while true; do
    read -p "Presiona Enter cuando hayas creado/verificado el archivo .env..."
    # Verificar si .env existe
    if [ -f "$BOT_DIR/.env" ]; then
        # Asegurar permisos correctos para .env
        echo "Verificando permisos de .env..."
        sudo chown "$CURRENT_USER:$CURRENT_USER" "$BOT_DIR/.env"
        sudo chmod 600 "$BOT_DIR/.env" # Solo lectura/escritura para el propietario
        echo "Archivo .env detectado y permisos ajustados. Continuando..."
        break
    else
        echo "ERROR: Faltan el archivo .env en $BOT_DIR. Por favor, créalo."
    fi
done


# --- 5. Entorno Virtual ---
echo "[4/8] Creando entorno virtual..."
# Ejecutar como el usuario propietario del directorio
sudo -u "$CURRENT_USER" $PYTHON_EXEC -m venv "$BOT_DIR/venv"
if [ $? -ne 0 ]; then
    echo "ERROR: Falló la creación del entorno virtual."
    exit 1
fi

# --- 6. Instalar Dependencias ---
echo "[5/8] Instalando dependencias de Python..."
# Activar venv y ejecutar pip como el usuario
sudo -u "$CURRENT_USER" bash -c "source \"$BOT_DIR/venv/bin/activate\" && pip install --upgrade pip && pip install -r \"$BOT_DIR/requirements.txt\""
if [ $? -ne 0 ]; then
    echo "ERROR: Falló la instalación de dependencias de Python."
    exit 1
fi

# --- 7. Configurar systemd ---
echo "[6/8] Configurando servicio systemd ($SERVICE_NAME.service)..."

# Crear el archivo de servicio
# Usar barras diagonales escapadas en las rutas dentro del bloque cat
cat << EOF > /etc/systemd/system/${SERVICE_NAME}.service
[Unit]
Description=Telegram Account Manager Bot (user $CURRENT_USER)
After=network.target

[Service]
User=$CURRENT_USER
Group=$(id -gn $CURRENT_USER) # Usar el grupo principal del usuario
WorkingDirectory=$BOT_DIR
# Usar la ruta completa al python del venv
ExecStart=$BOT_DIR/venv/bin/python $BOT_DIR/bot.py
Restart=on-failure # Reiniciar solo si falla
RestartSec=5
EnvironmentFile=$BOT_DIR/.env # Cargar variables de entorno desde .env

[Install]
WantedBy=multi-user.target
EOF

if [ $? -ne 0 ]; then
    echo "ERROR: Falló la creación del archivo de servicio systemd."
    exit 1
fi

# --- 8. Iniciar Servicio ---
echo "[7/8] Recargando systemd y habilitando el servicio..."
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}.service

echo "[8/8] Iniciando el servicio del bot..."
systemctl restart ${SERVICE_NAME}.service # Usar restart para asegurar que toma la nueva config

# Esperar un poco y verificar el estado
sleep 3
SERVICE_STATUS=$(systemctl is-active ${SERVICE_NAME}.service)
echo "Estado del servicio: $SERVICE_STATUS"

if [ "$SERVICE_STATUS" != "active" ]; then
     echo "ADVERTENCIA: El servicio no se inició correctamente. Revisa los logs."
     echo "Comandos útiles:"
     echo "  Ver estado: sudo systemctl status ${SERVICE_NAME}.service"
     echo "  Ver logs: sudo journalctl -u ${SERVICE_NAME}.service -f -n 50" # Muestra las últimas 50 líneas y sigue
     echo "  Reiniciar: sudo systemctl restart ${SERVICE_NAME}.service"
     echo "  Detener: sudo systemctl stop ${SERVICE_NAME}.service"
     exit 1
fi

echo "--- Instalación Completada ---"
echo "El bot se está ejecutando como un servicio systemd."
echo "  Ver estado: sudo systemctl status ${SERVICE_NAME}.service"
echo "  Ver logs: sudo journalctl -u ${SERVICE_NAME}.service -f"

exit 0
