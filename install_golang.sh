#!/bin/bash

# script to install golang on debian linux
# written by cyclone

goBinary="go1.20.3.linux-amd64.tar.gz" # <--- edit to latest go binary you wish to install
url="https://go.dev/dl/"

# download golang binary
while true; do
        rm $goBinary &> /dev/null
        wget $url$goBinary && break
        echo "Download failed, retrying..."
        sleep 5
done

# install golang
while true; do
        echo "Installing golang..."
        rm -rf /usr/local/go && tar -C /usr/local -xzf $goBinary && echo "Ok" || echo "Failed to install golang"
        break
done

# set path
while true; do
        echo "Setting golang path..."
        export PATH=$PATH:/usr/local/go/bin && echo "Ok" || echo "Failed to set golang path"
        break
done

# show golang version
go version

# end script
