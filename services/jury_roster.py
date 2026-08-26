"""
TechForge 3.0 official jury roster — data only, no I/O.

Single source of truth for who is on which panel and who is exception jury,
shared by seed_judges.py (fresh databases) and migrate_jury_panels.py (the
existing one).

  * 25 group jury across 5 panels of 5, weighted 60%, each panel scoring only
    its own assigned teams.
  * 3 exception jury outside every panel, weighted 40%, scoring every team and
    able to keep scoring while judging is locked.
"""

# Already present in the database as INTERNAL_JUDGE with SRHU mailboxes.
# 'name' is the corrected spelling to write; matching is always on email.
EXCEPTION_JURY = [
    {'email': 'sanjaykumar@srhu.edu.in',  'name': 'Mr. Sanjay Kumar'},        # was 'Er. Sanjay Kumar'
    {'email': 'akchoudhary@srhu.edu.in',  'name': 'Dr. Ashutosh Chaudhary'},  # was 'Er. A.K. Choudhary'
    {'email': 'gauravsharma@srhu.edu.in', 'name': 'Dr. Gaurav Sharma'},       # unchanged
]

# The three guests marked has_mailbox=False are outside the university and have
# no address that can receive mail, so their placeholder addresses are written
# out in full rather than derived from their names - deriving would need title
# stripping ('Prof. Sunil Semwal' -> 'sunil') and belongs in a reviewable diff.
# Checked: 'anupama.techforge@techforge' does not collide with the existing
# 'anupamamishra@srhu.edu.in' under the unique index on email.
GROUP_JURY = [
    # Panel 1
    {'panel_no': 1, 'name': 'Dr. Neel Mani',         'email': 'neelmani@srhu.edu.in', 'is_coordinator': True},
    {'panel_no': 1, 'name': 'Er. Deepak Srivastava', 'email': 'deepaksrivastava@srhu.edu.in'},
    {'panel_no': 1, 'name': 'Er. Vivek Katiyar',     'email': 'vivekkatiyar@srhu.edu.in'},
    {'panel_no': 1, 'name': 'Dr. Shefali Khatri',    'email': 'shefalikhatri@srhu.edu.in'},
    {'panel_no': 1, 'name': 'Dr. Raksha Sharma',     'email': 'raksha.techforge@techforge',
     'judge_type': 'EXTERNAL_JUDGE', 'has_mailbox': False},

    # Panel 2
    {'panel_no': 2, 'name': 'Dr. L.K. Tyagi',        'email': 'lktyagi@srhu.edu.in'},
    {'panel_no': 2, 'name': 'Dr. Suman Pant',        'email': 'sumanpant@srhu.edu.in'},
    {'panel_no': 2, 'name': 'Prof. Sunil Semwal',    'email': 'sunil.techforge@techforge',
     'judge_type': 'EXTERNAL_JUDGE', 'has_mailbox': False},
    {'panel_no': 2, 'name': 'Er. Radhe Shankar',     'email': 'radheshankar@srhu.edu.in'},
    {'panel_no': 2, 'name': 'Dr. Gaurav Aggarwal',   'email': 'gauravaggarwal@srhu.edu.in'},

    # Panel 3
    {'panel_no': 3, 'name': 'Dr. Rohit Kanauzia',    'email': 'rohitkanauzia@srhu.edu.in'},
    {'panel_no': 3, 'name': 'Dr. Anupama Mishra',    'email': 'anupamamishra@srhu.edu.in'},
    {'panel_no': 3, 'name': 'Dr. Shivpreet',         'email': 'shivpreet@srhu.edu.in'},
    {'panel_no': 3, 'name': 'Er. Rachit Lakhera',    'email': 'rachitlakhera@srhu.edu.in'},
    {'panel_no': 3, 'name': 'Er. Vinod Raturi',      'email': 'vinodraturi@srhu.edu.in'},

    # Panel 4
    {'panel_no': 4, 'name': 'Dr. Ashutosh Bhatt',    'email': 'ashutoshbhatt@srhu.edu.in'},
    {'panel_no': 4, 'name': 'Dr. Shikha Singh',      'email': 'shikhasingh@srhu.edu.in'},
    {'panel_no': 4, 'name': 'Er. Vibhor Sharma',     'email': 'vibhorsharma@srhu.edu.in'},
    {'panel_no': 4, 'name': 'Dr. Pooja Joshi',       'email': 'poojajoshi@srhu.edu.in'},
    {'panel_no': 4, 'name': 'Er. Princy Tyagi',      'email': 'princytyagi@srhu.edu.in'},

    # Panel 5
    {'panel_no': 5, 'name': 'Dr. Gunjan Chhabra',    'email': 'gunjanchhabra@srhu.edu.in'},
    {'panel_no': 5, 'name': 'Dr. Anupama Namburu',   'email': 'anupama.techforge@techforge',
     'judge_type': 'EXTERNAL_JUDGE', 'has_mailbox': False},
    {'panel_no': 5, 'name': 'Dr. Vaishali Gupta',    'email': 'vaishaligupta@srhu.edu.in'},
    {'panel_no': 5, 'name': 'Dr. Shivani Pant',      'email': 'shivanipant@srhu.edu.in'},
    {'panel_no': 5, 'name': 'Dr. Neelam Danu',       'email': 'Neelamdanu@srhu.edu.in'},
]

# Every judge who has a real SRHU mailbox, i.e. everyone the credential emailer
# may legitimately target. seed_judges.py exposes this as
# OFFICIAL_INTERNAL_JUDGES, which the test suite imports and asserts is 25.
MAILBOX_JURY = (
    [dict(j) for j in EXCEPTION_JURY]
    + [dict(j) for j in GROUP_JURY if j.get('has_mailbox', True)]
)


def has_mailbox(entry):
    return entry.get('has_mailbox', True)


def guests():
    """Group jury with no university mailbox - credentials shown on screen."""
    return [j for j in GROUP_JURY if not has_mailbox(j)]
