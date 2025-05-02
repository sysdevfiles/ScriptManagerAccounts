# Streaming Manager

A simple tool to manage streaming service accounts, including username, password, PIN, plan details, and renewal date. Sends notifications to a Telegram chat.

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

2.  **Transfer Files:**
    Copy the project files (`streaming_manager.sh`, `install.sh`, `.gitignore`) to your VPS. You can use `scp` or clone the repository if you are using Git.
    *   **Using `scp` (from your local machine):**
        ```bash
        scp -r /path/to/your/local/Streaming\ Manager your_username@your_vps_ip_address:~/streaming_manager
        ```
        (Replace `/path/to/your/local/Streaming\ Manager` with the actual path on your computer and `~/streaming_manager` with the desired location on the VPS).
    *   **Using Git:**
        ```bash
        # On your VPS
        git clone <your_repository_url> streaming_manager
        cd streaming_manager
        ```

3.  **Navigate to Directory:**
    Change into the directory where you transferred the files:
    ```bash
    cd ~/streaming_manager # Or the directory you chose
    ```

4.  **Run Installation Script:**
    Execute the installation script. This will check dependencies, ask for your Telegram details, and set up permissions.
    ```bash
    bash install.sh
    ```
    *   **Dependencies:** The script attempts to install `jq` and `curl`. If it fails (e.g., due to permissions or unknown package manager), you might need to install them manually using your VPS's package manager (like `sudo apt update && sudo apt install jq curl` for Debian/Ubuntu, or `sudo yum install jq curl` for CentOS/RHEL).
    *   **Telegram Details:** Have your Telegram Bot Token and Chat ID ready when prompted.

5.  **Verify:**
    After the installation script finishes, you should have `config.env` and `streaming_accounts.json` files created with the correct permissions.

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

Run the main script to access the interactive menu:
```bash
./scripts/streaming_manager.sh
```
Follow the on-screen prompts to list, add, edit, or delete accounts. Confirmation messages and account lists (when requested) will be sent to your configured Telegram chat.
