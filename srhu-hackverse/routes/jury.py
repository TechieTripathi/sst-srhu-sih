from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from utils.auth import roles_required
from models.jury import get_assigned_teams, is_team_assigned_to_jury
from models.team import get_team
from models.evaluation import (
    get_active_criteria, get_evaluation, upsert_draft_evaluation, submit_evaluation,
)
from services.scoring import validate_scores, ScoreValidationError

bp = Blueprint("jury", __name__, url_prefix="/jury")

DEFAULT_SLOT_SECONDS = 8 * 60  # 8-minute default presentation slot for the live timer


def _jury_id():
    return session.get("jury_id")


@bp.route("/dashboard")
@roles_required("jury")
def dashboard():
    jury_id = _jury_id()
    teams = get_assigned_teams(jury_id) if jury_id else []

    rows = []
    completed = 0
    for team in teams:
        ev = get_evaluation(jury_id, team["_id"])
        status = ev["status"] if ev else "pending"
        if status == "submitted":
            completed += 1
        rows.append({"team": team, "status": status, "score": ev.get("percentage") if ev else None})

    summary = {
        "assigned": len(teams),
        "evaluated": completed,
        "pending": len(teams) - completed,
        "avg_score": (
            round(sum(r["score"] for r in rows if r["score"] is not None) / completed, 1)
            if completed else 0
        ),
    }
    return render_template("jury_dashboard.html", rows=rows, summary=summary)


@bp.route("/evaluate/<team_id>", methods=["GET", "POST"])
@roles_required("jury")
def evaluate(team_id):
    jury_id = _jury_id()
    if not jury_id or not is_team_assigned_to_jury(jury_id, team_id):
        flash("You are not assigned to this team.", "danger")
        return redirect(url_for("jury.dashboard"))

    team = get_team(team_id)
    if not team:
        flash("Team not found.", "danger")
        return redirect(url_for("jury.dashboard"))

    criteria = get_active_criteria()
    existing = get_evaluation(jury_id, team_id)

    if existing and existing.get("status") == "submitted":
        return render_template("evaluation_view.html", team=team, evaluation=existing, locked=True)

    if request.method == "POST":
        action = request.form.get("action")
        submitted_scores = []
        for c in criteria:
            cid = str(c["_id"])
            value = request.form.get(f"score_{cid}")
            submitted_scores.append({"criterion_id": cid, "score": value})
        comments = request.form.get("comments", "")

        try:
            normalized = validate_scores(submitted_scores, criteria)
            evaluation = upsert_draft_evaluation(jury_id, team_id, normalized, comments)

            if action == "submit":
                submit_evaluation(jury_id, team_id)
                flash("Evaluation Submitted Successfully.", "success")
                return redirect(url_for("jury.dashboard"))

            flash("Draft saved.", "success")
            return redirect(url_for("jury.evaluate", team_id=team_id))

        except ScoreValidationError as exc:
            flash(str(exc), "danger")
        except PermissionError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("jury.dashboard"))

    return render_template(
        "evaluation.html", team=team, criteria=criteria, existing=existing,
    )


@bp.route("/session")
@roles_required("jury")
def session_view():
    """Live jury session — current / next team with a presentation timer.
    Ordered by presentation_slot when set, otherwise by team name."""
    jury_id = _jury_id()
    teams = get_assigned_teams(jury_id) if jury_id else []
    teams = sorted(teams, key=lambda t: (t.get("presentation_slot") or "zzz", t.get("team_name", "")))

    rows = []
    for team in teams:
        ev = get_evaluation(jury_id, team["_id"])
        rows.append({"team": team, "status": ev["status"] if ev else "pending"})

    current = next((r for r in rows if r["status"] != "submitted"), None)
    current_index = rows.index(current) if current else None
    next_row = rows[current_index + 1] if current_index is not None and current_index + 1 < len(rows) else None

    return render_template(
        "jury_session.html",
        current=current, next_row=next_row, rows=rows,
        timer_seconds=DEFAULT_SLOT_SECONDS,
    )
