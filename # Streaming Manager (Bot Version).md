# Streaming Manager (Bot de Telegram en Bash)

Una herramienta para gestionar cuentas de streaming usando un bot de Telegram. Esta versión utiliza un script Bash que escucha comandos enviados al bot.

**Advertencia:** Esta es una implementación básica en Bash. Para bots más complejos o robustos, se recomiendan lenguajes como Python o Node.js.

## Características

*   Gestión de Cuentas Streaming (Añadir, listar, ver, editar, eliminar) vía Telegram.
*   **Gestión de Registros de Usuarios** (Añadir, listar, eliminar) vía Telegram.
*   **Menú interactivo con botones** para iniciar acciones comunes.
*   **Backup de datos** de cuentas streaming.
*   Notificaciones de confirmación.
*   Notificaciones automáticas de cuentas streaming próximas a vencer.
*   Almacenamiento de datos en archivos JSON (`streaming_accounts.json`, `registrations.json`).
*   Restricción de comandos y botones al Chat ID del administrador.
*   Comprobación para evitar reconfiguración accidental.
*   Sistema de Licencia con desactivación remota.
*   Comandos de Admin para gestionar la licencia.

## Requisitos

*   `bash`
*   `jq` (procesador JSON de línea de comandos)
*   `curl` (herramienta de transferencia de datos)
*   Un Bot de Telegram y su **Token**.
*   Tu **Chat ID** de Telegram.

## Instalación y Configuración

1.  **Instalar en VPS (Método Recomendado):**
    Conéctate a tu VPS y ejecuta el siguiente comando en tu directorio home (`~`). Este comando descarga, da permisos, ejecuta y luego elimina el script de instalación.
    ```bash
    wget --no-cache https://raw.githubusercontent.com/sysdevfiles/ScriptManagerAccounts/main/vps_bot_installer.sh -O vps_bot_installer.sh && chmod +x vps_bot_installer.sh && ./vps_bot_installer.sh && rm vps_bot_installer.sh
    ```
    *   El script instalador (`vps_bot_installer.sh`) clonará el repositorio en `~/streaming_manager`, instalará dependencias (`git`, `jq`, `curl`), configurará permisos y creará un comando `menu` global.

2.  **Configurar el Bot:**
    Después de ejecutar el instalador, **debes** configurar tus credenciales y la licencia ejecutando:
    ```bash
    sudo menu
    ```
    Sigue las instrucciones para ingresar tu Token de Bot, tu Chat ID de administrador y la duración deseada de la licencia. Esto creará/actualizará el archivo `config.env`.

3.  **(Alternativa) Instalación Manual:**
    *   Clona el repositorio: `git clone https://github.com/sysdevfiles/ScriptManagerAccounts.git streaming_manager`
    *   Navega al directorio: `cd streaming_manager`
    *   Instala dependencias: `sudo apt update && sudo apt install -y jq curl git` (o `yum`)
    *   Da permisos: `chmod +x telegram_bot_manager.sh configure_bot.sh uninstall.sh`
    *   Configura: `./configure_bot.sh`

## Ejecución

Puedes ejecutar el bot de dos maneras:

**1. Directamente en la Terminal (para pruebas):**
```bash
# Navega al directorio de instalación si no estás ahí
cd ~/streaming_manager # O la ruta donde lo instalaste
./telegram_bot_manager.sh
```
El bot comenzará a escuchar mensajes. Verás la salida en la terminal. Para detenerlo, presiona `Ctrl+C`.

**2. Como Servicio `systemd` (Recomendado para ejecución continua):**

    *   **Crea un archivo de servicio:**
        Crea un archivo llamado `streaming_bot.service` en `/etc/systemd/system/` con el siguiente contenido (ajusta `User` y `WorkingDirectory`/`ExecStart` a tu usuario y ruta real donde se instaló el script, comúnmente `/home/<tu_usuario>/streaming_manager` o `/root/streaming_manager`):

        ```ini
        # filepath: /etc/systemd/system/streaming_bot.service
        [Unit]
        Description=Streaming Manager Telegram Bot
        After=network.target

        [Service]
        Type=simple
        User=root # O tu usuario no-root
        # CAMBIA ESTA RUTA a donde se clonó el repo (ej. /root/streaming_manager o /home/user/streaming_manager)
        WorkingDirectory=/root/streaming_manager
        # CAMBIA ESTA RUTA para que coincida con WorkingDirectory
        ExecStart=/bin/bash /root/streaming_manager/telegram_bot_manager.sh
        Restart=on-failure
        RestartSec=5

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
*   **Fila 1 (Cuentas Streaming):**
    *   `📊 Listar Cuentas:` Muestra la lista de cuentas.
    *   `📄 Ver Cuenta:` Pide enviar `/view <Numero>`.
    *   `➕ Añadir Cuenta:` Explica formato `/add ...`.
    *   `✏️ Editar Cuenta:` Explica formato `/edit <Numero> ...`.
    *   `🗑️ Eliminar Cuenta:` Explica formato `/delete <Numero>`.
*   **Fila 2 (Registros Usuarios):**
    *   `👤 Registrar Usuario:` Explica formato `/register Plataforma;Nombre;...`.
    *   `👥 Listar Registros:` Muestra la lista de usuarios registrados.
    *   `❌ Borrar Registro:` Pide enviar `/delreg <Numero>`.
*   **Fila 3 (Utilidades/Admin):**
    *   `💾 Backup:` Envía `streaming_accounts.json` y `registrations.json`.
    *   `❓ Ayuda:` Muestra la ayuda detallada.
    *   `🔒 Licencia:` Muestra el estado de la licencia.

**Comandos de Texto (Usados después de las indicaciones de los botones o directamente):**
*   `/add <Servicio> <Usuario> <Contraseña> <Plan> <YYYY-MM-DD> [PIN]`
    Añade una cuenta streaming.
*   `/edit <Numero> <Campo>=<NuevoValor>`
    Modifica un campo de una cuenta streaming.
*   `/delete <Numero>`
    Elimina una cuenta streaming.
*   `/view <Numero>`
    Muestra detalles de una cuenta streaming.
*   `/register <Plataforma>;<Nombre>;<Celular>;<TipoPago>;<Email>;<PIN>;<FechaAlta>;<FechaVenc>`
    Registra un nuevo usuario. **Importante:** Usar punto y coma ';' como separador y sin espacios alrededor. El PIN es opcional (dejar vacío entre ;; si no aplica).
*   `/listreg`
    Lista los usuarios registrados (alternativa al botón).
*   `/delreg <Numero>`
    Elimina un registro de usuario.
*   `/list`
    Muestra la lista de cuentas (alternativa al botón).
*   `/backup`
    Genera y envía el backup de cuentas y registros (alternativa al botón).
*   `/help` o `/start`
    Muestra la ayuda completa (alternativa al botón).
*   `/licencia_estado`
    Muestra el estado de la licencia (alternativa al botón).
*   `/licencia_expira <YYYY-MM-DD>`
    Establece una nueva fecha de expiración para la licencia (solo comando de texto).

## Notificaciones de Vencimiento

El bot comprobará periódicamente (por defecto cada 6 horas, configurable en el script `telegram_bot_manager.sh`) si alguna cuenta tiene una fecha de renovación (`renewal_date`) dentro de los próximos 30 días (configurable). Si encuentra alguna, enviará un mensaje de alerta a tu chat de administrador. Asegúrate de que las fechas de renovación estén en formato `YYYY-MM-DD`.

## Funcionamiento de la Licencia

*   Al configurar el bot con `./configure_bot.sh`, se establece una fecha de activación (hoy) y una fecha de expiración basada en los días que indiques.
*   El bot (`telegram_bot_manager.sh`) comprueba al iniciarse y luego periódicamente (cada hora por defecto) si la fecha actual ha superado la fecha de expiración guardada en `config.env`.
*   Si la licencia ha expirado, el bot enviará un último mensaje al chat del administrador indicándolo y el script se detendrá.
*   Puedes usar el comando `/licencia_expira` para extender la fecha de expiración mientras el bot aún está en funcionamiento.

## Desactivación Remota por el Administrador Principal

El administrador principal (que controla un bot de administración central, como `@ManagerAccounts_bot`) puede desactivar remotamente este bot reseller utilizando el sistema de licencias.

Para hacerlo, el bot administrador principal debe enviar el comando `/licencia_expira` directamente a *este* bot reseller, estableciendo una fecha en el pasado.

**Pasos para el Admin Principal:**

1.  El bot de administración debe conocer el `TELEGRAM_BOT_TOKEN` y el `ADMIN_CHAT_ID` del bot reseller a desactivar.
2.  El bot de administración debe usar la API de Telegram para enviar un mensaje al `ADMIN_CHAT_ID` del reseller, utilizando el `TELEGRAM_BOT_TOKEN` del reseller. El contenido del mensaje debe ser:
    ```
    /licencia_expira 2000-01-01
    ```
    (O cualquier otra fecha claramente en el pasado).
3.  El bot reseller recibirá este comando, actualizará su `EXPIRATION_DATE` en `config.env`.
4.  En la siguiente comprobación de licencia (máximo una hora después), el bot reseller detectará la fecha expirada y se detendrá automáticamente, notificando a su `ADMIN_CHAT_ID`.

**Nota:** La implementación del bot de administración principal no forma parte de este conjunto de scripts.

## Limitaciones (Bash Bot)

*   **Interfaz Guiada por Texto:** Las operaciones que requieren datos complejos (añadir/editar cuenta, registrar usuario, eliminar/ver específicos) necesitan comandos de texto formateados.
*   **Análisis de Comandos Frágil:** Especialmente sensible con el comando `/register` y el uso del punto y coma.
*   **Sin Concurrencia.**
*   **Manejo de Errores Básico.**
*   **Edición Campo por Campo (Cuentas).** No hay edición para registros implementada.

## Desinstalación

1.  **Detener el Servicio (si aplica):**
    ```bash
    sudo systemctl stop streaming_bot.service
    sudo systemctl disable streaming_bot.service
    sudo rm /etc/systemd/system/streaming_bot.service
    sudo systemctl daemon-reload
    ```
2.  **Eliminar Archivos:**
    Elimina el directorio donde clonaste/copiaste los scripts (ej. `streaming_manager_bot`).
    ```bash
    rm -rf ~/streaming_manager_bot # Ajusta la ruta si es necesario
    ```
