# Sentinel AI System — Developer Guidelines

## Git Workflow

### Branch Strategy
```
main          — production-ready code only
develop       — integration branch for features
feature/<name> — individual feature branches
hotfix/<name>  — urgent production fixes
```

### Commit Convention
```
feat: add new detection algorithm
fix: resolve frame extraction crash on corrupt video
chore: update dependencies
docs: update API endpoint documentation
refactor: simplify config loader
test: add unit tests for video service
```

### PR Rules
- All PRs target `develop`, never directly to `main`
- Require at least 1 approval before merging
- CI must pass (lint + tests)
- Include a short description of what changed and why

---

## Folder Structure

```
sentinel-ai-system/
├── backend/              FastAPI application
│   ├── app/
│   │   ├── api/          Route handlers
│   │   ├── core/         Config loading, settings
│   │   │   └── configs/  Per-scenario JSON config files
│   │   ├── models/       SQLAlchemy ORM models
│   │   └── services/     Business logic (video, alerts, etc.)
│   ├── main.py
│   └── requirements.txt
├── frontend/             React (Vite) SPA
├── ml/                   Training scripts, dataset tools
├── inference/            DetectionEngine and model wrappers
├── docs/                 This directory
└── scripts/              Utility shell/Python scripts
```

---

## Naming Conventions

| Context | Convention | Example |
|---|---|---|
| Python files | `snake_case` | `video_service.py` |
| Python classes | `PascalCase` | `DetectionEngine` |
| React components | `PascalCase` | `Dashboard.jsx` |
| React hooks | `camelCase` with `use` prefix | `useAlerts.js` |
| JSON config keys | `snake_case` | `"allowed_objects"` |
| API endpoints | `kebab-case` | `/process-video` |
| DB table names | `snake_case` plural | `events`, `detections` |
| Environment vars | `SCREAMING_SNAKE_CASE` | `DATABASE_URL` |

---

## Model Versioning Rules

1. **Never overwrite** a production model file in-place. Use versioned filenames:
   ```
   yolo_v1.0.0.pt
   yolo_v1.1.0.pt
   ```

2. **Track model metadata** alongside weights:
   ```json
   {
     "version": "1.1.0",
     "trained_on": "2025-04-10",
     "dataset": "coco-2017",
     "mAP": 0.72,
     "input_size": [640, 640]
   }
   ```

3. **DetectionEngine** must accept a `model_version` parameter so the API can request a specific version.

4. **Deprecation**: mark old versions in the metadata as `"deprecated": true`; remove only after 2 release cycles.

5. **Changelog**: update `ml/MODELS.md` for every new model version noting what changed and benchmark deltas.

---

## Environment Setup

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

---

## Code Style

- Python: follow PEP 8; max line length 100
- JS/JSX: Prettier defaults; no semicolons
- No commented-out dead code in PRs
- Secrets go in `.env` — never committed
