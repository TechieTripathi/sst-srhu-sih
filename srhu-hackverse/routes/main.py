from flask import Blueprint, render_template, current_app
from models.team import count_teams
from models.jury import count_jury
from models.evaluation import count_completed

bp = Blueprint("main", __name__)


@bp.route("/")
def landing():
    stats = {
        "total_teams": count_teams(),
        "total_jurors": count_jury(),
        "evaluations_done": count_completed(),
    }
    return render_template(
        "landing.html",
        event_name=current_app.config["EVENT_NAME"],
        tagline=current_app.config["EVENT_TAGLINE"],
        stats=stats,
    )
