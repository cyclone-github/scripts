#!/bin/bash

# vast.ai htp setup script
# by cyclone
# 
# Changelog:
# 2024-12-03.1845;
#   initial github release
# 2024-12-04.0945;
#   added pciutils to update PCI IDs for htp to recongize newer GPUs
#   added sanity check to ensure script is run as root
#   updated comments for bash compatibility

HTP_SERVER="https://htp_server.com" # EDIT your htp server ip / domain
HTP_VOUCHER="htp_voucher"           # EDIT your htp voucher (reusable voucher works best if setting up multiple agents)

if [ "$EUID" -ne 0 ]; then
  echo "Script must be run as root. Please run again using sudo or as root user."
  exit 1
fi

echo "This script will setup a new vast.ai instance to run htp."
echo
echo "Running apt update..."
apt update &> /dev/null && echo "Ok" || echo "Failed"
echo "Running apt dist-upgrade..."
apt dist-upgrade -y &> /dev/null && echo "Ok" || echo "Failed"
echo "Installing required software..."
apt install wget nano python3 python3-requests python3-psutil pciutils -y &> /dev/null && echo "Ok" || { echo "Failed, exiting"; exit 1; }
echo "Updating PCI IDs..."
update-pciids &> /dev/null && echo "Ok" || echo "Failed"
echo "Creating & entering htp directory..."
mkdir htp &> /dev/null
cd htp/ && echo "Ok" || { echo "Failed, exiting"; exit 1; }
echo "Downloading hashtopolis.zip from htp server..."
wget -O hashtopolis.zip "$HTP_SERVER/agents.php?download=1" &> /dev/null && echo "Ok" || { echo "Failed, exiting"; exit 1; }
echo "Creating config.json..."
echo '{
  "url": "'"$HTP_SERVER"'/api/server.php",
  "voucher": "'"$HTP_VOUCHER"'",
  "token": "",
  "uuid": ""
}' > config.json && echo "Ok" || { echo "Failed, exiting"; exit 1; }
echo "Running htp python client..."
python3 hashtopolis.zip && echo "Ok" || echo "Failed"