#!/bin/bash
# Streaming Manager Telegram Bot (Bash Implementation - Basic with Buttons)

# --- Colors ---
COL_RESET='\033[0m'
COL_CYAN='\033[0;36m'
COL_YELLOW='\033[0;33m'
COL_GREEN='\033[0;32m'
COL_RED='\033[0;31m'
COL_BOLD='\033[1m'
# --- End Colors ---

# --- Config ---
SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
CONFIG_FILE="$SCRIPT_DIR/config.env"
DATA_FILE="$SCRIPT_DIR/streaming_accounts.json"
REG_DATA_FILE="$SCRIPT_DIR/registrations.json" # Added
TMP_FILE="$SCRIPT_DIR/streaming_accounts.tmp" # Re-using tmp file for simplicity
REG_TMP_FILE="$SCRIPT_DIR/registrations.tmp" # Specific tmp for registrations
UPDATE_OFFSET_FILE="$SCRIPT_DIR/update_offset.txt" # File to store the last processed update ID
CHECK_RENEWAL_INTERVAL_SECONDS=$((3600 * 6)) # Check every 6 hours (adjust as needed)
DAYS_BEFORE_RENEWAL_NOTICE=30
CHECK_LICENSE_INTERVAL_SECONDS=$((3600)) # Check every hour

# --- Load Config ---
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
else
    echo -e "${COL_RED}Error: Archivo de configuración ($CONFIG_FILE) no encontrado.${COL_RESET}"
    echo -e "${COL_YELLOW}Ejecuta ./configure_bot.sh primero.${COL_RESET}"
    exit 1
fi

# Check essential config + license dates
if [[ -z "$TELEGRAM_BOT_TOKEN" || -z "$ADMIN_CHAT_ID" || -z "$ACTIVATION_DATE" || -z "$EXPIRATION_DATE" ]]; then
    echo -e "${COL_RED}Error: Falta configuración esencial (Token, Admin ID, Fechas de Licencia) en $CONFIG_FILE.${COL_RESET}"
    echo -e "${COL_YELLOW}Ejecuta ./configure_bot.sh para configurar.${COL_RESET}"
    exit 1
fi

# --- Dependency Checks ---
if ! command -v jq &> /dev/null || ! command -v curl &> /dev/null; then
    echo -e "${COL_RED}Error: 'jq' y 'curl' son necesarios. Instálalos.${COL_RESET}"
    exit 1
fi

# --- Telegram API Functions ---
API_URL="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}"

# Function to send message (now accepts optional inline keyboard JSON)
sendMessage() {
    local chat_id="$1"
    local text="$2"
    local keyboard_json="$3" # Optional: JSON string for inline keyboard

    # Prepare base arguments for curl
    local curl_args=(
        -s -o /dev/null -X POST
        "${API_URL}/sendMessage"
        -d "chat_id=${chat_id}"
        --data-urlencode "text=${text}" # Use --data-urlencode for robustness
        -d "parse_mode=MarkdownV2"
    )

    # Add reply_markup if keyboard_json is provided
    if [[ -n "$keyboard_json" ]]; then
        curl_args+=(-d "reply_markup=${keyboard_json}")
    fi

    # Execute curl directly with the arguments array
    curl "${curl_args[@]}"
}

# Function to answer callback queries (acknowledge button press)
answerCallbackQuery() {
    local callback_query_id="$1"
    local text="$2" # Optional text to show
    curl -s -o /dev/null -X POST "${API_URL}/answerCallbackQuery" \
         -d callback_query_id="${callback_query_id}" \
         -d text="${text}"
}

# Function to send document
sendDocument() {
    local chat_id="$1"
    local file_path="$2"
    local caption="$3" # Optional caption

    curl -s -o /dev/null -X POST "${API_URL}/sendDocument" \
         -F chat_id="${chat_id}" \
         -F document=@"${file_path}" \
         -F caption="${caption}" \
         -F parse_mode="MarkdownV2" # For caption
}

# Function to get updates
getUpdates() {
    local offset="$1"
    local response
    response=$(curl -s -X GET "${API_URL}/getUpdates?offset=${offset}&timeout=60")
    echo "$response"
}

# --- License Check Function ---
check_license_validity() {
    local current_time_sec=$(date +%s)
    local expiration_time_sec
    expiration_time_sec=$(date -d "$EXPIRATION_DATE" +%s)

    if [[ $? -ne 0 ]]; then
        echo -e "${COL_RED}Error: Formato de EXPIRATION_DATE ('$EXPIRATION_DATE') inválido en $CONFIG_FILE.${COL_RESET}"
        # Decide action: maybe notify admin and exit? For now, just log and exit.
        sendMessage "$ADMIN_CHAT_ID" "Error Crítico: Formato de fecha de expiración inválido en config\\.env\\. El bot se detendrá\\."
        return 1 # Indicate failure
    fi

    if (( current_time_sec > expiration_time_sec )); then
        echo -e "${COL_RED}Error: Licencia expirada el $EXPIRATION_DATE. Deteniendo bot.${COL_RESET}"
        sendMessage "$ADMIN_CHAT_ID" "Error Crítico: La licencia del bot expiró el $EXPIRATION_DATE\\. El bot se ha detenido\\."
        return 1 # Indicate failure (expired)
    fi

    # Optional: Warn if nearing expiration
    local days_left=$(((expiration_time_sec - current_time_sec) / 86400))
    if (( days_left <= 7 )); then # Warn if 7 days or less left
         echo -e "${COL_YELLOW}Advertencia: La licencia expira en $days_left días ($EXPIRATION_DATE).${COL_RESET}"
         # Consider sending a Telegram warning too, maybe less frequently than every hour.
    fi

    return 0 # Indicate success (valid)
}

# --- Initial License Check ---
if ! check_license_validity; then
    exit 1 # Exit if license is invalid/expired on startup
fi
echo -e "${COL_GREEN}Licencia válida hasta $EXPIRATION_DATE.${COL_RESET}"
# --- End Initial License Check ---

# --- Bot Logic Functions ---

# --- Account Management ---
# Function to check for upcoming renewals
check_renewals() {
    echo -e "${COL_CYAN}Ejecutando comprobación de renovaciones...${COL_RESET}"
    local current_time_sec=$(date +%s)
    local notification_sent=false

    # Check if data file is valid JSON before proceeding
    if ! jq -e '.accounts' "$DATA_FILE" > /dev/null 2>&1; then
        echo -e "${COL_RED}Error: Archivo de datos no válido para check_renewals.${COL_RESET}"
        return
    fi

    # Iterate through accounts using jq
    while IFS=$'\t' read -r service username renewal_date; do
        # Skip if renewal_date is empty or invalid format (basic check)
        if [[ -z "$renewal_date" ]] || ! date -d "$renewal_date" "+%s" > /dev/null 2>&1; then
            # echo "Skipping account '$service' - '$username': Invalid or empty renewal date '$renewal_date'"
            continue
        fi

        local renewal_time_sec=$(date -d "$renewal_date" +%s)
        local diff_sec=$((renewal_time_sec - current_time_sec))
        local diff_days=$((diff_sec / 86400)) # 86400 seconds in a day

        # echo "Checking $service ($username): Renews on $renewal_date ($diff_days days left)" # Debug

        if (( diff_sec > 0 && diff_days <= DAYS_BEFORE_RENEWAL_NOTICE )); then
            local message="⚠️ *Alerta de Renovación* ⚠️\nServicio: *$service*\nUsuario: \`$username\`\nFecha de Renovación: \`$renewal_date\` \\($diff_days días restantes\\)"
            sendMessage "$ADMIN_CHAT_ID" "$message"
            notification_sent=true
            sleep 1 # Small delay between potential multiple notifications
        fi
    done < <(jq -r '.accounts[] | select(.renewal_date != null and .renewal_date != "") | [.service, .username, .renewal_date] | @tsv' "$DATA_FILE")

    if $notification_sent; then
         echo -e "${COL_GREEN}Notificaciones de renovación enviadas.${COL_RESET}"
    else
         echo -e "${COL_YELLOW}No hay renovaciones próximas en los siguientes $DAYS_BEFORE_RENEWAL_NOTICE días.${COL_RESET}"
    fi
}


handle_list() {
    local chat_id="$1"
    local output
    if ! jq -e '.accounts' "$DATA_FILE" > /dev/null 2>&1 || [[ $(jq '.accounts | length' "$DATA_FILE") -eq 0 ]]; then
        output="No se encontraron cuentas\\."
    else
        output=$(jq -r '.accounts[] | "\(.service) \- \(.username)"' "$DATA_FILE" | nl | sed 's/^ *//; s/ /\\. /')
        output="--- Cuentas ---\n\`\`\`\n${output}\n\`\`\`"
    fi
    sendMessage "$chat_id" "$output"
}

handle_add() {
    local chat_id="$1"
    local args="$2" # Expecting: Service User Pass Plan YYYY-MM-DD [PIN]

    # Basic parsing (fragile!) - assumes space separation
    read -r service user pass plan renewal_date pin <<< "$args"

    if [[ -z "$service" || -z "$user" || -z "$pass" || -z "$plan" || -z "$renewal_date" ]]; then
        sendMessage "$chat_id" "Formato incorrecto\\. Uso: \`/add Servicio Usuario Contraseña Plan YYYY-MM-DD [PIN]\`"
        return
    fi

    local creation_date=$(date +%Y-%m-%d)
    pin=${pin:-""} # Default pin to empty if not provided

    jq --arg s "$service" --arg u "$user" --arg p "$pass" --arg pin "$pin" \
       --arg pl "$plan" --arg rd "$renewal_date" --arg cd "$creation_date" \
       '.accounts += [{service: $s, username: $u, password: $p, pin: $pin, plan: $pl, renewal_date: $rd, creation_date: $cd}]' \
       "$DATA_FILE" > "$TMP_FILE"

    if mv "$TMP_FILE" "$DATA_FILE"; then
        sendMessage "$chat_id" "Cuenta para *$service* añadida exitosamente\\."
    else
        sendMessage "$chat_id" "Error al guardar la cuenta para *$service*\\."
    fi
}

handle_delete() {
    local chat_id="$1"
    local index_str="$2"

    if ! [[ "$index_str" =~ ^[0-9]+$ ]]; then
         sendMessage "$chat_id" "Número inválido\\. Uso: \`/delete Numero\` \\(usa \`/list\` para ver los números\\)\\."
         return
    fi

    local count=$(jq '.accounts | length' "$DATA_FILE")
    local index=$((index_str)) # Convert to number

    if (( index < 1 || index > count )); then
        sendMessage "$chat_id" "Número fuera de rango \\($index\\)\\. Hay $count cuentas\\."
        return
    fi

    local jq_index=$((index - 1))
    local service=$(jq -r ".accounts[$jq_index].service" "$DATA_FILE")

    jq "del(.accounts[$jq_index])" "$DATA_FILE" > "$TMP_FILE"

    if mv "$TMP_FILE" "$DATA_FILE"; then
        sendMessage "$chat_id" "Cuenta #$index (*$service*) eliminada exitosamente\\."
    else
        sendMessage "$chat_id" "Error al eliminar la cuenta #$index (*$service*)\\."
    fi
}

# Function to view account details (Modified to ask for number if called without args)
handle_view() {
    local chat_id="$1"
    local index_str="$2"

    if [[ -z "$index_str" ]]; then
        # Called without args (likely from button), ask for number
        sendMessage "$chat_id" "Por favor, ingresa el número de la cuenta a ver\\. Ejemplo: \`/view 3\`"
        return
    fi

    # Validate index
    if ! [[ "$index_str" =~ ^[0-9]+$ ]]; then
         sendMessage "$chat_id" "Número inválido\\. Uso: \`/view Numero\` \\(usa \`/list\` para ver los números\\)\\."
         return
    fi

    local count=$(jq '.accounts | length' "$DATA_FILE")
    local index=$((index_str)) # Convert to number

    if (( index < 1 || index > count )); then
        sendMessage "$chat_id" "Número fuera de rango \\($index\\)\\. Hay $count cuentas\\."
        return
    fi

    local jq_index=$((index - 1))

    # Get all details using jq, format nicely for Telegram
    local details=$(jq -r ".accounts[$jq_index] | to_entries | map(\"\(.key): \(.value|tostring)\") | .[]" "$DATA_FILE")

    if [[ -z "$details" ]]; then
        sendMessage "$chat_id" "Error al obtener detalles para la cuenta #$index\\."
        return
    fi

    # Escape Markdown characters in the details (basic escaping)
    details=$(echo "$details" | sed 's/\([_*`\[\]()~>#+-=|{}.!]\)/\\\1/g')

    local output="*Detalles Cuenta #$index*\n\`\`\`\n$details\n\`\`\`"
    sendMessage "$chat_id" "$output"
}

# Function to edit an account field
handle_edit() {
    local chat_id="$1"
    local args="$2" # Expecting: Numero Campo=NuevoValor

    # Extract index and the rest
    local index_str=$(echo "$args" | cut -d' ' -f1)
    local update_arg=$(echo "$args" | cut -d' ' -f2-) # Get everything after the index

    # Validate index
    if ! [[ "$index_str" =~ ^[0-9]+$ ]]; then
         sendMessage "$chat_id" "Número inválido\\. Uso: \`/edit Numero Campo=NuevoValor\`\\."
         return
    fi

    local count=$(jq '.accounts | length' "$DATA_FILE")
    local index=$((index_str))
    if (( index < 1 || index > count )); then
        sendMessage "$chat_id" "Número fuera de rango \\($index\\)\\. Hay $count cuentas\\."
        return
    fi
    local jq_index=$((index - 1))

    # Parse Campo=NuevoValor (basic parsing, allows spaces in NuevoValor)
    local field=$(echo "$update_arg" | cut -d'=' -f1)
    local value=$(echo "$update_arg" | cut -d'=' -f2-)

    # Validate field and value
    if [[ -z "$field" || -z "$value" ]]; then
        sendMessage "$chat_id" "Formato inválido\\. Uso: \`/edit Numero Campo=NuevoValor\`\\. Asegúrate de incluir '='\\."
        return
    fi

    # Check if the field is valid (optional but recommended)
    local valid_fields=("service" "username" "password" "pin" "plan" "renewal_date") # creation_date shouldn't be edited
    if ! printf '%s\n' "${valid_fields[@]}" | grep -q -w "$field"; then
        sendMessage "$chat_id" "Campo inválido: \`$field\`\\. Campos válidos: service, username, password, pin, plan, renewal_date\\."
        return
    fi

    # Validate renewal_date format if that's the field being edited
    if [[ "$field" == "renewal_date" ]]; then
        if ! date -d "$value" "+%Y-%m-%d" > /dev/null 2>&1 || [[ ! "$value" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
            sendMessage "$chat_id" "Formato de fecha inválido para renewal_date\\. Usa YYYY-MM-DD\\."
            return
        fi
    fi

    # Update using jq
    jq --argjson idx "$jq_index" --arg fld "$field" --arg val "$value" \
       '.accounts[$idx][$fld] = $val' "$DATA_FILE" > "$TMP_FILE"

    if mv "$TMP_FILE" "$DATA_FILE"; then
        sendMessage "$chat_id" "Cuenta #$index actualizada exitosamente\\. Campo \`$field\` modificado\\."
    else
        sendMessage "$chat_id" "Error al actualizar la cuenta #$index\\."
    fi
}

# Function to handle backup request
handle_backup() {
    local chat_id="$1"
    local backup_successful=false

    if [[ -f "$DATA_FILE" ]]; then
        sendMessage "$chat_id" "Generando y enviando backup de \`streaming_accounts.json\`\\.\\.\\."
        sendDocument "$chat_id" "$DATA_FILE" "Backup de cuentas al $(date '+%Y-%m-%d %H:%M:%S')"
        echo -e "${COL_GREEN}Backup de cuentas enviado al chat $chat_id.${COL_RESET}"
        backup_successful=true
    else
        sendMessage "$chat_id" "Error: No se encontró el archivo de datos \`$DATA_FILE\` para hacer backup\\."
        echo -e "${COL_RED}Error de backup: $DATA_FILE no encontrado.${COL_RESET}"
    fi

    # Backup registrations file
    if [[ -f "$REG_DATA_FILE" ]]; then
        sendMessage "$chat_id" "Generando y enviando backup de \`registrations.json\`\\.\\.\\."
        sendDocument "$chat_id" "$REG_DATA_FILE" "Backup de registros al $(date '+%Y-%m-%d %H:%M:%S')"
        echo -e "${COL_GREEN}Backup de registros enviado al chat $chat_id.${COL_RESET}"
        backup_successful=true
    else
        # Don't send error if file just doesn't exist yet, maybe send info message
        if [[ -e "$REG_DATA_FILE" ]]; then # Check if it exists but isn't a file or readable
             sendMessage "$chat_id" "Error: No se pudo acceder al archivo de datos \`$REG_DATA_FILE\` para hacer backup\\."
             echo -e "${COL_RED}Error de backup: $REG_DATA_FILE no accesible.${COL_RESET}"
        else
             sendMessage "$chat_id" "Info: No se encontró archivo de registros \`$REG_DATA_FILE\` para backup \\(puede que aún no se haya usado la función de registro\\)\\."
             echo -e "${COL_YELLOW}Info backup: $REG_DATA_FILE no encontrado.${COL_RESET}"
        fi
    fi

    if ! $backup_successful; then
         sendMessage "$chat_id" "No se pudo generar ningún backup\\. Comprueba los logs del servidor\\."
    fi
}

# --- Registration Management ---

# Function to handle user registration command
handle_register() {
    local chat_id="$1"
    # Expecting: Platform;Name;Phone;PaymentType;Email;PIN;StartDate;EndDate
    local args_str="$2"
    local IFS=';' # Set Input Field Separator to semicolon
    read -r platform name phone payment_type email pin start_date end_date <<< "$args_str"
    local IFS=$' \t\n' # Reset IFS

    # Basic validation
    if [[ -z "$platform" || -z "$name" || -z "$phone" || -z "$payment_type" || -z "$email" || -z "$start_date" || -z "$end_date" ]]; then
        sendMessage "$chat_id" "Faltan datos o formato incorrecto\\. Asegúrate de separar todos los campos con punto y coma \\';'\\.\nFormato: \`/register Plataforma;Nombre;Celular;TipoPago;Email;PIN;FechaAlta;FechaVenc\`"
        return
    fi
    # Optional: More specific validation (date format, email format, etc.)

    pin=${pin:-"N/A"} # Default pin if empty

    # Ensure registrations file is valid JSON
    if ! jq -e '.registrations' "$REG_DATA_FILE" > /dev/null 2>&1; then
         echo '{"registrations": []}' > "$REG_DATA_FILE" # Recreate if invalid
         echo -e "${COL_YELLOW}Archivo $REG_DATA_FILE inválido o no encontrado, recreado.${COL_RESET}"
    fi

    # Add registration using jq
    jq --arg plat "$platform" --arg nm "$name" --arg ph "$phone" --arg pt "$payment_type" \
       --arg em "$email" --arg pin "$pin" --arg sd "$start_date" --arg ed "$end_date" \
       '.registrations += [{platform: $plat, name: $nm, phone: $ph, payment_type: $pt, email: $em, pin: $pin, start_date: $sd, end_date: $ed}]' \
       "$REG_DATA_FILE" > "$REG_TMP_FILE"

    if mv "$REG_TMP_FILE" "$REG_DATA_FILE"; then
        sendMessage "$chat_id" "Usuario *$name* registrado exitosamente para la plataforma *$platform*\\."
        echo -e "${COL_GREEN}Registro añadido para $name ($platform).${COL_RESET}"
    else
        sendMessage "$chat_id" "Error al guardar el registro para *$name*\\."
        echo -e "${COL_RED}Error al mover $REG_TMP_FILE a $REG_DATA_FILE.${COL_RESET}"
    fi
}

# Function to list registrations
handle_list_registrations() {
    local chat_id="$1"
    local output
    if ! jq -e '.registrations' "$REG_DATA_FILE" > /dev/null 2>&1 || [[ $(jq '.registrations | length' "$REG_DATA_FILE") -eq 0 ]]; then
        output="No se encontraron registros de usuarios\\."
    else
        # Format: Num. Name (Platform) - Ends: YYYY-MM-DD
        output=$(jq -r '.registrations[] | "\(.name) (\(.platform)) \- Vence: \(.end_date)"' "$REG_DATA_FILE" | nl | sed 's/^ *//; s/ /\\. /')
        output="--- Registros de Usuarios ---\n\`\`\`\n${output}\n\`\`\`"
    fi
    sendMessage "$chat_id" "$output"
}

# Function to delete a registration
handle_delete_registration() {
    local chat_id="$1"
    local index_str="$2"

    if ! [[ "$index_str" =~ ^[0-9]+$ ]]; then
         sendMessage "$chat_id" "Número inválido\\. Uso: \`/delreg Numero\` \\(usa \`/listreg\` para ver los números\\)\\."
         return
    fi

    local count=$(jq '.registrations | length' "$REG_DATA_FILE" 2>/dev/null || echo 0)
    local index=$((index_str)) # Convert to number

    if (( count == 0 )); then
        sendMessage "$chat_id" "No hay registros para eliminar\\."
        return
    fi

    if (( index < 1 || index > count )); then
        sendMessage "$chat_id" "Número fuera de rango \\($index\\)\\. Hay $count registros\\."
        return
    fi

    local jq_index=$((index - 1))
    # Get name and platform for confirmation message
    local reg_info=$(jq -r ".registrations[$jq_index] | \"\(.name) (\(.platform))\"" "$REG_DATA_FILE")

    jq "del(.registrations[$jq_index])" "$REG_DATA_FILE" > "$REG_TMP_FILE"

    if mv "$REG_TMP_FILE" "$REG_DATA_FILE"; then
        sendMessage "$chat_id" "Registro #$index (*$reg_info*) eliminado exitosamente\\."
        echo -e "${COL_GREEN}Registro #$index ($reg_info) eliminado.${COL_RESET}"
    else
        sendMessage "$chat_id" "Error al eliminar el registro #$index (*$reg_info*)\\."
        echo -e "${COL_RED}Error al mover $REG_TMP_FILE a $REG_DATA_FILE.${COL_RESET}"
    fi
}


# --- Common Functions ---

# Function to send the main menu with buttons
handle_menu() {
    local chat_id="$1"
    local menu_text="*Menú Principal*\nElige una opción:"
    # Define the inline keyboard JSON
    local keyboard='{"inline_keyboard":['
    # Row 1: Account Management
    keyboard+='[{"text":"📊 Listar Cuentas","callback_data":"list_accounts"},{"text":"📄 Ver Cuenta","callback_data":"view_account_prompt"}],'
    keyboard+='[{"text":"➕ Añadir Cuenta","callback_data":"add_account_prompt"},{"text":"✏️ Editar Cuenta","callback_data":"edit_account_prompt"},{"text":"🗑️ Eliminar Cuenta","callback_data":"delete_account_prompt"}],'
    # Row 2: Registration Management
    keyboard+='[{"text":"👤 Registrar Usuario","callback_data":"register_user_prompt"},{"text":"👥 Listar Registros","callback_data":"list_regs"},{"text":"❌ Borrar Registro","callback_data":"delete_reg_prompt"}],' # New row
    # Row 3: Utilities & Admin
    keyboard+='[{"text":"💾 Backup","callback_data":"backup_data"},{"text":"❓ Ayuda","callback_data":"show_help"},{"text":"🔒 Licencia","callback_data":"license_status"}]'
    keyboard+=']}'
    sendMessage "$chat_id" "$menu_text" "$keyboard"
}

handle_help() {
    local chat_id="$1"
    local help_text="Usa \`/menu\` para ver los botones\\. Algunas acciones requerirán que envíes un comando de texto después de presionar el botón correspondiente:\n\n"
    help_text+="*Gestión de Cuentas Streaming*\n"
    help_text+="*   📊 Listar:* Muestra la lista de cuentas\\.\n"
    help_text+="*   📄 Ver:* Pide número \\> \`/view Numero\`\\.\n"
    help_text+="*   ➕ Añadir:* Explica formato \\> \`/add Servicio ...\`\\.\n"
    help_text+="*   ✏️ Editar:* Explica formato \\> \`/edit Numero ...\`\\.\n"
    help_text+="*   🗑️ Eliminar:* Explica formato \\> \`/delete Numero\`\\.\n\n"
    help_text+="*Gestión de Registros de Usuarios*\n" # New Section
    help_text+="*   👤 Registrar:* Explica formato \\> \`/register Plataforma;Nombre;...;\`\\.\n"
    help_text+="*   👥 Listar:* Muestra la lista de registros\\.\n"
    help_text+="*   ❌ Borrar:* Pide número \\> \`/delreg Numero\`\\.\n\n"
    help_text+="*Utilidades y Admin*\n"
    help_text+="*   💾 Backup:* Envía los archivos de datos \`streaming_accounts.json\` y \`registrations.json\`\\.\n" # Updated backup description
    help_text+="*   ❓ Ayuda:* Muestra esta ayuda\\.\n"
    help_text+="*   🔒 Licencia:* Muestra el estado de la licencia\\.\n\n"
    help_text+="*Comandos Adicionales (Texto)*\n"
    help_text+="\`/licencia_expira YYYY-MM-DD\` \\- Cambia la fecha de expiración\\.\n"
    help_text+="\`/listreg\` \\- Alias para listar registros\\.\n"
    help_text+="\`/delreg Numero\` \\- Alias para borrar registro\\."
    sendMessage "$chat_id" "$help_text"
}

# --- Admin Commands ---
handle_license_status() {
    local chat_id="$1"
    local current_time_sec=$(date +%s)
    local expiration_time_sec=$(date -d "$EXPIRATION_DATE" +%s 2>/dev/null || echo 0)
    local activation_time_sec=$(date -d "$ACTIVATION_DATE" +%s 2>/dev/null || echo 0)
    local status_msg="*Estado de Licencia*\n"
    status_msg+="Activación: \`$ACTIVATION_DATE\`\n"
    status_msg+="Expiración: \`$EXPIRATION_DATE\`\n"

    if (( expiration_time_sec == 0 || activation_time_sec == 0 )); then
         status_msg+="Estado: ⚠️ *Error en formato de fechas*\n" # Removed color codes
    elif (( current_time_sec > expiration_time_sec )); then
         status_msg+="Estado: 🔴 *Expirada*\n" # Removed color codes
    else
         local days_left=$(((expiration_time_sec - current_time_sec) / 86400))
         status_msg+="Estado: 🟢 *Activa* \\($days_left días restantes\\)\n" # Removed color codes
    fi
    sendMessage "$chat_id" "$status_msg"
}

handle_set_expiry() {
    local chat_id="$1"
    local new_date="$2"

    # Validate date format YYYY-MM-DD
    if ! date -d "$new_date" "+%Y-%m-%d" > /dev/null 2>&1 || [[ ! "$new_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        sendMessage "$chat_id" "Formato de fecha inválido\\. Usa \`/licencia_expira YYYY-MM-DD\`\\."
        return
    fi

    # Use sed to update the EXPIRATION_DATE line in config.env
    # This is safer than rewriting the whole file if other vars exist
    if sed -i "s/^EXPIRATION_DATE=.*$/EXPIRATION_DATE='$new_date'/" "$CONFIG_FILE"; then
        # Update the loaded variable in the current script instance
        EXPIRATION_DATE="$new_date"
        sendMessage "$chat_id" "Fecha de expiración actualizada a \`$new_date\`\\. La comprobación se realizará en el próximo ciclo\\."
        echo -e "${COL_GREEN}Fecha de expiración actualizada a $new_date por admin.${COL_RESET}"
        # Re-check validity immediately? Optional.
        # check_license_validity
    else
        sendMessage "$chat_id" "Error al actualizar el archivo de configuración\\. Verifica los permisos\\."
        echo -e "${COL_RED}Error al intentar actualizar EXPIRATION_DATE en $CONFIG_FILE con sed.${COL_RESET}"
    fi
}

# --- Main Loop ---
echo -e "${COL_GREEN}Iniciando bot...${COL_RESET}"
offset=0
last_renewal_check_time=0 # Initialize last check time
last_license_check_time=$(date +%s) # Initialize license check time
# Load last offset if file exists
if [[ -f "$UPDATE_OFFSET_FILE" ]]; then
    offset=$(cat "$UPDATE_OFFSET_FILE")
    if ! [[ "$offset" =~ ^[0-9]+$ ]]; then offset=0; fi # Reset if invalid
fi
echo -e "${COL_YELLOW}Offset inicial: $offset${COL_RESET}"

while true; do
    # --- Check License Periodically ---
    current_time=$(date +%s)
    if (( current_time - last_license_check_time >= CHECK_LICENSE_INTERVAL_SECONDS )); then
        if ! check_license_validity; then
            exit 1 # Exit if license check fails
        fi
        last_license_check_time=$current_time
    fi
    # --- End Check License ---

    # --- Check Renewals Periodically ---
    if (( current_time - last_renewal_check_time >= CHECK_RENEWAL_INTERVAL_SECONDS )); then
        check_renewals
        last_renewal_check_time=$current_time
    fi
    # --- End Check Renewals ---

    updates=$(getUpdates "$offset")
    # Check for errors from getUpdates (e.g., network issues, invalid token)
    if ! jq -e '.ok == true' <<< "$updates" > /dev/null 2>&1; then
        echo -e "${COL_RED}Error al obtener actualizaciones de Telegram:${COL_RESET}"
        echo "$updates"
        sleep 10 # Wait before retrying
        continue
    fi

    # Process each update
    while IFS= read -r update_json; do
        # --- Extract common data ---
        update_id=$(jq -r '.update_id' <<< "$update_json")
        offset=$((update_id + 1)) # Update offset immediately

        # --- Check for Callback Query (Button Press) ---
        callback_query=$(jq -r '.callback_query // empty' <<< "$update_json")
        if [[ -n "$callback_query" ]]; then
            callback_id=$(jq -r '.id' <<< "$callback_query")
            callback_data=$(jq -r '.data' <<< "$callback_query")
            callback_chat_id=$(jq -r '.message.chat.id' <<< "$callback_query")
            callback_sender_id=$(jq -r '.from.id' <<< "$callback_query") # User who clicked

            echo -e "${COL_CYAN}Procesando callback $callback_id del chat $callback_chat_id: $callback_data${COL_RESET}"

            # --- Security Check: Only process callbacks from admin ---
            if [[ "$callback_chat_id" != "$ADMIN_CHAT_ID" ]]; then
                echo -e "${COL_YELLOW}Callback ignorado del chat ID: $callback_chat_id (no es admin)${COL_RESET}"
                answerCallbackQuery "$callback_id" "No autorizado" # Acknowledge, maybe show error
                continue # Skip to next update
            fi

            # Acknowledge the button press immediately
            answerCallbackQuery "$callback_id"

            # Handle callback data
            case "$callback_data" in
                # Account Callbacks
                "list_accounts") handle_list "$callback_chat_id" ;;
                "view_account_prompt") sendMessage "$callback_chat_id" "Para ver detalles, envía: \`/view Numero\`" ;;
                "add_account_prompt") sendMessage "$callback_chat_id" "Para añadir cuenta, envía:\n\`/add Servicio Usuario Contraseña Plan YYYY-MM-DD [PIN]\`" ;;
                "edit_account_prompt") sendMessage "$callback_chat_id" "Para editar cuenta, envía:\n\`/edit Numero Campo=NuevoValor\`" ;;
                "delete_account_prompt") sendMessage "$callback_chat_id" "Para eliminar cuenta, envía: \`/delete Numero\` ;;

                # Registration Callbacks
                "register_user_prompt") # New
                    sendMessage "$callback_chat_id" "Para registrar un usuario, envía el comando con *todos* los campos separados por punto y coma \\';':\n\`/register Plataforma;Nombre;Celular;TipoPago;Email;PIN;FechaAlta;FechaVenc\`\n*(Ej: /register Netflix;Juan Perez;12345;Paypal;jp@mail.com;1234;2024-01-01;2025-01-01)*"
                    ;;
                "list_regs") # New
                    handle_list_registrations "$callback_chat_id"
                    ;;
                "delete_reg_prompt") # New
                    sendMessage "$callback_chat_id" "Para eliminar un registro, envía: \`/delreg Numero\`\n\\(Usa el botón 'Listar Registros' o \`/listreg\` para ver los números\\)\\."
                    ;;

                # Utility/Admin Callbacks
                "backup_data") handle_backup "$callback_chat_id" ;; # Consider backing up both files?
                "show_help") handle_help "$callback_chat_id" ;;
                "license_status") handle_license_status "$callback_chat_id" ;;
                *) sendMessage "$callback_chat_id" "Acción desconocida desde botón: \`$callback_data\`" ;;
            esac
            continue # Finished processing callback, move to next update
        fi

        # --- Check for Message ---
        message=$(jq -r '.message // empty' <<< "$update_json")
        if [[ -n "$message" ]]; then
            chat_id=$(jq -r '.chat.id' <<< "$message")
            text=$(jq -r '.text // empty' <<< "$message") # Handle non-text messages gracefully
            sender_id=$(jq -r '.from.id' <<< "$message")

            # Ignore empty text messages
            if [[ -z "$text" ]]; then
                continue
            fi

            # --- Security Check: Only process messages from admin ---
            is_admin=false
            if [[ "$chat_id" == "$ADMIN_CHAT_ID" ]]; then
                is_admin=true
            else
                echo -e "${COL_YELLOW}Mensaje ignorado del chat ID: $chat_id (no es admin)${COL_RESET}"
                continue # Skip to next update
            fi

            # --- Command Handling (Text) ---
            command=""
            args=""
            if [[ "$text" == /* ]]; then
                command=$(echo "$text" | cut -d' ' -f1)
                args=$(echo "$text" | cut -d' ' -f2-)
            fi

            # Only process if it's a command
            if [[ -n "$command" ]]; then
                 echo -e "${COL_CYAN}Procesando comando $command del chat $chat_id: $args${COL_RESET}"
                 case "$command" in
                    "/menu") handle_menu "$chat_id" ;;
                    # Account Commands
                    "/list") handle_list "$chat_id" ;;
                    "/view") handle_view "$chat_id" "$args" ;;
                    "/add") handle_add "$chat_id" "$args" ;;
                    "/edit") handle_edit "$chat_id" "$args" ;;
                    "/delete") handle_delete "$chat_id" "$args" ;;
                    # Registration Commands
                    "/register") handle_register "$chat_id" "$args" ;; # New
                    "/listreg") handle_list_registrations "$chat_id" ;; # New alias
                    "/delreg") handle_delete_registration "$chat_id" "$args" ;; # New alias
                    # Utility/Admin Commands
                    "/backup") handle_backup "$chat_id" ;;
                    "/help"|"/start") handle_help "$chat_id" ;;
                    "/licencia_estado") handle_license_status "$chat_id" ;;
                    "/licencia_expira") handle_set_expiry "$chat_id" "$args" ;;
                    *)
                        # Basic check to avoid "unknown command" for multi-part inputs
                        if [[ "$command" != "/view" && "$command" != "/add" && "$command" != "/edit" && "$command" != "/delete" && "$command" != "/register" && "$command" != "/delreg" ]]; then
                             sendMessage "$chat_id" "Comando desconocido: \`$command\`\\. Usa \`/menu\` o \`/help\`\\."
                        fi
                        ;;
                 esac
            fi
        fi

    done < <(jq -c '.result[]' <<< "$updates") # Process each result object

    # Save the next offset
    echo "$offset" > "$UPDATE_OFFSET_FILE"

    # Optional: Short sleep to prevent busy-waiting if no updates
    # sleep 1

done

echo -e "${COL_RED}Bot detenido.${COL_RESET}"
