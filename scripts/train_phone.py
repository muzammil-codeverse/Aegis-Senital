import sys
import os
from pathlib import Path

sys.path.insert(0, "/content/sentinel-ai-system")

from ultralytics import YOLO
from utils.data_check import check_labels

CONFIG = "/content/sentinel-ai-system/configs/phone.yaml"
LABEL_DIR_TRAIN = "/content/datasets/phone/labels/train"
LABEL_DIR_VAL = "/content/datasets/phone/labels/val"
OUTPUT_DIR = "/content/sentinel-ai-system/models"

EPOCHS = 40
IMGSZ = 640
BATCH = 16


def main():
    print("=== Phone Detection Training ===")

    print("Validating training labels ...")
    check_labels(LABEL_DIR_TRAIN)
    print("Validating validation labels ...")
    check_labels(LABEL_DIR_VAL)

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    model = YOLO("yolov8n.pt")

    results = model.train(
        data=CONFIG,
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        project=OUTPUT_DIR,
        name="phone_detect",
        exist_ok=True,
        verbose=True,
    )

    print("\n=== Training Complete ===")
    print(f"Results saved to: {OUTPUT_DIR}/phone_detect")


if __name__ == "__main__":
    main()
