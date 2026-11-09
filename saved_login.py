"""Windows-user-bound OAuth renewal credential; never store a plaintext token."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
from typing import TypedDict, cast


class SavedLogin(TypedDict):
    id: str
    name: str
    refresh_token: str


def protect(value: bytes, *, decrypt: bool = False) -> bytes:
    if os.name != 'nt' or not 1 <= len(value) <= 8192:
        raise ValueError('Login salvo exige Windows e uma credencial válida.')

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    api = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = api.CryptUnprotectData if decrypt else api.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    storage = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    source, output = Blob(len(value), storage), Blob()
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError('O Windows não conseguiu proteger ou recuperar o login salvo.')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def validate(value: object) -> SavedLogin:
    if not isinstance(value, dict):
        raise ValueError('Login salvo inválido.')
    ident, name, refresh = value.get('id'), value.get('name'), value.get('refresh_token')
    if (not isinstance(ident, str) or not ident.isascii() or not ident.isdigit() or not 1 <= len(ident) <= 20
            or not 1 <= int(ident) <= 2**64 - 1 or not isinstance(name, str) or not 1 <= len(name) <= 48
            or not isinstance(refresh, str) or not 16 <= len(refresh) <= 2048
            or not refresh.isascii() or not refresh.isprintable()):
        raise ValueError('Login salvo inválido.')
    return cast(SavedLogin, {'id': ident, 'name': name, 'refresh_token': refresh})


def load(folder: Path) -> SavedLogin | None:
    path = folder / 'discord-login.dpapi'
    if not path.exists():
        return None
    if path.stat().st_size > 8192:
        raise ValueError('Arquivo de login salvo inválido.')
    return validate(json.loads(protect(path.read_bytes(), decrypt=True)))


def save(folder: Path, value: object) -> None:
    data = protect(json.dumps(validate(value), ensure_ascii=False).encode('utf-8'))
    folder.mkdir(parents=True, exist_ok=True)
    pending: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix='.discord-login-', suffix='.pending', delete=False) as stream:
            pending = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        pending.replace(folder / 'discord-login.dpapi')
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def forget(folder: Path) -> None:
    (folder / 'discord-login.dpapi').unlink(missing_ok=True)
