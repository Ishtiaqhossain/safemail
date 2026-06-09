import logging
from datetime import datetime, timezone, timedelta

from app.worker import celery
from app.database import SyncSessionLocal
from app.models.parent import Parent
from app.models.child import Child
from app.models.alert import Alert
from app.models.weekly_stats import WeeklyStats

logger = logging.getLogger(__name__)


@celery.task(name="app.tasks.digest.send_all_weekly_digests")
def send_all_weekly_digests():
    with SyncSessionLocal() as db:
        parents = db.query(Parent).all()
        for parent in parents:
            send_parent_digest.delay(str(parent.id))


@celery.task(name="app.tasks.digest.send_parent_digest", bind=True, max_retries=3)
def send_parent_digest(self, parent_id: str):
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    from app.config import get_settings
    settings = get_settings()

    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday() + 1)).date()

    with SyncSessionLocal() as db:
        parent = db.get(Parent, parent_id)
        if not parent:
            return

        children = db.query(Child).filter(Child.parent_id == parent_id).all()
        sections = []

        for child in children:
            stats = db.query(WeeklyStats).filter(
                WeeklyStats.child_id == child.id,
                WeeklyStats.week_start == week_start,
            ).first()

            medium_low = db.query(Alert).filter(
                Alert.child_id == child.id,
                Alert.severity.in_(["medium", "low"]),
                Alert.created_at >= datetime.combine(week_start, datetime.min.time()).replace(tzinfo=timezone.utc),
                Alert.notified_at.is_(None),
            ).all()

            sections.append(_build_child_section(child, stats, medium_low))

            for alert in medium_low:
                alert.notified_at = now
            db.commit()

        if not sections:
            return

        html = "<h2>OpenBark Weekly Summary</h2>" + "".join(sections)
        msg = Mail(
            from_email="digest@openbark.com",
            to_emails=parent.email,
            subject="Your OpenBark Weekly Summary",
            html_content=html,
        )
        try:
            SendGridAPIClient(settings.sendgrid_api_key).send(msg)
        except Exception as e:
            logger.error("Digest email failed for %s: %s", parent.email, e)
            raise self.retry(exc=e, countdown=300)


def _build_child_section(child, stats, alerts) -> str:
    total = stats.total_emails if stats else 0
    lines = [f"<h3>{child.display_name}</h3>", f"<p>{total} emails scanned this week.</p>"]
    if alerts:
        lines.append("<ul>")
        for a in alerts:
            lines.append(f"<li><strong>{a.severity.upper()}</strong> — {a.ai_summary}</li>")
        lines.append("</ul>")
    else:
        lines.append("<p>No concerns detected.</p>")
    return "".join(lines)


@celery.task(name="app.tasks.digest.cleanup_old_data")
def cleanup_old_data():
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    with SyncSessionLocal() as db:
        deleted = db.query(Alert).filter(Alert.created_at < cutoff).delete()
        db.commit()
        logger.info("Deleted %d alerts older than 12 months", deleted)
