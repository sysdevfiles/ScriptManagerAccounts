wget --no-cache https://raw.githubusercontent.com/sysdevfiles/ScriptManagerAccounts/main/vps_installer.sh -O vps_installer.sh && chmod +x vps_installer.sh && ./vps_installer.sh && rm vps_installer.sh


sudo apt update && sudo apt install screen

screen -S streaming_bot

cd ~/streaming_manager
python3 telegram_bot_python.py


ps aux | grep telegram_bot_python.py
kill <PID>