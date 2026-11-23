#!/usr/bin/env python3
"""Debian 12/13 CUDA + NVIDIA driver runfile installer (including Proxmox).

Usage: sudo python3 install_cuda.py

Downloads and verifies both runfiles before modifying an existing installation.
Uninstalls old runfile and APT-managed installations, then installs both components.
"""

import datetime
import fcntl
import signal
import time
import hashlib
from html.parser import HTMLParser
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

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
# v2026-11-23: due to changes to NVIDIA's cuda/driver installation process, script now focuses on Debian 12/13, CUDA 13.x +

CUDA_PAGE = 'https://developer.nvidia.com/cuda-downloads'
CUDA_DOWNLOAD_HOST = 'https://developer.download.nvidia.com/compute/cuda/'
CUDA_RELEASE_NOTES = 'https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/'
DRIVER_ARCHIVE = 'https://download.nvidia.com/XFree86/Linux-x86_64/'
BACKUP_ROOT = Path('/var/backups/cuda-installer')
CUDA_DIR = Path('/usr/local')
PC_PREFIXES = ('cuda', 'cublas', 'cudart', 'cufft', 'cufile', 'curand', 'cusolver',
               'cusparse', 'cupti', 'nvrtc', 'nvvm', 'nvjpeg', 'npp')
PACKAGE_PREFIXES = (
    'cuda', 'nvidia', 'libnvidia', 'libcuda', 'libcudadebugger', 'libnvcuvid',
    'libnvoptix', 'libnvsdm', 'libxnvctrl', 'libegl-nvidia', 'libgles-nvidia',
    'libglx-nvidia', 'libcublas', 'libcufft', 'libcufile', 'libcurand',
    'libcusolver', 'libcusparse', 'libnvjpeg', 'libnvvm', 'libnpp', 'libcupti',
    'libnvrtc', 'nsight', 'gds-tools', 'firmware-nvidia', 'xserver-xorg-video-nvidia',
    'glx-alternative-nvidia', 'nvidia-alternative', 'libcudnn',
    'libgl1-nvidia', 'libegl1-nvidia', 'libgles1-nvidia',
    'libgles2-nvidia', 'libnvjitlink', 'cuda-compat',
)
# Other Debian packages (notably libhwloc-plugins) depend on libxnvctrl0.
# Only preserve it when APT would otherwise remove an unrelated application.
SHARED_APT_LIBRARIES = frozenset({'libxnvctrl0'})
# APT must not be allowed to remove unrelated dependencies/meta packages.
PROTECTED_PREFIXES = (
    'proxmox-', 'pve-', 'linux-image-', 'linux-headers-', 'systemd', 'libc6',
    'apt', 'dpkg', 'openssh-', 'initramfs-tools', 'grub-', 'linux-base',
)


def die(message):
    raise RuntimeError(message)


def run(args, *, capture=False, check=True, env=None, heartbeat=False):
    print('+', ' '.join(map(str, args)), flush=True)
    if heartbeat and not capture:
        # NVIDIA installers can be quiet while extracting files or compiling DKMS.
        # On Ctrl-C, stop the child rather than waiting indefinitely for it.
        process = subprocess.Popen(list(map(str, args)), env=env)
        start = time.monotonic()
        try:
            while True:
                try:
                    code = process.wait(timeout=60)
                    break
                except subprocess.TimeoutExpired:
                    print(f'Installer still running ({int(time.monotonic() - start)}s). '
                          'Check /var/log/cuda-installer.log or '
                          '/var/log/nvidia-installer.log for details.', flush=True)
        except KeyboardInterrupt:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            raise
        result = subprocess.CompletedProcess(args, code)
    else:
        result = subprocess.run(list(map(str, args)), text=True,
                                stdout=subprocess.PIPE if capture else None,
                                stderr=subprocess.PIPE if capture else None,
                                env=env, check=False)
    if check and result.returncode:
        detail = ((result.stderr or result.stdout or '').strip()[-800:]
                  if capture else '')
        die(f"Command failed ({result.returncode}): {' '.join(map(str, args))}\n{detail}")
    return result


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Cyclone-CUDA-Installer/2026'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', errors='replace')


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def text_only(page):
    p = TextOnly()
    p.feed(page)
    return ' '.join(p.parts)


def distro():
    info = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            info[k] = v.strip('"')
    if info.get('ID') != 'debian' or info.get('VERSION_ID') not in ('12', '13'):
        die('Only Debian 12 and Debian 13 (including Proxmox) are supported.')
    if platform.machine() not in ('x86_64', 'amd64'):
        die('This version supports Debian x86_64/amd64 only.')
    return info['VERSION_ID']


def gpu_devices():
    found = []
    for dev in Path('/sys/bus/pci/devices').glob('*'):
        try:
            if (dev / 'vendor').read_text().strip() != '0x10de':
                continue
            pci_class = int((dev / 'class').read_text().strip(), 16) >> 16
            if pci_class in (0x03, 0x12):
                bound = (dev / 'driver').resolve().name if (dev / 'driver').exists() else 'none'
                gpu_id = (dev / 'device').read_text().strip().removeprefix('0x').upper()
                found.append((dev.name, bound, gpu_id))
        except (OSError, ValueError):
            continue
    return found


def discover_cuda(version):
    # Preserve the original NVIDIA download-page discovery mechanism.
    url = (f'{CUDA_PAGE}?target_os=Linux&target_arch=x86_64&Distribution=Debian'
           f'&target_version={version}&target_type=runfile_local')
    page = get(url)
    links = re.findall(
        r'(https://developer\.download\.nvidia\.com/compute/cuda/'
        r'([0-9]+\.[0-9]+\.[0-9]+)/local_installers/'
        r'(cuda_\2_linux\.run))', page)
    if not links:
        # NVIDIA may change the page layout; do not guess an installer URL.
        die('Could not locate a CUDA runfile on NVIDIA\'s official download page.')
    installer_url, full_version, filename = max(
        links, key=lambda item: tuple(map(int, item[1].split('.'))))
    if not full_version.startswith('13.'):
        die(f'Expected CUDA 13.x, got {full_version}. Update this installer.')
    checksum_url = (f'{CUDA_DOWNLOAD_HOST}{full_version}/docs/sidebar/md5sum.txt')
    return full_version, installer_url, filename, checksum_url


def discover_driver(cuda_version):
    # This is NVIDIA's CUDA-to-driver-branch compatibility table.
    notes = text_only(get(CUDA_RELEASE_NOTES))
    short = '.'.join(cuda_version.split('.')[:2])
    m = re.search(r'\bCUDA\s+' + re.escape(short) + r'\s+R(\d{3})\b', notes)
    if not m:
        die(f'Cannot determine NVIDIA driver branch for CUDA {short} from NVIDIA release notes.')
    branch = m.group(1)
    index = get(DRIVER_ARCHIVE)
    versions = set(re.findall(r'href=["\'](' + re.escape(branch) +
                              r'\.\d+(?:\.\d+)?)/["\']', index, re.I))
    if not versions:
        die(f'No driver runfiles found for NVIDIA R{branch} in the official archive.')
    driver_version = max(versions, key=lambda s: tuple(int(x) for x in s.split('.')))
    filename = f'NVIDIA-Linux-x86_64-{driver_version}.run'
    base = f'{DRIVER_ARCHIVE}{driver_version}/{filename}'
    return driver_version, base, filename, base + '.sha256sum'


def expected_checksum(url, filename, size):
    data = get(url)
    for line in data.splitlines():
        bits = line.strip().split()
        if len(bits) == 2 and bits[1].lstrip('*') == filename and re.fullmatch(r'[a-fA-F0-9]+', bits[0]):
            if len(bits[0]) == size:
                return bits[0].lower()
    die(f'Could not find expected checksum for {filename} at {url}')


def hash_file(path, algo):
    h = hashlib.new(algo)
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def fetch_verified(url, filename, checksum_url, algo):
    path = Path.cwd() / filename
    expected = expected_checksum(checksum_url, filename, 64 if algo == 'sha256' else 32)
    if path.exists():
        print(f'Verifying cached {filename} ({algo})...')
        if hash_file(path, algo) == expected:
            return path
        print('Cached checksum mismatch; redownloading.')
        path.unlink()
    print(f'Downloading: {url} -> {filename}')
    tmp = path.with_name(filename + '.partial')
    try:
        with urllib.request.urlopen(url, timeout=60) as response, tmp.open('wb') as dst:
            total = int(response.headers.get('Content-Length', '0'))
            count = 0
            while True:
                data = response.read(1024 * 1024)
                if not data:
                    break
                dst.write(data)
                count += len(data)
                if total:
                    print(f'\rDownloading: {count * 100 / total:.2f}% ({count}/{total} bytes)',
                          end='', flush=True)
        print()
        if hash_file(tmp, algo) != expected:
            die(f'{algo.upper()} checksum mismatch for {filename}')
        tmp.rename(path)
    finally:
        if tmp.exists():
            tmp.unlink()
    print(f'{algo.upper()} checksum matches.')
    return path


def preflight():
    kernel = platform.uname().release
    print(f'Checking prerequisites for kernel {kernel}...')
    # Prepare toolchain and DKMS without changing the NVIDIA installation yet.
    run(['apt-get', 'update'])
    tools = ['build-essential', 'dkms', 'pciutils', 'libglvnd-dev']
    check_apt_install(tools)
    run(['apt-get', 'install', '-y', *tools])
    header_build = Path('/lib/modules') / kernel / 'build'
    if not (header_build / 'Makefile').exists():
        if kernel.endswith('-pve'):
            candidates = (f'proxmox-headers-{kernel}', f'pve-headers-{kernel}')
        else:
            candidates = (f'linux-headers-{kernel}',)
        for package in candidates:
            r = run(['apt-cache', 'show', package], capture=True, check=False)
            if r.returncode == 0 and 'Package:' in r.stdout:
                check_apt_install([package])
                run(['apt-get', 'install', '-y', package])
                break
        if not (header_build / 'Makefile').exists():
            die(f'Matching headers not found for {kernel}. Install them before upgrading.')
    # MOK enrollment or a disabled Secure Boot is necessary for unsigned runfile modules.
    if shutil.which('mokutil'):
        sb = run(['mokutil', '--sb-state'], capture=True, check=False)
        if sb.returncode == 0 and 'SecureBoot enabled' in sb.stdout:
            die('Secure Boot is enabled. Runfile DKMS modules need signing/MOK enrollment; '
                'disable Secure Boot or configure module signing before rerunning.')
    for pci, bind, gpu_id in gpu_devices():
        if bind not in ('none', 'nvidia', 'nouveau'):
            die(f'NVIDIA GPU {pci} is bound to {bind}, not available to the host driver.')


def dpkg_packages():
    r = run(['dpkg-query', '-W', '-f=${binary:Package}\t${Status}\n'], capture=True)
    found = []
    for line in r.stdout.splitlines():
        if '\t' not in line:
            continue
        name, status = line.split('\t', 1)
        if status.strip() in ('install ok installed', 'deinstall ok config-files'):
            found.append(name)
    return found


def is_nvidia_package(name):
    simple = name.split(':', 1)[0]
    if simple in ('cuda', 'nvidia') or simple.startswith(('cuda-', 'nvidia-')):
        return True
    return any(simple.startswith(prefix) for prefix in PACKAGE_PREFIXES
               if prefix not in ('cuda', 'nvidia'))


def check_apt_install(packages):
    simulation = run(['apt-get', '-s', 'install', *packages], capture=True)
    removals = [line.split()[1] for line in simulation.stdout.splitlines()
                if line.startswith(('Remv ', 'Purg '))]
    if removals:
        die('Prerequisite installation would remove installed packages: ' +
            ', '.join(removals))


def purge_apt():
    packages = sorted(p for p in dpkg_packages() if is_nvidia_package(p))
    if not packages:
        return
    print(f'Checking {len(packages)} installed NVIDIA/CUDA APT packages.')
    # Never let APT cascade into an unrelated application or a Proxmox package.
    # Retain shared user-space support libraries only if removal would cause this.
    while packages:
        result = run(['apt-get', '-s', 'purge', *packages], capture=True)
        planned = [line.split()[1] for line in result.stdout.splitlines()
                   if line.startswith(('Remv ', 'Purg '))]
        if not planned:
            die('APT purge simulation did not identify packages to remove.')
        if any(p.split(':', 1)[0].startswith(PROTECTED_PREFIXES) for p in planned):
            die('APT purge simulation included protected system packages.')
        unexpected = [p for p in planned if not is_nvidia_package(p)]
        if unexpected:
            shared = [p for p in packages if p.split(':', 1)[0] in SHARED_APT_LIBRARIES]
            if shared:
                print('Preserving shared package(s) ' + ', '.join(shared) +
                      ' to avoid removing ' + ', '.join(unexpected))
                packages = [p for p in packages if p not in shared]
                continue  # Re-simulate with fewer removals.
            die('APT wants to remove unrelated packages: ' + ', '.join(unexpected))
        print(f'Purging {len(packages)} NVIDIA/CUDA APT packages.')
        run(['apt-get', '-y', 'purge', *packages])
        return


def unload_modules():
    # Shut down only persistence services; never kill arbitrary GPU users.
    if shutil.which('systemctl'):
        for name in ('nvidia-persistenced', 'nvidia-powerd'):
            run(['systemctl', 'stop', name], check=False, capture=True)
    nodes = [str(p) for p in Path('/dev').glob('nvidia*') if p.exists()]
    if nodes and shutil.which('fuser'):
        busy = run(['fuser', *nodes], check=False, capture=True)
        if busy.returncode == 0:
            die('NVIDIA devices are still held open by processes: ' + busy.stdout.strip())
    for name in ('nvidia_peermem', 'nvidia_uvm', 'nvidia_drm',
                 'nvidia_modeset', 'nvidia'):
        run(['modprobe', '-r', name], check=False, capture=True)
    loaded = Path('/proc/modules').read_text() if Path('/proc/modules').exists() else ''
    if re.search(r'^nvidia(?:_\w+)?\s', loaded, re.M):
        die('NVIDIA kernel modules remain loaded. Stop GPU/desktop/container workloads '
            'and retry from an SSH/maintenance session.')


def remove_runfiles(driver_file):
    for root in sorted(CUDA_DIR.glob('cuda-*')):
        if not root.is_dir() or not re.fullmatch(r'cuda-\d+\.\d+(?:\.\d+)?', root.name):
            continue
        tool = root / 'bin/cuda-uninstaller'
        if tool.is_file():
            print(f'Uninstalling old CUDA Toolkit: {root}')
            # The standalone uninstaller supports noninteractive silent mode.
            run([tool, '--silent'], heartbeat=True)
    tool = shutil.which('nvidia-uninstall')
    if not tool and Path('/usr/bin/nvidia-installer').is_file():
        tool = '/usr/bin/nvidia-installer'
    if tool:
        print('Uninstalling NVIDIA runfile driver...')
        cmd = [tool, '--silent', '--no-questions']
        if Path(tool).name == 'nvidia-installer':
            cmd.append('--uninstall')
        run(cmd, heartbeat=True)
    elif shutil.which('modinfo') and run(
            ['modinfo', '-F', 'version', 'nvidia'], capture=True, check=False).returncode == 0:
        # Some incomplete runfile installations have no nvidia-uninstall in PATH.
        # Only try the runfile uninstall fallback if no APT driver packages own it.
        driver_packages = [p for p in dpkg_packages() if p.startswith(
            ('nvidia-', 'libnvidia', 'libcuda', 'firmware-nvidia'))]
        if not driver_packages:
            print('Missing nvidia-uninstall; trying the downloaded NVIDIA runfile uninstaller...')
            run(['sh', driver_file, '--uninstall', '--silent', '--no-questions'],
                heartbeat=True)


def dpkg_owns(path):
    return run(['dpkg-query', '-S', path], capture=True, check=False).returncode == 0


def has_package_files_under(root):
    # Read dpkg manifests once rather than spawning dpkg-query for every CUDA file.
    directory = os.fsencode(str(root)).rstrip(b'/')
    prefix = directory + b'/'
    for manifest in Path('/var/lib/dpkg/info').glob('*.list'):
        try:
            with manifest.open('rb') as f:
                for line in f:
                    item = line.rstrip(b'\r\n')
                    if item == directory or item.startswith(prefix):
                        return True
        except OSError as exc:
            die(f'Cannot inspect package ownership manifest {manifest}: {exc}')
    return False


def backup_move(path, backup):
    # Only stale, package-unowned files under known installer paths.
    if dpkg_owns(str(path)):
        print(f'Keeping package-owned file: {path}')
        return False
    target = backup / path.relative_to('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        die(f'Backup target already exists: {target}')
    print(f'Moving leftover {path} -> {target}')
    shutil.move(str(path), str(target))
    return True


def cleanup_leftovers():
    backup = BACKUP_ROOT / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    for root in sorted(CUDA_DIR.glob('cuda-*')):
        if root.is_symlink() or not root.is_dir():
            continue
        if re.fullmatch(r'cuda-\d+\.\d+(?:\.\d+)?', root.name):
            # Check dpkg file manifests before moving the directory.
            if has_package_files_under(root):
                die(f'Package-owned files remain under {root}; refusing manual cleanup.')
            backup_move(root, backup)
    link = CUDA_DIR / 'cuda'
    if link.is_symlink() and re.fullmatch(r'cuda-\d+\.\d+(?:\.\d+)?',
                                           Path(os.readlink(link)).name):
        if dpkg_owns(str(link)):
            die(f'Cannot remove package-owned CUDA symlink: {link}')
        link.unlink()
    for link in CUDA_DIR.glob('cuda-[0-9]*'):
        if link.is_symlink() and not dpkg_owns(str(link)):
            link.unlink()
    for directory in (Path('/usr/lib64/pkgconfig'), Path('/usr/lib/pkgconfig'),
                      Path('/usr/lib/x86_64-linux-gnu/pkgconfig')):
        if not directory.exists():
            continue
        for file in directory.glob('*.pc'):
            if any(file.name.startswith(p + '-') or file.name == p + '.pc'
                   for p in PC_PREFIXES):
                backup_move(file, backup)
    if backup.exists():
        print(f'Old unowned files saved under {backup}')


def disable_nouveau():
    conf = Path('/etc/modprobe.d/blacklist-nouveau-cuda-installer.conf')
    content = 'blacklist nouveau\noptions nouveau modeset=0\n'
    if not conf.exists() or conf.read_text() != content:
        conf.write_text(content)
        run(['update-initramfs', '-u', '-k', platform.uname().release])
    if re.search(r'^nouveau\s', Path('/proc/modules').read_text(), re.M):
        run(['modprobe', '-r', 'nouveau'], check=False, capture=True)
        if re.search(r'^nouveau\s', Path('/proc/modules').read_text(), re.M):
            die('Nouveau is still loaded. Reboot with nouveau blacklisted and rerun.')


def ensure_supported_gpu(driver_version, devices):
    # Refuse to replace a working driver with one that drops this GPU's PCI ID.
    supported = text_only(get(
        f'{DRIVER_ARCHIVE}{driver_version}/README/supportedchips.html'))
    for pci, bound, device_id in devices:
        if not re.search(r'\b' + re.escape(device_id) + r'\b', supported, re.I):
            die(f'GPU {pci} (10de:{device_id}) is not listed by NVIDIA driver '
                f'{driver_version}; refusing to remove the existing driver.')


def install(driver_file, cuda_file, cuda_version, driver_version):
    print(f'Installing NVIDIA driver {driver_version}...')
    run(['sh', driver_file, '--silent', '--no-questions', '--accept-license',
         '--dkms', '--disable-nouveau', '--install-libglvnd'], heartbeat=True)
    print(f'Installing CUDA Toolkit {cuda_version}...')
    run(['sh', cuda_file, '--silent', '--toolkit'], heartbeat=True)
    path = CUDA_DIR / f"cuda-{'.'.join(cuda_version.split('.')[:2])}"
    if not (path / 'bin/nvcc').exists():
        die(f'CUDA installer returned success but nvcc was not found: {path}/bin/nvcc')
    link = CUDA_DIR / 'cuda'
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        die('/usr/local/cuda exists and is not a symlink; cannot replace it.')
    link.symlink_to(path)
    profile = Path('/etc/profile.d/cuda.sh')
    profile.write_text('export PATH=/usr/local/cuda/bin:$PATH\n')
    ldconf = Path('/etc/ld.so.conf.d/cuda.conf')
    ldconf.write_text('/usr/local/cuda/lib64\n')
    run(['ldconfig'])


def verify(cuda_version, driver_version):
    run(['modprobe', 'nvidia'])
    run(['modprobe', 'nvidia_uvm'])
    print('\n=== Driver ===')
    smi = run(['nvidia-smi', '-L'], capture=True)
    if not re.search(r'^GPU \d+:.*NVIDIA|^GPU \d+:', smi.stdout, re.M):
        die('nvidia-smi cannot see an NVIDIA GPU.')
    print(smi.stdout.strip())
    installed = run(['modinfo', '-F', 'version', 'nvidia'], capture=True).stdout.strip()
    if installed != driver_version:
        die(f'Kernel module version mismatch: expected {driver_version}, got {installed}')
    # modinfo checks the module on disk, but an old module can still be loaded.
    loaded_version_file = Path('/proc/driver/nvidia/version')
    if not loaded_version_file.is_file():
        die('NVIDIA kernel module is not loaded.')
    loaded_version = loaded_version_file.read_text()
    if not re.search(r'(?<!\d)' + re.escape(driver_version) + r'(?!\d)', loaded_version):
        die(f'Loaded NVIDIA kernel module does not match installed driver {driver_version}; '
            'a reboot may be necessary.')
    print('Loaded driver:', driver_version)
    print('\n=== Toolkit ===')
    nvcc = run(['/usr/local/cuda/bin/nvcc', '--version'], capture=True).stdout
    if f'release {".".join(cuda_version.split(".")[:2])}' not in nvcc:
        die('CUDA nvcc reported an unexpected toolkit version.')
    print(nvcc.strip())
    if shutil.which('hashcat'):
        print('\n=== Hashcat devices ===')
        result = run(['hashcat', '-I'], capture=True, check=False)
        if result.returncode or not re.search(r'Backend Device ID #\d+|Device #\d+',
                                              result.stdout) or not re.search(
                                                  r'NVIDIA|GeForce|RTX|Tesla|Quadro',
                                                  result.stdout, re.I):
            print('WARNING: Hashcat did not report an NVIDIA device. '
                  'Review hashcat -I output and runtime libraries.')
        print((result.stdout or result.stderr or '').strip()[-2000:])
    print('\nInstallation completed successfully. Start a new shell to update PATH.')


def acquire_lock():
    lockfile = Path('/run/lock/cyclone-cuda-installer.lock')
    lockfile.parent.mkdir(parents=True, exist_ok=True)
    handle = lockfile.open('w')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        die('Another CUDA installer instance is already running.')
    return handle


def main():
    if len(sys.argv) != 1:
        die('This installer takes no command-line options. Run: sudo python3 install_cuda.py')
    print(' ------------------------------------------- ')
    print("|       Cyclone's Linux CUDA Installer      |")
    print('|                v2026-11-23                |')
    print('| https://github.com/cyclone-github/scripts |')
    print(' ------------------------------------------- \n')
    if os.geteuid() != 0:
        die('Run as root: sudo python3 install_cuda.py')
    lock_handle = acquire_lock()
    version = distro()
    print('Detected Architecture: x86_64')
    print(f'Detected Linux distro: Debian {version}')
    found = gpu_devices()
    if not found:
        die('No NVIDIA GPU detected in PCI sysfs.')
    print('Detected NVIDIA GPU PCI device(s): ' + ', '.join(
        f'{pci} (10de:{gpu_id})' for pci, _, gpu_id in found))
    print('\nChecking for existing CUDA / NVIDIA installation...')
    old_toolkits = [p.name for p in CUDA_DIR.glob('cuda-*') if p.is_dir()]
    print('Existing CUDA toolkit directories: ' + (', '.join(sorted(old_toolkits)) or 'none'))
    old = run(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
              capture=True, check=False) if shutil.which('nvidia-smi') else None
    print('Current NVIDIA driver: ' + (old.stdout.splitlines()[0] if old and
          old.returncode == 0 and old.stdout.strip() else 'not detected'))
    cuda_version, cuda_url, cuda_name, cuda_md5 = discover_cuda(version)
    driver_version, driver_url, driver_name, driver_sha256 = discover_driver(cuda_version)
    print(f'Latest CUDA Toolkit: {cuda_version}')
    print(f'Matching NVIDIA driver branch: {driver_version}')
    ensure_supported_gpu(driver_version, found)
    if input(f'Install CUDA {cuda_version} and NVIDIA driver {driver_version}? (y/n): ').strip().lower() not in ('y', 'yes'):
        print('Installation aborted by user.')
        return
    # Download and validate both installers *before* destructive cleanup.
    cuda_file = fetch_verified(cuda_url, cuda_name, cuda_md5, 'md5')
    driver_file = fetch_verified(driver_url, driver_name, driver_sha256, 'sha256')
    run(['sh', driver_file, '--check'])
    preflight()
    unload_modules()
    disable_nouveau()
    remove_runfiles(driver_file)
    purge_apt()
    cleanup_leftovers()
    install(driver_file, cuda_file, cuda_version, driver_version)
    verify(cuda_version, driver_version)


if __name__ == '__main__':
    logfiles = ('/var/log/cuda-installer.log', '/var/log/nvidia-installer.log')
    log_before = {}
    for logfile in logfiles:
        try:
            log_before[logfile] = Path(logfile).stat().st_mtime_ns
        except FileNotFoundError:
            log_before[logfile] = None
    try:
        main()
    except (RuntimeError, OSError, urllib.error.URLError, KeyboardInterrupt) as exc:
        print(f'\nError: {exc}', file=sys.stderr)
        for logfile in logfiles:
            path = Path(logfile)
            try:
                if path.stat().st_mtime_ns == log_before[logfile]:
                    continue  # The installer did not update this log on this run.
                lines = path.read_text(errors='replace').splitlines()
                print(f'\n=== {logfile} (last 12 lines) ===', file=sys.stderr)
                print('\n'.join(lines[-12:]), file=sys.stderr)
            except FileNotFoundError:
                continue
            except OSError:
                print(f'Check {logfile}', file=sys.stderr)
        sys.exit(1)