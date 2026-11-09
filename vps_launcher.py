"""Player-only launcher for the fixed VPS; no hosting or administration controls."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, cast

from client_runtime import runtime_command, validate_client
from public_client import DiscordSession, LoginRejected, discord_login, join_ticket, renew_login
import saved_login
from vps_settings import VPS_IP

DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SurvariumForFriends'
DEFAULT_GAME = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Survarium\game')


def remember(session: DiscordSession) -> DiscordSession:
    if session.get('refresh_token'):
        saved_login.save(DATA, session)
    return session


def restore_login() -> DiscordSession | None:
    stored = saved_login.load(DATA)
    return remember(renew_login(stored['refresh_token'])) if stored else None


def admission(current: DiscordSession | None) -> tuple[DiscordSession, str]:
    session = current if current is not None else restore_login()
    if session is None:
        raise ValueError('Conecte o Discord primeiro.')
    try:
        name = join_ticket(session)
    except LoginRejected:
        restored = restore_login()
        if restored is None:
            raise
        session = restored
        name = join_ticket(session)
    return session, name


class PlayerLauncher:
    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.session: DiscordSession | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.busy = False
        self.has_saved = (DATA / 'discord-login.dpapi').is_file()
        self.results: queue.Queue[tuple[str, object, str]] = queue.Queue()
        self.folder = tk.StringVar(value=str(DEFAULT_GAME) if DEFAULT_GAME.is_dir() else '')
        self.identity = tk.StringVar(value='Conta salva neste PC' if self.has_saved else 'Conecte seu Discord')
        self.status = tk.StringVar(value='Conecte seu Discord e localize a instalação Steam.')
        window.title('Survarium for Friends')
        window.geometry('820x680')
        window.minsize(760, 660)
        window.configure(bg='#111815')
        style = ttk.Style(window)
        style.theme_use('clam')
        style.configure('TFrame', background='#111815')
        style.configure('Card.TFrame', background='#1d2822')
        style.configure('TLabel', background='#111815', foreground='#edf1e9', font=('Segoe UI', 11))
        style.configure('Title.TLabel', font=('Segoe UI Semibold', 32))
        style.configure('Note.TLabel', foreground='#aab9ad', font=('Segoe UI', 10))
        style.configure('Kicker.TLabel', foreground='#b9d47c', font=('Consolas', 10))
        style.configure('Card.TLabel', background='#1d2822', foreground='#edf1e9', font=('Segoe UI Semibold', 15))
        style.configure('CardNote.TLabel', background='#1d2822', foreground='#b8c5b9', font=('Segoe UI', 10))
        style.configure('CardKicker.TLabel', background='#1d2822', foreground='#b9d47c', font=('Consolas', 10))
        style.configure('TButton', background='#304137', foreground='#edf1e9', borderwidth=0,
                        padding=(18, 11), font=('Segoe UI Semibold', 10))
        style.map('TButton', background=[('disabled', '#253229'), ('active', '#415846')],
                  foreground=[('disabled', '#87978b')])
        style.configure('Connect.TButton', background='#c5df8a', foreground='#162116',
                        padding=(20, 17), font=('Segoe UI Semibold', 15))
        style.map('Connect.TButton', background=[('disabled', '#304137'), ('active', '#d9edaa')],
                  foreground=[('disabled', '#aab9ad'), ('active', '#162116')])
        body = ttk.Frame(window, padding=(36, 28))
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text='SURVARIUM / FOR FRIENDS', style='Kicker.TLabel').grid(row=0, sticky='w')
        ttk.Label(body, text='De volta à Zona.', style='Title.TLabel').grid(row=1, sticky='w', pady=(10, 4))
        ttk.Label(body, text='Seu equipamento. Sua conta. Um lugar para voltar.', style='Note.TLabel').grid(row=2, sticky='w', pady=(0, 24))
        identity = ttk.Frame(body, style='Card.TFrame', padding=20)
        identity.grid(row=3, sticky='ew')
        identity.columnconfigure(0, weight=1)
        ttk.Label(identity, text='01 / SUA CONTA', style='CardKicker.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(identity, textvariable=self.identity, style='Card.TLabel', wraplength=420).grid(row=1, column=0, sticky='w', pady=(8, 4))
        ttk.Label(identity, text='Login protegido e salvo neste usuário do Windows.', style='CardNote.TLabel').grid(row=2, column=0, sticky='w')
        self.discord_button = ttk.Button(identity, text='Conectar Discord', command=self.login)
        self.discord_button.grid(row=1, column=1, padx=(16, 0))
        self.forget_button = ttk.Button(identity, text='Esquecer conta', command=self.forget)
        self.forget_button.grid(row=2, column=1, padx=(16, 0), pady=(8, 0))
        game_card = ttk.Frame(body, style='Card.TFrame', padding=20)
        game_card.grid(row=4, sticky='ew', pady=(12, 18))
        game_card.columnconfigure(0, weight=1)
        ttk.Label(game_card, text='02 / INSTALAÇÃO STEAM', style='CardKicker.TLabel').grid(row=0, sticky='w')
        ttk.Label(game_card, textvariable=self.folder, style='CardNote.TLabel', wraplength=470).grid(row=1, sticky='w', pady=(10, 0))
        self.locate_button = ttk.Button(game_card, text='Localizar jogo', command=self.locate)
        self.locate_button.grid(row=1, column=1, padx=(16, 0))
        self.connect_button = ttk.Button(body, text='Conectar', style='Connect.TButton', command=self.connect, state='disabled')
        self.connect_button.grid(row=5, sticky='ew', pady=(0, 10))
        ttk.Label(body, textvariable=self.status, style='Note.TLabel', wraplength=720).grid(row=6, sticky='w')
        ttk.Label(body, text=f'VPS  {VPS_IP}     •     STEAM 0.69d0     •     LAUNCHER 0.2.0', style='Kicker.TLabel').grid(row=7, sticky='w', pady=(22, 0))
        try:
            path = DATA / 'settings.json'
            if path.exists():
                value = json.loads(path.read_text(encoding='utf-8'))
                if isinstance(value, dict) and isinstance(value.get('game'), str):
                    self.folder.set(value['game'])
        except (OSError, ValueError):
            self.status.set('Preferências indisponíveis. Localize o jogo novamente.')
        window.protocol('WM_DELETE_WINDOW', window.destroy)
        window.after(100, self.poll)
        if self.has_saved:
            window.after(200, self.restore)

    def buttons(self) -> None:
        self.discord_button.configure(state='disabled' if self.busy else 'normal')
        self.discord_button.configure(text='Trocar conta' if self.session is not None else 'Conectar Discord')
        self.forget_button.configure(state='normal' if self.has_saved and not self.busy else 'disabled')
        self.locate_button.configure(state='disabled' if self.busy else 'normal')
        playing = self.process is not None and self.process.poll() is None
        ready = not self.busy and not playing and (self.session is not None or self.has_saved) and bool(self.folder.get())
        self.connect_button.configure(state='normal' if ready else 'disabled')
        self.connect_button.configure(text='Jogo em execução' if playing else 'Conectar ao servidor')

    def work(self, action: str, callback: Callable[[], object]) -> None:
        if self.busy:
            return
        self.busy = True
        self.buttons()

        def run() -> None:
            try:
                self.results.put((action, callback(), ''))
            except Exception as exc:
                self.results.put((action, None, str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def login(self) -> None:
        self.status.set('Autorize o Discord no navegador. Não feche o launcher.')
        self.work('login', lambda: remember(discord_login()))

    def restore(self) -> None:
        self.status.set('Restaurando seu login salvo…')
        self.work('restore', restore_login)

    def forget(self) -> None:
        try:
            saved_login.forget(DATA)
        except OSError:
            messagebox.showerror('Login salvo', 'Não foi possível remover o login salvo neste PC.', parent=self.window)
            return
        self.has_saved = False
        self.session = None
        self.identity.set('Conecte seu Discord')
        self.status.set('Conta esquecida neste PC. Seu progresso continua salvo na VPS.')
        self.buttons()

    def locate(self) -> None:
        selected = filedialog.askopenfilename(parent=self.window, title='Localize survarium.exe na pasta game/binaries/x64',
                                             filetypes=[('Survarium', 'survarium.exe')])
        if not selected:
            return
        try:
            executable = Path(selected).resolve()
            game = executable.parent.parent.parent
            if game / 'binaries/x64/survarium.exe' != executable:
                raise ValueError('Selecione game/binaries/x64/survarium.exe da versão Steam compatível')
            validate_client(executable)
            DATA.mkdir(parents=True, exist_ok=True)
            pending = DATA / 'settings.pending'
            pending.write_text(json.dumps({'game': str(game)}, ensure_ascii=False), encoding='utf-8')
            pending.replace(DATA / 'settings.json')
            self.folder.set(str(game))
            self.status.set('Jogo localizado. Conecte-se quando estiver pronto.')
        except (OSError, ValueError) as exc:
            messagebox.showerror('Não foi possível localizar o jogo', str(exc), parent=self.window)
        self.buttons()

    def connect(self) -> None:
        current, game = self.session.copy() if self.session else None, Path(self.folder.get())
        self.status.set('Confirmando acesso e abrindo o jogo…')

        def launch() -> object:
            validate_client(game / 'binaries/x64/survarium.exe')
            session, name = admission(current)
            folder = DATA / 'profiles' / session['id']
            folder.mkdir(parents=True, exist_ok=True)
            ticket = folder / 'admission.json'
            ticket.write_text(json.dumps({'join_name': name}), encoding='utf-8')
            command = runtime_command(game, '127.0.0.1', folder) + ['--public-session', str(ticket)]
            with (folder / 'startup.log').open('wb') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                return process, session
        self.work('connect', launch)

    def poll(self) -> None:
        try:
            action, result, error = self.results.get_nowait()
            self.busy = False
            if error:
                if action in ('login', 'restore'):
                    self.session = None
                    self.identity.set('Discord desconectado')
                self.status.set(error)
                if action != 'restore':
                    messagebox.showerror('Conexão indisponível', error, parent=self.window)
            elif action in ('login', 'restore') and result is not None:
                self.session = cast(DiscordSession, result)
                self.has_saved = (DATA / 'discord-login.dpapi').is_file()
                self.identity.set(f"Discord: {self.session['name']}")
                self.status.set('Login restaurado. Tudo pronto para conectar.' if action == 'restore' else
                                'Discord conectado. Login salvo neste PC.' if self.has_saved else
                                'Discord conectado. Atualize o servidor para habilitar login salvo.')
            elif action == 'connect':
                self.process, self.session = cast(tuple[subprocess.Popen[bytes], DiscordSession], result)
                self.identity.set(f"Discord: {self.session['name']}")
                self.status.set('Jogo aberto. Seu inventário e saldo são salvos na VPS.')
        except queue.Empty:
            pass
        if self.process is not None and self.process.poll() is not None:
            self.process = None
            self.status.set('Jogo encerrado. Você pode conectar novamente.')
        self.buttons()
        self.window.after(250, self.poll)


def main() -> None:
    window = tk.Tk()
    PlayerLauncher(window)
    window.mainloop()
