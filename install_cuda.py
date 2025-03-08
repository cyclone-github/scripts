#!/usr/bin/env python3

import os
import re
import sys
import hashlib
import platform
import subprocess
import urllib.request
from urllib.parse import urljoin

# script to install nvidia cuda-toolkit on linux from offical URL: https://developer.nvidia.com/cuda-downloads
# run as root
# written by cyclone
# https://github.com/cyclone-github/scripts
#
# GNU General Public License v2.0
# https://github.com/cyclone-github/scripts/blob/main/LICENSE
#
# v2024-01-17; add support for Debian 11 & 12
# v2024-03-04; sanity checks, remove old cuda-keyring
# v2024-06-27; clean up script, post to github
# v2024-12-10; script no longer works on Proxmox 8.x (Debian 12) due to incompatible dependencies
# v2025-03-08; rewritten in python3, supports all nvidia supported linux distros, installs CUDA via *.run file instead of apt (fixes dependency issues on some distros)

print(" ------------------------------------------- ", file=sys.stderr)
print("|       Cyclone's Linux CUDA Installer      |", file=sys.stderr)
print("|                v2025-03-08                |", file=sys.stderr)
print("| https://github.com/cyclone-github/scripts |", file=sys.stderr)
print(" ------------------------------------------- \n", file=sys.stderr)

# run as root
if os.geteuid() != 0:
    print("Error: CUDA installer script must be run as root.", file=sys.stderr)
    sys.exit(1)

# supported architecture
ARCH = platform.machine().lower()
ARCH_MAP = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}

ARCH = ARCH_MAP.get(ARCH, None)

if not ARCH:
    print(
        f"Error: Unsupported architecture detected: {platform.machine()}. CUDA installer supports x86_64 and arm64.",
        file=sys.stderr,
    )
    sys.exit(1)

print(f"Detected Architecture: {ARCH}")


# detect Linux distro
def get_distro():
    try:
        if hasattr(platform, "freedesktop_os_release"):
            os_info = platform.freedesktop_os_release()
            distro_name = os_info.get("ID", "").lower()
            distro_version = os_info.get("VERSION_ID", "")
        else:
            result = subprocess.run(
                [". /etc/os-release && echo $ID $VERSION_ID"],
                shell=True,
                capture_output=True,
                text=True,
            )
            distro_info = result.stdout.strip().split()
            if len(distro_info) >= 2:
                distro_name, distro_version = distro_info[0].lower(), distro_info[1]
            else:
                raise ValueError("Incomplete OS information retrieved.")

        return distro_name, distro_version
    except Exception as e:
        print(f"Error: Unable to determine Linux distro. {e}", file=sys.stderr)
        sys.exit(1)


DISTRO, VERSION = get_distro()

# supported distro names
DISTRO_MAP = {
    "ubuntu": "Ubuntu",
    "debian": "Debian",
    "rhel": "RHEL",
    "centos": "RHEL",
    "fedora": "Fedora",
    "wsl-ubuntu": "WSL-Ubuntu",
    "rocky": "Rocky",
    "sles": "SLES",
    "amazon-linux": "Amazon-Linux",
    "amzn": "Amazon-Linux",
    "azure-linux": "Azure-Linux",
    "opensuse": "OpenSUSE",
    "oracle-linux": "Oracle-Linux",
    "kylinos": "KylinOS",
}

DISTRO = DISTRO_MAP.get(DISTRO)

if not DISTRO:
    print("Error: Unsupported Linux distro detected.", file=sys.stderr)
    sys.exit(1)

print(f"Detected Linux distro: {DISTRO} {VERSION}")

print("\nChecking for existing CUDA installation...\n")

cuda_version = None

try:
    result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
    if result.returncode == 0:
        match = re.search(r"CUDA Version: (\d+\.\d+)", result.stdout)
        cuda_version = match.group(1) if match else None
except FileNotFoundError:
    pass

if cuda_version:
    print(f"Current CUDA Version Installed: {cuda_version}\n")
else:
    print("No existing CUDA installation detected.\n")

# CUDA download page URL
SEARCH_URL = f"https://developer.nvidia.com/cuda-downloads?target_os=Linux&target_arch={ARCH}&Distribution={DISTRO}&target_version={VERSION}&target_type=runfile_local"

try:
    with urllib.request.urlopen(SEARCH_URL, timeout=10) as response:
        page_content = response.read().decode("utf-8")
except Exception as e:
    print(f"Error: Failed to parse CUDA download page. {e}", file=sys.stderr)
    sys.exit(1)

cuda_version_match = re.search(r"cuda/(\d+\.\d+)", page_content)

if not cuda_version_match:
    print(
        "Error: No CUDA version found. NVIDIA's website might have changed.",
        file=sys.stderr,
    )
    sys.exit(1)

CUDA_VERSION = cuda_version_match.group(1)

cuda_full_version_match = re.search(r"cuda/(\d+\.\d+\.\d+)/", page_content)
CUDA_FULL_VERSION = (
    cuda_full_version_match.group(1) if cuda_full_version_match else CUDA_VERSION
)

wget_match = re.search(
    r"wget\s+(https://developer\.download\.nvidia\.com/compute/cuda/[^\s]+linux\.run)",
    page_content,
)

if not wget_match:
    print("Error: Unable to find the CUDA installer URL.", file=sys.stderr)
    sys.exit(1)

installer_url = wget_match.group(1)
installer_filename = os.path.basename(installer_url)

installer_base_url = os.path.dirname(installer_url)
checksum_url = f"{installer_base_url}/../docs/sidebar/md5sum.txt"

# prompt user to install
while True:
    user_input = (
        input(f"Download and install CUDA {CUDA_FULL_VERSION}? (y/n): ").strip().lower()
    )
    if user_input in ["y", "yes"]:
        break
    elif user_input in ["n", "no"]:
        print("Installation aborted by user.")
        sys.exit(0)
    else:
        print("Invalid input. Please enter 'y' or 'n'.")


# checksum installer
def get_checksum(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            checksum_data = response.read().decode("utf-8")
    except Exception as e:
        print(f"Error: Failed to fetch checksum file. {e}", file=sys.stderr)
        sys.exit(1)

    checksums = {
        line.split()[1]: line.split()[0]
        for line in checksum_data.splitlines()
        if len(line.split()) == 2
    }
    return checksums


expected_md5 = get_checksum(checksum_url).get(installer_filename)

if not expected_md5:
    print(
        "Error: Could not find the expected MD5 checksum for the installer.",
        file=sys.stderr,
    )
    sys.exit(1)


# md5 checksum func
def compute_md5(filename):
    md5_hash = hashlib.md5()
    with open(filename, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def verify_checksum(filename):
    print(f"\nVerifying MD5 checksum of {filename}...")
    if compute_md5(filename) == expected_md5:
        print("Checksum matches. Proceeding with installation.")
        return True
    else:
        print("Checksum mismatch!")
        return False


# download CUDA installer
def download_file(url, filename):
    print(f"\nDownloading: {url} -> {filename}")

    with urllib.request.urlopen(url) as response, open(filename, "wb") as out_file:
        total_size = int(response.getheader("Content-Length", 0))
        downloaded_size = 0
        chunk_size = 1024 * 1024

        while chunk := response.read(chunk_size):
            out_file.write(chunk)
            downloaded_size += len(chunk)
            progress = (downloaded_size / total_size) * 100
            print(
                f"\rDownloading: {progress:.2f}% ({downloaded_size}/{total_size} bytes)",
                end="",
                flush=True,
            )

    print("\nDownload complete!")


# verify checksum of downloaded installer
if os.path.exists(installer_filename):
    print(f"\nInstaller {installer_filename} already exists. Verifying checksum...")
    if verify_checksum(installer_filename):
        skip_download = True
    else:
        print("\nChecksum mismatch! Redownloading installer...")
        os.remove(installer_filename)
        skip_download = False
else:
    skip_download = False

if not skip_download:
    download_file(installer_url, installer_filename)

    if not verify_checksum(installer_filename):
        print(
            "\nError: Downloaded file has a checksum mismatch. Exiting.",
            file=sys.stderr,
        )
        sys.exit(1)

# run CUDA installer
print("\nRunning CUDA installer (this may take several minutes)...")
os.chmod(installer_filename, 0o755)
try:
    subprocess.run([f"./{installer_filename}"], check=True)
except subprocess.CalledProcessError:
    print("\nError: CUDA installation failed.", file=sys.stderr)
    sys.exit(1)

# end script
