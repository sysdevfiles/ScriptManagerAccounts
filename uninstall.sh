#!/bin/bash
# Uninstallation script for Streaming Manager Bot (Python Version)

echo "--- Streaming Manager Bot (Python) Uninstallation ---"
read -p "Are you sure you want to remove Streaming Manager Bot and its configuration? (y/N): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
fi

echo "Removing 'menu' command link (/usr/local/bin/menu)..."
sudo rm -f /usr/local/bin/menu

echo "Removing configuration file (config.env)..."
rm -f config.env

read -p "Do you also want to remove the data files (streaming_accounts.json, registrations.json, update_offset.txt)? This cannot be undone. (y/N): " confirm_data

if [[ "$confirm_data" =~ ^[Yy]$ ]]; then
    echo "Removing account data file (streaming_accounts.json)..."
    rm -f streaming_accounts.json
    echo "Removing registration data file (registrations.json)..."
    rm -f registrations.json
    echo "Removing update offset file (update_offset.txt)..."
    rm -f update_offset.txt # Keep removing this for now, though Python version doesn't use it yet
else
    echo "Keeping data files."
fi

echo "Removing temporary files..."
rm -f streaming_accounts.tmp
rm -f registrations.tmp
rm -f *.pyc # Remove Python cache files
rm -rf __pycache__ # Remove Python cache directory

echo "Removing script files (telegram_bot_python.py, configure_bot.sh, vps_installer.sh, README.md)..." # Updated list
rm -f telegram_bot_python.py # Changed from telegram_bot_manager.sh
rm -f configure_bot.sh
rm -f vps_installer.sh # Changed from vps_bot_installer.sh
rm -f README.md
rm -f .gitignore

# Remove obsolete scripts just in case they weren't removed by installer
rm -f streaming_manager.sh
rm -f install.sh
rm -f telegram_bot_manager.sh # Ensure old bash bot is removed
rm -f "# Streaming Manager.md"
rm -f "# Streaming Manager (Bot Version).md"

echo "Streaming Manager Bot files removed."
# Optionally add steps to uninstall python libraries if desired, but usually not necessary
# echo "Note: Python libraries (python-dotenv, python-telegram-bot) are not automatically uninstalled."

echo "Removing uninstall script (uninstall.sh)..."
rm -- "$0" # Self-delete

echo "Uninstallation complete."
