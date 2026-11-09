"""Browser OAuth and a loopback-to-TLS bridge; no server code or OAuth secret."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import secrets
import socket
import threading
import time
from typing import TypedDict, cast
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener
import webbrowser

from vps_settings import CALLBACK_URI, DISCORD_CLIENT_ID, NATIVE_TLS_PORT, PUBLIC_API_PORT, VPS_IP, client_tls


class DiscordSession(TypedDict):
    session: str
    id: str
    name: str


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: object, code: int, msg: str, headers: object, newurl: str) -> None:
        raise ValueError('O servidor respondeu com um redirecionamento inesperado')


def api(path: str, payload: dict[str, str] | None = None, token: str = '') -> dict[str, object]:
    if path not in ('/health', '/oauth/exchange', '/session'):
        raise ValueError('Invalid public API path')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = Request(f'https://{VPS_IP}:{PUBLIC_API_PORT}{path}',
                      data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    try:
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=client_tls()), NoRedirect())
        with opener.open(request, timeout=20) as response:
            body = response.read(16385)
            if len(body) > 16384:
                raise ValueError('Resposta excessiva da VPS')
            value = json.loads(body)
    except HTTPError as exc:
        messages = {
            401: 'Sessão expirada. Conecte o Discord novamente.',
            403: 'A VPS recusou o login. Confira OAuth e acesso da conta; consulte dedicated-data/worker.log no servidor.',
            429: 'Muitas tentativas. Aguarde um minuto e tente novamente.',
        }
        message = messages.get(exc.code, 'Serviço da VPS indisponível. Confira o servidor e tente novamente.')
        exc.close()
        raise ValueError(message) from exc
    if not isinstance(value, dict):
        raise ValueError('Resposta inválida da VPS')
    return cast(dict[str, object], value)


def oauth_parameters() -> tuple[str, str, str]:
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    query = urlencode({'client_id': DISCORD_CLIENT_ID, 'response_type': 'code', 'scope': 'identify',
                       'redirect_uri': CALLBACK_URI, 'state': state, 'code_challenge': challenge,
                       'code_challenge_method': 'S256', 'prompt': 'consent'})
    return state, verifier, 'https://discord.com/oauth2/authorize?' + query


def callback_code(path: str, state: str) -> str:
    if len(path) > 4096:
        raise ValueError('Retorno OAuth inválido')
    value = urlsplit(path)
    fields = parse_qs(value.query, max_num_fields=12)
    if value.path != '/callback' or fields.get('iss') != ['https://discord.com']:
        raise ValueError('Retorno OAuth inválido')
    if fields.get('state') != [state] or not secrets.compare_digest(fields['state'][0], state):
        raise ValueError('Estado OAuth inválido')
    if 'error' in fields:
        raise ValueError('Autorização Discord cancelada')
    code = fields.get('code', [])
    if len(code) != 1 or not 1 <= len(code[0]) <= 2048:
        raise ValueError('Código OAuth inválido')
    return code[0]


def discord_login() -> DiscordSession:
    api('/health')
    state, verifier, url = oauth_parameters()
    result: list[str] = []
    cancelled: list[str] = []

    class Callback(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            try:
                if self.headers.get('Host') != '127.0.0.1:65110' or result:
                    raise ValueError('Retorno OAuth inválido')
                result.append(callback_code(self.path, state))
                text, status = 'Discord autorizado. Volte ao launcher.', 200
            except ValueError as exc:
                if 'error=' in self.path and 'state=' + state in self.path:
                    cancelled.append(str(exc))
                text, status = 'Retorno recusado. Volte ao launcher e tente novamente.', 400
            body = text.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    try:
        server = HTTPServer(('127.0.0.1', 65110), Callback)
    except OSError as exc:
        raise ValueError('A porta local do login está ocupada. Feche outro launcher e tente novamente.') from exc
    with server:
        server.timeout = 0.5
        if not webbrowser.open(url):
            raise ValueError('Não foi possível abrir o navegador para conectar o Discord')
        deadline = time.monotonic() + 180
        while not result and not cancelled and time.monotonic() < deadline:
            server.handle_request()
    if not result:
        raise ValueError('Login cancelado ou expirado; conecte o Discord novamente')
    value = api('/oauth/exchange', {'code': result[0], 'verifier': verifier})
    if (not isinstance(value.get('session'), str) or not 20 <= len(value['session']) <= 100
            or not isinstance(value.get('id'), str) or re.fullmatch(r'[0-9]{1,20}', value['id']) is None
            or not isinstance(value.get('name'), str)):
        raise ValueError('Identidade Discord inválida')
    return cast(DiscordSession, value)


def join_ticket(session: DiscordSession) -> str:
    value = api('/session', {}, session['session'])
    name = value.get('join_name')
    if not isinstance(name, str) or re.fullmatch(r'J[0-9a-f]{32}', name) is None:
        raise ValueError('Admissão inválida da VPS')
    return name


class AuthBridge:
    def __init__(self) -> None:
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.listener.settimeout(30)
        self.port = self.listener.getsockname()[1]
        self.sockets: list[socket.socket] = []
        self.error = ''
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self) -> int:
        self.thread.start()
        return self.port

    def close(self) -> None:
        self.listener.close()
        for stream in self.sockets:
            try:
                stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            stream.close()

    @staticmethod
    def pump(source: socket.socket, target: socket.socket) -> None:
        try:
            while data := source.recv(65536):
                target.sendall(data)
        except OSError:
            pass
        finally:
            try:
                target.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    def run(self) -> None:
        try:
            local, _ = self.listener.accept()
            self.sockets.append(local)
            raw = socket.create_connection((VPS_IP, NATIVE_TLS_PORT), timeout=10)
            self.sockets.append(raw)
            remote = client_tls().wrap_socket(raw, server_hostname=VPS_IP)
            self.sockets.append(remote)
            remote.settimeout(30)
            outgoing = threading.Thread(target=self.pump, args=(local, remote), daemon=True)
            outgoing.start()
            self.pump(remote, local)
        except OSError:
            self.error = 'Falha na conexão TLS com a VPS; confira o certificado e as portas do servidor'
        finally:
            self.close()
