"""
TechForge 3.0 — Database Inspection Script
Inspects current collections and documents to identify dummy/test data.
"""

from app import create_app
from models.database import Database

app = create_app()
with app.app_context():
    db = Database.db
    print("\n=== Current Database State ===")
    for col_name in sorted(db.list_collection_names()):
        col = db[col_name]
        count = col.count_documents({})
        print(f"\nCollection: {col_name} ({count} documents)")
        for doc in col.find().limit(5):
            # Print summary of doc
            doc_id = str(doc.get('_id'))
            name = doc.get('name') or doc.get('team_name') or doc.get('panel_name') or doc.get('action') or doc.get('criterion_id')
            email = doc.get('email') or doc.get('leader_email')
            print(f"  - [{doc_id}] {name} ({email})")
