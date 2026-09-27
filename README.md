# OpsPilot

OpsPilot is an AI-powered incident management and observability platform designed to ingest distributed system logs, detect operational anomalies, correlate failures across microservices, and generate automated root-cause diagnostics and postmortems.

---

## Architecture Stack (Phase 1 Baseline)

- **Backend:** Python / FastAPI (Asynchronous ASGI gateway)
- **Frontend:** React / TypeScript / Vite
- **Data Layer:** PostgreSQL 16
- **Message Broker & Cache:** Redis 7
- **Orchestration:** Docker Compose

---

## Local Development Setup

### 1. Prerequisites
- Docker Engine & Docker Compose (v2+)
- Python 3.11+
- Node.js (v20+ LTS) & npm

### 2. Environment Configuration
Copy the development environment template:
```bash
cp .env.example .env
```

### 3. Start Database & Message Broker
Start PostgreSQL and Redis containers in detached mode:
```bash
docker compose up -d
```
Verify both containers are healthy:
```bash
docker compose ps
```

### 4. Run the Backend API
Set up the Python virtual environment and launch Uvicorn:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Verify health check:
```bash
curl http://localhost:8000/health
```

### 5. Run the Frontend Dashboard
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```
The dashboard runs at `http://localhost:5173`.
