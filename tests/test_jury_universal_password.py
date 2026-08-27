"""Jury sign-in accepts either the judge's unique password or the shared
JURY_UNIVERSAL_PASSWORD. Pure unit test: collections and audit are mocked, so
this never touches MongoDB."""
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask
from werkzeug.security import generate_password_hash

import services.otp_service as svc

UID = 'abc123'
USER = {'_id': UID, 'email': 'judge@srhu.edu.in', 'name': 'Dr. Judge', 'role': 'JUDGE',
        'status': 'ACTIVE', 'password_hash': generate_password_hash('TF3-Unique99')}


class TestJuryUniversalPassword(unittest.TestCase):
    def _auth(self, password, shared):
        app = Flask(__name__)
        app.config['JURY_UNIVERSAL_PASSWORD'] = shared
        users = MagicMock(); users.find_one.return_value = dict(USER)
        judges = MagicMock(); judges.find_one.return_value = {'_id': 'j1', 'judge_type': 'INTERNAL_JUDGE'}
        audit = MagicMock()
        with app.app_context(), \
             patch.object(svc, 'get_users_collection', return_value=users), \
             patch.object(svc, 'get_judges_collection', return_value=judges), \
             patch.object(svc, 'log_audit', audit):
            res = svc.authenticate_jury_credentials(USER['email'], password, '127.0.0.1')
        return res, audit

    def test_unique_password_still_works(self):
        res, audit = self._auth('TF3-Unique99', 'Shared@1')
        self.assertTrue(res['success'])
        self.assertEqual(audit.call_args[0][4]['auth_method'], 'unique')

    def test_universal_password_accepted(self):
        res, audit = self._auth('Shared@1', 'Shared@1')
        self.assertTrue(res['success'])
        self.assertEqual(audit.call_args[0][4]['auth_method'], 'universal')

    def test_wrong_password_rejected(self):
        res, _ = self._auth('nope', 'Shared@1')
        self.assertFalse(res['success']); self.assertEqual(res['status_code'], 401)

    def test_disabled_when_unset(self):
        for shared in ('', '   ', None):
            res, _ = self._auth('', shared)  # empty submitted password
            self.assertFalse(res['success'])
            res, _ = self._auth('   ', shared)
            self.assertFalse(res['success'])

    def test_universal_not_leaked_to_staff_login(self):
        import inspect, routes.auth
        self.assertNotIn('JURY_UNIVERSAL_PASSWORD', inspect.getsource(routes.auth))


if __name__ == '__main__':
    unittest.main()
