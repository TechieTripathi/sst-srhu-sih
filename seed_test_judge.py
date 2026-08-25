"""
Create (or reset) a jury TEST account for trying out the judge portal.

    python seed_test_judge.py                 # internal judge, default password
    python seed_test_judge.py external        # external judge
    python seed_test_judge.py internal MyPass # custom password

Login at /judge/login with the credentials printed below.
Delete it before the event: it is removed by clean_dummy_data.py
(email matches the 'test_' pattern).
"""
import sys
from datetime import datetime
from werkzeug.security import generate_password_hash

from app import create_app
from models.database import get_users_collection, get_judges_collection

EMAIL = 'test_judge@srhu.edu.in'
NAME = 'Test Judge'


def seed_test_judge(judge_type='internal', password='TestJudge@123'):
    judge_type = 'EXTERNAL_JUDGE' if judge_type.lower().startswith('ext') else 'INTERNAL_JUDGE'
    users, judges = get_users_collection(), get_judges_collection()
    now = datetime.utcnow()

    user = users.find_one({'email': EMAIL})
    if user:
        users.update_one({'_id': user['_id']}, {'$set': {
            'password_hash': generate_password_hash(password), 'role': 'judge',
            'status': 'active', 'updated_at': now}})
        user_id = str(user['_id'])
        action = 'RESET'
    else:
        user_id = str(users.insert_one({
            'name': NAME, 'email': EMAIL, 'password_hash': generate_password_hash(password),
            'role': 'judge', 'status': 'active', 'credentials_sent': False, 'created_at': now
        }).inserted_id)
        action = 'CREATED'

    judges.update_one({'email': EMAIL}, {'$set': {
        'user_id': user_id, 'name': NAME, 'email': EMAIL, 'judge_type': judge_type,
        'status': 'active', 'updated_at': now}, '$setOnInsert': {'created_at': now}}, upsert=True)

    print(f"\n[{action}] Jury test account ({judge_type})")
    print(f"  Login URL : /judge/login")
    print(f"  Email     : {EMAIL}")
    print(f"  Password  : {password}\n")


if __name__ == '__main__':
    jt = sys.argv[1] if len(sys.argv) > 1 else 'internal'
    pw = sys.argv[2] if len(sys.argv) > 2 else 'TestJudge@123'
    with create_app().app_context():
        seed_test_judge(jt, pw)
