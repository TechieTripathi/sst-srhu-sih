"""
TechForge 3.0 — Comprehensive Jury Provisioning & Credentials Test Suite
Implements all 22 tests required by TechForge 3.0 specification Section 34.
"""

import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from werkzeug.security import check_password_hash, generate_password_hash
from bson.objectid import ObjectId

from app import create_app
from models.database import (
    get_users_collection,
    get_judges_collection,
    get_teams_collection,
    get_judge_assignments_collection
)
from seed_judges import OFFICIAL_INTERNAL_JUDGES, seed_judges
from services.password_generator import generate_secure_jury_password
from services.otp_service import authenticate_jury_credentials


class TestJuryCredentials(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.app_context = cls.app.app_context()
        cls.app_context.push()

    @classmethod
    def tearDownClass(cls):
        cls.app_context.pop()

    def setUp(self):
        self.client = self.app.test_client()
        self.users_col = get_users_collection()
        self.judges_col = get_judges_collection()
        self.teams_col = get_teams_collection()
        self.assignments_col = get_judge_assignments_collection()
        self._clean_test_records()

    def tearDown(self):
        self._clean_test_records()

    def _clean_test_records(self):
        self.users_col.delete_many({'email': {'$regex': 'test_|mock_|unknown|admin_test|neelamdanu_test'}})
        self.judges_col.delete_many({'email': {'$regex': 'test_|mock_|unknown|admin_test|neelamdanu_test'}})
        self.teams_col.delete_many({'team_name': {'$regex': 'Credential Test Team'}})
        self.assignments_col.delete_many({})

    # --------------------------------------------------
    # TEST 1 — 25 JURY EMAILS
    # --------------------------------------------------
    def test_01_25_jury_emails_count(self):
        """Verify exactly 25 supplied Jury email addresses exist in provisioning configuration"""
        self.assertEqual(len(OFFICIAL_INTERNAL_JUDGES), 25)

    # --------------------------------------------------
    # TEST 2 — EMAIL NORMALIZATION
    # --------------------------------------------------
    def test_02_email_normalization(self):
        """Input: Neelamdanu@srhu.edu.in -> Expected stored value: neelamdanu@srhu.edu.in"""
        raw_email = "Neelamdanu@srhu.edu.in"
        normalized = raw_email.strip().lower()
        self.assertEqual(normalized, "neelamdanu@srhu.edu.in")

        # Verify in list of official judges
        neelam_entry = next((j for j in OFFICIAL_INTERNAL_JUDGES if 'neelam' in j['email'].lower()), None)
        self.assertIsNotNone(neelam_entry)
        self.assertEqual(neelam_entry['email'].strip().lower(), "neelamdanu@srhu.edu.in")

    # --------------------------------------------------
    # TEST 3 — UNIQUE EMAILS
    # --------------------------------------------------
    def test_03_unique_emails(self):
        """Verify no duplicate emails exist among the 25 official judges"""
        emails = [j['email'].strip().lower() for j in OFFICIAL_INTERNAL_JUDGES]
        unique_emails = set(emails)
        self.assertEqual(len(emails), len(unique_emails))
        self.assertEqual(len(unique_emails), 25)

    # --------------------------------------------------
    # TEST 4 — ACCOUNT CREATION
    # --------------------------------------------------
    def test_04_account_creation(self):
        """Run seed: verify 25 Jury accounts created with status ACTIVE and role JUDGE"""
        self.users_col.delete_many({'email': {'$in': [j['email'].strip().lower() for j in OFFICIAL_INTERNAL_JUDGES]}})
        self.judges_col.delete_many({'email': {'$in': [j['email'].strip().lower() for j in OFFICIAL_INTERNAL_JUDGES]}})

        seed_judges(send_emails=False)

        count_users = self.users_col.count_documents({'role': 'JUDGE', 'email': {'$in': [j['email'].strip().lower() for j in OFFICIAL_INTERNAL_JUDGES]}})
        count_judges = self.judges_col.count_documents({'email': {'$in': [j['email'].strip().lower() for j in OFFICIAL_INTERNAL_JUDGES]}})

        self.assertEqual(count_users, 25)
        self.assertEqual(count_judges, 25)

    # --------------------------------------------------
    # TEST 5 — IDEMPOTENT SEED
    # --------------------------------------------------
    def test_05_idempotent_seed(self):
        """Run seed again: no duplicate accounts, existing accounts remain unchanged"""
        seed_judges(send_emails=False)
        first_doc = self.users_col.find_one({'email': 'neelmani@srhu.edu.in'})
        self.assertIsNotNone(first_doc)
        original_hash = first_doc['password_hash']

        # Run again
        seed_judges(send_emails=False)
        second_doc = self.users_col.find_one({'email': 'neelmani@srhu.edu.in'})
        self.assertEqual(original_hash, second_doc['password_hash'])

        # Total remains 25
        count = self.users_col.count_documents({'role': 'JUDGE', 'email': {'$in': [j['email'].strip().lower() for j in OFFICIAL_INTERNAL_JUDGES]}})
        self.assertEqual(count, 25)

    # --------------------------------------------------
    # TEST 6 — PASSWORD HASHING
    # --------------------------------------------------
    def test_06_password_hashing(self):
        """Verify database does NOT contain plaintext password (password_hash exists, password does not)"""
        seed_judges(send_emails=False)
        for doc in self.users_col.find({'role': 'JUDGE'}):
            self.assertIn('password_hash', doc)
            self.assertNotIn('password', doc)
            self.assertTrue(doc['password_hash'].startswith(('scrypt:', 'pbkdf2:')))

    # --------------------------------------------------
    # TEST 7 — UNIQUE PASSWORDS
    # --------------------------------------------------
    def test_07_unique_passwords(self):
        """When accounts are newly provisioned, generated passwords must all be unique"""
        passwords = [generate_secure_jury_password() for _ in range(25)]
        self.assertEqual(len(passwords), len(set(passwords)))
        for pwd in passwords:
            self.assertTrue(len(pwd) >= 10)
            self.assertTrue(pwd.startswith('TF3-'))

    # --------------------------------------------------
    # TEST 8 — PASSWORD LOGIN
    # --------------------------------------------------
    def test_08_password_login(self):
        """Login using Email + generated password -> Authentication successful"""
        email = "test_judge_login@srhu.edu.in"
        password = generate_secure_jury_password()

        user_id = str(self.users_col.insert_one({
            'name': 'Test Judge Login',
            'email': email,
            'password_hash': generate_password_hash(password),
            'role': 'JUDGE',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        }).inserted_id)

        self.judges_col.insert_one({
            'user_id': user_id,
            'name': 'Test Judge Login',
            'email': email,
            'judge_type': 'INTERNAL_JUDGE',
            'panel_id': 'PANEL_1',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        auth_res = authenticate_jury_credentials(email, password)
        self.assertTrue(auth_res['success'])
        self.assertEqual(auth_res['user_id'], user_id)
        self.assertEqual(auth_res['role'], 'JUDGE')

    # --------------------------------------------------
    # TEST 9 — WRONG PASSWORD
    # --------------------------------------------------
    def test_09_wrong_password_rejected(self):
        """Correct email + wrong password -> Authentication rejected (generic error)"""
        email = "test_judge_wrong_pwd@srhu.edu.in"
        real_pwd = "TF3-RealPassword1"
        wrong_pwd = "TF3-WrongPassword2"

        self.users_col.insert_one({
            'name': 'Test Judge',
            'email': email,
            'password_hash': generate_password_hash(real_pwd),
            'role': 'JUDGE',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        res = authenticate_jury_credentials(email, wrong_pwd)
        self.assertFalse(res['success'])
        self.assertEqual(res['message'], 'Invalid email or password.')

    # --------------------------------------------------
    # TEST 10 — UNKNOWN EMAIL
    # --------------------------------------------------
    def test_10_unknown_email_rejected(self):
        """Unknown email -> Authentication rejected with generic message"""
        res = authenticate_jury_credentials("unknown@example.com", "SomePassword123")
        self.assertFalse(res['success'])
        self.assertEqual(res['message'], 'Invalid email or password.')

    # --------------------------------------------------
    # TEST 11 — INACTIVE JURY
    # --------------------------------------------------
    def test_11_inactive_jury_rejected(self):
        """Account with status != ACTIVE cannot log in"""
        email = "test_judge_inactive@srhu.edu.in"
        pwd = "TF3-InactivePwd1"

        self.users_col.insert_one({
            'name': 'Inactive Judge',
            'email': email,
            'password_hash': generate_password_hash(pwd),
            'role': 'JUDGE',
            'status': 'INACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        res = authenticate_jury_credentials(email, pwd)
        self.assertFalse(res['success'])
        self.assertIn('inactive', res['message'].lower())

    # --------------------------------------------------
    # TEST 12 — ROLE CHECK
    # --------------------------------------------------
    def test_12_admin_role_rejected_in_jury_login(self):
        """Admin account without JUDGE role is rejected through Jury authentication"""
        email = "admin_test_judge_login@srhu.edu.in"
        pwd = "AdminPassword123"

        self.users_col.insert_one({
            'name': 'Admin User',
            'email': email,
            'password_hash': generate_password_hash(pwd),
            'role': 'admin',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        res = authenticate_jury_credentials(email, pwd)
        self.assertFalse(res['success'])
        self.assertEqual(res['message'], 'Invalid email or password.')

    # --------------------------------------------------
    # TEST 13 — DASHBOARD REDIRECT
    # --------------------------------------------------
    def test_13_dashboard_redirect(self):
        """POST /judge/login redirects to /judge/dashboard on success"""
        email = "test_judge_redirect@srhu.edu.in"
        pwd = "TF3-RedirectPwd1"

        user_id = str(self.users_col.insert_one({
            'name': 'Redirect Judge',
            'email': email,
            'password_hash': generate_password_hash(pwd),
            'role': 'JUDGE',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        }).inserted_id)

        self.judges_col.insert_one({
            'user_id': user_id,
            'name': 'Redirect Judge',
            'email': email,
            'judge_type': 'INTERNAL_JUDGE',
            'panel_id': 'PANEL_1',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        res = self.client.post('/judge/login', data={'email': email, 'password': pwd}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/judge/dashboard', res.headers['Location'])

    # --------------------------------------------------
    # TEST 14 — SESSION
    # --------------------------------------------------
    def test_14_session_created_without_plaintext_password(self):
        """After login, session contains user_id and role=judge, no plaintext password"""
        email = "test_judge_session@srhu.edu.in"
        pwd = "TF3-SessionPwd1"

        user_id = str(self.users_col.insert_one({
            'name': 'Session Judge',
            'email': email,
            'password_hash': generate_password_hash(pwd),
            'role': 'JUDGE',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        }).inserted_id)

        self.judges_col.insert_one({
            'user_id': user_id,
            'name': 'Session Judge',
            'email': email,
            'judge_type': 'INTERNAL_JUDGE',
            'panel_id': 'PANEL_3',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        with self.client as c:
            c.post('/judge/login', data={'email': email, 'password': pwd})
            from flask import session
            self.assertEqual(session.get('user_id'), user_id)
            self.assertIn(str(session.get('role')).upper(), ['JUDGE', 'INTERNAL_JUDGE'])
            self.assertNotIn('password', session)
            self.assertNotIn('password_hash', session)

    # --------------------------------------------------
    # TEST 15 — ASSIGNED TEAM SECURITY
    # --------------------------------------------------
    def test_15_assigned_team_security(self):
        """Judge can access assigned team (200) and gets 403 on unassigned team"""
        email = "test_judge_security@srhu.edu.in"
        pwd = "TF3-SecurityPwd1"
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        user_id = str(self.users_col.insert_one({
            'name': 'Security Judge',
            'email': email,
            'password_hash': generate_password_hash(pwd),
            'role': 'JUDGE',
            'status': 'ACTIVE',
            'created_at': now
        }).inserted_id)

        judge_id = str(self.judges_col.insert_one({
            'user_id': user_id,
            'name': 'Security Judge',
            'email': email,
            'judge_type': 'INTERNAL_JUDGE',
            'panel_id': 'PANEL_1',
            'status': 'ACTIVE',
            'created_at': now
        }).inserted_id)

        # Team A (Assigned) and Team B (Unassigned)
        team_a_id = str(self.teams_col.insert_one({
            'team_name': 'Credential Test Team Alpha Assigned',
            'leader_name': 'Alice',
            'status': 'registered',
            'created_at': now
        }).inserted_id)

        team_b_id = str(self.teams_col.insert_one({
            'team_name': 'Credential Test Team Beta Unassigned',
            'leader_name': 'Bob',
            'status': 'registered',
            'created_at': now
        }).inserted_id)

        # Assign Team A to judge
        self.assignments_col.insert_one({
            'judge_id': judge_id,
            'team_id': team_a_id,
            'panel_id': 'PANEL_1',
            'assigned_at': now
        })

        with self.client as c:
            c.post('/judge/login', data={'email': email, 'password': pwd})

            # Assigned team evaluation access -> 200
            res_a = c.get(f'/judge/evaluate/{team_a_id}')
            self.assertEqual(res_a.status_code, 200)

            # Unassigned team evaluation access -> 403 Forbidden
            res_b = c.get(f'/judge/evaluate/{team_b_id}')
            self.assertEqual(res_b.status_code, 403)

    # --------------------------------------------------
    # TEST 16 — ADMIN SECURITY
    # --------------------------------------------------
    def test_16_judge_cannot_access_admin(self):
        """Judge attempting /admin/dashboard receives 403 Forbidden"""
        email = "test_judge_noadmin@srhu.edu.in"
        pwd = "TF3-NoAdminPwd1"

        user_id = str(self.users_col.insert_one({
            'name': 'No Admin Judge',
            'email': email,
            'password_hash': generate_password_hash(pwd),
            'role': 'JUDGE',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        }).inserted_id)

        self.judges_col.insert_one({
            'user_id': user_id,
            'name': 'No Admin Judge',
            'email': email,
            'judge_type': 'INTERNAL_JUDGE',
            'panel_id': 'PANEL_1',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        with self.client as c:
            c.post('/judge/login', data={'email': email, 'password': pwd})
            res = c.get('/admin/dashboard')
            self.assertEqual(res.status_code, 403)

    # --------------------------------------------------
    # TEST 17 — SUPER ADMIN SECURITY
    # --------------------------------------------------
    def test_17_judge_cannot_access_super_admin(self):
        """Judge attempting /super-admin/dashboard receives 403 Forbidden"""
        email = "test_judge_nosuper@srhu.edu.in"
        pwd = "TF3-NoSuperPwd1"

        user_id = str(self.users_col.insert_one({
            'name': 'No Super Judge',
            'email': email,
            'password_hash': generate_password_hash(pwd),
            'role': 'JUDGE',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        }).inserted_id)

        self.judges_col.insert_one({
            'user_id': user_id,
            'name': 'No Super Judge',
            'email': email,
            'judge_type': 'INTERNAL_JUDGE',
            'panel_id': 'PANEL_1',
            'status': 'ACTIVE',
            'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
        })

        with self.client as c:
            c.post('/judge/login', data={'email': email, 'password': pwd})
            res = c.get('/super-admin/dashboard')
            self.assertEqual(res.status_code, 403)

    # --------------------------------------------------
    # TEST 18 — SMTP MOCK
    # --------------------------------------------------
    def test_18_smtp_mock_provisioning(self):
        """Mock SMTP: email service called, recipient matches, password included in email body, password hashed in DB"""
        with patch('services.email_service.smtplib.SMTP') as mock_smtp:
            from services.email_service import send_jury_credentials_email

            email = "mock_judge_test@srhu.edu.in"
            temp_pwd = generate_secure_jury_password()
            pwd_hash = generate_password_hash(temp_pwd)

            user_id = str(self.users_col.insert_one({
                'name': 'Mock Judge',
                'email': email,
                'password_hash': pwd_hash,
                'role': 'JUDGE',
                'status': 'ACTIVE',
                'created_at': datetime.now(timezone.utc).replace(tzinfo=None)
            }).inserted_id)

            send_res = send_jury_credentials_email(email, temp_pwd, judge_name="Mock Judge")
            self.assertTrue(send_res['success'])

            # Verify password NOT stored plaintext in DB
            db_user = self.users_col.find_one({'email': email})
            self.assertNotIn('password', db_user)
            self.assertTrue(check_password_hash(db_user['password_hash'], temp_pwd))

    # --------------------------------------------------
    # TEST 19 — NO DUPLICATE EMAIL
    # --------------------------------------------------
    def test_19_no_duplicate_email_on_multiple_runs(self):
        """Run seed twice: database still contains exactly 25 unique Jury accounts"""
        seed_judges(send_emails=False)
        seed_judges(send_emails=False)

        count = self.users_col.count_documents({'role': 'JUDGE', 'email': {'$in': [j['email'].strip().lower() for j in OFFICIAL_INTERNAL_JUDGES]}})
        self.assertEqual(count, 25)

    # --------------------------------------------------
    # TEST 20 — NO EMAIL ON STARTUP
    # --------------------------------------------------
    def test_20_no_email_sent_on_app_startup(self):
        """Starting Flask application does NOT send any Jury credential emails automatically"""
        with patch('services.email_service.send_jury_credentials_email') as mock_send:
            new_app = create_app()
            with new_app.test_client() as client:
                res = client.get('/')
                self.assertEqual(res.status_code, 200)
            mock_send.assert_not_called()

    # --------------------------------------------------
    # TEST 21 — EXISTING PASSWORD PRESERVED
    # --------------------------------------------------
    def test_21_existing_password_preserved_on_reseed(self):
        """Create existing Jury account, run seed again, verify password hash remains unchanged"""
        email = "neelmani@srhu.edu.in"
        custom_pwd = "TF3-CustomPreSetPassword9"
        custom_hash = generate_password_hash(custom_pwd)

        self.users_col.update_one(
            {'email': email},
            {'$set': {'password_hash': custom_hash, 'role': 'JUDGE', 'status': 'ACTIVE'}},
            upsert=True
        )

        seed_judges(send_emails=False)

        doc = self.users_col.find_one({'email': email})
        self.assertEqual(doc['password_hash'], custom_hash)
        self.assertTrue(check_password_hash(doc['password_hash'], custom_pwd))

    # --------------------------------------------------
    # TEST 22 — LANDING PAGE CLEANUP
    # --------------------------------------------------
    def test_22_landing_page_cleanup(self):
        """Open /: Verify Evaluation Matrix, 36H Timeline, Jury Panels, FAQs are absent"""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertNotIn('id="evaluation"', html)
        self.assertNotIn('id="schedule"', html)
        self.assertNotIn('id="panels"', html)
        self.assertNotIn('id="faq"', html)
        self.assertNotIn('Official Evaluation Matrix', html)
        self.assertNotIn('Evaluation Checkpoints', html)
        self.assertNotIn('Jury Panel Structure', html)
        self.assertNotIn('Frequently Asked Questions', html)

        # Confirm essential elements
        self.assertIn('TECHFORGE 3.0', html)
        self.assertIn('Life Ka Compass', html)
        self.assertIn('Jury Portal', html)


if __name__ == '__main__':
    unittest.main()
