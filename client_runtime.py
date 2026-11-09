"""Launch our client with a bounded animation guard retained until process exit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import secrets
import re

from lan_settings import game_command

ROOT = Path(__file__).resolve().parent
CLIENT_SHA256 = '1e1ae04dc981fc4f5734c56559fb0f2e0e74c787bcc53ebbfdc233f440d65448'


def local_identity(data: Path) -> str:
    path = data / 'identity.json'
    try:
        with path.open('x', encoding='utf-8') as stream:
            json.dump({'name': 'F' + secrets.token_hex(12)}, stream)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        pass
    value = json.loads(path.read_text(encoding='utf-8'))
    name = value.get('name') if isinstance(value, dict) else None
    if not isinstance(name, str) or re.fullmatch(r'F[0-9a-f]{24}', name) is None:
        raise ValueError('Invalid local identity; restore identity.json instead of resetting player progress')
    return name


def runtime_command(game: Path, host: str, data: Path) -> list[str]:
    game_command(game, host, data)
    prefix = [sys.executable, '--runtime'] if getattr(sys, 'frozen', False) else [sys.executable, str(ROOT / 'client_runtime.py')]
    return [*prefix, '--game', str(game.resolve()),
            '--host', host, '--data', str(data.resolve())]


def validate_client(executable: Path) -> None:
    if hashlib.sha256(executable.read_bytes()).hexdigest() != CLIENT_SHA256:
        raise ValueError('Animation guard supports only the verified Steam 0.69d0 executable')


def main(game: Path, host: str, data: Path, public_session: Path | None = None) -> None:
    command = game_command(game, host, data)
    validate_client(Path(command[0]))
    data.mkdir(parents=True, exist_ok=True)
    if public_session is None:
        command = [('-account_name=' + local_identity(data)) if argument.startswith('-account_name=') else argument for argument in command]
    sys.path.insert(0, str(ROOT / 'vendor'))
    import frida
    device = frida.get_local_device()
    completed = threading.Event()
    process_terminated = threading.Event()
    ready = threading.Event()
    failures: list[str] = []
    guards: set[str] = set()
    pid: int | None = None
    session = None
    script = None
    bridge = None
    with (data.parent / 'client-runtime.log').open('w', encoding='utf-8', buffering=1) as log:
        lock = threading.Lock()

        def report(event: dict[str, object]) -> None:
            with lock:
                log.write(json.dumps({'time': time.time(), **event}) + '\n')

        def message(event: dict[str, object], _binary: bytes | None) -> None:
            if event.get('type') == 'send':
                payload = event.get('payload')
                if isinstance(payload, dict):
                    report(payload)
                    if payload.get('event') in ('animation_guard_ready', 'movement_guard_ready'):
                        guards.add(str(payload['event']))
                    if guards == {'animation_guard_ready', 'movement_guard_ready'}:
                        ready.set()
            elif event.get('type') == 'error':
                failures.append(str(event.get('description', 'Native guard failed')))
                report({'event': 'native_script_error', 'details': str(event.get('stack', failures[-1]))})
                ready.set()

        def detached(reason: str, _crash: object) -> None:
            if reason == 'process-terminated':
                process_terminated.set()
            report({'event': 'session_detached', 'reason': reason})
            completed.set()

        try:
            if public_session is not None:
                from public_client import AuthBridge
                value = json.loads(public_session.read_text())
                name = value.get('join_name')
                if not isinstance(name, str) or re.fullmatch(r'J[0-9a-f]{32}', name) is None:
                    raise ValueError('Invalid public admission')
                public_session.unlink()
                bridge = AuthBridge()
                port = bridge.start()
                command = [f'-server=127.0.0.1:{port}' if argument.startswith('-server=')
                           else '-account_name=' + name if argument.startswith('-account_name=') else argument for argument in command]
            (data.parent / 'client-session.json').write_text(json.dumps({'controller': os.getpid(), 'guard_ready': False}), encoding='utf-8')
            pid = device.spawn(command, cwd=str(Path(command[0]).parent))
            session = device.attach(pid)
            session.on('detached', detached)
            program = '\n'.join('{\n' + (ROOT / name).read_text(encoding='utf-8') + '\n}'
                                for name in ('animation_guard.js', 'movement_guard.js'))
            script = session.create_script(program)
            script.on('message', message)
            script.load()
            if not ready.wait(10) or failures or completed.is_set():
                raise RuntimeError('; '.join(failures) or 'Animation guard did not initialize')
            (data.parent / 'client-session.json').write_text(json.dumps({'controller': os.getpid(), 'client': pid, 'guard_ready': True, 'movement_ready': True}), encoding='utf-8')
            report({'event': 'client_resuming', 'pid': pid})
            device.resume(pid)
            completed.wait()
            report({'event': 'client_exited', 'pid': pid})
        finally:
            if bridge is not None:
                bridge.close()
                if bridge.error:
                    report({'event': 'public_connection_error', 'details': bridge.error})
            # A trampoline must never outlive its owner while the client still runs.
            if pid is not None and not process_terminated.is_set():
                try:
                    device.kill(pid)
                except frida.ProcessNotFoundError:
                    pass
            if session is not None and not session.is_detached:
                session.detach()
            script = None


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--public-session', type=Path)
    args = parser.parse_args()
    try:
        main(args.game, args.host, args.data, args.public_session)
    except Exception as exc:
        raise SystemExit(f'Client runtime failed: {exc}') from exc


if __name__ == '__main__':
    cli()
