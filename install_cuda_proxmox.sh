#!/bin/bash

# Script to install nvidia-cuda-toolkit on Proxmox (Debian) from offical Nvidia repository
# Run as root
# Written by cyclone

# v2024-01-17; add support for Debian 11 & 12
# v2024-03-04; sanity checks, remove old cuda-keyring
# v2024-06-27; clean up script, post to github

# Check if root
if [ "$EUID" -ne 0 ]; then
    echo "Must be run as root"
    exit 1
else
    echo "Checking if root: OK"
fi

# Check if running on a Debian-based distro
if grep -qi debian /etc/os-release; then
    echo "Checking if Debian-based distro: OK"
else
    echo "This script is intended to run on Debian-based distributions only."
    exit 1
fi

# Check if running on Proxmox
if dpkg -l | grep -qi pve-manager; then
    echo "Checking if Proxmox: OK"
else
    echo "This script is intended to run on Proxmox and will install Proxmox Kernel Headers."
    read -p "Are you sure you want to continue? (y/n): " choice
    case "$choice" in 
        y|Y ) echo "Continuing...";;
        n|N ) echo "Exiting script."; exit 1;;
        * ) echo "Invalid choice. Exiting script."; exit 1;;
    esac
fi

cat <<EOF

#################################################################
Script will install nvidia-cuda-toolkit on Proxmox (Debian)

--> This will remove all existing *cuda and *nvidia packages <--

Press any key to continue, or ctrl+c to cancel...
#################################################################

EOF
read

# Blacklist nouveau driver
echo "Blacklisting nouveau driver..."
echo "blacklist nouveau" > /etc/modprobe.d/blacklist-nouveau.conf &> /dev/null && echo "Ok" || echo "Failed"

# Enable contrib and non-free repositories
echo "Enabling contrib and non-free repositories..."
apt install software-properties-common -y &> /dev/null && echo "Ok" || echo "Failed"
add-apt-repository contrib
add-apt-repository non-free

# Install GCC
echo "Installing GCC..."
apt install gcc -y &> /dev/null && echo "Ok" || echo "Failed"

# Install pve headers
echo "Installing pve-headers..."
apt update
apt install pve-headers-$(uname -r) -y &> /dev/null && echo "Ok" || echo "Failed"

# Install DKMS
echo "Installing DKMS..."
apt install dkms -y &> /dev/null && echo "Ok" || echo "Failed"

# Update initramfs
echo "Updating initramfs..."
update-initramfs -u &> /dev/null && echo "Ok" || echo "Failed"

# Remove old cuda-keyring downloads
echo "Removing old cuda-keyring downloads..."
rm cuda-keyring_1.* &> /dev/null && echo "Ok"

# Remove existing cuda and nvidia
echo "Removing previously installed nvidia & cuda programs..."
apt autoremove --purge cuda* nvidia* -y &> /dev/null && echo "Ok" || echo "Failed"

# User options for cuda-keyring installation
echo "Select the cuda-keyring version to install:"
echo "1. Install cuda-keyring v1.1.1 for Debian 12"
echo "2. Install cuda-keyring v1.1.1 for Debian 11"
echo "3. Install cuda-keyring v1.0.1 for Debian 11"
read -p "Enter your choice (1, 2, or 3): " choice

case $choice in
    1) CUDA_KEYRING_URL="https://developer.download.nvidia.com/compute/cuda/repos/debian12/x86_64/cuda-keyring_1.1-1_all.deb" ;;
    2) CUDA_KEYRING_URL="https://developer.download.nvidia.com/compute/cuda/repos/debian11/x86_64/cuda-keyring_1.1-1_all.deb" ;;
    3) CUDA_KEYRING_URL="https://developer.download.nvidia.com/compute/cuda/repos/debian11/x86_64/cuda-keyring_1.0-1_all.deb" ;;
    *) echo "Invalid choice"; exit 1 ;;
esac

echo "Downloading cuda-keyring..."
wget $CUDA_KEYRING_URL &> /dev/null && echo "Ok" || echo "Failed"
echo "Installing cuda-keyring..."
dpkg -i $(basename $CUDA_KEYRING_URL) &> /dev/null && echo "Ok" || echo "Failed"

# Run apt-update and dist-upgrade
echo "Running apt-update..."
apt update &> /dev/null && echo "Ok" || echo "Failed"
echo "Running dist-upgrade..."
apt dist-upgrade -y &> /dev/null && echo "Ok" || echo "Failed"

# Remove old packages
echo "Removing old packages..."
apt autoremove --purge -y &> /dev/null && echo "Ok" || echo "Failed"

# Install cuda
echo "Installing nvidia-cuda-toolkit... (this may take a while)"
apt install cuda -y && echo "Ok" || echo "Failed"

# Reboot computer
echo "Please reboot computer..."

# script end
