import json
import uuid
import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Response, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Set
from jose import JWTError, jwt

from app import models, schemas, crud, security
from app.database import get_db, engine, Base
from app.redis_client import redis_db
from app.celery_worker import send_incident_alert, poll_all_services

# --- Phase 3: Active WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: str):
        dead_connections = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead_connections.append(connection)
        for dead in dead_connections:
            self.active_connections.discard(dead)

ws_manager = ConnectionManager()

# --- Phase 5: Chaos Engineering State Simulator ---
CHAOS_STATE = {
    "mode": "healthy",      # healthy | error_500 | latency_spike
    "delay_ms": 0
}


async def redis_pubsub_listener():
    """Listens to Redis Pub/Sub channel 'opspilot_events' and forwards events to all WebSocket clients."""
    while True:
        try:
            pubsub = redis_db.pubsub()
            await pubsub.subscribe("opspilot_events")
            async for message in pubsub.listen():
                if message and message.get("type") == "message":
                    await ws_manager.broadcast(message["data"])
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[WebSocket Pub/Sub Listener Reconnecting] {e}")
            await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure all tables (Users, Services, Incidents, AuditLogs) exist in PostgreSQL
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Start background Redis Pub/Sub -> WebSocket relay
    listener_task = asyncio.create_task(redis_pubsub_listener())
    yield
    listener_task.cancel()


app = FastAPI(title="OpsPilot AIOps Platform", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Trace-ID", "X-Process-Time-Ms", "X-Cache"],
)


# --- Phase 3: Distributed Tracing Middleware (OpenTelemetry-style Trace Propagation) ---
@app.middleware("http")
async def distributed_tracing_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID", f"trace-{uuid.uuid4().hex[:12]}")
    start_time = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Process-Time-Ms"] = str(duration_ms)
    return response


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        email: str = payload.get("email")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await crud.get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    return user


@app.get("/health")
async def health_check():
    try:
        await redis_db.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"disconnected: {str(e)}"
    return {
        "status": "healthy",
        "version": "2.0.0-aiops",
        "redis": redis_status,
        "chaos_mode": CHAOS_STATE["mode"]
    }


# --- Phase 3: Live WebSocket Stream Endpoint ---
@app.websocket("/ws/incidents")
async def websocket_incidents_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps({
            "event": "WS_CONNECTED",
            "data": {"message": "Connected to OpsPilot Real-Time Incident Stream"}
        }))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.post("/login", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_email(db, email=form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    access_token = security.create_access_token(data={"email": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/users/", response_model=schemas.UserResponse, status_code=201)
async def create_user(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return await crud.create_user(db=db, user=user)


@app.post("/services/", response_model=schemas.ServiceResponse, status_code=201)
async def create_service(service: schemas.ServiceCreate, db: AsyncSession = Depends(get_db)):
    db_service = await crud.get_service_by_name(db, name=service.name)
    if db_service:
        raise HTTPException(status_code=400, detail="Service name already registered")
    return await crud.create_service(db=db, service=service)


@app.get("/services/", response_model=List[schemas.ServiceResponse])
async def read_services(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.get_services(db, skip=skip, limit=limit)


@app.post("/incidents/", response_model=schemas.IncidentResponse, status_code=201)
async def create_incident(incident: schemas.IncidentCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_service = await crud.get_service(db, service_id=incident.service_id)
    if not db_service:
        raise HTTPException(status_code=404, detail="Linked Service not found")

    new_incident = await crud.create_incident(db=db, incident=incident)
    await redis_db.flushdb()

    # Broadcast over Redis Pub/Sub -> WebSockets
    event_payload = schemas.IncidentResponse.model_validate(new_incident).model_dump(mode="json")
    await redis_db.publish("opspilot_events", json.dumps({"event": "INCIDENT_CREATED", "data": event_payload}))

    if new_incident.severity in ["sev-1", "sev-2"]:
        send_incident_alert.delay(new_incident.title, new_incident.severity)

    return new_incident


@app.get("/incidents/", response_model=List[schemas.IncidentResponse])
async def read_incidents(response: Response, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    cache_key = f"incidents_skip:{skip}_limit:{limit}"
    cached_data = await redis_db.get(cache_key)
    if cached_data:
        response.headers["X-Cache"] = "HIT"
        return json.loads(cached_data)

    response.headers["X-Cache"] = "MISS"
    incidents = await crud.get_incidents(db, skip=skip, limit=limit)
    incident_responses = [schemas.IncidentResponse.model_validate(i).model_dump(mode='json') for i in incidents]
    await redis_db.setex(cache_key, 30, json.dumps(incident_responses))
    return incidents


@app.patch("/incidents/{incident_id}", response_model=schemas.IncidentResponse)
async def update_incident(incident_id: int, incident_update: schemas.IncidentUpdate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_incident = await crud.get_incident(db, incident_id=incident_id)
    if not db_incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    updated_incident = await crud.update_incident(db, db_incident=db_incident, incident_update=incident_update)
    await redis_db.flushdb()

    event_payload = schemas.IncidentResponse.model_validate(updated_incident).model_dump(mode="json")
    await redis_db.publish("opspilot_events", json.dumps({"event": "INCIDENT_UPDATED", "data": event_payload}))

    return updated_incident


# --- Phase 1/4: Incident Millisecond Audit Trail Endpoint ---
@app.get("/incidents/{incident_id}/audit-logs", response_model=List[schemas.AuditLogResponse])
async def read_incident_audit_logs(incident_id: int, db: AsyncSession = Depends(get_db)):
    return await crud.get_incident_audit_logs(db, incident_id=incident_id)


# --- Phase 5: Chaos Engineering Simulator Endpoints ---
@app.get("/chaos/target")
async def chaos_target_service():
    """Simulated microservice endpoint monitored by Celery Active Polling."""
    if CHAOS_STATE["mode"] == "latency_spike":
        await asyncio.sleep(CHAOS_STATE["delay_ms"] / 1000.0)
        return {"status": "degraded", "simulated_delay_ms": CHAOS_STATE["delay_ms"]}
    if CHAOS_STATE["mode"] == "error_500":
        raise HTTPException(
            status_code=500,
            detail="FATAL: Simulated 500 Upstream Gateway Crash — database connection pool exhausted"
        )
    return {"status": "healthy", "service": "Chaos-Target-Microservice"}


@app.post("/chaos/inject")
async def inject_chaos(mode: str = "error_500", delay_ms: int = 2200, db: AsyncSession = Depends(get_db)):
    """
    Triggers a live failure or latency anomaly and ensures a monitored Service exists
    pointing to http://api:8000/chaos/target, then immediately dispatches a Celery poll!
    """
    CHAOS_STATE["mode"] = mode
    CHAOS_STATE["delay_ms"] = delay_ms

    # Ensure demo service exists so Celery monitors it automatically
    demo_svc = await crud.get_service_by_name(db, name="Payment-Gateway-API")
    if not demo_svc:
        demo_svc = await crud.create_service(
            db,
            schemas.ServiceCreate(
                name="Payment-Gateway-API",
                description="Core payment microservice monitored by OpsPilot AIOps",
                repository_url="http://api:8000/chaos/target"
            )
        )

    # Trigger immediate Celery poll so the interviewer sees instant detection!
    poll_all_services.delay()

    await redis_db.publish("opspilot_events", json.dumps({
        "event": "CHAOS_INJECTED",
        "data": {"mode": mode, "delay_ms": delay_ms, "target_service": demo_svc.name}
    }))
    return {
        "message": f"Chaos mode '{mode}' injected on {demo_svc.name}. Celery poll dispatched!",
        "chaos_state": CHAOS_STATE
    }


@app.post("/chaos/reset")
async def reset_chaos():
    CHAOS_STATE["mode"] = "healthy"
    CHAOS_STATE["delay_ms"] = 0
    poll_all_services.delay()
    return {"message": "Chaos reset to healthy.", "chaos_state": CHAOS_STATE}


from app.aiops_engine import load_trained_artifacts

@app.post("/aiops/retrain")
async def retrain_aiops_models():
    metrics = load_trained_artifacts(force_retrain=True)
    return {"status": "retrained", "model_artifact": "aiops_model_weights.npz", "metrics": metrics}
