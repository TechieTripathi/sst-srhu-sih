"""
TechForge 3.0 — Jury Access Control Test Suite
Judges authenticate with email + password; every judge can evaluate every team.
"""

import unittest
from datetime import datetime, timezone
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash

from app import create_app
from models.database import (
    get_users_collection,
    get_judges_collection,
    get_teams_collection
)
from seed_judges import seed_judges


class TestJuryAccess(unittest.TestCase):
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
        self.teams_col = get_teams_collection()

        self._clean_test_records()

    def tearDown(self):
        self._clean_test_records()

    def _clean_test_records(self):
        # Clean up transient test records
        self.users_col.delete_many({'email': {'$regex': 'test|industry\\.org|inactive_judge'}})
        self.judges_col.delete_many({'email': {'$regex': 'test|industry\\.org|inactive_judge'}})
        self.teams_col.delete_many({'team_name': {'$regex': 'Test Team'}})

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

    # --- TEST 16: Every judge can evaluate every team ---
    def test_16_every_judge_can_evaluate_every_team(self):
        """Test 16: A judge can open the dashboard and the evaluation form for any registered team"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        judge_doc = self.judges_col.find_one({'email': 'neelmani@srhu.edu.in'})
        user_id = judge_doc['user_id']

        team_ids = [str(self.teams_col.insert_one({
            'team_name': name, 'team_code': code, 'leader_name': leader, 'created_at': now
        }).inserted_id) for name, code, leader in [
            ('Test Team Alpha', 'TF3-ALPHA01', 'Alice'),
            ('Test Team Beta', 'TF3-BETA02', 'Bob'),
        ]]

        client = self.app.test_client()
        with client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['role'] = 'JUDGE'
            sess['email'] = 'neelmani@srhu.edu.in'
            sess['judge_type'] = 'INTERNAL_JUDGE'

        dash = client.get('/judge/dashboard')
        self.assertEqual(dash.status_code, 200)
        html = dash.data.decode('utf-8')
        self.assertIn('Test Team Alpha', html)
        self.assertIn('Test Team Beta', html)

        for team_id in team_ids:
            self.assertEqual(client.get(f'/judge/evaluate/{team_id}').status_code, 200)

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
