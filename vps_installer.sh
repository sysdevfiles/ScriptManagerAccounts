#!/bin/bash
# Installer script for Streaming Manager Bot (Python Version) on a VPS

REPO_URL="https://github.com/sysdevfiles/ScriptManagerAccounts.git"
INSTALL_DIR="streaming_manager"

# --- Prevent running inside the target directory ---
CURRENT_DIR_NAME=$(basename "$(pwd)")
if [[ "$CURRENT_DIR_NAME" == "$INSTALL_DIR" ]]; then
    echo -e "\033[0;31mError: No ejecutes este script desde dentro de un directorio llamado '$INSTALL_DIR'.\033[0m"
    echo -e "\033[0;33mVe a tu directorio home (cd ~) o a otro directorio y vuelve a intentarlo.\033[0m"
    exit 1
fi
# --- End Prevention Check ---


# Get the absolute path to the install directory *before* changing into it
ABS_INSTALL_DIR="$(pwd)/$INSTALL_DIR"

echo "--- Streaming Manager Bot (Python) VPS Installer ---"

# --- Attempt Dependency Installation ---
echo "Checking and attempting to install dependencies (git, jq, curl, python3, python3-pip)..."
install_cmd=""
pkg_manager=""

if command -v apt-get &> /dev/null; then
    pkg_manager="apt-get"
    # Added python3 and python3-pip
    install_cmd="sudo apt-get update && sudo apt-get install -y git jq curl python3 python3-pip"
elif command -v yum &> /dev/null; then
    pkg_manager="yum"
    # Added python3 and python3-pip (package names might vary slightly on CentOS/RHEL)
    install_cmd="sudo yum install -y git jq curl python3 python3-pip"
else
    echo "Warning: Could not detect apt-get or yum. Please ensure git, jq, curl, python3, and python3-pip are installed manually."
fi

missing_deps=()
command -v git >/dev/null 2>&1 || missing_deps+=("git")
command -v jq >/dev/null 2>&1 || missing_deps+=("jq")
command -v curl >/dev/null 2>&1 || missing_deps+=("curl")
command -v python3 >/dev/null 2>&1 || missing_deps+=("python3")
command -v pip3 >/dev/null 2>&1 || missing_deps+=("pip3")


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
        command -v python3 >/dev/null 2>&1 || missing_deps+=("python3")
        command -v pip3 >/dev/null 2>&1 || missing_deps+=("pip3")
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
echo "System dependencies found or installed."

# --- Clone Repository ---
# Remove old directory if it exists to ensure a clean installation
if [ -d "$INSTALL_DIR" ]; then
    echo "Directorio de instalación anterior '$INSTALL_DIR' encontrado. Eliminándolo para una instalación limpia..."
    rm -rf "$INSTALL_DIR"
fi
echo "Cloning repository from $REPO_URL into $INSTALL_DIR..."
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
# chmod +x telegram_bot_manager.sh # Removed old bash script
chmod +x configure_bot.sh
chmod +x uninstall.sh
# No need to make python script executable, will run with python3 interpreter
if [ $? -ne 0 ]; then
    echo "Error: Failed to set permissions."
    # Attempt to clean up cloned directory before exiting
    cd .. && rm -rf "$INSTALL_DIR"
    exit 1
fi

# --- Install Python Libraries using requirements.txt ---
echo "Installing required Python libraries from requirements.txt..."
if sudo pip3 install -r requirements.txt; then
    echo "Python libraries installed successfully."
else
    echo "Error: Failed to install Python libraries using pip3 and requirements.txt."
    echo "Please check your pip3 installation, network connection, and requirements.txt."
    # Attempt to clean up cloned directory before exiting
    cd .. && rm -rf "$INSTALL_DIR"
    exit 1
fi


# --- Create 'menu' command (symlink) ---
echo "Creating system-wide 'menu' command for Telegram Bot configuration..."
# Use absolute path for the link source, point to configure_bot.sh
if sudo ln -sf "$ABS_INSTALL_DIR/configure_bot.sh" /usr/local/bin/menu; then
    echo "'menu' command created successfully."
    echo "You can now run 'sudo menu' to configure Telegram Bot Token, Admin Chat ID, and License." # Updated message
else
    echo "Error: Failed to create 'menu' command in /usr/local/bin/."
    echo "You might need to run this installer with sudo, or create the link manually:"
    echo "sudo ln -sf \"$ABS_INSTALL_DIR/configure_bot.sh\" /usr/local/bin/menu" # Updated command example
    # Attempt to clean up cloned directory before exiting
    cd .. && rm -rf "$INSTALL_DIR"
    exit 1
fi

# --- Clean up old scripts --- # Added section
echo "Removing obsolete scripts (streaming_manager.sh, install.sh, telegram_bot_manager.sh)..."
rm -f streaming_manager.sh
rm -f install.sh
rm -f telegram_bot_manager.sh # Remove the old bash bot script

# --- Clean up old README --- # Added section
echo "Removing obsolete README (# Streaming Manager.md)..."
rm -f "# Streaming Manager.md"
if [[ -f "# Streaming Manager (Bot Version).md" ]]; then
    echo "Renaming '# Streaming Manager (Bot Version).md' to README.md..."
    mv "# Streaming Manager (Bot Version).md" README.md
fi

echo "--- Installation Complete ---"
echo "Streaming Manager Bot (Python) files are installed in the '$INSTALL_DIR' directory."
echo "IMPORTANT: Run 'sudo menu' now to configure your Telegram Bot Token, Admin Chat ID, and License."
# Updated run command for Python
echo "After configuration, run the manager using: cd $INSTALL_DIR && python3 telegram_bot_python.py"

exit 0
