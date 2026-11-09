import base64
import hashlib
from io import BytesIO
from pathlib import Path
import ssl
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit

from public_client import NoRedirect, api, callback_code, oauth_parameters
from urllib.request import Request
from vps_settings import CALLBACK_URI, DISCORD_CLIENT_ID, VPS_IP, client_tls


class PublicClientTests(unittest.TestCase):
    def test_http_errors_do_not_blame_every_failure_on_account_access(self) -> None:
        for status, expected in ((401, 'Sessão expirada'), (403, 'worker.log'),
                                 (429, 'Muitas tentativas'), (503, 'indisponível')):
            with self.subTest(status=status):
                body = BytesIO(b'private-upstream-detail')
                error = HTTPError('https://181.215.254.230:65443/oauth/exchange', status, 'Failure', {}, body)
                opener = Mock()
                opener.open.side_effect = error
                with patch('public_client.build_opener', return_value=opener):
                    with self.assertRaisesRegex(ValueError, expected) as caught:
                        api('/oauth/exchange', {'code': 'test', 'verifier': 'test'})
                self.assertNotIn('private-upstream-detail', str(caught.exception))
                self.assertTrue(body.closed)

    def test_public_api_never_redirects_credentials(self) -> None:
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(Request('https://181.215.254.230:65443/session'), None,
                                          302, 'Found', {}, 'http://untrusted.invalid/')

    def test_pkce_and_state_are_per_attempt_without_client_secret(self) -> None:
        state, verifier, url = oauth_parameters()
        fields = parse_qs(urlsplit(url).query)
        expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        self.assertEqual(fields['client_id'], [DISCORD_CLIENT_ID])
        self.assertEqual(fields['redirect_uri'], [CALLBACK_URI])
        self.assertEqual(fields['code_challenge'], [expected])
        self.assertNotIn('client_secret', fields)
        self.assertNotEqual(oauth_parameters()[0], state)
        query = {'state': state, 'code': 'once', 'iss': 'https://discord.com'}
        self.assertEqual(callback_code('/callback?' + urlencode(query), state), 'once')
        for changed in ({**query, 'state': 'wrong'}, {**query, 'iss': 'https://attacker.invalid'}):
            with self.assertRaises(ValueError):
                callback_code('/callback?' + urlencode(changed), state)

    def test_certificate_verification_is_mandatory(self) -> None:
        context = client_tls()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(VPS_IP, '181.215.254.230')

    def test_client_tree_has_no_server_or_private_key(self) -> None:
        root = Path(__file__).parent
        for name in ('menu_server.py', 'dedicated_store.py', 'server-key.pem', 'oauth-secret.dpapi'):
            self.assertFalse((root / name).exists())
