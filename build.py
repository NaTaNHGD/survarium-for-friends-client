"""Build a portable player executable; reject server code and private data."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'build-libs'))


def main() -> None:
    if not (ROOT / 'vps-server-ca.pem').is_file():
        raise ValueError('Restore the public certificate for this VPS deployment; never disable TLS verification')
    staging = ROOT / 'build/player-package'
    if not staging.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Invalid staging path')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
               '--name', 'SurvariumFriends', '--distpath', str(staging), '--paths', str(ROOT / 'vendor')]
    for name in ('animation_guard.js', 'movement_guard.js', 'vps-server-ca.pem'):
        command += ['--add-data', f'{ROOT / name};.']
    command += ['--collect-all', 'frida', str(ROOT / 'client_entry.py')]
    subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT / 'build-libs')), check=True)
    client = staging / 'SurvariumFriends'
    shutil.copy2(ROOT / 'LICENSE', client / 'LICENSE')
    shutil.copy2(ROOT / 'README.md', client / 'LEIA-ME.md')
    licenses = client / 'licenses'
    licenses.mkdir(exist_ok=True)
    for path in (ROOT / 'vendor').rglob('*'):
        if path.is_file() and any(word in path.name.lower() for word in ('copying', 'license', 'notice')):
            target = licenses / path.relative_to(ROOT / 'vendor')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        shutil.copy2(python_license, licenses / 'Python-LICENSE.txt')
    from PyInstaller.archive.readers import CArchiveReader
    contents = CArchiveReader(str(client / 'SurvariumFriends.exe')).open_embedded_archive('PYZ.pyz')
    if any(name in contents.toc for name in ('menu_server', 'dedicated_store', 'dedicated_service', 'vps_auth')):
        raise ValueError('Server implementation leaked into player executable')
    (ROOT / 'dist').mkdir(exist_ok=True)
    destination = ROOT / 'dist/SurvariumFriends-Cliente.zip'
    with ZipFile(destination, 'w', ZIP_DEFLATED) as package:
        for path in sorted(client.rglob('*')):
            if path.is_file():
                package.write(path, path.relative_to(client.parent))
    with ZipFile(destination) as package:
        if package.testzip() is not None or any(
                any(word in name.lower() for word in ('server-key', 'oauth-secret', 'dedicated-data', 'players.sqlite'))
                for name in package.namelist()):
            raise ValueError('Invalid or private player archive')
    print('Player-only ZIP verified:', destination)


if __name__ == '__main__':
    main()
