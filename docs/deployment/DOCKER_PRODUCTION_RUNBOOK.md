# Docker Production Runbook — Aegis Sentinel AI

## Overview

This runbook covers deploying the Aegis Sentinel AI system using Docker Compose in production.
The stack consists of: backend (FastAPI), frontend (Nginx/React), PostgreSQL 16, and Redis 7.
A GPU override compose file is provided for CUDA inference.

---

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- NVIDIA Container Toolkit installed if using GPU (`docker compose -f docker-compose.gpu.yml`)
- `.env` file populated with all required secrets (see Environment Variables below)
- Model assets present at `./models/` on the host
- Storage volume at `./storage/` writable by Docker

---

## Environment Variables

Copy the example and fill in real values before deploying:

```bash
cp .env.docker.example .env
```

**Required secrets (must be set — deployment fails without these):**

| Variable | Description |
|---|---|
| `AEGIS_JWT_SECRET` | JWT signing secret — minimum 64 random characters, never default |
| `POSTGRES_DSN` | PostgreSQL connection string: `postgresql://user:pass@postgres:5432/aegis` |
| `REDIS_URL` | Redis connection string: `redis://redis:6379/0` |
| `OPENAI_API_KEY` | OpenAI API key (required if LLM provider is `openai`) |
| `AEGIS_BOOTSTRAP_ADMIN_PASSWORD` | Initial admin password — change after first login |

**Optional overrides:**

| Variable | Default | Description |
|---|---|---|
| `APP_ENV` | `production` | Runtime profile |
| `AEGIS_DEVICE_PREFERENCE` | `auto` | `cpu`, `cuda`, or `auto` |
| `POSTGRES_USER` | `aegis` | PostgreSQL user |
| `POSTGRES_PASSWORD` | `aegis` | PostgreSQL password — override in production |
| `POSTGRES_DB` | `aegis` | PostgreSQL database name |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend API base URL |
| `VITE_WS_BASE_URL` | `ws://localhost:8000` | Frontend WebSocket base URL |

---

## Services

### backend

- Image: built from `Dockerfile.backend`
- Port: `8000`
- Health check: `GET /health` (HTTP 200 = healthy)
- Depends on: postgres (service_healthy), redis (service_healthy) — optional (soft deps)
- Mounts:
  - `./models:/app/models` — YOLO/face/re-ID/segmentation model weights
  - `./storage:/app/storage` — runtime outputs, anomaly eval, production readiness evidence
  - `./configs/runtime:/app/configs/runtime` — runtime YAML config overrides
- Restart: `unless-stopped`

### frontend

- Image: built from `Dockerfile.frontend`
- Port: `80` (Nginx)
- Depends on: backend
- Build args: `VITE_API_BASE_URL`, `VITE_WS_BASE_URL`
- Health check: HTTP 200 on port 80
- Restart: `unless-stopped`

### postgres

- Image: `postgres:16-alpine`
- Named volume: `postgres_data`
- Health check: `pg_isready`
- Schema bootstrap: run `python scripts/bootstrap_postgres.py --apply` after container is healthy

### redis

- Image: `redis:7-alpine`
- Named volume: `redis_data`
- Persistence: RDB save every 60s if 1+ key changed
- Health check: `redis-cli ping`

---

## GPU Override

For CUDA inference, overlay the GPU compose file:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Requires NVIDIA Container Toolkit on the host. Sets `AEGIS_DEVICE_PREFERENCE=cuda` and
configures the NVIDIA runtime via `deploy.resources.reservations.devices`.

---

## Volumes

| Volume | Purpose |
|---|---|
| `postgres_data` | PostgreSQL data directory |
| `redis_data` | Redis persistence (RDB snapshots) |
| `./models` | Host-mounted model weights (not stored in Docker image) |
| `./storage` | Host-mounted runtime outputs and governance evidence |

---

## Deployment Steps

### 1. Prepare environment

```bash
cp .env.docker.example .env
# Edit .env and fill in all required secrets
```

### 2. Validate compose syntax

```bash
AEGIS_JWT_SECRET=placeholder docker compose config --quiet
```

### 3. Build images

```bash
docker compose build
```

### 4. Start infrastructure (postgres + redis first)

```bash
docker compose up -d postgres redis
# Wait for health checks to pass
docker compose ps
```

### 5. Bootstrap PostgreSQL schema

```bash
docker compose exec backend python scripts/bootstrap_postgres.py --apply
# Verify schema
docker compose exec backend python scripts/check_postgres_schema.py
```

### 6. Start all services

```bash
docker compose up -d
```

### 7. Verify health

```bash
# Backend health
curl http://localhost:8000/api/system/health

# Readiness (returns 503 if any required subsystem is down)
curl http://localhost:8000/api/system/readiness

# Liveness
curl http://localhost:8000/api/system/liveness

# Frontend
curl http://localhost:80/
```

### 8. Run production runtime validation

```bash
docker compose exec backend python scripts/validate_runtime.py --profile production
docker compose exec backend python scripts/validate_production_secrets.py --profile production
```

---

## Health Check Endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | Public | Simple backend alive check |
| `GET /api/system/health` | Public (filtered) / Admin (full) | Detailed subsystem health |
| `GET /api/system/readiness` | Public | Readiness probe — 200 OK or 503 |
| `GET /api/system/liveness` | Public | Liveness probe — always 200 if process alive |

The `/api/system/readiness` endpoint returns `503` if:
- Database (PostgreSQL) is unavailable
- Redis is unavailable
- JWT secret is default or missing in production
- Required model governance evidence is missing
- OpenAI provider is enabled but API key is missing

---

## Stopping and Restarting

```bash
# Stop all services (preserves volumes)
docker compose down

# Stop and remove volumes (DESTRUCTIVE — loses DB data)
docker compose down -v

# Restart a single service
docker compose restart backend
```

---

## Logs

```bash
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Tail last 100 lines
docker compose logs --tail=100 backend
```

---

## Model Path Mounts

Model weights are mounted from the host at `./models`. Required paths:

- `./models/buffalo_l/` — InsightFace face recognition model bundle
- YOLO weights (e.g. `yolov8n.pt`) referenced in `configs/runtime/`
- SAM2 checkpoint at project root (e.g. `sam2_t.pt`)
- Open-vocab model path configured via `AEGIS_OPEN_VOCAB_MODEL_PATH`

**Models are never baked into the Docker image.** They must be present on the host before starting.

---

## Nginx Configuration

The frontend container uses `docker/nginx.conf` which:
- Serves the React SPA on port 80
- Proxies `/api/` and WebSocket paths to the backend on port 8000
- Handles SPA routing with `try_files $uri /index.html`

---

## Drone Simulation

The drone simulation subsystem (Cosys-AirSim) is optional and runs outside Docker.
- The backend drone routes work without a live AirSim connection
- Drone simulation mode is detected via `AEGIS_AIRSIM_HOST` environment variable
- If not set, drone routes operate in simulation-only mode with safe wording preserved

---

## Production Checklist (Quick Reference)

Before going live:
- [ ] `AEGIS_JWT_SECRET` set to a unique 64+ character random string
- [ ] `AEGIS_BOOTSTRAP_ADMIN_PASSWORD` changed from default
- [ ] `POSTGRES_PASSWORD` changed from default `aegis`
- [ ] PostgreSQL schema bootstrapped: `bootstrap_postgres.py --apply`
- [ ] `docker compose exec backend python scripts/validate_runtime.py --profile production` passes
- [ ] `GET /api/system/readiness` returns HTTP 200
- [ ] Frontend accessible on port 80
- [ ] No `.env` file committed to git

See [PRODUCTION_DEPLOYMENT_CHECKLIST.md](PRODUCTION_DEPLOYMENT_CHECKLIST.md) for the full checklist.
