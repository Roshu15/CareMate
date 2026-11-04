"""Send queued CareMate notifications to subscribed browsers via Web Push."""
import json
import logging
import os
from pathlib import Path

from . import database as store

log = logging.getLogger("caremate.push")


def _vapid_settings():
    public = os.getenv("CAREMATE_VAPID_PUBLIC_KEY", "").strip()
    private = os.getenv("CAREMATE_VAPID_PRIVATE_KEY", "").replace("\\n", "\n").strip()
    subject = os.getenv("CAREMATE_VAPID_SUBJECT", "mailto:admin@example.com")
    if not public or not private:
        config_path = Path(__file__).resolve().parents[1] / ".local_vapid_keys.json"
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            public = public or config.get("public_key", "")
            private = private or config.get("private_key", "")
        except (OSError, ValueError):
            pass
    return public, private, subject


def vapid_public_key():
    return _vapid_settings()[0]


def send_pending_pushes():
    public_key, private_key, subject = _vapid_settings()
    if not private_key or not public_key:
        return
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        log.error("Push delivery is configured but pywebpush is not installed")
        return

    with store.connection() as db:
        rows = db.execute("""SELECT n.id,n.user_id,n.title,n.body,n.kind
            FROM notifications n WHERE n.user_id IS NOT NULL AND n.push_sent=0
            ORDER BY n.id LIMIT 50""").fetchall()
        for note in rows:
            subscriptions = db.execute(
                "SELECT endpoint,p256dh,auth FROM push_subscriptions WHERE user_id=?",
                (note["user_id"],),
            ).fetchall()
            if not subscriptions:
                continue
            all_delivered = True
            # Keep medicine and patient details off lock screens.
            payload = json.dumps({"title": "CareMate alert", "body": "Open CareMate to review a new care alert.", "id": note["id"]})
            for sub in subscriptions:
                try:
                    webpush(
                        subscription_info={
                            "endpoint": sub["endpoint"],
                            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                        },
                        data=payload,
                        vapid_private_key=private_key,
                        vapid_claims={"sub": subject},
                        ttl=3600,
                        timeout=10,
                    )
                except WebPushException as error:
                    status = getattr(getattr(error, "response", None), "status_code", None)
                    if status in (404, 410):
                        db.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (sub["endpoint"],))
                    else:
                        all_delivered = False
                        log.warning("Web Push delivery failed for notification %s (HTTP %s)", note["id"], status)
                except Exception:
                    all_delivered = False
                    log.exception("Web Push delivery failed for notification %s", note["id"])
            if all_delivered:
                db.execute("UPDATE notifications SET push_sent=1 WHERE id=?", (note["id"],))
