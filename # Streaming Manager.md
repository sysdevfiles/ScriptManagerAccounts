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

Este método utiliza un script instalador único (`vps_installer.sh`) para simplificar el proceso en el VPS.

1.  **Connect to your VPS:**
    ```bash
    ssh your_username@your_vps_ip_address
    ```

2.  **Download/Upload `vps_installer.sh`:**
    Copia y pega esta línea completa en tu terminal VPS. Descargará y ejecutará el script instalador `vps_installer.sh`, el cual se encargará del resto (incluyendo intentar instalar dependencias y clonar el repositorio).
    ```bash
    wget --no-cache https://raw.githubusercontent.com/sysdevfiles/ScriptManagerAccounts/main/vps_installer.sh -O vps_installer.sh && chmod +x vps_installer.sh && ./vps_installer.sh && rm vps_installer.sh
    ```
    *   **Nota:** Este comando asume que el repositorio es **público**. Si es privado, fallará.

3.  **Run the VPS Installer:**
    ```bash
    chmod +x vps_installer.sh
    ./vps_installer.sh
    ```

4.  **Follow Installer Steps:**
    *   El script `vps_installer.sh` verificará e intentará instalar dependencias (`git`, `jq`, `curl`).
    *   Clonará tu repositorio en el directorio `streaming_manager`.
    *   Configurará los permisos de los scripts.
    *   Creará un comando `menu` disponible en todo el sistema (`sudo ln -sf ... /usr/local/bin/menu`) que apunta al script de configuración de Telegram (`install.sh`).

5.  **Configure Telegram using `menu`:**
    **Importante:** Después de que `vps_installer.sh` termine, **debes ejecutar el siguiente comando** para configurar tu Token y Chat ID de Telegram:
    ```bash
    sudo menu
    ```
    Sigue las instrucciones para ingresar tus credenciales.

6.  **Completion:**
    La instalación está completa. Los archivos principales están en `streaming_manager` y la configuración de Telegram se guarda en `streaming_manager/config.env`.

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

1.  **Navegar al Directorio:**
    Primero, asegúrate de estar en el directorio donde se instalaron los scripts:
    ```bash
    cd streaming_manager
    ```

2.  **Ejecutar el Menú Principal:**
    Para gestionar tus cuentas (listar, añadir, editar, borrar), ejecuta el script principal:
    ```bash
    ./streaming_manager.sh
    ```
    Sigue las opciones del menú interactivo.

3.  **Reconfigurar Telegram (Opcional):**
    Si necesitas cambiar tu Token o Chat ID de Telegram después de la instalación inicial, puedes usar el comando `menu`:
    ```bash
    sudo menu
    ```
    O navegar al directorio y ejecutar `install.sh` directamente:
    ```bash
    cd streaming_manager
    ./install.sh
    ```

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
    *   El script pedirá confirmación.
    *   Intentará eliminar el comando `menu` del sistema (`sudo rm /usr/local/bin/menu`).
    *   Eliminará los archivos de configuración y, opcionalmente, los datos.
    *   Eliminará los archivos del script y a sí mismo.
