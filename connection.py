"""Stable local access key and terminal QR, independent of capture code."""
import os
import pathlib
import re
import secrets
import subprocess
import qrcode


def persistent_key(path):
    path = pathlib.Path(path)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = path.read_text().strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', key):
            raise RuntimeError(f'Некорректный ключ в {path}. Удалите этот файл, чтобы создать новую ссылку.')
        return key
    key = secrets.token_urlsafe(24)
    with os.fdopen(fd, 'w') as file:
        file.write(key + '\n')
    return key


def phone_addresses(port, key):
    addresses = []
    result = subprocess.run(['/usr/sbin/scutil', '--get', 'LocalHostName'], capture_output=True, text=True)
    name = result.stdout.strip()
    if result.returncode == 0 and re.fullmatch(r'[A-Za-z0-9-]+', name):
        addresses.append(('Постоянная ссылка iPhone', f'http://{name}.local:{port}/#{key}'))
    for interface in ('en0', 'en1'):
        result = subprocess.run(['/usr/sbin/ipconfig', 'getifaddr', interface], capture_output=True, text=True)
        address = result.stdout.strip()
        if result.returncode == 0 and address:
            item = ('Запасная ссылка по IP', f'http://{address}:{port}/#{key}')
            if item not in addresses:
                addresses.append(item)
    return addresses


def print_phone_qr(url, translate=lambda value: value):
    qr = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(url)
    qr.make(fit=True)
    print('\n' + translate('Наведите камеру iPhone на QR (оба устройства в одной Wi-Fi сети):'))
    qr.print_ascii(invert=True)
