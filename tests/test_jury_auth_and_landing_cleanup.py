"""
TechForge 3.0 — Jury Authentication & Landing Page Cleanup Test Suite
Tests:
1. Landing page cleanup: Evaluation Matrix, 36H Timeline, Jury Panels, and FAQs are NOT visible.
2. Jury Login: Email + Password -> opens Jury Dashboard.
3. Jury Login rejection: Incorrect password rejected.
4. Jury logout and re-login.
"""

import unittest
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

from app import create_app
from models.database import (
    get_users_collection,
    get_judges_collection,
    get_teams_collection
)
from services.otp_service import authenticate_jury_credentials


class TestJuryAuthAndLandingCleanup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.app_context = cls.app.app_context()
        cls.app_context.push()
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.app_context.pop()

    def setUp(self):
        self.users_col = get_users_collection()
        self.judges_col = get_judges_collection()
        self.teams_col = get_teams_collection()
        self._clean()

    def tearDown(self):
        self._clean()

    def _clean(self):
        self.users_col.delete_many({'email': {'$regex': 'test_jury|new_judge|unauth'}})
        self.judges_col.delete_many({'email': {'$regex': 'test_jury|new_judge|unauth'}})

    # =========================================================================
    # TEST 1: Landing Page Cleanup Verification
    # =========================================================================
    def test_01_landing_page_cleanup(self):
        """
        TEST 1: Homepage does NOT render:
        - Evaluation Matrix
        - 36H Timeline / Evaluation Checkpoints
        - Jury Panels
        - FAQs
        """
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')

        # Check that removed sections and IDs are NOT in HTML
        self.assertNotIn('id="evaluation"', html)
        self.assertNotIn('id="schedule"', html)
        self.assertNotIn('id="panels"', html)
        self.assertNotIn('id="faq"', html)
        self.assertNotIn('Official Evaluation Matrix', html)
        self.assertNotIn('Evaluation Checkpoints', html)
        self.assertNotIn('Jury Panel Structure', html)
        self.assertNotIn('Frequently Asked Questions', html)

        # Check that essential branding & rules remain
        self.assertIn('TECHFORGE 3.0', html)
        self.assertIn('Life Ka Compass', html)
        self.assertIn('SIH 2026 Team Requirements', html)
        self.assertIn('Register Team', html)
        self.assertIn('Jury Login', html)

    # =========================================================================
    # TEST 5: Normal Jury Login (Email + Password)
    # =========================================================================
    def test_05_normal_jury_login_email_password(self):
        """
        TEST 5: Normal Jury Login uses Email + Password and redirects to Dashboard
        """
        email = "test_jury_login@example.com"
        password = "CorrectPassword123"
        name = "Dr. Login Test"

        # Create registered user
        user_id = str(self.users_col.insert_one({
            'name': name,
            'email': email,
            'password_hash': generate_password_hash(password),
            'role': 'judge',
            'status': 'active',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        }).inserted_id)

        self.judges_col.insert_one({
            'user_id': user_id,
            'name': name,
            'email': email,
            'judge_type': 'INTERNAL_JUDGE',
            'status': 'active',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        # Test POST /judge/login form
        res = self.client.post('/judge/login', data={
            'email': email,
            'password': password
        }, follow_redirects=False)

        self.assertEqual(res.status_code, 302)
        self.assertIn('/judge/dashboard', res.headers['Location'])

        # Test API POST /api/auth/judge/login
        api_res = self.client.post('/api/auth/judge/login', json={
            'email': email,
            'password': password
        })
        self.assertEqual(api_res.status_code, 200)
        api_data = api_res.get_json()
        self.assertTrue(api_data['success'])
        self.assertEqual(api_data['redirect_url'], '/judge/dashboard')

    # =========================================================================
    # TEST 6: Incorrect Password Rejection
    # =========================================================================
    def test_06_incorrect_password_rejected(self):
        """
        TEST 6: Login with incorrect password is rejected (401)
        """
        email = "test_jury_wrong_pwd@example.com"
        password = "RealPassword123"

        user_id = str(self.users_col.insert_one({
            'name': 'Prof. Test',
            'email': email,
            'password_hash': generate_password_hash(password),
            'role': 'judge',
            'status': 'active',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        }).inserted_id)

        self.judges_col.insert_one({
            'user_id': user_id,
            'name': 'Prof. Test',
            'email': email,
            'judge_type': 'INTERNAL_JUDGE',
            'status': 'active',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        # Try logging in with wrong password
        api_res = self.client.post('/api/auth/judge/login', json={
            'email': email,
            'password': 'WrongPassword999'
        })
        self.assertEqual(api_res.status_code, 401)
        api_data = api_res.get_json()
        self.assertFalse(api_data['success'])
        self.assertIn('Invalid email or password', api_data['message'])

    # =========================================================================
    # TEST 7: Logout and Re-Login
    # =========================================================================
    def test_07_jury_logout_and_relogin(self):
        """
        TEST 7: Logout clears session, and re-login succeeds
        """
        email = "test_jury_session@example.com"
        password = "MyPassword789"

        user_id = str(self.users_col.insert_one({
            'name': 'Dr. Session Test',
            'email': email,
            'password_hash': generate_password_hash(password),
            'role': 'judge',
            'status': 'active',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        }).inserted_id)

        self.judges_col.insert_one({
            'user_id': user_id,
            'name': 'Dr. Session Test',
            'email': email,
            'judge_type': 'INTERNAL_JUDGE',
            'status': 'active',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        # Login
        self.client.post('/judge/login', data={'email': email, 'password': password})

        # Logout
        logout_res = self.client.get('/auth/logout')
        self.assertEqual(logout_res.status_code, 302)

        # Re-login with credentials
        relogin_res = self.client.post('/judge/login', data={'email': email, 'password': password})
        self.assertEqual(relogin_res.status_code, 302)
        self.assertIn('/judge/dashboard', relogin_res.headers['Location'])


if __name__ == '__main__':
    unittest.main()
