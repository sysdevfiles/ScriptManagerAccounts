# Streaming Manager

A simple tool to manage streaming service accounts, including username, password, PIN, plan details, renewal date, and creation date. Sends notifications to a Telegram chat.

## Setup

1.  **Get Telegram Details:**
    *   Create a Telegram Bot using BotFather and get the **Bot Token**.
    *   Find your **Chat ID**. You can get this by sending a message to your bot and visiting `https://api.telegram.org/bot<YourBotToken>/getUpdates`. Look for the `chat` object and its `id`.
2.  **Install Dependencies & Configure:** This tool requires `jq` and `curl`. Run the installation script which attempts to install them and prompts you for your Telegram Bot Token and Chat ID:
    ```bash
    ./scripts/install.sh
    ```
    *   If the script fails to install dependencies, please install `jq` and `curl` manually.
    *   The script will create a `config.env` file with your Telegram credentials. Keep this file secure.
    *   It also creates an empty `streaming_accounts.json` if one doesn't exist and sets permissions.
3.  **Protect Credentials:** Ensure `config.env` is included in your `.gitignore` file if using version control.

## Installation on VPS

1.  **Connect to your VPS:**
    Use SSH to connect to your server:
    ```bash
    ssh your_username@your_vps_ip_address
    ```

2.  **Install Dependencies Manually:**
    This tool requires `jq` and `curl`. Install them using your VPS's package manager:
    *   Debian/Ubuntu: `sudo apt update && sudo apt install jq curl git wget unzip`
    *   CentOS/RHEL: `sudo yum install jq curl git wget unzip`
    (You only need `git` or `wget`/`unzip` depending on the download method below).

3.  **Get the Files:** Choose **one** of the following methods:

    *   **Method A: Using `git clone` (Recommended)**
        ```bash
        # On your VPS
        git clone https://github.com/sysdevfiles/ScriptManagerAccounts.git streaming_manager
        cd streaming_manager
        ```

    *   **Method B: Using `wget` and `unzip`**
        ```bash
        # On your VPS
        wget https://github.com/sysdevfiles/ScriptManagerAccounts/archive/refs/heads/main.zip -O ScriptManagerAccounts.zip
        unzip ScriptManagerAccounts.zip
        cd ScriptManagerAccounts-main
        # Optional: Rename the directory
        # cd .. && mv ScriptManagerAccounts-main streaming_manager && cd streaming_manager
        ```

4.  **Set Permissions Manually:**
    Navigate into the project directory (`streaming_manager` or `ScriptManagerAccounts-main`) and make the main script executable:
    ```bash
    chmod +x streaming_manager.sh
    ```
    The data file (`streaming_accounts.json`) will be created with appropriate permissions by the main script on first run if needed, or you can create it manually (`touch streaming_accounts.json && chmod 600 streaming_accounts.json`).

5.  **Configure Telegram:**
    Run the `install.sh` script. This script **only** configures the Telegram settings by asking for your Bot Token and Chat ID and saving them to `config.env`.
    ```bash
    bash install.sh
    ```
    Have your Telegram Bot Token and Chat ID ready.

6.  **Verify:**
    After running `install.sh`, you should have a `config.env` file with the correct permissions.

## Saving to GitHub

If you want to store your project code (excluding sensitive data like `config.env`) on GitHub, follow these steps:

1.  **Install Git:** If you don't have Git installed on your local machine or VPS, install it first.
    *   Debian/Ubuntu: `sudo apt update && sudo apt install git`
    *   CentOS/RHEL: `sudo yum install git`
    *   macOS (with Homebrew): `brew install git`
    *   Windows: Download from [git-scm.com](https://git-scm.com/)

2.  **Initialize Git Repository:** Navigate to your project directory (`c:\Streaming Manager` or `~/streaming_manager` on the VPS) in your terminal and run:
    ```bash
    git init
    ```

3.  **Check `.gitignore`:** Make sure the `.gitignore` file exists and contains at least:
    ```gitignore
    config.env
    streaming_accounts.tmp
    # Optional: Add streaming_accounts.json if you don't want to commit account data
    # streaming_accounts.json
    ```
    This prevents your Telegram token and temporary files from being uploaded. Decide if you want to commit your `streaming_accounts.json` file. **It's generally safer not to commit files containing credentials or personal data.**

4.  **Add Files and Commit:** Stage the project files and make your first commit:
    ```bash
    git add streaming_manager.sh install.sh "# Streaming Manager.md" .gitignore
    # If you decided NOT to commit your accounts file, make sure it's in .gitignore
    # If you decided TO commit your accounts file (use with caution):
    # git add streaming_accounts.json

    git commit -m "Initial commit of Streaming Manager scripts"
    ```

5.  **Create GitHub Repository:**
    *   Go to [GitHub](https://github.com/).
    *   Log in or sign up.
    *   Create a new repository (e.g., named `streaming-manager`). You can choose whether to make it public or private. **Do not** initialize it with a README, .gitignore, or license if you've already created them locally.

6.  **Link Local Repository to GitHub:** Copy the commands provided by GitHub after creating the repository. They will look similar to this (replace `<your_username>` and `<your_repository_name>`):
    ```bash
    git remote add origin https://github.com/<your_username>/<your_repository_name>.git
    git branch -M main # Or master, depending on your default branch name
    git push -u origin main # Or master
    ```

Now your code is saved on GitHub. You can use `git pull` to fetch updates and `git push` to save future changes.

## Usage

Ensure dependencies are installed and `streaming_manager.sh` is executable. Then run the main script:
```bash
./streaming_manager.sh
```
Follow the on-screen prompts to list, add, edit, or delete accounts. The creation date is automatically recorded when adding an account. Confirmation messages and account lists (when requested) will be sent to your configured Telegram chat.

## Uninstallation

To remove the Streaming Manager scripts and configuration:

1.  **Navigate to Directory:**
    Make sure you are in the directory where the scripts are located (e.g., `~/streaming_manager`).
    ```bash
    cd ~/streaming_manager
    ```

2.  **Run Uninstall Script:**
    Execute the `uninstall.sh` script. You might need to make it executable first if you haven't already or if permissions were reset.
    ```bash
    chmod +x uninstall.sh # Ensure it's executable
    ./uninstall.sh
    ```

3.  **Confirm:**
    *   The script will first ask for confirmation to remove the application files and configuration (`config.env`).
    *   It will then ask separately if you want to delete the account data file (`streaming_accounts.json`). **Be careful**, as deleting this file removes all your stored account information.
    *   If confirmed, the script will remove the specified files and finally itself.
