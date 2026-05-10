#!/usr/bin/env bash
# Resume weapon_v2 after VideoMAE 20-epoch training completes.
# Run in background: bash scripts/resume_weapon_v2_after_videomae.sh &

set -e
cd "$(dirname "$0")/.."

VIDEOMAE_LOG="logs/videomae_20ep.log"
WEAPON_LAST_PT="runs/detect/runs/aegis_weapon/yolo11s_weapon_v2/weights/last.pt"
WEAPON_DATA="datasets/training/weapon_v2/data.yaml"
LOG="logs/weapon_v2_resume.log"

echo "[weapon_v2_scheduler] Waiting for VideoMAE to complete..."

# Poll until VideoMAE log shows completion or process exits
until grep -q "Training complete\|Training already complete\|Best checkpoint" "$VIDEOMAE_LOG" 2>/dev/null; do
    sleep 60
done

echo "[weapon_v2_scheduler] VideoMAE complete. Checking GPU..."
nvidia-smi

echo "[weapon_v2_scheduler] Resuming weapon_v2 from $WEAPON_LAST_PT"

.venv/Scripts/python -c "
from ultralytics import YOLO
model = YOLO(r'$WEAPON_LAST_PT')
model.train(
    data=r'$WEAPON_DATA',
    epochs=80,
    imgsz=640,
    batch=8,
    device=0,
    workers=4,
    amp=True,
    cache=False,
    save=True,
    save_period=5,
    resume=True,
    project='runs/detect/runs/aegis_weapon',
    name='yolo11s_weapon_v2',
    exist_ok=True,
)
" >> "$LOG" 2>&1

echo "[weapon_v2_scheduler] Done." >> "$LOG"
