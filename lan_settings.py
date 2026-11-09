"""Addresses and launch arguments for the independent two-seat menu preview."""
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path

LAN_NETWORKS = tuple(IPv4Network(value) for value in (
    '127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def lan_address(value: str) -> str:
    address = IPv4Address(value)
    if not any(address in network for network in LAN_NETWORKS):
        raise ValueError('Use an IPv4 address from your private LAN or loopback')
    return str(address)


def game_command(game: Path, host: str, data: Path) -> list[str]:
    host = lan_address(host)
    executable = game.resolve() / 'binaries/x64/survarium.exe'
    if not executable.is_file():
        raise ValueError('Select the game folder containing binaries/x64/survarium.exe')
    return [str(executable), f'-server={host}:65001', '-product_name=Survarium-Steam',
            '-localization=english', '-silent_login_client=1',
            '-account_name=Local', '-account_password=local',
            f'-user_data_folder={data.resolve()}']
