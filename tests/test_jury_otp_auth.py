"""
TechForge 3.0 — Jury Access Control Test Suite
Judges authenticate with email + password. Group jury score only their own
panel's teams; exception jury score every team.
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
    def test_16_exception_jury_sees_every_team(self):
        """Test 16: exception jury reach every team; group jury only their panel.

        Supersedes a test that asserted every judge could evaluate every team,
        which is no longer how the app works.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # This test is about panel scoping, so the judging lock must not be the
        # thing under test - a locked event blocks group jury for a completely
        # different reason and would make the assertions below misleading.
        from services.checkpoint_manager import unlock_judging
        unlock_judging(actor_id=None)

        judge_doc = self.judges_col.find_one({'email': 'neelmani@srhu.edu.in'})
        user_id = judge_doc['user_id']

        team_ids = [str(self.teams_col.insert_one({
            'team_name': name, 'team_code': code, 'leader_name': leader,
            'panel_no': panel, 'created_at': now
        }).inserted_id) for name, code, leader, panel in [
            ('Test Team Alpha', 'TF3-ALPHA01', 'Alice', 1),
            ('Test Team Beta', 'TF3-BETA02', 'Bob', 3),
        ]]

        def client_for(scope, panel_no):
            self.judges_col.update_one(
                {'_id': judge_doc['_id']},
                {'$set': {'jury_scope': scope, 'panel_no': panel_no}},
            )
            c = self.app.test_client()
            with c.session_transaction() as sess:
                sess['user_id'] = user_id
                sess['role'] = 'JUDGE'
                sess['email'] = 'neelmani@srhu.edu.in'
                sess['judge_type'] = 'INTERNAL_JUDGE'
            return c

        # Exception jury: both teams reachable.
        c = client_for('all_teams', None)
        html = c.get('/judge/dashboard').data.decode('utf-8')
        self.assertIn('Test Team Alpha', html)
        self.assertIn('Test Team Beta', html)
        for team_id in team_ids:
            self.assertEqual(c.get(f'/judge/evaluate/{team_id}').status_code, 200)

        # Same judge as Panel 1 group jury: only the Panel 1 team.
        c = client_for('assigned_only', 1)
        html = c.get('/judge/dashboard').data.decode('utf-8')
        self.assertIn('Test Team Alpha', html)
        self.assertNotIn('Test Team Beta', html)
        self.assertEqual(c.get(f'/judge/evaluate/{team_ids[0]}').status_code, 200)
        refused = c.get(f'/judge/evaluate/{team_ids[1]}')
        self.assertEqual(refused.status_code, 403)
        # Assert the reason too, so a future judging lock cannot make this pass
        # for the wrong cause.
        self.assertIn('Not Your Panel', refused.data.decode('utf-8'))

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
