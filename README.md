# Sentinel AI System

A modular AI-powered surveillance platform with a FastAPI backend, React frontend, and pluggable ML inference engine.

## Quick Start

### Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # macOS/Linux
pip install -r requirements.txt
uvicorn main:app --reload
```
Verify: http://127.0.0.1:8000/health

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Verify: http://localhost:5173

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Root |
| GET | `/health` | Health check |
| POST | `/process-video` | Upload video, returns frame count |
| GET | `/config/{scenario}` | Load scenario config |
| GET | `/events` | List recent events |
| GET | `/detections` | List recent detections |

## Scenarios
- `classroom` — attendance, device detection
- `traffic` — speed, violations, pedestrians
- `security` — intrusion, loitering, unattended objects

## Project Structure
See [docs/dev-guidelines.md](docs/dev-guidelines.md)
