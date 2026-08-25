"""
TechForge 3.0 — Comprehensive Jury OTP Authentication Test Suite
Covers all 18 official test cases for Internal & External Jury Authentication.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash

from app import create_app
from models.database import (
    get_users_collection,
    get_judges_collection,
    get_otp_sessions_collection,
    get_teams_collection,
    get_judge_assignments_collection
)
from services.otp_service import request_jury_otp, verify_jury_otp, find_authorized_judge
from seed_judges import seed_judges


class TestJuryOTPAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.app_context = cls.app.app_context()
        cls.app_context.push()
        cls.client = cls.app.test_client()

        # Seed the official 25 judges
        seed_judges()

    @classmethod
    def tearDownClass(cls):
        cls.app_context.pop()

    def setUp(self):
        self.users_col = get_users_collection()
        self.judges_col = get_judges_collection()
        self.otp_col = get_otp_sessions_collection()
        self.teams_col = get_teams_collection()
        self.assignments_col = get_judge_assignments_collection()

        self._clean_test_records()

    def tearDown(self):
        self._clean_test_records()

    def _clean_test_records(self):
        # Clean up transient test records
        self.users_col.delete_many({'email': {'$regex': 'test|industry\\.org|inactive_judge'}})
        self.judges_col.delete_many({'email': {'$regex': 'test|industry\\.org|inactive_judge'}})
        self.otp_col.delete_many({'email': {'$regex': 'test|industry\\.org|inactive_judge|srhu\\.edu\\.in'}})
        self.teams_col.delete_many({'team_name': {'$regex': 'Team Alpha Assigned|Team Beta Unassigned|Test Team'}})

    # --- TEST 1: Authorized Internal Judge ---
    def test_01_authorized_internal_judge_lookup_and_request(self):
        """Test 1: Authorized Internal Judge is found and OTP request succeeds"""
        email = "neelmani@srhu.edu.in"
        judge = find_authorized_judge(email)
        self.assertIsNotNone(judge)
        self.assertEqual(judge['role'], 'JUDGE')
        self.assertEqual(judge['judge_type'], 'INTERNAL_JUDGE')
        self.assertEqual(judge['panel_id'], 'PANEL_1')

        res = self.client.post('/api/auth/judge/request-otp', json={'email': email})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('masked_email', data)
        self.assertNotIn('otp', data)  # Never leak OTP

    # --- TEST 2: Mock SMTP called ---
    @patch('services.otp_service.send_otp_email')
    def test_02_otp_sent_via_smtp_service(self, mock_send_email):
        """Test 2: OTP email service is invoked with 6-digit numeric OTP"""
        mock_send_email.return_value = {'success': True}
        email = "deepaksrivastava@srhu.edu.in"

        res = self.client.post('/api/auth/judge/request-otp', json={'email': email})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(mock_send_email.called)

        # Check call arguments
        args, kwargs = mock_send_email.call_args
        self.assertEqual(args[0], email)
        otp = args[1]
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

    # --- TEST 3: Correct OTP Verification & Session Establishment ---
    def test_03_correct_otp_verification_creates_session(self):
        """Test 3: Correct OTP verification authenticates judge with role, judge_type, panel_id"""
        email = "neelmani@srhu.edu.in"
        # Seed an OTP session directly
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        otp_code = "482917"
        self.otp_col.insert_one({
            'email': email,
            'judge_id': 'test_judge_1',
            'user_id': 'test_user_1',
            'judge_name': 'Dr. Neel Mani',
            'judge_type': 'INTERNAL_JUDGE',
            'panel_id': 'PANEL_1',
            'otp_hash': generate_password_hash(otp_code),
            'attempts': 0,
            'used': False,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5)
        })

        client = self.app.test_client()
        res = client.post('/api/auth/judge/verify-otp', json={
            'email': email,
            'otp': otp_code
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['redirect_url'], '/judge/dashboard')

        # Check session in client
        with client.session_transaction() as sess:
            self.assertEqual(sess.get('role'), 'JUDGE')
            self.assertEqual(sess.get('judge_type'), 'INTERNAL_JUDGE')
            self.assertEqual(sess.get('panel_id'), 'PANEL_1')
            self.assertEqual(sess.get('email'), email)

    # --- TEST 4: Internal Jury Dashboard Rendering ---
    def test_04_internal_jury_dashboard_renders(self):
        """Test 4: Internal Jury Dashboard displays Panel 1 and Internal Jury badge"""
        email = "neelmani@srhu.edu.in"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        otp_code = "482917"
        self.otp_col.insert_one({
            'email': email,
            'judge_id': 'test_judge_1',
            'user_id': 'test_user_1',
            'judge_name': 'Dr. Neel Mani',
            'judge_type': 'INTERNAL_JUDGE',
            'panel_id': 'PANEL_1',
            'otp_hash': generate_password_hash(otp_code),
            'attempts': 0,
            'used': False,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5)
        })

        client = self.app.test_client()
        client.post('/api/auth/judge/verify-otp', json={'email': email, 'otp': otp_code})

        dash_res = client.get('/judge/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        content = dash_res.data.decode('utf-8')
        self.assertIn('Internal Jury Dashboard', content)
        self.assertIn('PANEL_1', content)

    # --- TEST 5: External Jury Authentication & Dashboard ---
    def test_05_external_jury_flow_and_dashboard(self):
        """Test 5: External Jury member authenticates and sees External Jury Dashboard"""
        ext_email = "external.jury.test@industry.org"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # Create external judge record
        user_id = self.users_col.insert_one({
            'name': 'Dr. Industry Expert',
            'email': ext_email,
            'role': 'judge',
            'status': 'active',
            'created_at': now
        }).inserted_id

        self.judges_col.insert_one({
            'name': 'Dr. Industry Expert',
            'email': ext_email,
            'user_id': str(user_id),
            'judge_type': 'EXTERNAL_JUDGE',
            'panel_id': 'PANEL_EXTERNAL',
            'status': 'active',
            'created_at': now
        })

        otp_code = "987654"
        self.otp_col.insert_one({
            'email': ext_email,
            'judge_id': str(user_id),
            'user_id': str(user_id),
            'judge_name': 'Dr. Industry Expert',
            'judge_type': 'EXTERNAL_JUDGE',
            'panel_id': 'PANEL_EXTERNAL',
            'otp_hash': generate_password_hash(otp_code),
            'attempts': 0,
            'used': False,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5)
        })

        client = self.app.test_client()
        res = client.post('/api/auth/judge/verify-otp', json={'email': ext_email, 'otp': otp_code})
        self.assertEqual(res.status_code, 200)

        dash_res = client.get('/judge/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        content = dash_res.data.decode('utf-8')
        self.assertIn('External Jury Dashboard', content)

    # --- TEST 6: Unauthorized Random Email ---
    def test_06_unauthorized_random_email_rejected(self):
        """Test 6: Non-registered email does not receive OTP (403 Forbidden)"""
        res = self.client.post('/api/auth/judge/request-otp', json={'email': 'random.person@gmail.com'})
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertIn('not authorized', data['message'])

        # Confirm no account was created
        self.assertIsNone(self.users_col.find_one({'email': 'random.person@gmail.com'}))

    # --- TEST 7: Unauthorized SRHU Email ---
    def test_07_unauthorized_srhu_email_rejected(self):
        """Test 7: SRHU email not in jury database does not receive OTP (403)"""
        res = self.client.post('/api/auth/judge/request-otp', json={'email': 'unregistered_staff@srhu.edu.in'})
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertFalse(data['success'])

    # --- TEST 8: Expired OTP Rejection ---
    def test_08_expired_otp_rejected(self):
        """Test 8: Expired OTP (>5 min) is rejected"""
        email = "vivekkatiyar@srhu.edu.in"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        otp_code = "123456"
        self.otp_col.insert_one({
            'email': email,
            'judge_id': 'test_judge',
            'user_id': 'test_user',
            'otp_hash': generate_password_hash(otp_code),
            'attempts': 0,
            'used': False,
            'created_at': now - timedelta(minutes=10),
            'expires_at': now - timedelta(minutes=5)  # Expired
        })

        res = self.client.post('/api/auth/judge/verify-otp', json={'email': email, 'otp': otp_code})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertIn('expired', data['message'].lower())

    # --- TEST 9: Wrong OTP Increments Attempt Counter ---
    def test_09_wrong_otp_increments_attempts(self):
        """Test 9: Invalid OTP increments attempt counter and returns error"""
        email = "shefalikhatri@srhu.edu.in"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.otp_col.insert_one({
            'email': email,
            'judge_id': 'test_judge',
            'user_id': 'test_user',
            'otp_hash': generate_password_hash('654321'),
            'attempts': 0,
            'used': False,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5)
        })

        res = self.client.post('/api/auth/judge/verify-otp', json={'email': email, 'otp': '000000'})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertIn('invalid', data['message'].lower())

        # Verify attempt counter in database
        doc = self.otp_col.find_one({'email': email, 'used': False})
        self.assertEqual(doc['attempts'], 1)

    # --- TEST 10: 5 Wrong Attempts Invalidate OTP ---
    def test_10_max_wrong_attempts_invalidates_otp(self):
        """Test 10: 5 incorrect attempts invalidate the OTP session"""
        email = "sanjaykumar@srhu.edu.in"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.otp_col.insert_one({
            'email': email,
            'judge_id': 'test_judge',
            'user_id': 'test_user',
            'otp_hash': generate_password_hash('654321'),
            'attempts': 4,
            'used': False,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5)
        })

        res = self.client.post('/api/auth/judge/verify-otp', json={'email': email, 'otp': '000000'})
        self.assertEqual(res.status_code, 429)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertIn('too many', data['message'].lower())

        # Verify session is invalidated
        doc = self.otp_col.find_one({'email': email})
        self.assertTrue(doc['used'])

    # --- TEST 11: OTP Single-Use Invalidation ---
    def test_11_otp_single_use(self):
        """Test 11: Verified OTP cannot be reused"""
        email = "lktyagi@srhu.edu.in"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        otp_code = "777888"
        self.otp_col.insert_one({
            'email': email,
            'judge_id': 'test_judge',
            'user_id': 'test_user',
            'judge_name': 'Dr. L.K. Tyagi',
            'judge_type': 'INTERNAL_JUDGE',
            'panel_id': 'PANEL_2',
            'otp_hash': generate_password_hash(otp_code),
            'attempts': 0,
            'used': False,
            'created_at': now,
            'expires_at': now + timedelta(minutes=5)
        })

        # 1st verification: Success
        res1 = self.client.post('/api/auth/judge/verify-otp', json={'email': email, 'otp': otp_code})
        self.assertEqual(res1.status_code, 200)

        # 2nd verification: Fail
        res2 = self.client.post('/api/auth/judge/verify-otp', json={'email': email, 'otp': otp_code})
        self.assertEqual(res2.status_code, 400)

    # --- TEST 12: New OTP Invalidates Prior OTP ---
    def test_12_new_otp_invalidates_prior_otp(self):
        """Test 12: Requesting a second OTP invalidates the first OTP"""
        email = "sumanpant@srhu.edu.in"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # Old OTP
        self.otp_col.insert_one({
            'email': email,
            'judge_id': 'test_judge',
            'user_id': 'test_user',
            'otp_hash': generate_password_hash('111111'),
            'attempts': 0,
            'used': False,
            'created_at': now - timedelta(seconds=40),
            'expires_at': now + timedelta(minutes=5)
        })

        # Request new OTP via service
        with patch('services.otp_service.send_otp_email') as mock_send:
            mock_send.return_value = {'success': True}
            res = self.client.post('/api/auth/judge/request-otp', json={'email': email})
            self.assertEqual(res.status_code, 200)

        # Attempt with OLD OTP -> must fail
        res_old = self.client.post('/api/auth/judge/verify-otp', json={'email': email, 'otp': '111111'})
        self.assertEqual(res_old.status_code, 400)

    # --- TEST 13: Inactive Judge Rejection ---
    def test_13_inactive_judge_rejected(self):
        """Test 13: Inactive judge cannot request OTP"""
        inactive_email = "inactive_judge_test@srhu.edu.in"
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        user_id = self.users_col.insert_one({
            'name': 'Inactive Judge',
            'email': inactive_email,
            'role': 'judge',
            'status': 'inactive',
            'created_at': now
        }).inserted_id

        self.judges_col.insert_one({
            'name': 'Inactive Judge',
            'email': inactive_email,
            'user_id': str(user_id),
            'judge_type': 'INTERNAL_JUDGE',
            'status': 'inactive',
            'created_at': now
        })

        res = self.client.post('/api/auth/judge/request-otp', json={'email': inactive_email})
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertIn('inactive', data['message'].lower())

    # --- TEST 14: Judge Cannot Access Admin Portal ---
    def test_14_judge_cannot_access_admin_portal(self):
        """Test 14: Judge receives 403 Forbidden on /admin/*"""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 'judge_123'
            sess['role'] = 'JUDGE'
            sess['email'] = 'neelmani@srhu.edu.in'

        res = client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 403)

    # --- TEST 15: Judge Cannot Access Super Admin Portal ---
    def test_15_judge_cannot_access_super_admin_portal(self):
        """Test 15: Judge receives 403 Forbidden on /super-admin/*"""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 'judge_123'
            sess['role'] = 'JUDGE'
            sess['email'] = 'neelmani@srhu.edu.in'

        res = client.get('/super-admin/dashboard')
        self.assertEqual(res.status_code, 403)

    # --- TEST 16: Judge Can Access Only Assigned Team (403 for unassigned) ---
    def test_16_team_assignment_authorization_guard(self):
        """Test 16: Accessing unassigned team returns 403 Forbidden"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # Setup Judge
        judge_doc = self.judges_col.find_one({'email': 'neelmani@srhu.edu.in'})
        judge_id = str(judge_doc['_id'])
        user_id = judge_doc['user_id']

        # Setup Team A (assigned) and Team B (unassigned)
        team_a_id = str(self.teams_col.insert_one({
            'team_name': 'Team Alpha Assigned',
            'team_code': 'TF3-ALPHA01',
            'leader_name': 'Alice',
            'created_at': now
        }).inserted_id)

        team_b_id = str(self.teams_col.insert_one({
            'team_name': 'Team Beta Unassigned',
            'team_code': 'TF3-BETA02',
            'leader_name': 'Bob',
            'created_at': now
        }).inserted_id)

        # Assign only Team A
        self.assignments_col.delete_many({'judge_id': judge_id})
        self.assignments_col.insert_one({
            'judge_id': judge_id,
            'team_id': team_a_id,
            'created_at': now
        })

        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['role'] = 'JUDGE'
            sess['email'] = 'neelmani@srhu.edu.in'
            sess['judge_type'] = 'INTERNAL_JUDGE'

        # Team A -> 200 OK
        res_a = client.get(f'/judge/evaluate/{team_a_id}')
        self.assertEqual(res_a.status_code, 200)

        # Team B -> 403 Forbidden!
        res_b = client.get(f'/judge/evaluate/{team_b_id}')
        self.assertEqual(res_b.status_code, 403)

    # --- TEST 17: Logout ---
    def test_17_judge_logout_redirects(self):
        """Test 17: Judge logout clears session and redirects"""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 'judge_123'
            sess['role'] = 'JUDGE'

        res = client.post('/api/auth/logout')
        self.assertEqual(res.status_code, 200)

        # Dashboard access without session redirects to login
        dash_res = client.get('/judge/dashboard')
        self.assertEqual(dash_res.status_code, 302)

    # --- TEST 18: Logged-In Judge at /judge/login Redirects to Dashboard ---
    def test_18_already_logged_in_judge_redirects_to_dashboard(self):
        """Test 18: Active judge session visiting /judge/login redirects to dashboard"""
        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = 'judge_123'
            sess['role'] = 'JUDGE'

        res = client.get('/judge/login', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(res.location.endswith('/judge/dashboard'))


if __name__ == '__main__':
    unittest.main()
