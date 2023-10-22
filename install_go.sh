#!/bin/bash

# script to automatically download and install the latest version of Go on linux
# tested on debian amd64 & raspberry OS arm32/arm64
# written by cyclone
# v10-22-2023.1530; auto-select OS-arch

# clear screen
clear

# get latest Go binary based on architecture
get_latest_go_version() {
	curl -s https://go.dev/dl/ | grep -o "go[0-9]*\.[0-9]*\.[0-9]*\.$1\.tar\.gz" | head -n 1
}

# check if Go is already installed
if command -v go >/dev/null 2>&1; then
	installed_version=$(go version | awk '{print $3}')
	echo "Go version: $installed_version"
else
	installed_version="none"
	echo "Go version: not detected"
fi

# detect system architecture
machine=$(uname -m)
case $machine in
i386 | i686) arch="linux-386" ;;
x86_64) arch="linux-amd64" ;;
armv7l) arch="linux-armv6l" ;;
aarch64) arch="linux-arm64" ;;
*)
	echo "Unknown architecture"
	exit 1
	;;
esac
echo "OS detected: $arch"

# get latest Go binary version
goBinary=$(get_latest_go_version $arch)
latest_version=$(echo $goBinary | grep -o 'go[0-9]*\.[0-9]*\.[0-9]*')

# prompt for upgrade / reinstallation
if [ "$installed_version" != "none" ]; then
	msg="Would you like to upgrade to $latest_version? (y/n): "
	[ "$installed_version" == "$latest_version" ] && msg="Do you want to reinstall Go $latest_version? (y/n): "
	read -p "$msg" choice
	[ "$choice" != "y" ] && echo "No changes made, exiting..." && exit 0
fi

# download Go binary
wget -O $goBinary "https://go.dev/dl/$goBinary" || {
	echo "Download failed, exiting..."
	exit 1
}

# install Go
echo "Installing Go..."
if sudo rm -rf /usr/local/go && sudo tar -C /usr/local -xzf $goBinary; then
	echo 'export PATH=$PATH:/usr/local/go/bin' >>~/.bashrc
	source ~/.bashrc
	echo "Go installed and PATH updated successfully."
else
	echo "Failed to install Go"
	exit 1
fi

# verify installation
if command -v go >/dev/null 2>&1; then
	new_installed_version=$(go version | awk '{print $3}')
	if [ "$new_installed_version" == "$latest_version" ]; then
		echo "Go installation successful. Installed version: $new_installed_version"
	else
		echo "Go installation failed. Version mismatch. Expected: $latest_version, Got: $new_installed_version"
	fi
else
	echo "Go installation failed. 'go' command not found."
fi

# end code