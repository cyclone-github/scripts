#!/bin/bash

# script to x-compile go binaries for linux / windows / mac
# written by cyclone
version="v1.1.1; 2023.1.9-1500"

clear

echo "Cyclone go compiler $version"
echo ""

# check prerequisites
# upx
if ! command -v upx &> /dev/null
then
    echo "upx needs to be installed"
    echo "use apt install upx -y to install"
    break
fi
# go
if ! command -v go version &> /dev/null
then
    echo "go needs to be installed"
    echo "https://go.dev/doc/install"
    break
fi

#############################
## Collect the files in the array $files
echo "Select go app to compile:"
echo
files=( *.go )
shopt -s extglob
string="@(${files[0]}"
for((i=1;i<${#files[@]};i++))
do
    string+="|${files[$i]}"
done
string+=")"

## Show menu
select file in "${files[@]}"
do
    case $file in
    $string)
        # show array
        echo "$file"
        break;
        ;;

    *)
        file=""
        echo "Enter 1 to $((${#files[@]}+1))";;
    esac
done

app=$(echo "$file" | cut -d. -f1)

#############################
# run go fmt
while true; do
    echo "Running 'go fmt $app.go'..."
    gofmt -w $app.go &>/dev/null && echo "Ok" || echo "Failed"
    break
done

# run go mod init & tidy before compiling
while true; do
    rm go.mod &>/dev/null
    echo "Running 'go mod init $app.go'..."
    go mod init $app.go &>/dev/null && echo "Ok" || echo "Failed"
    echo "Running 'go mod tidy' for $app.go..."
    go mod tidy &>/dev/null && echo "Ok" || echo "Failed"
    break
done

# compile go package for linux
while true; do
    echo "Compiling $app.bin for Linux x64..."
    GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o bin/$app.bin $app.go &> /dev/null && echo "Ok" || echo "Failed"
    echo "Compressing $app.bin..."
    upx --brute bin/$app.bin &>/dev/null && echo "Ok" || echo "Failed"
    break
done

# compile go package for windows
while true; do
    echo "Compiling $app.exe for Windows x64..."
    GOOS=windows GOARCH=amd64 go build -ldflags="-s -w" -o bin/$app.exe $app.go &>/dev/null && echo "Ok" || echo "Failed"
    echo "Compressing $app.exe..."
    upx --brute bin/$app.exe &>/dev/null && echo "Ok" || echo "Failed"
    break
done

# compile go package for mac
while true; do
    echo "Compiling $app-darwin for Mac x64..."
    GOOS=darwin GOARCH=amd64 go build -ldflags="-s -w" -o bin/$app-darwin $app.go &>/dev/null && echo "Ok" || echo "Failed"
    echo "Compressing $app-darwin..."
    upx --brute bin/$app-darwin &>/dev/null && echo "Ok" || echo "Failed"
    break
done

echo "End of script."
