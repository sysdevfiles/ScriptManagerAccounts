#!/bin/bash
# Uninstallation script for Streaming Manager Bot

echo "--- Streaming Manager Bot Uninstallation ---"
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
    rm -f update_offset.txt
else
    echo "Keeping data files."
fi

echo "Removing temporary files..."
rm -f streaming_accounts.tmp
rm -f registrations.tmp

echo "Removing script files (telegram_bot_manager.sh, configure_bot.sh, vps_bot_installer.sh, README.md)..." # Updated list
rm -f telegram_bot_manager.sh
rm -f configure_bot.sh
rm -f vps_bot_installer.sh # Changed from vps_installer.sh
rm -f README.md
rm -f .gitignore

# Remove obsolete scripts just in case they weren't removed by installer
rm -f streaming_manager.sh
rm -f install.sh
rm -f "# Streaming Manager.md"
rm -f "# Streaming Manager (Bot Version).md"

echo "Streaming Manager Bot files removed."
echo "Removing uninstall script (uninstall.sh)..."
rm -- "$0" # Self-delete

echo "Uninstallation complete."
