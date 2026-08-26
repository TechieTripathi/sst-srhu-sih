#!/usr/bin/env python3
"""
TechForge 3.0 — Jury Panel Migration

Brings an existing database up to the panel model:

  * reclassifies the 3 exception jurors (all_teams scope, 40% weight, may score
    while judging is locked) and corrects their names,
  * stamps panel membership and assigned_only scope on the 25 group jury,
  * creates the 3 outside guests who have no university mailbox,
  * optionally distributes the teams across the five panels.

    python migrate_jury_panels.py --dry-run
    python migrate_jury_panels.py
    python migrate_jury_panels.py --assign-teams [--mode blocks|round_robin]

This is a separate script rather than part of seed_judges.py on purpose:
seed_judges.py skips its entire per-judge body when the user already has a
password_hash, and every live judge does, so anything added there would never
run against the real database.

Idempotent. Every write is a $set or an upsert keyed on email; the script never
calls regenerate_external_password, reset_judge_password or
send_judge_credentials, and never touches password_hash. Re-running it reports
the same guest passwords rather than minting new ones.
"""

import argparse
import sys

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from models.database import get_judges_collection, get_users_collection
from services.audit import log_audit
from services.jury_panels import auto_assign_teams
from services.jury_roster import EXCEPTION_JURY, GROUP_JURY, has_mailbox
from services.jury_scope import SCOPE_ALL, SCOPE_ASSIGNED
from datetime import datetime

BAR = "=" * 60


class Report:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.reclassified = 0
        self.stamped = 0
        self.created = 0
        self.unchanged = 0
        self.errors = []
        self.passwords = []

    def fail(self, message):
        self.errors.append(message)
        print(f"[SKIP] {message}")


def _find_judge(email):
    return get_judges_collection().find_one({'email': email.strip().lower()})


def _write_name_everywhere(judge, name, report):
    """Names must land on the users document too.

    The judges list overlays name/email from users, jury login puts users.name
    into the session, and the audit log resolves actor names from users. A
    judges-only rename would leave the old spelling on every screen that matters.
    """
    if judge.get('name') == name:
        return False
    if report.dry_run:
        return True
    get_judges_collection().update_one(
        {'_id': judge['_id']},
        {'$set': {'name': name, 'updated_at': datetime.utcnow()}},
    )
    if judge.get('user_id'):
        from bson.objectid import ObjectId
        try:
            get_users_collection().update_one(
                {'_id': ObjectId(judge['user_id'])},
                {'$set': {'name': name, 'updated_at': datetime.utcnow()}},
            )
        except Exception:
            pass
    return True


def reclassify_exception_jury(report):
    print(f"\nException jury ({len(EXCEPTION_JURY)}) — scope=all_teams, 40% weight")
    print("-" * 60)
    for entry in EXCEPTION_JURY:
        email = entry['email'].strip().lower()
        judge = _find_judge(email)
        if not judge:
            # Never create one here: it would mint a password nobody knows.
            report.fail(f"{email} not found — create the account first, then re-run")
            continue

        renamed = _write_name_everywhere(judge, entry['name'], report)
        needs_scope = (judge.get('jury_scope') != SCOPE_ALL
                       or judge.get('panel_no') is not None)

        if not needs_scope and not renamed:
            report.unchanged += 1
            print(f"[OK]   {entry['name']:<26} {email:<34} unchanged")
            continue

        if not report.dry_run and needs_scope:
            get_judges_collection().update_one({'_id': judge['_id']}, {
                '$set': {'jury_scope': SCOPE_ALL, 'updated_at': datetime.utcnow()},
                '$unset': {'panel_no': ''},
            })
            log_audit(None, 'judge_scope_updated', 'judge', str(judge['_id']), {
                'from': judge.get('jury_scope'), 'to': SCOPE_ALL,
                'from_panel': judge.get('panel_no'), 'email': email,
                'via': 'migrate_jury_panels.py',
            })

        report.reclassified += 1
        note = 'exception jury' + (' + renamed' if renamed else '')
        print(f"[OK]   {entry['name']:<26} {email:<34} {note}")


def stamp_group_jury(report):
    print(f"\nGroup jury ({len(GROUP_JURY)}) — scope=assigned_only, 60% weight")
    print("-" * 60)
    from services.judge_management import create_judge

    for entry in GROUP_JURY:
        email = entry['email'].strip().lower()
        panel = entry['panel_no']
        judge = _find_judge(email)

        if not judge:
            if has_mailbox(entry):
                report.fail(f"{email} not found and has a mailbox — expected to exist already")
                continue
            # An outside guest. create_judge writes judge_type EXTERNAL_JUDGE,
            # which is what persists a retrievable temp_password so the admin
            # Judges page can show and copy it indefinitely.
            if report.dry_run:
                report.created += 1
                print(f"[OK]   {entry['name']:<26} {email:<34} would create (panel {panel}, guest)")
                continue
            result = create_judge(
                name=entry['name'], email=email, phone='',
                judge_type='external', actor_id=None,
                jury_scope=SCOPE_ASSIGNED, panel_no=panel,
                credentials_deliverable=False,
            )
            if result.get('error') and 'exists' not in str(result['error']).lower():
                report.fail(f"{email}: {result['error']}")
                continue
            judge = _find_judge(email)
            if not judge:
                report.fail(f"{email}: created but could not be read back")
                continue
            report.created += 1
            if result.get('temp_password'):
                report.passwords.append((entry['name'], email, result['temp_password']))
            print(f"[OK]   {entry['name']:<26} {email:<34} created (panel {panel}, guest)")

        renamed = _write_name_everywhere(judge, entry['name'], report)

        updates = {
            'jury_scope': SCOPE_ASSIGNED,
            'panel_no': panel,
            'credentials_deliverable': has_mailbox(entry),
        }
        # Only ever promote a coordinator; never write False, which would demote
        # someone an admin promoted through the UI.
        if entry.get('is_coordinator'):
            updates['is_overall_jury_coordinator'] = True

        changed = any(judge.get(k) != v for k, v in updates.items())
        if not changed and not renamed:
            report.unchanged += 1
            print(f"[OK]   {entry['name']:<26} {email:<34} panel {panel}, unchanged")
            continue

        if not report.dry_run and changed:
            updates['updated_at'] = datetime.utcnow()
            get_judges_collection().update_one({'_id': judge['_id']}, {'$set': updates})
            log_audit(None, 'judge_panel_updated', 'judge', str(judge['_id']), {
                'from_scope': judge.get('jury_scope'), 'to_scope': SCOPE_ASSIGNED,
                'from_panel': judge.get('panel_no'), 'to_panel': panel,
                'email': email, 'via': 'migrate_jury_panels.py',
            })

        report.stamped += 1
        note = f"panel {panel}" + (' + renamed' if renamed else '')
        if not has_mailbox(entry):
            note += ', guest (no mail)'
        print(f"[OK]   {entry['name']:<26} {email:<34} {note}")

    # A guest that already existed still needs its password surfaced, so the
    # report stays useful on a re-run.
    for entry in GROUP_JURY:
        if has_mailbox(entry):
            continue
        email = entry['email'].strip().lower()
        if any(p[1] == email for p in report.passwords):
            continue
        judge = _find_judge(email)
        if judge and judge.get('temp_password'):
            report.passwords.append((entry['name'], email, judge['temp_password']))


def main():
    parser = argparse.ArgumentParser(description='TechForge 3.0 jury panel migration')
    parser.add_argument('--dry-run', action='store_true', help='report without writing')
    parser.add_argument('--assign-teams', action='store_true',
                        help='also distribute teams across the five panels')
    parser.add_argument('--mode', choices=['blocks', 'round_robin'], default='blocks',
                        help='team distribution strategy (default: blocks)')
    parser.add_argument('--overwrite', action='store_true',
                        help='reassign teams that already have a panel')
    args = parser.parse_args()

    report = Report(dry_run=args.dry_run)

    print(f"\n{BAR}\nTechForge 3.0 — Jury Panel Migration"
          f"{'  (DRY RUN — no writes)' if args.dry_run else ''}\n{BAR}")

    app = create_app()
    with app.app_context():
        reclassify_exception_jury(report)
        stamp_group_jury(report)

        if args.assign_teams:
            print(f"\nTeam assignment — mode={args.mode}, overwrite={args.overwrite}")
            print("-" * 60)
            if args.dry_run:
                print("[SKIP] --dry-run: no teams assigned")
            else:
                result = auto_assign_teams(mode=args.mode, overwrite=args.overwrite,
                                          actor_id=None)
                print(f"[OK]   assigned {result['assigned']}, "
                      f"left alone {result['skipped']}")
                for panel, count in sorted(result['per_panel'].items()):
                    print(f"       Panel {panel}: {count} teams")

        if report.passwords:
            print(f"\n{BAR}\nGUEST SIGN-IN DETAILS — hand these over in person\n{BAR}")
            for name, email, password in report.passwords:
                print(f"[PASSWORD] {name}\n           email    : {email}\n"
                      f"           password : {password}")
            print("These stay retrievable on the admin Judges page.")

        if not args.dry_run:
            log_audit(None, 'jury_roster_migrated', 'jury_panel', 'techforge3', {
                'reclassified': report.reclassified, 'stamped': report.stamped,
                'created': report.created, 'unchanged': report.unchanged,
                'errors': len(report.errors),
            })

    print(f"\n{BAR}\nreclassified {report.reclassified} · stamped {report.stamped} · "
          f"created {report.created} · unchanged {report.unchanged} · "
          f"errors {len(report.errors)}\n{BAR}")
    if report.errors:
        for e in report.errors:
            print(f"  ! {e}")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
