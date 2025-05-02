#!/bin/bash
# Installer script for Streaming Manager on a VPS

REPO_URL="https://github.com/sysdevfiles/ScriptManagerAccounts.git"
INSTALL_DIR="streaming_manager"

echo "--- Streaming Manager VPS Installer ---"

# --- Dependency Check ---
echo "Checking dependencies (git, jq, curl)..."
missing_deps=()
command -v git >/dev/null 2>&1 || missing_deps+=("git")
command -v jq >/dev/null 2>&1 || missing_deps+=("jq")
command -v curl >/dev/null 2>&1 || missing_deps+=("curl")

if [ ${#missing_deps[@]} -ne 0 ]; then
    echo "Error: Missing dependencies: ${missing_deps[*]}"
    echo "Please install them using your package manager."
    echo "e.g., sudo apt update && sudo apt install ${missing_deps[*]}"
    echo "or    sudo yum install ${missing_deps[*]}"
    exit 1
fi
echo "Dependencies found."

# --- Clone Repository ---
echo "Cloning repository from $REPO_URL into $INSTALL_DIR..."
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR already exists. Please remove or rename it first."
    exit 1
fi

# Cloning a private repository requires authentication.
# Ensure SSH keys are set up between VPS and GitHub, or use HTTPS with a PAT/password.
git clone "$REPO_URL" "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    echo "Error: Failed to clone repository."
    echo "Ensure you have access rights and proper authentication (SSH key or HTTPS token/password)."
    exit 1
fi
echo "Repository cloned successfully."

# --- Navigate and Set Permissions ---
cd "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    echo "Error: Failed to change directory to $INSTALL_DIR."
    exit 1
fi

echo "Setting execute permissions for scripts..."
chmod +x streaming_manager.sh
chmod +x install.sh
chmod +x uninstall.sh
if [ $? -ne 0 ]; then
    echo "Error: Failed to set permissions."
    # Attempt to clean up cloned directory before exiting
    cd .. && rm -rf "$INSTALL_DIR"
    exit 1
fi

# --- Configure Telegram ---
echo "Running Telegram configuration (install.sh)..."
bash install.sh
if [ $? -ne 0 ]; then
    echo "Error: Telegram configuration failed."
    # Attempt to clean up cloned directory before exiting
    cd .. && rm -rf "$INSTALL_DIR"
    exit 1
fi

echo "--- Installation Complete ---"
echo "Streaming Manager is installed in the '$INSTALL_DIR' directory."
echo "You can now run the manager using: cd $INSTALL_DIR && ./streaming_manager.sh"

exit 0
