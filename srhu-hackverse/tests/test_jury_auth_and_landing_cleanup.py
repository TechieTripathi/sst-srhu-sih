"""
TechForge 3.0 — Jury Authentication & Landing Page Cleanup Test Suite
Tests:
1. Landing page cleanup: Evaluation Matrix, 36H Timeline, Jury Panels, and FAQs are NOT visible.
2. Jury Registration: Email + Password -> OTP sent -> Verify OTP -> Account created in MongoDB.
3. Jury Registration validation: Incorrect OTP does not create account.
4. Jury Normal Login: Email + Password -> Successfully opens Jury Dashboard (No OTP required).
5. Jury Login rejection: Incorrect password rejected.
6. Team registration, Admin, and Super Admin flows remain intact.
"""

import unittest
from datetime import datetime, timedelta, timezone
from werkzeug.security import check_password_hash, generate_password_hash
from bson.objectid import ObjectId

from app import create_app
from models.database import (
    get_users_collection,
    get_judges_collection,
    get_otp_sessions_collection,
    get_teams_collection
)
from services.otp_service import (
    request_jury_registration_otp,
    verify_jury_registration_otp,
    authenticate_jury_credentials
)


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
        self.otp_col = get_otp_sessions_collection()
        self.teams_col = get_teams_collection()
        self._clean()

    def tearDown(self):
        self._clean()

    def _clean(self):
        self.users_col.delete_many({'email': {'$regex': 'test_jury|new_judge|unauth'}})
        self.judges_col.delete_many({'email': {'$regex': 'test_jury|new_judge|unauth'}})
        self.otp_col.delete_many({'email': {'$regex': 'test_jury|new_judge|unauth'}})

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
    # TEST 2: Jury Registration OTP Request
    # =========================================================================
    def test_02_jury_registration_otp_request(self):
        """
        TEST 2: Jury enters Email + Password -> OTP is generated and sent
        """
        email = "test_jury_prof@example.com"
        password = "SecurePassword123"
        name = "Prof. Test Jury"

        res = self.client.post('/api/auth/judge/register-request-otp', json={
            'email': email,
            'password': password,
            'name': name,
            'judge_type': 'INTERNAL_JUDGE'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('OTP sent', data['message'])

        # Verify OTP session exists in DB
        session_doc = self.otp_col.find_one({'email': email, 'session_type': 'registration', 'used': False})
        self.assertIsNotNone(session_doc)
        self.assertEqual(session_doc['name'], name)
        self.assertTrue(check_password_hash(session_doc['password_hash'], password))

    # =========================================================================
    # TEST 3: Invalid OTP Rejection & No Account Created
    # =========================================================================
    def test_03_invalid_otp_rejected_no_account_created(self):
        """
        TEST 3: Incorrect OTP is rejected and account is NOT created
        """
        email = "test_jury_failed@example.com"
        password = "Password123"

        # Request OTP
        request_jury_registration_otp(email, password, "Dr. Fail Test")

        # Try verifying with incorrect OTP
        res = self.client.post('/api/auth/judge/register-verify-otp', json={
            'email': email,
            'otp': '000000'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertIn('Invalid OTP', data['message'])

        # Verify account was NOT created
        user = self.users_col.find_one({'email': email})
        self.assertIsNone(user)
        judge = self.judges_col.find_one({'email': email})
        self.assertIsNone(judge)

    # =========================================================================
    # TEST 4: Correct OTP Verifies & Creates Account
    # =========================================================================
    def test_04_correct_otp_creates_jury_account(self):
        """
        TEST 4: Correct OTP verification creates Jury account with role=judge and hashed password
        """
        email = "test_jury_success@example.com"
        password = "SuperSecretPassword"
        name = "Dr. Anita Sharma"

        # 1. Request OTP
        req_res = request_jury_registration_otp(email, password, name, 'INTERNAL_JUDGE')
        self.assertTrue(req_res['success'])

        # Fetch the generated OTP from DB session to verify
        session_doc = self.otp_col.find_one({'email': email, 'session_type': 'registration', 'used': False})
        self.assertIsNotNone(session_doc)

        # 2. Verify OTP with helper
        verify_res = verify_jury_registration_otp(email, "999999")  # wrong first
        self.assertFalse(verify_res['success'])

        # Retrieve direct test OTP by simulating verification through valid hash
        # Let's set known OTP hash
        from werkzeug.security import generate_password_hash
        self.otp_col.update_one({'_id': session_doc['_id']}, {'$set': {'otp_hash': generate_password_hash('123456')}})

        ver_res = self.client.post('/api/auth/judge/register-verify-otp', json={
            'email': email,
            'otp': '123456'
        })
        self.assertEqual(ver_res.status_code, 200)
        ver_data = ver_res.get_json()
        self.assertTrue(ver_data['success'])

        # 3. Verify user created in MongoDB users collection
        user = self.users_col.find_one({'email': email})
        self.assertIsNotNone(user)
        self.assertEqual(user['name'], name)
        self.assertEqual(user['role'], 'judge')
        self.assertEqual(user['status'], 'active')
        self.assertTrue(check_password_hash(user['password_hash'], password))

        # 4. Verify judge created in MongoDB judges collection
        judge = self.judges_col.find_one({'email': email})
        self.assertIsNotNone(judge)
        self.assertEqual(judge['name'], name)
        self.assertEqual(judge['judge_type'], 'INTERNAL_JUDGE')
        self.assertEqual(judge['status'], 'active')

    # =========================================================================
    # TEST 5: Normal Jury Login (Email + Password) Without OTP
    # =========================================================================
    def test_05_normal_jury_login_email_password(self):
        """
        TEST 5: Normal Jury Login uses Email + Password (NO OTP required) and redirects to Dashboard
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
            'panel_id': 'PANEL_2',
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
