#!/bin/bash
# Main script for Streaming Manager

DATA_FILE="streaming_accounts.json"
TMP_FILE="streaming_accounts.tmp"
CONFIG_FILE="config.env"

# --- Dependency Checks ---
if ! command -v jq &> /dev/null; then
    echo "Error: 'jq' command not found. Please install jq (e.g., sudo apt install jq)."
    exit 1
fi
if ! command -v curl &> /dev/null; then
    echo "Error: 'curl' command not found. Please install curl (e.g., sudo apt install curl)."
    exit 1
fi
# --- End Dependency Checks ---

# --- Load Configuration ---
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
else
    echo "Error: Configuration file ($CONFIG_FILE) not found."
    echo "Please run the install script (bash install.sh) to configure Telegram."
    exit 1
fi
# --- End Load Configuration ---

# --- Ensure Data File Exists ---
if [[ ! -f "$DATA_FILE" ]]; then
    echo "Data file ($DATA_FILE) not found. Creating it..."
    echo '{"accounts": []}' > "$DATA_FILE"
    chmod 600 "$DATA_FILE" # Set permissions (rw-------)
    echo "Data file created successfully."
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
    echo "--- Streaming Accounts ---"
    local output
    # Check if the file is valid JSON and has accounts array before proceeding
    if ! jq -e '.accounts' "$DATA_FILE" > /dev/null 2>&1; then
        echo "Error: Data file ($DATA_FILE) is not valid JSON or is missing the 'accounts' array."
        echo "Please check or recreate the file with content: {\"accounts\": []}"
        return 1 # Indicate error
    fi

    if ! jq '.accounts | length' "$DATA_FILE" > /dev/null 2>&1 || [[ $(jq '.accounts | length' "$DATA_FILE") -eq 0 ]]; then
        output="No accounts found."
        echo "$output"
    else
        # Prepare output for both console and Telegram
        output=$(jq -r '.accounts[] | "\(.service) \- \(.username)"' "$DATA_FILE" | nl | sed 's/^ *//; s/ /\\. /') # Format for MarkdownV2
        echo "--- Streaming Accounts ---" # Console header
        jq -r '.accounts[] | "\(.service) - \(.username)"' "$DATA_FILE" | nl # Console output
        echo "------------------------" # Console footer
        # Send formatted list to Telegram
        send_telegram_message "--- Streaming Accounts ---\n\`\`\`\n${output}\n\`\`\`"
        output="" # Clear output var as it was sent
    fi
    # If there was a simple message (like "No accounts found"), send it
    [[ -n "$output" ]] && send_telegram_message "$output"
    echo "------------------------"
}

# Function to add an account
add_account() {
    echo "--- Add New Account ---"
    read -p "Service Name: " service
    read -p "Username: " username
    read -sp "Password: " password # -s hides input
    echo
    read -sp "PIN (optional, leave blank if none): " pin # -s hides input
    echo
    read -p "Plan: " plan
    read -p "Renewal Date (YYYY-MM-DD): " renewal_date
    local creation_date=$(date +%Y-%m-%d) # Get current date

    jq --arg s "$service" --arg u "$username" --arg p "$password" --arg pin "$pin" \
       --arg pl "$plan" --arg rd "$renewal_date" --arg cd "$creation_date" \
       '.accounts += [{service: $s, username: $u, password: $p, pin: $pin, plan: $pl, renewal_date: $rd, creation_date: $cd}]' \
       "$DATA_FILE" > "$TMP_FILE" && mv "$TMP_FILE" "$DATA_FILE"

    local message="Account for *$service* added successfully on $creation_date\\." # Escape Markdown characters
    echo "Account for $service added successfully on $creation_date." # Console message
    send_telegram_message "$message"
}

# Function to edit an account
edit_account() {
    list_accounts # List first (already sends to Telegram if accounts exist)
    local count=$(jq '.accounts | length' "$DATA_FILE")
    if [[ $count -eq 0 ]]; then
        return
    fi

    read -p "Enter the number of the account to edit: " index
    # Validate index (subtract 1 for 0-based jq index)
    if ! [[ "$index" =~ ^[0-9]+$ ]] || (( index < 1 || index > count )); then
        echo "Invalid selection."
        return
    fi
    local jq_index=$((index - 1))
    local old_service=$(jq -r ".accounts[$jq_index].service" "$DATA_FILE") # Get service name for message

    echo "--- Edit Account #$index ($old_service) ---"
    # Display current data (optional)
    jq -r ".accounts[$jq_index]" "$DATA_FILE"

    read -p "New Service Name (leave blank to keep current): " service
    read -p "New Username (leave blank to keep current): " username
    read -sp "New Password (leave blank to keep current): " password
    echo
    read -sp "New PIN (leave blank to keep current): " pin
    echo
    read -p "New Plan (leave blank to keep current): " plan
    read -p "New Renewal Date (YYYY-MM-DD, leave blank to keep current): " renewal_date

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
        local message="Account #$index (*$service*) updated successfully\\."
        echo "Account #$index ($service) updated successfully." # Console message
        send_telegram_message "$message"
    else
        echo "No changes made."
        # Optionally send a "No changes" message to Telegram
        # send_telegram_message "No changes made to account #$index (*$service*)\\."
    fi
}


# Function to delete an account
delete_account() {
    list_accounts # List first (already sends to Telegram if accounts exist)
    local count=$(jq '.accounts | length' "$DATA_FILE")
     if [[ $count -eq 0 ]]; then
        return
    fi

    read -p "Enter the number of the account to delete: " index
    # Validate index (subtract 1 for 0-based jq index)
     if ! [[ "$index" =~ ^[0-9]+$ ]] || (( index < 1 || index > count )); then
        echo "Invalid selection."
        return
    fi
    local jq_index=$((index - 1))

    local service=$(jq -r ".accounts[$jq_index].service" "$DATA_FILE")
    read -p "Are you sure you want to delete the account for $service? (y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        jq "del(.accounts[$jq_index])" "$DATA_FILE" > "$TMP_FILE" && mv "$TMP_FILE" "$DATA_FILE"
        local message="Account for *$service* deleted successfully\\."
        echo "Account deleted successfully." # Console message
        send_telegram_message "$message"
    else
        echo "Deletion cancelled."
        # Optionally send cancellation message
        # send_telegram_message "Deletion of account *$service* cancelled\\."
    fi
}

# Main menu
while true; do
    echo "--- Streaming Manager Menu ---"
    echo "1. List Accounts"
    echo "2. Add Account"
    echo "3. Edit Account"
    echo "4. Delete Account"
    echo "5. Exit"
    read -p "Choose an option: " choice

    case $choice in
        1) list_accounts ;;
        2) add_account ;;
        3) edit_account ;;
        4) delete_account ;;
        5) echo "Exiting."; send_telegram_message "Streaming Manager script stopped\\."; break ;; # Notify on exit
        *) echo "Invalid option. Please try again." ;;
    esac
    read -p "Press Enter to continue..." # Pause for user
    # clear # Clear screen for next menu display (optional) - maybe remove if debugging telegram
done
