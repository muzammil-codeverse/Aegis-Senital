# Local Docker Deployment

## Prerequisites
- Docker Desktop or Docker Engine + Compose v2
- 4GB+ RAM

## Quick Start (CPU)

1. Copy the environment template:
   ```
   cp .env.docker.example .env.docker
   ```
2. Edit `.env.docker` — set `AEGIS_JWT_SECRET` to a random 32+ character string.
3. Start services:
   ```
   docker compose --env-file .env.docker up --build
   ```
4. Access:
   - Frontend: http://localhost:80
   - Backend API: http://localhost:8000
   - API docs: http://localhost:8000/docs

## Volume Mounts

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| ./models | /app/models | YOLO weights, model artifacts |
| ./storage | /app/storage | Runtime storage, JSONL logs |
| ./backend/output | /app/backend/output | Frame snapshots |
| ./configs/runtime | /app/configs/runtime | Runtime YAML configs |

## Stopping
```
docker compose down
```

## Troubleshooting
- Backend not starting: check AEGIS_JWT_SECRET is set in .env.docker
- Port 8000 in use: change `ports: "8001:8000"` in docker-compose.yml
