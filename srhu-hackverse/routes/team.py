from flask import Blueprint, render_template, session, flash, redirect, url_for
from utils.auth import roles_required
from models.team import get_team
from services.results import get_results_published, build_leaderboard

bp = Blueprint("team", __name__, url_prefix="/team")

HACKATHON_ID = "srhu-hackverse-2026"


@bp.route("/dashboard")
@roles_required("team")
def dashboard():
    team_id = session.get("team_id")
    team = get_team(team_id) if team_id else None
    if not team:
        flash("No team profile linked to this account yet.", "warning")
    return render_template("team_dashboard.html", team=team)


@bp.route("/results")
@roles_required("team")
def my_results():
    if not get_results_published(HACKATHON_ID):
        return render_template("results.html", leaderboard=[], published=False, is_admin=False)
    return render_template("results.html", leaderboard=build_leaderboard(), published=True, is_admin=False)
