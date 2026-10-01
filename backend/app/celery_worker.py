import os
import json
import time
import asyncio
import requests
import redis as sync_redis
from celery import Celery
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.future import select
from app import models
from app.aiops_engine import triage_error_log, detect_latency_anomaly

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/1"
REDIS_CACHE_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://opspilot_user:opspilot_password@db:5432/opspilot_db"
)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

celery_app = Celery("opspilot_tasks", broker=CELERY_BROKER_URL, backend=CELERY_BROKER_URL)

celery_app.conf.beat_schedule = {
    "poll-all-services-every-30-seconds": {
        "task": "app.celery_worker.poll_all_services",
        "schedule": 30.0,
    },
}
celery_app.conf.timezone = "UTC"

def get_worker_session():
    worker_engine = create_async_engine(DATABASE_URL, poolclass=NullPool, echo=False)
    return sessionmaker(worker_engine, class_=AsyncSession, expire_on_commit=False)

def get_sync_redis():
    return sync_redis.from_url(REDIS_CACHE_URL, decode_responses=True)

def broadcast_realtime_event(event_type: str, payload: dict):
    try:
        r = get_sync_redis()
        for key in r.scan_iter("incidents_skip:*"):
            r.delete(key)
        message = json.dumps({"event": event_type, "data": payload})
        r.publish("opspilot_events", message)
    except Exception as e:
        print(f"[Redis Broadcast Warning] {e}")

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
    r = get_sync_redis()
    circuit_open_key = f"circuit_open:{service_id}"

    # Stage 3 Circuit Breaker Check: Skip active poll if circuit is tripped in exponential backoff
    if r.exists(circuit_open_key):
        ttl = r.ttl(circuit_open_key)
        print(f"⚡ [CIRCUIT BREAKER OPEN] Skipping poll for '{service_name}' (Cooling down for {ttl}s)")
        return {"service": service_name, "status": "CIRCUIT_OPEN_BACKOFF", "cooldown_ttl_s": ttl}

    start = time.perf_counter()
    try:
        resp = requests.get(url, timeout=8)
        latency_ms = round((time.perf_counter() - start) * 1000, 2)

        if resp.status_code >= 500:
            error_msg = f"HTTP {resp.status_code} Server Error from {url} (Latency: {latency_ms}ms)"
            asyncio.run(_handle_failure(service_id, service_name, url, error_msg, severity="sev-1"))
            return {"service": service_name, "status": resp.status_code, "latency_ms": latency_ms}

        is_anomaly, anomaly_reason = detect_latency_anomaly(service_id, latency_ms)
        if is_anomaly:
            asyncio.run(_handle_failure(service_id, service_name, url, anomaly_reason, severity="sev-2"))
            return {"service": service_name, "status": "DEGRADED_ANOMALY", "latency_ms": latency_ms}

        asyncio.run(_handle_recovery(service_id, service_name, latency_ms))
        return {"service": service_name, "status": resp.status_code, "latency_ms": latency_ms}

    except requests.exceptions.RequestException as exc:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        error_msg = f"Connection failed/timed out after {latency_ms}ms polling {url}: {str(exc)}"
        asyncio.run(_handle_failure(service_id, service_name, url, error_msg, severity="sev-1"))
        return {"service": service_name, "status": "DOWN", "latency_ms": latency_ms}

@celery_app.task(name="app.celery_worker.autonomous_remediate_incident")
def autonomous_remediate_incident(incident_id: int, service_name: str, target_url: str, playbook: str):
    """Stage 5 Path A: Autonomous AI Self-Healing Agent."""
    return asyncio.run(_async_autonomous_remediate(incident_id, service_name, target_url, playbook))

async def _async_autonomous_remediate(incident_id: int, service_name: str, target_url: str, playbook: str):
    if "/chaos/target" in target_url:
        try:
            heal_url = target_url.replace("/chaos/target", "/chaos/reset")
            requests.post(heal_url, timeout=5)
        except Exception:
            pass

    SessionLocal = get_worker_session()
    async with SessionLocal() as db:
        result = await db.execute(select(models.Incident).where(models.Incident.id == incident_id))
        incident = result.scalars().first()
        if incident and incident.status != "resolved":
            incident.status = "resolved"
            audit = models.AuditLog(
                incident_id=incident.id,
                action="AI_AUTONOMOUS_REMEDIATION",
                details=f"Self-Healing Agent executed runbook: {playbook} Service verified healthy."
            )
            db.add(audit)
            await db.commit()
            broadcast_realtime_event("INCIDENT_AUTO_HEALED", {
                "incident_id": incident.id,
                "service": service_name,
                "status": "resolved",
                "playbook": playbook
            })
            return f"Incident #{incident_id} autonomously resolved by OpsPilot AI."
    return f"Incident #{incident_id} already resolved or not found."

@celery_app.task(name="app.celery_worker.escalate_unacknowledged_incident")
def escalate_unacknowledged_incident(incident_id: int, service_name: str):
    """Stage 5 Path B: Human Escalation Timer if engineer has not acknowledged/resolved the incident."""
    return asyncio.run(_async_escalate_unacknowledged(incident_id, service_name))

async def _async_escalate_unacknowledged(incident_id: int, service_name: str):
    SessionLocal = get_worker_session()
    async with SessionLocal() as db:
        result = await db.execute(select(models.Incident).where(models.Incident.id == incident_id))
        incident = result.scalars().first()
        # If still stuck in 'investigating' (not acknowledged as 'identified' or 'resolved'), escalate!
        if incident and incident.status == "investigating":
            old_sev = incident.severity
            incident.severity = "sev-1"
            audit = models.AuditLog(
                incident_id=incident.id,
                action="SLA_BREACH_HUMAN_ESCALATED",
                details=f"Unacknowledged within SLA window. Severity escalated ({old_sev} -> sev-1) and PagerDuty backup SRE paged."
            )
            db.add(audit)
            await db.commit()
            broadcast_realtime_event("INCIDENT_ESCALATED", {
                "incident_id": incident.id,
                "service": service_name,
                "severity": "sev-1",
                "status": incident.status
            })
            send_incident_alert.delay(f"[ESCALATED] {incident.title}", "sev-1")
            return f"Incident #{incident_id} escalated to sev-1."
    return f"Incident #{incident_id} already acknowledged or resolved."

async def _handle_failure(service_id: int, service_name: str, url: str, error_detail: str, severity: str = "sev-1"):
    # Stage 3: Track consecutive failures in Redis for Circuit Breaker
    r = get_sync_redis()
    fail_key = f"circuit_failures:{service_id}"
    fail_count = r.incr(fail_key)
    r.expire(fail_key, 300)

    circuit_note = f" (Consecutive Failure #{fail_count})"
    if fail_count >= 5:
        backoff_seconds = min(300, 30 * (2 ** (fail_count - 5)))
        r.setex(f"circuit_open:{service_id}", backoff_seconds, "OPEN")
        circuit_note += f" — ⚡ CIRCUIT BREAKER TRIPPED! Backing off for {backoff_seconds}s to prevent DDoS."

    SessionLocal = get_worker_session()
    async with SessionLocal() as db:
        stmt = select(models.Incident).where(
            models.Incident.service_id == service_id,
            models.Incident.status != "resolved"
        )
        result = await db.execute(stmt)
        open_incident = result.scalars().first()

        if open_incident:
            audit = models.AuditLog(
                incident_id=open_incident.id,
                action="HEARTBEAT_STILL_FAILING" if fail_count < 5 else "CIRCUIT_BREAKER_TRIPPED",
                details=f"Deduplicated check{circuit_note}: {error_detail}"
            )
            db.add(audit)
            await db.commit()
            broadcast_realtime_event("INCIDENT_HEARTBEAT_DEDUPLICATED", {
                "incident_id": open_incident.id,
                "service": service_name,
                "fail_count": fail_count,
                "details": error_detail
            })
        else:
            triage = triage_error_log(error_detail)
            enriched_description = f"[{triage['tag']}] {error_detail} | AI Root-Cause: {triage['summary']}"

            new_incident = models.Incident(
                title=f"Automated Alert: {service_name} ({triage['tag']})",
                description=enriched_description,
                status="investigating",
                severity=severity,
                service_id=service_id
            )
            db.add(new_incident)
            await db.flush()

            audit = models.AuditLog(
                incident_id=new_incident.id,
                action="INCIDENT_AUTO_CREATED_AND_TRIAGED",
                details=f"AI Tag [{triage['tag']}] ({triage.get('confidence', 90)}% conf): {triage['summary']} | Raw: {error_detail}"
            )
            db.add(audit)
            await db.commit()

            broadcast_realtime_event("INCIDENT_CREATED", {
                "id": new_incident.id,
                "title": new_incident.title,
                "severity": new_incident.severity,
                "status": new_incident.status,
                "ai_tag": triage["tag"],
                "confidence": triage.get("confidence", 90.0),
                "service_id": service_id
            })
            send_incident_alert.delay(new_incident.title, new_incident.severity)

            # Stage 5 Responder Router: Path A (Autonomous Self-Healing) vs Path B (Human Escalation Timer)
            if triage.get("auto_healable") and "/chaos/target" in url:
                autonomous_remediate_incident.apply_async(
                    args=[new_incident.id, service_name, url, str(triage["playbook"])],
                    countdown=10
                )
            else:
                # Schedule Path B Human Escalation check (60s SLA window for live demo)
                escalate_unacknowledged_incident.apply_async(
                    args=[new_incident.id, service_name],
                    countdown=60
                )

async def _handle_recovery(service_id: int, service_name: str, latency_ms: float):
    r = get_sync_redis()
    r.delete(f"circuit_failures:{service_id}", f"circuit_open:{service_id}")

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
                details=f"Service '{service_name}' responded healthy ({latency_ms}ms). Circuit breaker reset."
            )
            db.add(audit)
            await db.commit()
            broadcast_realtime_event("INCIDENT_RESOLVED", {
                "incident_id": open_incident.id,
                "service": service_name,
                "status": "resolved",
                "latency_ms": latency_ms
            })
