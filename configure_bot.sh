#!/bin/bash
# Configuration script for Streaming Manager Telegram Bot

# --- Colors ---
COL_RESET='\033[0m'
COL_CYAN='\033[0;36m'
COL_YELLOW='\033[0;33m'
COL_GREEN='\033[0;32m'
COL_RED='\033[0;31m'
COL_BOLD='\033[1m'
# --- End Colors ---

SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
CONFIG_FILE="$SCRIPT_DIR/config.env"
DATA_FILE="$SCRIPT_DIR/streaming_accounts.json"
REG_DATA_FILE="$SCRIPT_DIR/registrations.json" # Added

echo -e "${COL_BOLD}${COL_CYAN}--- Configuración del Bot de Telegram para Streaming Manager ---${COL_RESET}"
echo -e "${COL_YELLOW}By @lestermel${COL_RESET}"
echo

# --- Check if already configured ---
if [[ -f "$CONFIG_FILE" ]]; then
    echo -e "${COL_YELLOW}El archivo de configuración ($CONFIG_FILE) ya existe.${COL_RESET}"
    echo -e "${COL_YELLOW}Token y Chat ID ya están registrados.${COL_RESET}"
    echo -en "${COL_YELLOW}¿Deseas reconfigurar y sobrescribir los datos existentes? (s/N): ${COL_RESET}"
    read confirm_overwrite
    if [[ ! "$confirm_overwrite" =~ ^[Ss]$ ]]; then
        echo -e "${COL_GREEN}Configuración existente mantenida. Saliendo.${COL_RESET}"
        exit 0
    fi
    echo -e "${COL_YELLOW}Procediendo a reconfigurar...${COL_RESET}"
    echo
fi
# --- End Check ---

echo -e "${COL_YELLOW}Este script configurará el Token del Bot, tu Chat ID como administrador y la licencia.${COL_RESET}"
echo

# Prompt for Telegram Credentials
echo -en "${COL_YELLOW}Ingresa tu Token de Bot de Telegram:${COL_RESET} "
read TELEGRAM_BOT_TOKEN
echo -en "${COL_YELLOW}Ingresa tu Chat ID (será el ID de administrador):${COL_RESET} "
read ADMIN_CHAT_ID

# --- Prompt for License Details ---
echo
echo -e "${COL_CYAN}Configuración de Licencia:${COL_RESET}"
activation_date=$(date +%Y-%m-%d)
echo -e "${COL_YELLOW}Fecha de Activación establecida a hoy: $activation_date${COL_RESET}"

default_days=30
echo -en "${COL_YELLOW}Ingresa la duración de la licencia en días (ej. $default_days): ${COL_RESET}"
read license_days

# Validate input is a number
if ! [[ "$license_days" =~ ^[0-9]+$ ]]; then
    echo -e "${COL_RED}Número de días inválido. Usando $default_days días por defecto.${COL_RESET}"
    license_days=$default_days
fi

# Calculate expiration date (requires GNU date for -d option flexibility)
expiration_date=$(date -d "$activation_date + $license_days days" +%Y-%m-%d)
if [[ $? -ne 0 ]]; then
    echo -e "${COL_RED}Error al calcular la fecha de expiración. Verifica que 'date' soporte la opción '-d'.${COL_RESET}"
    # Fallback or exit? Let's fallback to 30 days manually if possible, otherwise exit.
    expiration_date=$(date -d "+$default_days days" +%Y-%m-%d) # Try simpler format
     if [[ $? -ne 0 ]]; then
        echo -e "${COL_RED}No se pudo calcular la fecha de expiración. Abortando.${COL_RESET}"
        exit 1
     fi
     echo -e "${COL_YELLOW}Usando fecha de expiración calculada de forma alternativa: $expiration_date${COL_RESET}"
else
     echo -e "${COL_GREEN}Fecha de Expiración calculada: $expiration_date${COL_RESET}"
fi
# --- End License Details ---

# Create config file
echo
echo -e "${COL_CYAN}Creando archivo de configuración ($CONFIG_FILE)...${COL_RESET}"
echo "TELEGRAM_BOT_TOKEN='${TELEGRAM_BOT_TOKEN}'" > "$CONFIG_FILE"
echo "ADMIN_CHAT_ID='${ADMIN_CHAT_ID}'" >> "$CONFIG_FILE"
echo "ACTIVATION_DATE='${activation_date}'" >> "$CONFIG_FILE"
echo "EXPIRATION_DATE='${expiration_date}'" >> "$CONFIG_FILE"

# Set permissions for config file
chmod 600 "$CONFIG_FILE"
echo -e "${COL_GREEN}Permisos establecidos para $CONFIG_FILE (rw-------)${COL_RESET}"

# Ensure Data File Exists
if [[ ! -f "$DATA_FILE" ]]; then
    echo -e "${COL_YELLOW}Archivo de datos de cuentas ($DATA_FILE) no encontrado. Creándolo...${COL_RESET}"
    echo '{"accounts": []}' > "$DATA_FILE"
    chmod 600 "$DATA_FILE" # Set permissions
    echo -e "${COL_GREEN}Archivo de datos de cuentas creado exitosamente.${COL_RESET}"
fi

# Ensure Registrations Data File Exists # Added Section
if [[ ! -f "$REG_DATA_FILE" ]]; then
    echo -e "${COL_YELLOW}Archivo de datos de registros ($REG_DATA_FILE) no encontrado. Creándolo...${COL_RESET}"
    echo '{"registrations": []}' > "$REG_DATA_FILE"
    chmod 600 "$REG_DATA_FILE" # Set permissions
    echo -e "${COL_GREEN}Archivo de datos de registros creado exitosamente.${COL_RESET}"
fi

echo
echo -e "${COL_BOLD}${COL_GREEN}Configuración completada.${COL_RESET}"
echo -e "Ahora puedes ejecutar el bot con: ${COL_YELLOW}./telegram_bot_manager.sh${COL_RESET}"
echo -e "${COL_YELLOW}Se recomienda ejecutarlo en segundo plano o como un servicio (ver README).${COL_RESET}"

