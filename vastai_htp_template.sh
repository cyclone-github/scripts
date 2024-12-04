#!/bin/bash
"""
vast.ai htp setup script
by cyclone
2024-12-03.1845
"""

HTP_SERVER="https://htp_server.com" # EDIT your htp server ip / domain
HTP_VOUCHER="htp_voucher"           # EDIT your htp voucher (reusable voucher works best if setting up multiple agents)

echo "This script will setup a new vast.ai instance to run htp."
echo
echo "Running apt update..."
apt update &> /dev/null && echo "Ok" || echo "Failed"
echo "Running apt dist-upgrade..."
apt dist-upgrade -y &> /dev/null && echo "Ok" || echo "Failed"
echo "Installing required software..."
apt install wget nano python3 python3-requests python3-psutil -y &> /dev/null && echo "Ok" || echo "Failed"
echo "Creating & entering htp directory..."
mkdir htp &> /dev/null
cd htp/ && echo "Ok" || echo "Failed"
echo "Downloading hashtopolis.zip from htp server..."
wget -O hashtopolis.zip "$HTP_SERVER/agents.php?download=1" &> /dev/null && echo "Ok" || echo "Failed"
echo "Creating config.json..."
echo '{
  "url": "'"$HTP_SERVER"'/api/server.php",
  "voucher": "'"$HTP_VOUCHER"'",
  "token": "",
  "uuid": ""
}' > config.json && echo "Ok" || echo "Failed"
echo "Running htp python client..."
python3 hashtopolis.zip && echo "Ok" || echo "Failed"