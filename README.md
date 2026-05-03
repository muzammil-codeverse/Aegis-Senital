# Sentinel AI System

A modular AI-powered surveillance platform with a FastAPI backend, React frontend, and YOLOv8-based ML training pipeline.

---

## YOLOv8 Training Pipeline (Google Colab)

### Step 1 — Clone the repository

```python
!git clone https://github.com/muzammil-codeverse/sentinel-ai-system.git /content/sentinel-ai-system
%cd /content/sentinel-ai-system
```

### Step 2 — Install dependencies

```python
!pip install -r requirements.txt
```

### Step 3 — Download datasets via Roboflow

Replace `<API_KEY>` and project details with your Roboflow credentials.

**Weapon dataset:**
```python
from roboflow import Roboflow

rf = Roboflow(api_key="<API_KEY>")
project = rf.workspace("<WORKSPACE>").project("weapon-detection")
dataset = project.version(1).download("yolov8", location="/content/datasets/weapon")
```

**Phone dataset:**
```python
project = rf.workspace("<WORKSPACE>").project("phone-detection")
dataset = project.version(1).download("yolov8", location="/content/datasets/phone")
```

### Step 4 — Validate labels (optional but recommended)

```python
import sys
sys.path.insert(0, "/content/sentinel-ai-system")
from utils.data_check import check_labels

check_labels("/content/datasets/weapon/labels/train")
check_labels("/content/datasets/weapon/labels/val")
check_labels("/content/datasets/phone/labels/train")
check_labels("/content/datasets/phone/labels/val")
```

### Step 5 — Train weapon detection model

```python
!python /content/sentinel-ai-system/scripts/train_weapon.py
```

### Step 6 — Train phone detection model

```python
!python /content/sentinel-ai-system/scripts/train_phone.py
```

### Step 7 — Validate trained models

```python
# Validate both models
!python /content/sentinel-ai-system/scripts/validate.py --model both

# Or validate individually
!python /content/sentinel-ai-system/scripts/validate.py --model weapon
!python /content/sentinel-ai-system/scripts/validate.py --model phone
```

### Step 8 — Export to ONNX

```python
# Export both models to models/exports/
!python /content/sentinel-ai-system/scripts/export.py --model both
```

Exported files are saved to `/content/sentinel-ai-system/models/exports/`.

---

## Repository Structure

```
sentinel-ai-system/
├── configs/
│   ├── weapon.yaml          # YOLO dataset config for weapon detection
│   └── phone.yaml           # YOLO dataset config for phone detection
├── scripts/
│   ├── train_weapon.py      # Train weapon detection model
│   ├── train_phone.py       # Train phone detection model
│   ├── validate.py          # Run validation, print mAP/precision/recall
│   └── export.py            # Export models to ONNX
├── utils/
│   └── data_check.py        # Label validation utility
├── models/
│   └── exports/             # ONNX exports saved here
├── datasets/                # Placeholder — populated by Roboflow download
├── requirements.txt
├── backend/                 # FastAPI backend
├── frontend/                # React frontend
└── inference/               # Real-time inference engine
```

---

## Local Development

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

---

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
