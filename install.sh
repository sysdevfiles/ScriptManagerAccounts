#!/bin/bash
# Installation script for Streaming Manager - Telegram Configuration Only

CONFIG_FILE="config.env"

echo "--- Streaming Manager Telegram Configuration ---"
echo "This script will configure the Telegram Bot Token and Chat ID."
echo "Ensure jq, curl are installed and streaming_manager.sh is executable before running the main script."

# Prompt for Telegram Credentials
read -p "Enter your Telegram Bot Token: " TELEGRAM_BOT_TOKEN
read -p "Enter your Telegram Chat ID: " TELEGRAM_CHAT_ID

# Create config file
echo "Creating configuration file ($CONFIG_FILE)..."
echo "TELEGRAM_BOT_TOKEN='${TELEGRAM_BOT_TOKEN}'" > "$CONFIG_FILE"
echo "TELEGRAM_CHAT_ID='${TELEGRAM_CHAT_ID}'" >> "$CONFIG_FILE"

# Set permissions for config file (readable only by owner)
chmod 600 "$CONFIG_FILE"
echo "Set permissions for $CONFIG_FILE (rw-------)"

echo "Telegram configuration complete. You can now run ./streaming_manager.sh"
