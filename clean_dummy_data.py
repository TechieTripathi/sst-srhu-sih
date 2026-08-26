"""
TechForge 3.0 — Database Cleanup Script
Removes all dummy test data, test teams, mock users and test evaluations while preserving the official system configuration:
- Super Admin (superadmin@srhu.edu.in)
- Default Admin (admin@srhu.edu.in)
- 25 Official Internal Jury Accounts
- 6 Official Evaluation Criteria
- Event Settings
"""

from app import create_app
from models.database import (
    get_users_collection,
    get_judges_collection,
    get_teams_collection,
    get_team_members_collection,
    get_evaluations_collection,
    get_evaluation_scores_collection,
    get_team_results_collection,
    get_audit_logs_collection
)

# Every official juror, derived from services/jury_roster.py rather than
# hand-listed. A hardcoded list would treat any newly added juror as dummy data
# and delete them - including the three outside guests and the exception jury,
# who are exactly the accounts that must not disappear.
from services.jury_roster import EXCEPTION_JURY, GROUP_JURY

OFFICIAL_JURY_EMAILS = {
    j['email'].strip().lower() for j in (EXCEPTION_JURY + GROUP_JURY)
}

# Administrative Whitelist
OFFICIAL_ADMIN_EMAILS = {
    "superadmin@srhu.edu.in",
    "admin@srhu.edu.in"
}

PRESERVED_EMAILS = OFFICIAL_JURY_EMAILS | OFFICIAL_ADMIN_EMAILS


def clean_dummy_data():
    """Remove dummy test records across all collections"""
    print("\n" + "=" * 55)
    print("  TechForge 3.0: Cleaning Dummy & Test Data")
    print("=" * 55)

    users_col = get_users_collection()
    judges_col = get_judges_collection()
    teams_col = get_teams_collection()
    team_members_col = get_team_members_collection()
    evals_col = get_evaluations_collection()
    eval_scores_col = get_evaluation_scores_collection()
    team_results_col = get_team_results_collection()
    audit_col = get_audit_logs_collection()

    # 1. Clean dummy teams and team members
    del_teams = teams_col.delete_many({})
    del_members = team_members_col.delete_many({})
    print(f"[OK] Removed {del_teams.deleted_count} dummy teams and {del_members.deleted_count} dummy team member records.")

    # 2. Clean dummy users (keep only official Super Admin, Admin, and 25 Jury Members)
    del_users = users_col.delete_many({'email': {'$nin': list(PRESERVED_EMAILS)}})
    print(f"[OK] Removed {del_users.deleted_count} dummy/test user accounts.")

    # 3. Clean dummy judges (keep only the 25 official internal jury members)
    del_judges = judges_col.delete_many({'email': {'$nin': list(OFFICIAL_JURY_EMAILS)}})
    print(f"[OK] Removed {del_judges.deleted_count} non-official judge profiles.")

    # 4. Clean test evaluations and scores
    del_evals = evals_col.delete_many({})
    del_scores = eval_scores_col.delete_many({})
    del_results = team_results_col.delete_many({})
    print(f"[OK] Cleared {del_evals.deleted_count} test evaluations, {del_scores.deleted_count} scores, and {del_results.deleted_count} results.")

    # 5. Clean test audit logs (keep system activity clean)
    del_audit = audit_col.delete_many({'action': {'$regex': 'test|Test'}})
    print(f"[OK] Cleared {del_audit.deleted_count} test audit log entries.")

    print("\n" + "-" * 55)
    print("  Pristine Production Database Status:")
    print("-" * 55)
    print(f"  - Official Users:             {users_col.count_documents({})} (1 Super Admin + 1 Admin + 25 Jury Members)")
    print(f"  - Official Jury Profiles:     {judges_col.count_documents({})} (25 Pre-authorized Internal Jury Members)")
    print(f"  - Teams (Registered):         {teams_col.count_documents({})} (Ready for fresh registrations)")
    print(f"  - Evaluations / Scores:       {evals_col.count_documents({})}")
    print("=" * 55 + "\n")


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        clean_dummy_data()
