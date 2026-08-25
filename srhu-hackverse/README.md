# TechForge 3.0 - Internal Hackathon Jury & Evaluation Platform

Official judging and evaluation platform for **TechForge 3.0**, the 36-hours Internal Hackathon organized by the School of Science & Technology (SST), Swami Rama Himalayan University (SRHU).

**Institutional Selection Round aligned with Smart India Hackathon (SIH) 2026**

## Features

- **Student Leader Registration** - Team registration with validation
- **Dual Judge System** - Separate Internal and External judge roles
- **Evaluation Matrix** - Six-criterion scoring system with official weights
- **Jury Panels** - Multiple jury panel management
- **Real-time Scoring** - Backend-calculated weighted scores
- **Results Engine** - Internal 40% + External 60% final scoring
- **Audit Logging** - Complete activity tracking
- **Role-Based Access** - Secure authorization for all roles
- **Responsive Design** - Mobile, tablet, and desktop support
- **SRHU Brand Identity** - Official institutional styling

## Technology Stack

- **Backend**: Python 3.x, Flask 3.0.0
- **Database**: MongoDB Atlas (PyMongo)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Authentication**: Flask Sessions, Werkzeug Password Hashing
- **Deployment**: Can be deployed on any WSGI-compatible platform

## Installation

### Prerequisites

- Python 3.8 or higher
- MongoDB Atlas account (or local MongoDB)
- pip package manager

### Setup

1. **Clone the repository**
   ```bash
   cd d:\Hackathon_Platforms\srhu-hackverse
   ```

2. **Create virtual environment** (recommended)
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   
   Copy `.env.example` to `.env` and update with your MongoDB connection string:
   ```
   MONGO_URI=your_mongodb_connection_string
   SECRET_KEY=your_secret_key
   ```

5. **Initialize database**
   
   Run the initialization script to set up evaluation criteria and create admin user:
   ```bash
   python init_db.py
   ```

6. **Run the application**
   ```bash
   python app.py
   ```

7. **Access the platform**
   
   Open your browser and navigate to:
   ```
   http://localhost:5000
   ```

## Default Credentials

After initialization, use these credentials to log in as admin:

- **Email**: admin@srhu.edu.in
- **Password**: admin123

**⚠️ IMPORTANT**: Change the admin password immediately after first login.

## User Roles & Authentication

### Jury (Internal & External) — Secure Email + OTP Authentication

Jury authentication uses a dedicated passwordless flow. Jury accounts are pre-authorized in the database and authenticate strictly via email-delivered 6-digit one-time passcodes (OTP).

```text
Official Judge Email
        ↓
Cryptographic 6-Digit OTP Generated
        ↓
Delivered via SMTP Email (5 min expiry)
        ↓
Single-Use Verification & Audit Log
        ↓
Jury Dashboard (Internal / External)
```

- **Internal Jury**: Evaluates assigned teams per panel (Contributes **40%** to final score).
- **External Jury**: Evaluates allocated presentations (Contributes **60%** to final score).
- **Official Internal Panels (25 Pre-authorized Faculty Members)**:
  - `PANEL_1`: Dr. Neel Mani (Overall Coordinator), Er. Deepak Srivastava, Er. Vivek Katiyar, Dr. Shefali Khatri, Er. Sanjay Kumar
  - `PANEL_2`: Dr. L.K. Tyagi, Dr. Suman Pant, Er. A.K. Choudhary, Er. Radhe Shankar, Dr. Gaurav Aggarwal
  - `PANEL_3`: Dr. Rohit Kanauzia, Dr. Anupama Mishra, Dr. Shivpreet, Er. Rachit Lakhera, Er. Vinod Raturi
  - `PANEL_4`: Dr. Ashutosh Bhatt, Dr. Shikha Singh, Dr. Pooja Joshi, Er. Vibhor Sharma, Er. Princy Tyagi
  - `PANEL_5`: Dr. Gunjan Chhabra, Dr. Gaurav Sharma, Dr. Vaishali Gupta, Dr. Shivani Pant, Dr. Neelam Danu
- **Seeding Jury Members**:
  ```bash
  python seed_judges.py
  ```

### SMTP Email Configuration

Configure the following environment variables in `.env`:
```env
SMTP_HOST=smtp.gmail.com # or university SMTP server
SMTP_PORT=587
SMTP_USERNAME=your-email@srhu.edu.in
SMTP_PASSWORD=your-app-password
SMTP_FROM=techforge@srhu.edu.in
SMTP_USE_TLS=true
```

### Super Admin & Admin
- **Super Administrator**: Apex authority with full admin governance, audit trail inspection, and global event locks.
- **Admin**: Standard event management, jury coordination, criteria configuration, and CSV export.

## Evaluation Criteria

| Criterion | Weight |
|-----------|--------|
| Problem Understanding & Relevance | 15% |
| Innovation & Differentiation | 15% |
| Technical Design & Feasibility | 20% |
| Prototype & Implementation | 25% |
| Impact, Scalability & Sustainability | 15% |
| Presentation & Team Response | 10% |
| **Total** | **100%** |

**Raw Score Range**: 0-10 for each criterion

**Final Score Calculation**:
- Internal Average: 40%
- External Average: 60%

## Project Structure

```
srhu-hackverse/
│
├── app.py                      # Main Flask application
├── config.py                   # Configuration settings
├── init_db.py                  # Database initialization script
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (not in git)
├── .env.example               # Environment template
│
├── models/
│   ├── __init__.py
│   └── database.py            # MongoDB connection manager
│
├── routes/
│   ├── __init__.py
│   ├── auth.py                # Authentication routes
│   ├── admin.py               # Admin dashboard routes
│   ├── judge.py               # Judge dashboard routes
│   ├── teams.py               # Team registration routes
│   ├── evaluations.py         # Evaluation API routes
│   └── results.py             # Results and leaderboard
│
├── services/
│   ├── __init__.py
│   ├── audit.py               # Audit logging service
│   └── init_data.py           # Database initialization
│
├── templates/
│   ├── base.html              # Base template
│   ├── landing.html           # Landing page
│   ├── auth/
│   │   └── login.html         # Login page
│   ├── admin/
│   ├── judge/
│   ├── teams/
│   ├── results/
│   └── errors/
│       └── error.html         # Error pages
│
└── static/
    ├── css/
    │   ├── variables.css      # CSS custom properties
    │   ├── base.css           # Base styles
    │   ├── layout.css         # Layout components
    │   ├── components.css     # Reusable components
    │   └── main.css           # Main stylesheet
    └── js/
        └── main.js            # JavaScript utilities
```

## Security Features

- Server-side role-based access control (RBAC)
- Password hashing with Werkzeug
- Secure session management
- MongoDB injection prevention
- Input validation (frontend + backend)
- Audit logging for all critical actions
- Duplicate evaluation prevention
- Immutable evaluation submissions

## Database Collections

- `users` - All user accounts
- `teams` - Registered teams
- `team_members` - Team member details
- `judges` - Judge records
- `jury_panels` - Jury panel assignments
- `judge_assignments` - Team-judge mappings
- `evaluation_criteria` - Scoring criteria
- `evaluation_stages` - Checkpoint configurations
- `evaluations` - Submitted evaluations
- `evaluation_scores` - Raw scores per criterion
- `results` - Calculated final results
- `audit_logs` - Activity audit trail
- `event_settings` - Global event configuration

## Development

### Running in Development Mode

```bash
export FLASK_ENV=development  # Linux/Mac
set FLASK_ENV=development     # Windows CMD
$env:FLASK_ENV="development"  # Windows PowerShell

python app.py
```

### Running in Production

1. Set production environment variables
2. Use a production WSGI server (Gunicorn, uWSGI)
3. Enable HTTPS
4. Set strong SECRET_KEY
5. Configure proper MongoDB security

## Event Information

- **Event Name**: TechForge 3.0
- **Duration**: 36 Hours
- **Dates**: 26-27 August 2026
- **Organizer**: School of Science & Technology (SST), SRHU
- **Purpose**: Institutional screening for SIH 2026 nomination

## Support

For technical issues or questions:

**SPOC**: Dr. Gaurav Sharma  
**Email**: Contact event coordinators

**Coordinators**:
- Dr. Rohit Kanauzia
- Dr. Gunjan Chhabra
- Ms. Simranjeet Kaur

## License

Internal use only for TechForge 3.0 event management by SRHU.

## Acknowledgments

Built for Swami Rama Himalayan University's TechForge 3.0 Internal Hackathon, aligned with Smart India Hackathon 2026.

**Life Ka Compass** - SRHU
