import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from public_client import DiscordSession, LoginRejected
import saved_login
import vps_launcher


class SavedLoginTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_real_dpapi_roundtrip_rotation_and_forget_preserve_game_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            value = {'id': '123', 'name': 'Player', 'refresh_token': 'R' * 40}
            settings = folder / 'settings.json'
            settings.write_text('{"game":"example"}')
            saved_login.save(folder, value)
            self.assertNotIn(value['refresh_token'].encode(), (folder / 'discord-login.dpapi').read_bytes())
            self.assertEqual(saved_login.load(folder), value)
            rotated = {**value, 'refresh_token': 'N' * 40}
            saved_login.save(folder, rotated)
            self.assertEqual(saved_login.load(folder), rotated)
            self.assertEqual(list(folder.glob('.discord-login-*.pending')), [])
            saved_login.forget(folder)
            self.assertIsNone(saved_login.load(folder))
            self.assertTrue(settings.exists())

    def test_unavailable_vps_does_not_discard_saved_credential(self) -> None:
        old = {'id': '123', 'name': 'Player', 'refresh_token': 'R' * 40}
        with patch('vps_launcher.saved_login.load', return_value=old), \
                patch('vps_launcher.renew_login', side_effect=OSError('offline')), \
                patch('vps_launcher.saved_login.forget') as forget:
            with self.assertRaises(OSError):
                vps_launcher.restore_login()
            forget.assert_not_called()

    def test_expired_session_renews_and_saves_before_requesting_new_admission(self) -> None:
        old: DiscordSession = {'session': 'S' * 40, 'id': '123', 'name': 'Player'}
        new: DiscordSession = {**old, 'session': 'N' * 40, 'refresh_token': 'R' * 40}
        order: list[str] = []
        def ticket(session: DiscordSession) -> str:
            order.append('ticket')
            if session['session'] == old['session']:
                raise LoginRejected('expired')
            return 'J' + '1' * 32
        with patch('vps_launcher.join_ticket', side_effect=ticket), \
                patch('vps_launcher.saved_login.load', return_value=new), \
                patch('vps_launcher.renew_login', return_value=new), \
                patch('vps_launcher.saved_login.save', side_effect=lambda *_: order.append('saved')):
            session, name = vps_launcher.admission(old)
        self.assertEqual(session, new)
        self.assertEqual(name, 'J' + '1' * 32)
        self.assertEqual(order, ['ticket', 'saved', 'ticket'])

    def test_invalid_credentials_are_rejected_without_echoing_them(self) -> None:
        for value in (None, {}, {'id': '0', 'name': 'Player', 'refresh_token': 'R' * 40},
                      {'id': '123', 'name': 'Player', 'refresh_token': '\n' * 40}):
            with self.assertRaisesRegex(ValueError, 'Login salvo inválido'):
                saved_login.validate(value)
