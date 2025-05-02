#!/bin/bash
# Installation script for Streaming Manager

CONFIG_FILE="config.env"

echo "Setting up Streaming Manager..."

# Check if jq is installed, install if not (example using apt)
if ! command -v jq &> /dev/null
then
    echo "jq could not be found, attempting to install..."
    # Use the appropriate package manager for your system
    # sudo apt-get update && sudo apt-get install -y jq
    # sudo yum install jq
    # brew install jq
    echo "Please install jq manually if the above command failed."
    # exit 1 # Optional: exit if jq installation fails
fi

# Check if curl is installed
if ! command -v curl &> /dev/null
then
    echo "curl could not be found, attempting to install..."
    # Add appropriate install command for curl based on the system
    # sudo apt-get update && sudo apt-get install -y curl
    # sudo yum install curl
    # brew install curl
    echo "Please install curl manually if the above command failed."
    # exit 1 # Optional: exit if curl installation fails
fi

# Prompt for Telegram Credentials
echo "--- Telegram Bot Setup ---"
read -p "Enter your Telegram Bot Token: " TELEGRAM_BOT_TOKEN
read -p "Enter your Telegram Chat ID: " TELEGRAM_CHAT_ID

# Create config file
echo "Creating configuration file ($CONFIG_FILE)..."
echo "TELEGRAM_BOT_TOKEN='${TELEGRAM_BOT_TOKEN}'" > "$CONFIG_FILE"
echo "TELEGRAM_CHAT_ID='${TELEGRAM_CHAT_ID}'" >> "$CONFIG_FILE"

# Set permissions for config file (readable only by owner)
chmod 600 "$CONFIG_FILE"
echo "Set permissions for $CONFIG_FILE (rw-------)"

# Ensure the main script is executable
chmod +x streaming_manager.sh
echo "Set execute permission for streaming_manager.sh"

# Ensure the data file exists and has read/write permissions for the owner
touch streaming_accounts.json
chmod 600 streaming_accounts.json # Read/Write for owner only
echo "Ensured streaming_accounts.json exists and set permissions (rw-------)"

# Add other installation commands here later

echo "Setup complete."
