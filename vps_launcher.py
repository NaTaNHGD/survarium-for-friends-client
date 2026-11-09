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
from public_client import DiscordSession, discord_login, join_ticket
from vps_settings import VPS_IP

DATA = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'SurvariumForFriends'
DEFAULT_GAME = Path(r'C:\Program Files (x86)\Steam\steamapps\common\Survarium\game')


class PlayerLauncher:
    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.session: DiscordSession | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.busy = False
        self.results: queue.Queue[tuple[str, object, str]] = queue.Queue()
        self.folder = tk.StringVar(value=str(DEFAULT_GAME) if DEFAULT_GAME.is_dir() else '')
        self.identity = tk.StringVar(value='Discord desconectado')
        self.status = tk.StringVar(value='Conecte seu Discord e localize a instalação Steam.')
        window.title('Survarium for Friends')
        window.geometry('680x520')
        window.minsize(620, 500)
        window.configure(bg='#252b29')
        style = ttk.Style(window)
        style.theme_use('clam')
        style.configure('TFrame', background='#252b29')
        style.configure('TLabel', background='#252b29', foreground='#edf0e5', font=('Segoe UI', 11))
        style.configure('Title.TLabel', font=('Segoe UI Semibold', 27))
        style.configure('Note.TLabel', foreground='#bfc8bc', font=('Segoe UI', 10))
        style.configure('TButton', padding=(16, 11), font=('Segoe UI Semibold', 11))
        style.configure('Connect.TButton', background='#c5ceab', foreground='#202820')
        body = ttk.Frame(window, padding=30)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text='Survarium for Friends', style='Title.TLabel').grid(row=0, sticky='w')
        ttk.Label(body, text=f'Servidor  {VPS_IP}', style='Note.TLabel').grid(row=1, sticky='w', pady=(5, 24))
        identity = ttk.Frame(body)
        identity.grid(row=2, sticky='ew')
        identity.columnconfigure(0, weight=1)
        ttk.Label(identity, textvariable=self.identity).grid(row=0, column=0, sticky='w')
        self.discord_button = ttk.Button(identity, text='Conectar Discord', command=self.login)
        self.discord_button.grid(row=0, column=1, padx=(12, 0))
        ttk.Separator(body).grid(row=3, sticky='ew', pady=22)
        ttk.Label(body, text='Sua instalação do jogo').grid(row=4, sticky='w')
        ttk.Label(body, textvariable=self.folder, style='Note.TLabel', wraplength=560).grid(row=5, sticky='w', pady=(5, 10))
        self.locate_button = ttk.Button(body, text='Localizar jogo', command=self.locate)
        self.locate_button.grid(row=6, sticky='w')
        self.connect_button = ttk.Button(body, text='Conectar', style='Connect.TButton', command=self.connect, state='disabled')
        self.connect_button.grid(row=7, sticky='ew', pady=(24, 8))
        ttk.Label(body, textvariable=self.status, wraplength=580).grid(row=8, sticky='w', pady=(5, 0))
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

    def buttons(self) -> None:
        self.discord_button.configure(state='disabled' if self.busy else 'normal')
        self.locate_button.configure(state='disabled' if self.busy else 'normal')
        playing = self.process is not None and self.process.poll() is None
        ready = not self.busy and not playing and self.session is not None and bool(self.folder.get())
        self.connect_button.configure(state='normal' if ready else 'disabled')

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
        self.work('login', discord_login)

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
        if self.session is None:
            return
        session, game = self.session.copy(), Path(self.folder.get())
        self.status.set('Confirmando acesso e abrindo o jogo…')

        def launch() -> object:
            validate_client(game / 'binaries/x64/survarium.exe')
            name = join_ticket(session)
            folder = DATA / 'profiles' / session['id']
            folder.mkdir(parents=True, exist_ok=True)
            ticket = folder / 'admission.json'
            ticket.write_text(json.dumps({'join_name': name}), encoding='utf-8')
            command = runtime_command(game, '127.0.0.1', folder) + ['--public-session', str(ticket)]
            with (folder / 'startup.log').open('wb') as log:
                return subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.work('connect', launch)

    def poll(self) -> None:
        try:
            action, result, error = self.results.get_nowait()
            self.busy = False
            if error:
                if action == 'login':
                    self.session = None
                    self.identity.set('Discord desconectado')
                self.status.set('Não foi possível conectar. Confira o acesso e tente novamente.')
                messagebox.showerror('Conexão indisponível', error, parent=self.window)
            elif action == 'login':
                self.session = cast(DiscordSession, result)
                self.identity.set(f"Discord: {self.session['name']}")
                self.status.set('Discord conectado. Sua conta será carregada na VPS.')
            else:
                self.process = cast(subprocess.Popen[bytes], result)
                self.status.set('Jogo aberto. Seu inventário e saldo são salvos na VPS.')
        except queue.Empty:
            pass
        self.buttons()
        self.window.after(250, self.poll)


def main() -> None:
    window = tk.Tk()
    PlayerLauncher(window)
    window.mainloop()
