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

Este método utiliza un script instalador único para simplificar el proceso en el VPS.

1.  **Connect to your VPS:**
    ```bash
    ssh your_username@your_vps_ip_address
    ```

2.  **Download the VPS Installer:**
    Descarga el script `vps_installer.sh` desde el repositorio a tu VPS.
    **Importante:** Como el repositorio es privado, necesitas una forma de descargar este *único* archivo.
    *   **Opción A (Recomendada):** Si tienes acceso web a GitHub, descarga `vps_installer.sh` manualmente a tu máquina local y súbelo al VPS usando `scp`:
        ```bash
        # En tu máquina local, después de descargar vps_installer.sh
        scp /path/to/local/vps_installer.sh your_username@your_vps_ip_address:~/
        ```
    *   **Opción B (Si haces el repo público temporalmente o usas un token):** Podrías usar `wget` o `curl` con autenticación, pero es más complejo y menos seguro para un script inicial. Si el repo fuera público, sería:
        ```bash
        # SOLO SI EL REPO ES PÚBLICO
        # wget https://raw.githubusercontent.com/sysdevfiles/ScriptManagerAccounts/main/vps_installer.sh -O vps_installer.sh
        ```

3.  **Run the VPS Installer:**
    Una vez que tengas `vps_installer.sh` en tu VPS, dale permisos de ejecución y ejecútalo:
    ```bash
    chmod +x vps_installer.sh
    ./vps_installer.sh
    ```

4.  **Follow Installer Steps:**
    *   El script verificará las dependencias (`git`, `jq`, `curl`) y te indicará si falta alguna.
    *   Intentará clonar el repositorio `https://github.com/sysdevfiles/ScriptManagerAccounts.git`. **Necesitarás tener autenticación configurada entre tu VPS y GitHub** (preferiblemente claves SSH) para que esto funcione, ya que el repositorio es privado. Si falla, el script te dará un error indicando problemas de autenticación o acceso.
    *   Si la clonación es exitosa, configurará los permisos de los scripts descargados.
    *   Finalmente, ejecutará `install.sh`, que te pedirá tu Token y Chat ID de Telegram.

5.  **Completion:**
    Si todo va bien, el script te indicará que la instalación está completa y dónde se encuentran los archivos (en el directorio `streaming_manager`).

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

Después de una instalación exitosa con `vps_installer.sh`, navega al directorio y ejecuta el script principal:
```bash
cd streaming_manager
./streaming_manager.sh
```
Follow the on-screen prompts to list, add, edit, or delete accounts. The creation date is automatically recorded when adding an account. Confirmation messages and account lists (when requested) will be sent to your configured Telegram chat.

## Uninstallation

To remove the Streaming Manager scripts and configuration:

1.  **Navigate to Directory:**
    Make sure you are in the directory where the scripts are located (e.g., `~/streaming_manager` or `~/ScriptManagerAccounts-main`).
    ```bash
    cd ~/streaming_manager # O el directorio donde se instaló
    ```

2.  **Run Uninstall Script:**
    Execute the `uninstall.sh` script (it should already be executable if you used the `wget` method above).
    ```bash
    ./uninstall.sh
    ```

3.  **Confirm:**
    *   The script will first ask for confirmation to remove the application files and configuration (`config.env`).
    *   It will then ask separately if you want to delete the account data file (`streaming_accounts.json`). **Be careful**, as deleting this file removes all your stored account information.
    *   If confirmed, the script will remove the specified files and finally itself.
