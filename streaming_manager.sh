#!/bin/bash
# Main script for Streaming Manager

# --- Colors ---
COL_RESET='\033[0m'
COL_CYAN='\033[0;36m'
COL_YELLOW='\033[0;33m'
COL_GREEN='\033[0;32m'
COL_RED='\033[0;31m'
COL_BOLD='\033[1m'
# --- End Colors ---

# Determine the script's *real* directory, following symlinks
SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")

DATA_FILE="$SCRIPT_DIR/streaming_accounts.json" # Use absolute path
TMP_FILE="$SCRIPT_DIR/streaming_accounts.tmp" # Use absolute path
CONFIG_FILE="$SCRIPT_DIR/config.env"          # Use absolute path

# --- Dependency Checks ---
if ! command -v jq &> /dev/null; then
    echo -e "${COL_RED}Error: Comando 'jq' no encontrado. Por favor, instala jq (ej. sudo apt install jq).${COL_RESET}"
    exit 1
fi
if ! command -v curl &> /dev/null; then
    echo -e "${COL_RED}Error: Comando 'curl' no encontrado. Por favor, instala curl (ej. sudo apt install curl).${COL_RESET}"
    exit 1
fi
# --- End Dependency Checks ---

# --- Load Configuration ---
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
else
    echo -e "${COL_RED}Error: Archivo de configuración ($CONFIG_FILE) no encontrado.${COL_RESET}"
    echo -e "${COL_YELLOW}Por favor, ejecuta 'sudo menu' o '$SCRIPT_DIR/install.sh' para configurar Telegram.${COL_RESET}"
    exit 1
fi
# --- End Load Configuration ---

# --- Ensure Data File Exists ---
if [[ ! -f "$DATA_FILE" ]]; then
    echo -e "${COL_YELLOW}Archivo de datos ($DATA_FILE) no encontrado. Creándolo...${COL_RESET}"
    echo '{"accounts": []}' > "$DATA_FILE"
    chmod 600 "$DATA_FILE" # Set permissions (rw-------)
    echo -e "${COL_GREEN}Archivo de datos creado exitosamente.${COL_RESET}"
fi
# --- End Ensure Data File Exists ---


# Function to send message to Telegram
send_telegram_message() {
    local message_text="$1"
    # URL encode the message text
    local encoded_message=$(printf %s "$message_text" | jq -s -R -r @uri)
    local telegram_api_url="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"

    # Send message using curl, suppress output, ignore errors for now
    curl -s -o /dev/null -X POST "$telegram_api_url" -d chat_id="${TELEGRAM_CHAT_ID}" -d text="${encoded_message}" -d parse_mode="MarkdownV2" &
    # The '&' runs curl in the background to avoid blocking script execution
}


# Function to list accounts
list_accounts() {
    echo -e "${COL_CYAN}--- Cuentas de Streaming ---${COL_RESET}"
    local output
    # Check if the file is valid JSON and has accounts array before proceeding
    if ! jq -e '.accounts' "$DATA_FILE" > /dev/null 2>&1; then
        echo -e "${COL_RED}Error: El archivo de datos ($DATA_FILE) no es un JSON válido o le falta el array 'accounts'.${COL_RESET}"
        echo -e "${COL_YELLOW}Por favor, revisa o recrea el archivo con el contenido: {\"accounts\": []}${COL_RESET}"
        return 1 # Indicate error
    fi

    if ! jq '.accounts | length' "$DATA_FILE" > /dev/null 2>&1 || [[ $(jq '.accounts | length' "$DATA_FILE") -eq 0 ]]; then
        output="No se encontraron cuentas."
        echo -e "${COL_YELLOW}$output${COL_RESET}"
    else
        # Prepare output for both console and Telegram
        # CORRECTED: Removed backslash before hyphen
        output=$(jq -r '.accounts[] | "\(.service) - \(.username)"' "$DATA_FILE" | nl | sed 's/^ *//; s/ /\\. /') # Format for MarkdownV2
        echo -e "${COL_CYAN}--- Cuentas de Streaming ---${COL_RESET}" # Console header
        jq -r '.accounts[] | "\(.service) - \(.username)"' "$DATA_FILE" | nl # Console output
        echo "------------------------" # Console footer
        # Send formatted list to Telegram
        send_telegram_message "--- Cuentas de Streaming ---\n\`\`\`\n${output}\n\`\`\`"
        output="" # Clear output var as it was sent
    fi
    # If there was a simple message (like "No accounts found"), send it
    [[ -n "$output" ]] && send_telegram_message "$output"
    echo "------------------------"
}

# Function to list only usernames
list_users() {
    echo -e "${COL_CYAN}--- Nombres de Usuario ---${COL_RESET}"
    local output
    # Check if the file is valid JSON and has accounts array before proceeding
    if ! jq -e '.accounts' "$DATA_FILE" > /dev/null 2>&1; then
        echo -e "${COL_RED}Error: El archivo de datos ($DATA_FILE) no es un JSON válido o le falta el array 'accounts'.${COL_RESET}"
        echo -e "${COL_YELLOW}Por favor, revisa o recrea el archivo con el contenido: {\"accounts\": []}${COL_RESET}"
        return 1 # Indicate error
    fi

    if ! jq '.accounts | length' "$DATA_FILE" > /dev/null 2>&1 || [[ $(jq '.accounts | length' "$DATA_FILE") -eq 0 ]]; then
        output="No se encontraron cuentas."
        echo -e "${COL_YELLOW}$output${COL_RESET}"
    else
        # Prepare output for both console and Telegram
        output=$(jq -r '.accounts[] | .username' "$DATA_FILE" | nl | sed 's/^ *//; s/ /\\. /') # Format for MarkdownV2
        echo -e "${COL_CYAN}--- Nombres de Usuario ---${COL_RESET}" # Console header
        jq -r '.accounts[] | .username' "$DATA_FILE" | nl # Console output
        echo "-------------------------" # Console footer
        # Send formatted list to Telegram
        send_telegram_message "--- Nombres de Usuario ---\n\`\`\`\n${output}\n\`\`\`"
        output="" # Clear output var as it was sent
    fi
    # If there was a simple message (like "No accounts found"), send it
    [[ -n "$output" ]] && send_telegram_message "$output"
    echo "-------------------------"
}

# Function to add an account
add_account() {
    echo -e "${COL_CYAN}--- Añadir Nueva Cuenta ---${COL_RESET}"
    echo -en "${COL_YELLOW}Nombre del Servicio: ${COL_RESET}"
    read service
    echo -en "${COL_YELLOW}Nombre de Usuario: ${COL_RESET}"
    read username
    echo -en "${COL_YELLOW}Contraseña: ${COL_RESET}"
    read -sp password # -s hides input
    echo
    echo -en "${COL_YELLOW}PIN (opcional, dejar en blanco si no tiene): ${COL_RESET}"
    read -sp pin # -s hides input
    echo
    echo -en "${COL_YELLOW}Plan: ${COL_RESET}"
    read plan
    echo -en "${COL_YELLOW}Fecha de Renovación (YYYY-MM-DD): ${COL_RESET}"
    read renewal_date
    local creation_date=$(date +%Y-%m-%d) # Get current date

    jq --arg s "$service" --arg u "$username" --arg p "$password" --arg pin "$pin" \
       --arg pl "$plan" --arg rd "$renewal_date" --arg cd "$creation_date" \
       '.accounts += [{service: $s, username: $u, password: $p, pin: $pin, plan: $pl, renewal_date: $rd, creation_date: $cd}]' \
       "$DATA_FILE" > "$TMP_FILE" && mv "$TMP_FILE" "$DATA_FILE"

    local message="Cuenta para *$service* añadida exitosamente el $creation_date\\." # Escape Markdown characters
    echo -e "${COL_GREEN}Cuenta para $service añadida exitosamente el $creation_date.${COL_RESET}" # Console message
    send_telegram_message "$message"
}

# Function to edit an account
edit_account() {
    list_accounts # List first (already sends to Telegram if accounts exist)
    local count=$(jq '.accounts | length' "$DATA_FILE")
    if [[ $count -eq 0 ]]; then
        return
    fi

    echo -en "${COL_YELLOW}Ingresa el número de la cuenta a editar: ${COL_RESET}"
    read index
    # Validate index (subtract 1 for 0-based jq index)
    if ! [[ "$index" =~ ^[0-9]+$ ]] || (( index < 1 || index > count )); then
        echo -e "${COL_RED}Selección inválida.${COL_RESET}"
        return
    fi
    local jq_index=$((index - 1))
    local old_service=$(jq -r ".accounts[$jq_index].service" "$DATA_FILE") # Get service name for message

    echo -e "${COL_CYAN}--- Editar Cuenta #$index ($old_service) ---${COL_RESET}"
    # Display current data (optional)
    echo -e "${COL_YELLOW}Datos actuales:${COL_RESET}"
    jq -r ".accounts[$jq_index]" "$DATA_FILE"
    echo

    echo -en "${COL_YELLOW}Nuevo Nombre del Servicio (dejar en blanco para mantener actual): ${COL_RESET}"
    read service
    echo -en "${COL_YELLOW}Nuevo Nombre de Usuario (dejar en blanco para mantener actual): ${COL_RESET}"
    read username
    echo -en "${COL_YELLOW}Nueva Contraseña (dejar en blanco para mantener actual): ${COL_RESET}"
    read -sp password
    echo
    echo -en "${COL_YELLOW}Nuevo PIN (dejar en blanco para mantener actual): ${COL_RESET}"
    read -sp pin
    echo
    echo -en "${COL_YELLOW}Nuevo Plan (dejar en blanco para mantener actual): ${COL_RESET}"
    read plan
    echo -en "${COL_YELLOW}Nueva Fecha de Renovación (YYYY-MM-DD, dejar en blanco para mantener actual): ${COL_RESET}"
    read renewal_date

    # Build the jq update expression dynamically
    local update_expr=".accounts[$jq_index]"
    local args=()
    if [[ -n "$service" ]]; then update_expr+=' | .service = $s'; args+=(--arg s "$service"); else service=$old_service; fi # Keep old name if blank
    if [[ -n "$username" ]]; then update_expr+=' | .username = $u'; args+=(--arg u "$username"); fi
    if [[ -n "$password" ]]; then update_expr+=' | .password = $p'; args+=(--arg p "$password"); fi
    if [[ -n "$pin" ]]; then update_expr+=' | .pin = $pin'; args+=(--arg pin "$pin"); fi
    if [[ -n "$plan" ]]; then update_expr+=' | .plan = $pl'; args+=(--arg pl "$plan"); fi
    if [[ -n "$renewal_date" ]]; then update_expr+=' | .renewal_date = $rd'; args+=(--arg rd "$renewal_date"); fi

    if [[ ${#args[@]} -gt 0 ]]; then
        jq "${args[@]}" "$update_expr" "$DATA_FILE" > "$TMP_FILE" && mv "$TMP_FILE" "$DATA_FILE"
        local message="Cuenta #$index (*$service*) actualizada exitosamente\\."
        echo -e "${COL_GREEN}Cuenta #$index ($service) actualizada exitosamente.${COL_RESET}" # Console message
        send_telegram_message "$message"
    else
        echo -e "${COL_YELLOW}No se realizaron cambios.${COL_RESET}"
        # Optionally send a "No changes" message to Telegram
        # send_telegram_message "No se realizaron cambios en la cuenta #$index (*$service*)\\."
    fi
}


# Function to delete an account
delete_account() {
    list_accounts # List first (already sends to Telegram if accounts exist)
    local count=$(jq '.accounts | length' "$DATA_FILE")
     if [[ $count -eq 0 ]]; then
        return
    fi

    echo -en "${COL_YELLOW}Ingresa el número de la cuenta a eliminar: ${COL_RESET}"
    read index
    # Validate index (subtract 1 for 0-based jq index)
     if ! [[ "$index" =~ ^[0-9]+$ ]] || (( index < 1 || index > count )); then
        echo -e "${COL_RED}Selección inválida.${COL_RESET}"
        return
    fi
    local jq_index=$((index - 1))

    local service=$(jq -r ".accounts[$jq_index].service" "$DATA_FILE")
    echo -en "${COL_YELLOW}¿Estás seguro de que quieres eliminar la cuenta para $service? (s/N): ${COL_RESET}"
    read confirm
    if [[ "$confirm" =~ ^[Ss]$ ]]; then # Changed to accept 's' or 'S'
        jq "del(.accounts[$jq_index])" "$DATA_FILE" > "$TMP_FILE" && mv "$TMP_FILE" "$DATA_FILE"
        local message="Cuenta para *$service* eliminada exitosamente\\."
        echo -e "${COL_GREEN}Cuenta eliminada exitosamente.${COL_RESET}" # Console message
        send_telegram_message "$message"
    else
        echo -e "${COL_YELLOW}Eliminación cancelada.${COL_RESET}"
        # Optionally send cancellation message
        # send_telegram_message "Eliminación de la cuenta *$service* cancelada\\."
    fi
}

# Main menu
while true; do
    echo -e "${COL_BOLD}${COL_CYAN}--- Menú del Gestor de Streaming ---${COL_RESET}"
    echo -e "${COL_YELLOW}1.${COL_RESET} Listar Cuentas (Completo)"
    echo -e "${COL_YELLOW}2.${COL_RESET} Añadir Cuenta"
    echo -e "${COL_YELLOW}3.${COL_RESET} Editar Cuenta"
    echo -e "${COL_YELLOW}4.${COL_RESET} Eliminar Cuenta"
    echo -e "${COL_YELLOW}5.${COL_RESET} Listar Solo Usuarios"
    echo -e "${COL_YELLOW}6.${COL_RESET} Salir"
    echo -en "${COL_CYAN}Elige una opción: ${COL_RESET}"
    read choice

    case $choice in
        1) list_accounts ;;
        2) add_account ;;
        3) edit_account ;;
        4) delete_account ;;
        5) list_users ;;
        6) echo -e "${COL_YELLOW}Saliendo...${COL_RESET}"; send_telegram_message "Script Gestor de Streaming detenido\\."; break ;;
        *) echo -e "${COL_RED}Opción inválida. Por favor, intenta de nuevo.${COL_RESET}" ;;
    esac
    echo -en "${COL_CYAN}Presiona Enter para continuar...${COL_RESET}"
    read -p "" # Pause for user, prompt text removed as it's now colored
    # clear # Clear screen for next menu display (optional) - maybe remove if debugging telegram
done
