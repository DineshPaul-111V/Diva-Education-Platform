
import click

from flask.cli import with_appcontext
from app.extensions import db
from app.models.lesson_progress import LessonProgress
from app.learning.services.telemetry import SPACED_REPETITION_DECAY_DAYS, DECAY_MULTIPLIER
from datetime import datetime, timedelta

@click.command("decay-check")
@with_appcontext
def decay_check():
    """
    Spaced repetition decay job: reduces the mastery score of completed lessons 
    that have not been updated or reviewed in >14 days.
    """
    click.echo("Running spaced repetition decay check...")
    cutoff = datetime.utcnow() - timedelta(days=SPACED_REPETITION_DECAY_DAYS)
    
    stale_lessons = LessonProgress.query.filter(
        LessonProgress.status == "COMPLETED",
        LessonProgress.updated_at < cutoff
    ).all()
    
    decayed_count = 0
    for lesson in stale_lessons:
        # Decaying the mastery score by multiplying by DECAY_MULTIPLIER (0.8)
        old_score = lesson.mastery_score
        new_score = round(old_score * DECAY_MULTIPLIER, 1)
        lesson.mastery_score = new_score
        # Increment attempts count if required, or just let it update the timestamp
        lesson.updated_at = datetime.utcnow() # Reset timestamp so it doesn't decay again tomorrow
        decayed_count += 1
        
    db.session.commit()
    click.echo(f"Successfully decayed {decayed_count} stale lessons.")

def register_commands(app):
    app.cli.add_command(decay_check)
