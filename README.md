# Gestor de Cuentas de Streaming para Telegram (Modelo Usuario Añade Cuentas)

Este es un bot de Telegram simple, escrito en Python, diseñado para que **usuarios autorizados** gestionen el acceso a **sus propios perfiles** de servicios de streaming (como Netflix, HBO Max, Spotify, etc.). Utiliza una base de datos SQLite para almacenar la información de forma persistente. Las cuentas añadidas por los usuarios tienen una **validez de 30 días** desde su registro.

**Nota de Seguridad Importante:** Este bot almacena los PIN de los perfiles en texto plano en la base de datos SQLite. Esto **no es seguro** para entornos de producción o información sensible real. Úsalo bajo tu propio riesgo. Además, compartir cuentas puede violar los Términos de Servicio de las plataformas.

## Características

*   **Almacenamiento Persistente:** Guarda perfiles de cuentas (vinculados a usuarios), usuarios autorizados en una base de datos SQLite (`accounts.db`).
*   **Modelo de Usuario Añade Cuentas:** Los usuarios autorizados por el administrador pueden añadir sus propios perfiles (Servicio, Email, Nombre Perfil, PIN) a través de un proceso interactivo.
*   **Caducidad de Cuentas:** Cada perfil añadido por un usuario tiene una validez de 30 días desde el momento de su registro. Después de ese tiempo, dejará de aparecer en sus listas y no podrá obtener sus detalles.
*   **Autorización de Usuarios:** El administrador controla qué usuarios pueden usar el bot y por cuánto tiempo (caducidad general del usuario).
*   **Acceso Controlado:** Los usuarios solo pueden ver y obtener detalles de los perfiles que ellos mismos han añadido y que aún están activos (no caducados).
*   **Comandos de Usuario (Autorizado):**
    *   `/list`: Muestra los perfiles propios que están activos.
    *   `/get`: Obtiene los detalles (Email/Perfil/PIN) de sus perfiles activos (enviado por mensaje privado).
    *   `/addmyaccount`: Inicia un proceso interactivo para añadir un nuevo perfil propio.
*   **Comandos de Usuario (Todos):**
    *   `/start`: Mensaje de bienvenida y menú principal.
    *   `/help`: Muestra la ayuda (comandos varían según autorización).
    *   `/status`: Verifica si su permiso general para usar el bot está activo y hasta cuándo.
*   **Comandos de Administrador:**
    *   `/adduser <user_id> <nombre> <días>`: Autoriza/actualiza un usuario para usar el bot y define la caducidad de su permiso general.
    *   `/listusers`: Muestra todos los usuarios registrados y el estado de su permiso general.
    *   `/listallaccounts`: Muestra todos los perfiles registrados en el sistema (de todos los usuarios), indicando el dueño y la fecha de caducidad de cada perfil.
*   **Interfaz Interactiva:** Uso de conversaciones y borrado automático de mensajes para una experiencia más limpia.
*   **Configuración Fácil:** Mediante un archivo `.env`.
*   **Estructura Modular:** Código organizado en `bot.py`, `user_handlers.py`, `admin_handlers.py`, `callback_handlers.py`, `database.py`, `utils.py`.

## Instalación y Ejecución (Enfoque en VPS)

Estas instrucciones se centran en desplegar el bot en un servidor **VPS con Ubuntu 20.04 LTS o superior**. La configuración local es útil para pruebas previas.

### 1. Prerrequisitos

Antes de empezar con el despliegue del bot, asegúrate de que tu VPS cumple con lo siguiente y ejecuta los comandos necesarios:

*   **Acceso a un VPS con Ubuntu 20.04 LTS o superior:** Necesitas poder conectarte vía SSH.
*   **Actualizar el sistema e instalar Python y herramientas básicas:** Ejecuta los siguientes comandos en tu VPS Ubuntu:
    ```bash
    # Actualiza la lista de paquetes
    sudo apt update
    sudo apt upgrade -y # Opcional: actualiza paquetes instalados

    # Instala Python 3 (generalmente ya presente), pip y venv
    sudo apt install python3 python3-pip python3-venv -y

    # (Opcional pero recomendado) Instala SQLite por si acaso no viene con Python
    sudo apt install sqlite3 libsqlite3-dev -y
    ```
*   **Obtener credenciales de Telegram:**
    *   Un **Token de Bot de Telegram**: Habla con `@BotFather` en Telegram para crear un bot y obtener su token.
    *   Tu **ID de usuario de Telegram**: Habla con `@userinfobot` en Telegram para obtener tu ID numérico. Este será el `ADMIN_USER_ID`.

### 2. Despliegue en VPS

**Instalación Rápida (Una Línea)**

Puedes intentar usar el siguiente comando para descargar y ejecutar el script de instalación automáticamente. Ejecútalo directamente en la terminal de tu VPS:

```bash
wget --no-cache https://raw.githubusercontent.com/sysdevfiles/ScriptManagerAccounts/main/install.sh -O install.sh && chmod +x install.sh && sudo bash install.sh && rm install.sh
```
*Este comando descargará `install.sh`, lo hará ejecutable, lo ejecutará con `sudo` (necesario para instalar paquetes y configurar `systemd`), y luego lo eliminará. **Requerirá tu intervención manual** durante la ejecución para crear el archivo `.env` con tus credenciales si no existe.*

**Pasos Detallados (Alternativa Manual)**

Si prefieres seguir los pasos manualmente o si el comando anterior falla:

**a. Limpieza de Instalación Anterior (Opcional)**

Si estás reinstalando el bot y ya tenías una versión anterior configurada (especialmente si usaste `systemd`), sigue estos pasos primero para asegurar una instalación limpia. **Si es la primera vez, puedes omitir esta subsección.**

1.  **Detén el servicio `systemd` (si existe):**
    ```bash
    sudo systemctl stop telegrambot.service
    ```
    *(Puede que dé un error si el servicio no existe o no se llama así, es normal).*

2.  **Deshabilita el servicio `systemd` (si existe):**
    ```bash
    sudo systemctl disable telegrambot.service
    ```

3.  **Elimina el directorio anterior del bot:**
    ```bash
    # ¡CUIDADO! Esto borrará todo el contenido, incluyendo la base de datos anterior.
    rm -rf ~/telegram_bot
    ```

4.  **Elimina el archivo de servicio `systemd` anterior (si existe):**
    ```bash
    sudo rm /etc/systemd/system/telegrambot.service
    ```

5.  **Recarga `systemd` para aplicar la eliminación del archivo:**
    ```bash
    sudo systemctl daemon-reload
    ```

**b. Pasos de Instalación**

1.  **Conéctate a tu VPS Ubuntu** (usando SSH).

2.  **Crea un directorio para el bot y navega a él:**
    ```bash
    mkdir ~/telegram_bot
    cd ~/telegram_bot
    ```

3.  **Sube los archivos del bot:**
    Transfiere `bot.py`, `handlers.py`, `database.py` y `requirements.txt` a este directorio (`~/telegram_bot`). Puedes usar `scp`, `rsync` o un cliente SFTP.

4.  **Crea el archivo `.env` en el VPS:**
    Dentro del directorio `~/telegram_bot`, crea el archivo `.env` con el siguiente contenido, usando un editor como `nano` (`nano .env`):
    ```dotenv
    # filepath: ~/telegram_bot/.env (Ejemplo de ruta en VPS)
    # Inserte su token de Telegram (obtenido de @BotFather)
    TELEGRAM_BOT_TOKEN="TU_TOKEN_DE_BOT_AQUI_OBTENIDO_DE_BOTFATHER"
    # Inserte su ID de Telegram (obtenido de @userinfobot)
    ADMIN_USER_ID="TU_ID_DE_USUARIO_AQUI_OBTENIDO_DE_USERINFOBOT"
    ```
    *Guarda y cierra el editor (en `nano`, `Ctrl+X`, luego `Y`, luego `Enter`).*
    ***Nota:** Debes reemplazar los valores de ejemplo con tus credenciales reales.*

5.  **Crea y activa un entorno virtual:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
    *Verás `(venv)` al principio de tu prompt.*

6.  **Instala las dependencias del bot:**
    ```bash
    pip install -r requirements.txt
    ```

7.  **Prueba la ejecución:**
    ```bash
    python bot.py
    ```
    *El bot debería iniciarse. Puedes detenerlo con `Ctrl+C`. Se creará el archivo `accounts.db`.*

8.  **Ejecutar en segundo plano (Producción):**
    Para que el bot siga funcionando después de cerrar la sesión SSH y se reinicie automáticamente si falla o si el servidor se reinicia, **se recomienda encarecidamente usar `systemd`**. El script `install.sh` configura esto automáticamente.

    **Método Recomendado: `systemd` (Configurado por `install.sh`)**

    El script `install.sh` crea y configura un servicio llamado `telegrambot.service`.

    a.  **Asegúrate de que el script de instalación se ejecutó correctamente.**
    b.  **Habilita el servicio (si no lo hizo el script):** Para que se inicie automáticamente al arrancar el VPS.
        ```bash
        sudo systemctl enable telegrambot.service
        ```
    c.  **Inicia o Reinicia el servicio:**
        ```bash
        # Para iniciar por primera vez o si estaba detenido:
        sudo systemctl start telegrambot.service
        # Para aplicar cambios o reiniciar si ya corría:
        sudo systemctl restart telegrambot.service
        ```
    d.  **Verifica el estado:**
        ```bash
        sudo systemctl status telegrambot.service
        ```
        *Deberías ver `active (running)`. Presiona `q` para salir. Ahora puedes cerrar tu sesión SSH.*
    e.  **Ver los logs:** `systemd` captura la salida del bot.
        ```bash
        # Ver los últimos logs:
        sudo journalctl -u telegrambot.service -n 50 --no-pager
        # Seguir los logs en tiempo real:
        sudo journalctl -u telegrambot.service -f
        ```
        *Usa `Ctrl+C` para detener el seguimiento.*
    f.  **Otros comandos útiles:**
        *   `sudo systemctl stop telegrambot.service`: Detiene el bot.
        *   `sudo systemctl disable telegrambot.service`: Evita que el bot inicie automáticamente al arrancar.

    **Alternativas Simples (Menos Robustas):**

    Si prefieres no usar `systemd` (no recomendado para producción), puedes usar `nohup` o `screen`/`tmux`.

    *   **`nohup`:** Ejecuta el bot en segundo plano, ignorando la señal de cierre de sesión. La salida se guarda en `bot.log`. No se reinicia automáticamente.
        ```bash
        # En el directorio del bot, con venv activado:
        nohup python bot.py > bot.log 2>&1 &
        ```
        *Para detenerlo, busca su ID de proceso (`ps aux | grep bot.py`) y usa `kill <PID>`.*

    *   **`screen` / `tmux`:** Multiplexores de terminal. Creas una sesión, ejecutas el bot, te desconectas de la sesión dejándola activa. Tampoco se reinicia automáticamente. Busca tutoriales de `screen` o `tmux` si te interesa esta opción.

9.  **Firewall:** Asegúrate de que el firewall de tu VPS (si está activo, ej. `ufw`) permite las conexiones salientes en el puerto 443/TCP para que el bot pueda comunicarse con la API de Telegram. Normalmente, las reglas por defecto permiten el tráfico saliente.

### 3. Configuración Local (Opcional, para Pruebas)

Si deseas probar el bot en tu máquina local antes de desplegarlo:

1.  **Asegúrate de tener Python 3 y pip.**
2.  **Crea una carpeta** (ej. `c:\AccessControl`).
3.  **Coloca `bot.py` y `requirements.txt`** en la carpeta.
4.  **Crea el archivo `.env`** como se describe en el paso 5 del despliegue VPS, pero en tu carpeta local.
5.  **Abre una terminal** en esa carpeta.
6.  **Crea y activa un entorno virtual:**
    ```bash
    python -m venv venv
    # En Windows: .\venv\Scripts\activate
    # En Linux/macOS: source venv/bin/activate
    ```
7.  **Instala dependencias:** `pip install -r requirements.txt`
8.  **Ejecuta:** `python bot.py`

## Comandos del Bot

**Comandos para Todos:**

*   `/start`: Inicia la conversación y muestra el menú.
*   `/help`: Muestra la lista de comandos disponibles según tu nivel de acceso.
*   `/status`: Verifica si tienes permiso para usar el bot y hasta qué fecha.

**Comandos para Usuarios Autorizados (No Admin):**

*   `/list`: Muestra un resumen de los perfiles propios que has añadido y están activos.
*   `/get`: Te envía por privado los detalles (Email, Perfil y PIN) de tus perfiles activos.
*   `/addmyaccount`: Inicia el proceso interactivo para añadir un nuevo perfil (tendrá 30 días de validez).
*   `/editmyaccount`: Inicia el proceso interactivo para editar el Email o PIN de un perfil propio.
*   `/deletemyaccount`: Inicia el proceso interactivo para eliminar un perfil propio.
*   `/backupmyaccounts`: Genera y te envía un archivo `.txt` con la información de tus cuentas activas.
*   `/importmyaccounts`: Inicia el proceso interactivo para importar/actualizar cuentas desde un archivo `.txt` de backup (las cuentas importadas tendrán 30 días de validez).

**Comandos Solo para Administrador:**

*   `/adduser <user_id_telegram> <nombre_usuario> <días_acceso>`: Autoriza a un usuario de Telegram para usar el bot por un número determinado de días.
*   `/listusers`: Muestra todos los usuarios autorizados y la fecha de expiración de su permiso.
*   `/listallaccounts`: Muestra todos los perfiles registrados por todos los usuarios, incluyendo su `ID` único, dueño y fecha de caducidad.

## Próximos Pasos / Mejoras Posibles
*   **Backup Admin:** Añadir comando `/backupallaccounts` para que el admin genere un backup de todas las cuentas.
*   **Restaurar Backup (Admin):** Funcionalidad para que el admin restaure cuentas desde un archivo (más complejo, requiere mapeo de user_id).
*   **Cifrado de PINs:** Implementar cifrado para el PIN en la base de datos.
*   **Eliminar Cuentas (Admin):** Añadir comando `/deleteaccount <account_id>` para admin.
*   **Eliminar Usuarios (Admin):** Añadir comando `/deleteuser <user_id>` para admin.
*   **Modificar Usuarios (Admin):** Comando para editar nombre o días de un usuario existente.
*   **Notificaciones:** Avisar a usuarios antes de que expire su permiso general o sus cuentas.
*   **Gestión de Errores:** Mejorar el manejo de errores específicos y el parseo de archivos.
