# Streaming Manager (Bot de Telegram en Python)

Una herramienta para gestionar cuentas de streaming y registros de usuarios usando un bot de Telegram. Esta versión utiliza Python y la librería `python-telegram-bot`.

**Nota:** Esta versión implementa la funcionalidad básica y el registro de usuarios paso a paso. Otras funciones (gestión de cuentas, backups, etc.) se portarán gradualmente.

## Características

*   **Gestión de Registros de Usuarios** (Añadir paso a paso, listar, eliminar) vía Telegram.
*   **Menú interactivo con botones** para iniciar acciones comunes.
*   Notificaciones de confirmación.
*   Almacenamiento de datos en archivos JSON (`streaming_accounts.json`, `registrations.json`).
*   Restricción de comandos y botones al Chat ID del administrador.
*   Sistema de Licencia con comprobación periódica y desactivación.
*   *Próximamente:* Gestión completa de Cuentas Streaming, Backups, Notificaciones de Renovación.

## Requisitos

*   `python3` (versión 3.7 o superior recomendada)
*   `pip3` (gestor de paquetes de Python)
*   Librerías Python listadas en `requirements.txt` (`python-telegram-bot`, `python-dotenv`)
*   `git`, `jq`, `curl` (para el instalador y scripts auxiliares)
*   Un Bot de Telegram y su **Token**.
*   Tu **Chat ID** de Telegram.

## Instalación y Configuración

1.  **Instalar en VPS (Método Recomendado):**
    Conéctate a tu VPS y ejecuta el siguiente comando en tu directorio home (`~`). Este comando descarga, da permisos, ejecuta y luego elimina el script de instalación.
    ```bash
    wget --no-cache https://raw.githubusercontent.com/sysdevfiles/ScriptManagerAccounts/main/vps_installer.sh -O vps_installer.sh && chmod +x vps_installer.sh && ./vps_installer.sh && rm vps_installer.sh
    ```
    *   El script instalador (`vps_installer.sh`) clonará el repositorio en `~/streaming_manager`, instalará dependencias (`git`, `jq`, `curl`, `python3`, `pip3`), instalará las librerías Python necesarias, configurará permisos y creará un comando `menu` global.

2.  **Configurar el Bot:**
    Después de ejecutar el instalador, **debes** configurar tus credenciales y la licencia ejecutando:
    ```bash
    sudo menu
    ```
    Sigue las instrucciones para ingresar tu Token de Bot, tu Chat ID de administrador y la duración deseada de la licencia. Esto creará/actualizará el archivo `config.env`.

3.  **(Alternativa) Instalación Manual:**
    *   Clona el repositorio: `git clone https://github.com/sysdevfiles/ScriptManagerAccounts.git streaming_manager`
    *   Navega al directorio: `cd streaming_manager`
    *   Instala dependencias del sistema: `sudo apt update && sudo apt install -y jq curl git python3 python3-pip` (o `yum`)
    *   Instala librerías Python: `sudo pip3 install -r requirements.txt`
    *   Da permisos a scripts auxiliares: `chmod +x configure_bot.sh uninstall.sh`
    *   Configura: `./configure_bot.sh`

## Ejecución

Puedes ejecutar el bot de dos maneras:

**1. Directamente en la Terminal (para pruebas):**
```bash
# Navega al directorio de instalación si no estás ahí
cd ~/streaming_manager # O la ruta donde lo instalaste
python3 telegram_bot_python.py
```
El bot comenzará a escuchar mensajes. Verás la salida en la terminal. Para detenerlo, presiona `Ctrl+C`.

**2. Como Servicio `systemd` (Recomendado para ejecución continua):**

    *   **Crea un archivo de servicio:**
        Crea un archivo llamado `streaming_bot.service` en `/etc/systemd/system/` con el siguiente contenido (ajusta `User` y `WorkingDirectory`/`ExecStart` a tu usuario y ruta real donde se instaló el script, comúnmente `/home/<tu_usuario>/streaming_manager` o `/root/streaming_manager`):

        ```ini
        # filepath: /etc/systemd/system/streaming_bot.service
        [Unit]
        Description=Streaming Manager Telegram Bot (Python)
        After=network.target

        [Service]
        Type=simple
        User=root # O tu usuario no-root
        # CAMBIA ESTA RUTA a donde se clonó el repo (ej. /root/streaming_manager o /home/user/streaming_manager)
        WorkingDirectory=/root/streaming_manager
        # CAMBIA ESTA RUTA para que coincida con WorkingDirectory y usa python3
        ExecStart=/usr/bin/python3 /root/streaming_manager/telegram_bot_python.py
        Restart=on-failure
        RestartSec=5
        StandardOutput=journal # Redirige stdout a journald
        StandardError=journal  # Redirige stderr a journald

        [Install]
        WantedBy=multi-user.target
        ```

    *   **Habilita e inicia el servicio:**
        ```bash
        sudo systemctl daemon-reload
        sudo systemctl enable streaming_bot.service
        sudo systemctl start streaming_bot.service
        ```

    *   **Verificar estado:**
        ```bash
        sudo systemctl status streaming_bot.service
        ```

    *   **Ver logs:**
        ```bash
        sudo journalctl -u streaming_bot.service -f
        ```

    *   **Detener servicio:**
        ```bash
        sudo systemctl stop streaming_bot.service
        ```

## Uso (Comandos y Botones)

La interacción principal se realiza a través del menú de botones. Envía `/menu` para empezar.

**Menú Principal (Botones):**
*   Envía `/menu` para mostrar el menú principal con botones.
*   **Fila 1 (Cuentas Streaming):** _(Funcionalidad pendiente de implementación)_
    *   `📊 Listar Cuentas:`
    *   `📄 Ver Cuenta:`
    *   `➕ Añadir Cuenta:`
    *   `✏️ Editar Cuenta:`
    *   `🗑️ Eliminar Cuenta:`
*   **Fila 2 (Registros Usuarios):**
    *   `👤 Registrar Usuario:` Inicia el proceso de registro paso a paso.
    *   `👥 Listar Registros:` _(Funcionalidad pendiente)_
    *   `❌ Borrar Registro:` _(Funcionalidad pendiente)_
*   **Fila 3 (Utilidades/Admin):**
    *   `💾 Backup:` _(Funcionalidad pendiente)_
    *   `❓ Ayuda:` Muestra la ayuda detallada.
    *   `🔒 Licencia:` _(Funcionalidad pendiente)_

**Comandos de Texto:**
*   `/start`, `/help`: Muestra la ayuda.
*   `/menu`: Muestra el menú de botones.
*   `/cancel`: Cancela una operación en curso (como el registro).
*   *Otros comandos (`/add`, `/edit`, `/delete`, `/view`, `/listreg`, `/delreg`, `/list`, `/backup`, `/licencia_estado`, `/licencia_expira`) se implementarán gradualmente.*

## Funcionamiento de la Licencia

*   Al configurar el bot con `./configure_bot.sh`, se establece una fecha de activación y expiración en `config.env`.
*   El bot Python (`telegram_bot_python.py`) comprueba la licencia al iniciarse y luego periódicamente (cada hora por defecto).
*   Si la licencia ha expirado, el bot enviará un mensaje al admin y se detendrá.
*   *Próximamente:* Comando `/licencia_expira` para extenderla.

## Desactivación Remota por el Administrador Principal

_(La lógica es la misma, pero el comando `/licencia_expira` debe ser implementado en el bot Python para que funcione)._

## Desinstalación

1.  **Detener el Servicio (si aplica):**
    ```bash
    sudo systemctl stop streaming_bot.service
    sudo systemctl disable streaming_bot.service
    sudo rm /etc/systemd/system/streaming_bot.service
    sudo systemctl daemon-reload
    ```
2.  **Ejecutar script de desinstalación:**
    Navega al directorio del bot (ej. `~/streaming_manager`) y ejecuta:
    ```bash
    ./uninstall.sh
    ```
    Confirma las acciones cuando se te pregunte. El script eliminará los archivos del bot, la configuración, el enlace `menu` y, opcionalmente, los datos.
