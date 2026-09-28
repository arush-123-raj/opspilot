import os
import time
from celery import Celery

# Connect to Redis database 1 (FastAPI cache uses database 0)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"

celery_app = Celery("opspilot_tasks", broker=CELERY_BROKER_URL)

@celery_app.task
def send_incident_alert(incident_title: str, severity: str):
    # Simulate a slow network call (e.g., sending an email or Slack message)
    time.sleep(5)
    alert_msg = f"*** ALERT: High Severity Incident [{severity}] - '{incident_title}' declared! ***"
    print(alert_msg)
    return alert_msg
