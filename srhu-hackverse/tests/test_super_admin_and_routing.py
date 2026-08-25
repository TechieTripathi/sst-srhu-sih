"""
TechForge 3.0 Test Suite:
1. Homepage Routing (Verifies / renders landing page, never redirects to registration-success)
2. Registration Success Protection (Direct access blocked unless fresh registration session)
3. Full Team Registration Flow
4. Super Admin Login & Dashboard Routing
5. Judge Login & Dashboard Routing (Separation from Admin/Super Admin)
6. RBAC 403 Tests (Judge cannot access Super Admin; Admin cannot access Super Admin governance)
7. Super Admin full capability on Admin endpoints
"""

import unittest
from werkzeug.security import generate_password_hash
from bson.objectid import ObjectId
from datetime import datetime

from app import create_app
from models.database import get_users_collection, get_teams_collection


class TestHomepageAndSuperAdmin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.client = cls.app.test_client()

        with cls.app.app_context():
            users_col = get_users_collection()
            
            # Setup Super Admin Test User
            users_col.update_one(
                {'email': 'test_superadmin@srhu.edu.in'},
                {
                    '$set': {
                        'name': 'Test Super Admin',
                        'email': 'test_superadmin@srhu.edu.in',
                        'password_hash': generate_password_hash('superadmin123'),
                        'role': 'super_admin',
                        'status': 'active',
                        'created_at': datetime.utcnow()
                    }
                },
                upsert=True
            )

            # Setup Normal Admin Test User
            users_col.update_one(
                {'email': 'test_admin@srhu.edu.in'},
                {
                    '$set': {
                        'name': 'Test Event Admin',
                        'email': 'test_admin@srhu.edu.in',
                        'password_hash': generate_password_hash('admin123'),
                        'role': 'admin',
                        'status': 'active',
                        'created_at': datetime.utcnow()
                    }
                },
                upsert=True
            )

            # Setup Judge Test User
            users_col.update_one(
                {'email': 'test_judge@srhu.edu.in'},
                {
                    '$set': {
                        'name': 'Dr. Test Judge',
                        'email': 'test_judge@srhu.edu.in',
                        'password_hash': generate_password_hash('judge123'),
                        'role': 'internal_judge',
                        'status': 'active',
                        'created_at': datetime.utcnow()
                    }
                },
                upsert=True
            )

    # --- CASE 1: Startup / Root Route Test ---
    def test_case_1_homepage_renders_landing_not_registration_success(self):
        """Case 1: GET / renders TechForge 3.0 homepage, NOT registration success"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        self.assertIn('TECHFORGE 3.0', content)
        self.assertIn('36-Hours', content)
        self.assertIn('Swami Rama Himalayan University', content)
        self.assertNotIn('Registration Successful!', content)

    # --- CASE 2: Prevent Direct Success Page Access ---
    def test_case_2_direct_registration_success_redirects_home(self):
        """Case 2: Direct GET /teams/registration-success redirects to / without session flag"""
        response = self.client.get('/teams/registration-success', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith('/') or response.location == '/')

    # --- CASE 3: Full Team Registration Flow ---
    def test_case_3_registration_flow_success(self):
        """Case 3: Complete registration flow and display generated Team ID"""
        import time
        unique_team = f"TestTeam_{int(time.time())}"
        unique_email = f"lead_{int(time.time())}@srhu.edu.in"
        
        response = self.client.post('/teams/register', data={
            'leader_name': 'Test Leader',
            'team_name': unique_team,
            'email': unique_email,
            'mobile': '9876543210'
        }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        content = response.data.decode('utf-8')
        self.assertIn('Registration Successful!', content)
        self.assertIn('TF3-', content)

    # --- CASE 4: Super Admin Login & Dashboard Routing ---
    def test_case_4_super_admin_login_and_dashboard(self):
        """Case 4: Super Admin logs in and is routed to /super-admin/dashboard"""
        client = self.app.test_client()
        response = client.post('/auth/login', data={
            'email': 'test_superadmin@srhu.edu.in',
            'password': 'superadmin123'
        }, follow_redirects=False)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/super-admin/dashboard', response.location)
        
        # Follow to dashboard
        dash_response = client.get('/super-admin/dashboard')
        self.assertEqual(dash_response.status_code, 200)
        content = dash_response.data.decode('utf-8')
        self.assertIn('Super Administration', content)
        self.assertIn('TECHFORGE 3.0', content)

    # --- CASE 5: Judge Login & Dashboard Routing ---
    def test_case_5_judge_login_and_dashboard(self):
        """Case 5: Judge logs in and is routed to /judge/dashboard, NOT Admin"""
        client = self.app.test_client()
        response = client.post('/auth/login', data={
            'email': 'test_judge@srhu.edu.in',
            'password': 'judge123'
        }, follow_redirects=False)
        
        self.assertEqual(response.status_code, 302)
        self.assertIn('/judge/dashboard', response.location)
        self.assertNotIn('/admin/dashboard', response.location)

    # --- CASE 6: Judge attempts Super Admin Dashboard (403) ---
    def test_case_6_judge_cannot_access_super_admin(self):
        """Case 6: Judge attempting to access /super-admin/dashboard gets 403 Forbidden"""
        client = self.app.test_client()
        # Login as judge
        client.post('/auth/login', data={
            'email': 'test_judge@srhu.edu.in',
            'password': 'judge123'
        })
        
        # Attempt super admin
        response = client.get('/super-admin/dashboard')
        self.assertEqual(response.status_code, 403)

    # --- CASE 7: Normal Admin attempts Super Admin Governance (403) ---
    def test_case_7_admin_cannot_access_super_admin_governance(self):
        """Case 7: Admin attempting /super-admin/admins or /super-admin/dashboard gets 403"""
        client = self.app.test_client()
        # Login as admin
        client.post('/auth/login', data={
            'email': 'test_admin@srhu.edu.in',
            'password': 'admin123'
        })
        
        # Admin can access admin dashboard
        admin_dash = client.get('/admin/dashboard')
        self.assertEqual(admin_dash.status_code, 200)

        # Admin CANNOT access super admin dashboard
        sa_dash = client.get('/super-admin/dashboard')
        self.assertEqual(sa_dash.status_code, 403)

        # Admin CANNOT access admin management
        sa_admins = client.get('/super-admin/admins')
        self.assertEqual(sa_admins.status_code, 403)

    # --- Super Admin has access to standard Admin endpoints ---
    def test_super_admin_can_access_admin_endpoints(self):
        """Super Admin has full authority on /admin endpoints"""
        client = self.app.test_client()
        client.post('/auth/login', data={
            'email': 'test_superadmin@srhu.edu.in',
            'password': 'superadmin123'
        })
        
        admin_dash = client.get('/admin/dashboard')
        self.assertEqual(admin_dash.status_code, 200)
        
        teams_page = client.get('/admin/teams')
        self.assertEqual(teams_page.status_code, 200)

    def test_super_admin_system_settings_view_and_post(self):
        """Super Admin can view and save system settings"""
        client = self.app.test_client()
        client.post('/auth/login', data={
            'email': 'test_superadmin@srhu.edu.in',
            'password': 'superadmin123'
        })
        
        # GET settings page
        res = client.get('/super-admin/system-settings')
        self.assertEqual(res.status_code, 200)
        content = res.data.decode('utf-8')
        self.assertIn('Event Control Switches', content)
        self.assertIn('Lock Judging Submissions', content)
        
        # POST toggle settings
        post_res = client.post('/super-admin/system-settings', data={
            'judging_locked': 'on',
            'results_published': 'on',
            'registration_open': 'on'
        }, follow_redirects=True)
        self.assertEqual(post_res.status_code, 200)


if __name__ == '__main__':
    unittest.main()
