"""Deployment identity shared by the player launcher and the VPS."""
from pathlib import Path
import ssl

VPS_IP = '181.215.254.230'
DISCORD_CLIENT_ID = '1522343360004882492'
CALLBACK_URI = 'http://127.0.0.1:65110/callback'
PUBLIC_API_PORT = 65443
NATIVE_TLS_PORT = 65001
ROOT = Path(__file__).resolve().parent


def client_tls() -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=str(ROOT / 'vps-server-ca.pem'))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context

