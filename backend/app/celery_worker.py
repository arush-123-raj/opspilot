import os
import time
import asyncio
import requests
from celery import Celery
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.future import select
from app import models

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://opspilot_user:opspilot_password@db:5432/opspilot_db"
)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

celery_app = Celery("opspilot_tasks", broker=CELERY_BROKER_URL, backend=CELERY_BROKER_URL)

# Schedule active health polling every 30 seconds via Celery Beat
celery_app.conf.beat_schedule = {
    "poll-all-services-every-30-seconds": {
        "task": "app.celery_worker.poll_all_services",
        "schedule": 30.0,
    },
}
celery_app.conf.timezone = "UTC"


def get_worker_session():
    """Creates an isolated AsyncSession with NullPool for safe asyncio execution inside Celery."""
    worker_engine = create_async_engine(DATABASE_URL, poolclass=NullPool, echo=False)
    return sessionmaker(worker_engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task
def send_incident_alert(incident_title: str, severity: str):
    alert_msg = f"🚨 *ALERT: High Severity Incident [{severity.upper()}]* 🚨\nTitle: {incident_title}"
    print(alert_msg)

    if WEBHOOK_URL:
        try:
            response = requests.post(WEBHOOK_URL, json={"text": alert_msg, "content": alert_msg}, timeout=5)
            response.raise_for_status()
            return "Alert dispatched successfully"
        except Exception as e:
            return f"Failed to dispatch alert: {str(e)}"

    return "Webhook URL not configured. Logged to console only."


@celery_app.task(name="app.celery_worker.poll_all_services")
def poll_all_services():
    """Fan-Out Dispatcher: Fetches all services with a valid HTTP URL and spawns parallel health checks."""
    return asyncio.run(_async_poll_all_services())


async def _async_poll_all_services():
    SessionLocal = get_worker_session()
    async with SessionLocal() as db:
        result = await db.execute(select(models.Service))
        services = result.scalars().all()
        dispatched = 0
        for svc in services:
            if svc.repository_url and svc.repository_url.startswith(("http://", "https://")):
                check_single_service.delay(svc.id, svc.name, svc.repository_url)
                dispatched += 1
        return f"Dispatched active health checks for {dispatched} services."


@celery_app.task(name="app.celery_worker.check_single_service")
def check_single_service(service_id: int, service_name: str, url: str):
    """Pings target service URL, measures response latency, and runs Deduplication / Auto-Recovery."""
    start = time.perf_counter()
    try:
        resp = requests.get(url, timeout=8)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        if resp.status_code >= 500:
            error_msg = f"HTTP {resp.status_code} Server Error from {url} (Latency: {latency_ms}ms)"
            asyncio.run(_handle_failure(service_id, service_name, error_msg))
            return {"service": service_name, "status": resp.status_code, "latency_ms": latency_ms}
        else:
            asyncio.run(_handle_recovery(service_id, service_name, latency_ms))
            return {"service": service_name, "status": resp.status_code, "latency_ms": latency_ms}

    except requests.exceptions.RequestException as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        error_msg = f"Connection failed/timed out after {latency_ms}ms polling {url}: {str(exc)}"
        asyncio.run(_handle_failure(service_id, service_name, error_msg))
        return {"service": service_name, "status": "DOWN", "latency_ms": latency_ms}


async def _handle_failure(service_id: int, service_name: str, error_detail: str):
    SessionLocal = get_worker_session()
    async with SessionLocal() as db:
        # Check if an unresolved incident already exists for this service (Smart Deduplication)
        stmt = select(models.Incident).where(
            models.Incident.service_id == service_id,
            models.Incident.status != "resolved"
        )
        result = await db.execute(stmt)
        open_incident = result.scalars().first()

        if open_incident:
            # Deduplicate: Do not create a duplicate incident! Record heartbeat failure in AuditLog
            audit = models.AuditLog(
                incident_id=open_incident.id,
                action="HEARTBEAT_STILL_FAILING",
                details=f"Deduplicated check — service remains unreachable. {error_detail}"
            )
            db.add(audit)
            await db.commit()
            print(f"[DEDUPLICATED] Service '{service_name}' still down (Incident #{open_incident.id})")
        else:
            # Brand new outage -> Create SEV-1 Incident + AuditLog + Trigger Alert
            new_incident = models.Incident(
                title=f"Automated Outage: {service_name} is unreachable",
                description=error_detail,
                status="investigating",
                severity="sev-1",
                service_id=service_id
            )
            db.add(new_incident)
            await db.flush()

            audit = models.AuditLog(
                incident_id=new_incident.id,
                action="INCIDENT_AUTO_CREATED",
                details=f"Triggered automatically by Celery Active Poller. {error_detail}"
            )
            db.add(audit)
            await db.commit()
            print(f"[NEW OUTAGE] Created Incident #{new_incident.id} for '{service_name}'")
            send_incident_alert.delay(new_incident.title, new_incident.severity)


async def _handle_recovery(service_id: int, service_name: str, latency_ms: float):
    SessionLocal = get_worker_session()
    async with SessionLocal() as db:
        stmt = select(models.Incident).where(
            models.Incident.service_id == service_id,
            models.Incident.status != "resolved"
        )
        result = await db.execute(stmt)
        open_incident = result.scalars().first()

        if open_incident:
            open_incident.status = "resolved"
            audit = models.AuditLog(
                incident_id=open_incident.id,
                action="AUTO_RESOLVED_ON_RECOVERY",
                details=f"Service '{service_name}' recovered and responded healthy ({latency_ms}ms)."
            )
            db.add(audit)
            await db.commit()
            print(f"[AUTO-RESOLVED] Incident #{open_incident.id} for '{service_name}' marked resolved!")
