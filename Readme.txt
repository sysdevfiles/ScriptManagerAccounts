wget --no-cache https://raw.githubusercontent.com/sysdevfiles/ScriptManagerAccounts/main/vps_installer.sh -O vps_installer.sh && chmod +x vps_installer.sh && ./vps_installer.sh && rm vps_installer.sh


sudo apt update && sudo apt install screen

screen -S streaming_bot

cd ~/streaming_manager
./telegram_bot_manager.sh
