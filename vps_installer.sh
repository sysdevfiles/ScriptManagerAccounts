#!/bin/bash
# Installer script for Streaming Manager on a VPS

REPO_URL="https://github.com/sysdevfiles/ScriptManagerAccounts.git"
INSTALL_DIR="streaming_manager"
# Get the absolute path to the install directory *before* changing into it
ABS_INSTALL_DIR="$(pwd)/$INSTALL_DIR"

echo "--- Streaming Manager VPS Installer ---"

# --- Attempt Dependency Installation ---
echo "Checking and attempting to install dependencies (git, jq, curl)..."
install_cmd=""
pkg_manager=""

if command -v apt-get &> /dev/null; then
    pkg_manager="apt-get"
    install_cmd="sudo apt-get update && sudo apt-get install -y git jq curl"
elif command -v yum &> /dev/null; then
    pkg_manager="yum"
    install_cmd="sudo yum install -y git jq curl"
else
    echo "Warning: Could not detect apt-get or yum. Please ensure git, jq, and curl are installed manually."
fi

missing_deps=()
command -v git >/dev/null 2>&1 || missing_deps+=("git")
command -v jq >/dev/null 2>&1 || missing_deps+=("jq")
command -v curl >/dev/null 2>&1 || missing_deps+=("curl")

if [ ${#missing_deps[@]} -ne 0 ]; then
    echo "Missing dependencies: ${missing_deps[*]}"
    if [ -n "$install_cmd" ]; then
        echo "Attempting installation using $pkg_manager..."
        eval "$install_cmd"
        # Re-check after attempting install
        missing_deps=()
        command -v git >/dev/null 2>&1 || missing_deps+=("git")
        command -v jq >/dev/null 2>&1 || missing_deps+=("jq")
        command -v curl >/dev/null 2>&1 || missing_deps+=("curl")
        if [ ${#missing_deps[@]} -ne 0 ]; then
             echo "Error: Failed to install dependencies: ${missing_deps[*]}"
             echo "Please install them manually and re-run the installer."
             exit 1
        fi
    else
        echo "Error: Please install missing dependencies manually and re-run."
        exit 1
    fi
fi
echo "Dependencies found or installed."

# --- Clone Repository ---
echo "Cloning repository from $REPO_URL into $INSTALL_DIR..."
# Remove check for existing directory to allow re-installation/update
# if [ -d "$INSTALL_DIR" ]; then
#     echo "Directory $INSTALL_DIR already exists. Please remove or rename it first."
#     exit 1
# fi
rm -rf "$INSTALL_DIR" # Remove old directory if it exists
git clone "$REPO_URL" "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    echo "Error: Failed to clone repository."
    # If cloning fails with a public repo, it might be a network issue or incorrect URL.
    echo "Please check the URL ($REPO_URL) and your network connection."
    exit 1
fi
echo "Repository cloned successfully."

# --- Navigate and Set Permissions ---
cd "$INSTALL_DIR"
if [ $? -ne 0 ]; then
    echo "Error: Failed to change directory to $INSTALL_DIR."
    exit 1
fi
# Update ABS_INSTALL_DIR to be certain after cd
ABS_INSTALL_DIR="$(pwd)"

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

# --- Create 'menu' command (symlink) ---
echo "Creating system-wide 'menu' command for Telegram configuration..."
# Use absolute path for the link source
if sudo ln -sf "$ABS_INSTALL_DIR/install.sh" /usr/local/bin/menu; then
    echo "'menu' command created successfully."
    echo "You can now run 'sudo menu' to configure Telegram Bot Token and Chat ID."
else
    echo "Error: Failed to create 'menu' command in /usr/local/bin/."
    echo "You might need to run this installer with sudo, or create the link manually:"
    echo "sudo ln -sf \"$ABS_INSTALL_DIR/install.sh\" /usr/local/bin/menu"
    # Attempt to clean up cloned directory before exiting
    cd .. && rm -rf "$INSTALL_DIR"
    exit 1
fi

echo "--- Installation Complete ---"
echo "Streaming Manager core files are installed in the '$INSTALL_DIR' directory."
echo "IMPORTANT: Run 'sudo menu' now to configure your Telegram Bot Token and Chat ID."
echo "After configuration, run the manager using: cd $INSTALL_DIR && ./streaming_manager.sh"

exit 0
