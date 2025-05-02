#!/bin/bash
# Uninstallation script for Streaming Manager

echo "--- Streaming Manager Uninstallation ---"
read -p "Are you sure you want to remove Streaming Manager and its configuration? (y/N): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
fi

echo "Removing configuration file (config.env)..."
rm -f config.env

read -p "Do you also want to remove the account data file (streaming_accounts.json)? This cannot be undone. (y/N): " confirm_data

if [[ "$confirm_data" =~ ^[Yy]$ ]]; then
    echo "Removing account data file (streaming_accounts.json)..."
    rm -f streaming_accounts.json
else
    echo "Keeping account data file (streaming_accounts.json)."
fi

echo "Removing script files (streaming_manager.sh, install.sh, .gitignore)..."
rm -f streaming_manager.sh
rm -f install.sh
rm -f .gitignore
rm -f streaming_accounts.tmp # Remove temporary file if it exists

echo "Streaming Manager files removed."
echo "Removing uninstall script (uninstall.sh)..."
rm -- "$0" # Self-delete

echo "Uninstallation complete."
