#!/bin/bash
# Installation script for Streaming Manager - Telegram Configuration Only

# --- Colors ---
COL_RESET='\033[0m'
COL_CYAN='\033[0;36m'
COL_YELLOW='\033[0;33m'
COL_GREEN='\033[0;32m'
COL_RED='\033[0;31m'
COL_BOLD='\033[1m'
# --- End Colors ---

# Determine the script's directory
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
CONFIG_FILE="$SCRIPT_DIR/config.env" # Use absolute path

echo -e "${COL_BOLD}${COL_CYAN}--- Configuración de Telegram para Streaming Manager ---${COL_RESET}" # Changed title
echo -e "${COL_YELLOW}By @lestermel${COL_RESET}" # Credit line
echo
echo -e "${COL_YELLOW}Este script configurará el Token del Bot y el Chat ID de Telegram.${COL_RESET}" # Changed description
echo -e "Asegúrate de que jq, curl estén instalados y streaming_manager.sh sea ejecutable antes de correr el script principal." # Changed note
echo

# Prompt for Telegram Credentials
# Use -e with echo to interpret color codes, and add color to prompt text
echo -en "${COL_YELLOW}Ingresa tu Token de Bot de Telegram:${COL_RESET} " # Changed prompt
read TELEGRAM_BOT_TOKEN
echo -en "${COL_YELLOW}Ingresa tu Chat ID de Telegram:${COL_RESET} " # Changed prompt
read TELEGRAM_CHAT_ID

# Create config file
echo
echo -e "${COL_CYAN}Creando archivo de configuración ($CONFIG_FILE)...${COL_RESET}" # Changed message
echo "TELEGRAM_BOT_TOKEN='${TELEGRAM_BOT_TOKEN}'" > "$CONFIG_FILE"
echo "TELEGRAM_CHAT_ID='${TELEGRAM_CHAT_ID}'" >> "$CONFIG_FILE"

# Set permissions for config file (readable only by owner)
chmod 600 "$CONFIG_FILE"
echo -e "${COL_GREEN}Permisos establecidos para $CONFIG_FILE (rw-------)${COL_RESET}" # Changed message
echo
echo -e "${COL_BOLD}${COL_GREEN}Configuración de Telegram completada.${COL_RESET}" # Changed message
echo -e "Ahora puedes ejecutar ${COL_YELLOW}$SCRIPT_DIR/streaming_manager.sh${COL_RESET}" # Changed message
